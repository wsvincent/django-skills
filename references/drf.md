# Django REST Framework Reference

Serializers, views and viewsets, routers, authentication and permissions, throttling, pagination, filtering, versioning, errors, OpenAPI schemas, and testing for APIs built with [Django REST framework](https://www.django-rest-framework.org/) (DRF). Everything in the main skill still applies — DRF views are Django views, and the ORM, settings, and security rules are the same.

## Versions

DRF 3.18 supports Django 5.2, 6.0, and 6.1 and Python 3.10–3.15. DRF 3.17 added Django 6.0 and removed the deprecated CoreAPI support; 3.18 added Django 6.1 and dropped Django 4.2–5.1. Run the latest patch release — 3.18.2 was a security release.

On 3.18+, errors from list serializers (`many=True`) use a dict format. The `LIST_SERIALIZER_ERRORS_AS_DICT` compatibility setting restores the old list format, but that format is deprecated and will be removed in DRF 3.20 — update clients rather than reverting.

Surface upcoming removals in tests by turning DRF's `RemovedInNextDRFVersionWarning` into an error, the same way as Django's deprecation warnings.

## Settings: Lock Down the Defaults

DRF's out-of-the-box defaults are permissive: `DEFAULT_PERMISSION_CLASSES` is `AllowAny`, pagination is off, and throttling is off. Set secure defaults globally and loosen them per view:

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "100/hour", "user": "1000/hour"},
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}
```

instead of:

```python
# DO NOT DO THIS — every endpoint is public, unpaginated, and unthrottled
REST_FRAMEWORK = {}
```

The default authentication classes are `SessionAuthentication` then `BasicAuthentication`; `BasicAuthentication` is only appropriate for testing, so list the classes explicitly. Pagination happens only when both `DEFAULT_PAGINATION_CLASS` and `PAGE_SIZE` are set.

Django's `LoginRequiredMiddleware` (5.1+) does not protect DRF views — DRF views opt out of it. Enforce authentication with DRF's own permission classes.

## Serializers

Use `ModelSerializer` and list `fields` explicitly. The DRF docs strongly recommend it, because it makes it less likely that new model fields are unintentionally exposed:

```python
from rest_framework import serializers

from .models import Article


class ArticleSerializer(serializers.ModelSerializer):
    author = serializers.HiddenField(default=serializers.CurrentUserDefault())
    author_name = serializers.CharField(source="author.get_full_name", read_only=True)

    class Meta:
        model = Article
        fields = ["id", "title", "slug", "body", "status", "author", "author_name", "created_at"]
        read_only_fields = ["slug", "created_at"]
```

instead of:

```python
# DO NOT DO THIS — exposes every current and future column
class Meta:
    model = Article
    fields = "__all__"
```

- `read_only_fields` and `extra_kwargs` are ignored for fields declared explicitly on the serializer — set `read_only=True` (or `write_only=True`) on the field itself.
- Use `extra_kwargs = {"password": {"write_only": True}}` for write-only model fields, and never return password hashes, tokens, or internal flags.
- Use separate serializers for input and output, or for list and detail, when their shapes differ, and pick between them in `get_serializer_class()`.
- `HiddenField(default=CurrentUserDefault())` needs `request` in the serializer context (generic views provide it) and is not included in `partial=True` updates.
- `source=` with a dotted path or method follows relations — each one is a query per object unless the view's queryset loads it up front.

### Validation

```python
class ArticleSerializer(serializers.ModelSerializer):
    ...

    def validate_title(self, value):
        if value.isupper():
            raise serializers.ValidationError("Don't shout.")
        return value

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", None))
        if status == Article.Status.PUBLISHED and not attrs.get("body", getattr(self.instance, "body", "")):
            raise serializers.ValidationError("Published articles need a body.")
        return attrs
```

- `validate_<field>()` must return the (possibly cleaned) value; it is skipped when a non-required field is absent.
- In `validate()`, a `PATCH` only contains the submitted fields — fall back to `self.instance` for the rest, as above.
- Model-level `UniqueConstraint`s become serializer validators automatically; add `UniqueTogetherValidator` in `Meta.validators` only for combinations the model doesn't declare.
- Raise `serializers.ValidationError`, not Django's `ValidationError`, inside serializers.

### Nested Writes

Nested serializers are read-only unless you write `create()` and `update()` yourself — `ModelSerializer` does not handle writable nested data. Prefer a flat write serializer with primary keys (`PrimaryKeyRelatedField`, or `SlugRelatedField`) and a nested read serializer. Avoid `Meta.depth`: it nests everything read-only and makes the payload and the query count hard to control.

Always limit the `queryset` of writable related fields to what the user may reference, exactly as with `ModelChoiceField` in forms.

## Views and ViewSets

Choose the least machinery that fits:

- `APIView` — one-off endpoints that aren't CRUD on a model.
- Concrete generic views (`ListCreateAPIView`, `RetrieveUpdateDestroyAPIView`, …) — CRUD on a model with explicit URLs.
- `ModelViewSet` / `ReadOnlyModelViewSet` with a router — a full resource with conventional URLs.

```python
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Article
from .permissions import IsAuthorOrReadOnly
from .serializers import ArticleSerializer


class ArticleViewSet(viewsets.ModelViewSet):
    serializer_class = ArticleSerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]

    def get_queryset(self):
        return (
            Article.objects.filter(author=self.request.user)
            .select_related("author")
            .prefetch_related("tags")
        )

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        article = self.get_object()
        article.publish()
        return Response(self.get_serializer(article).data)
```

- Override `get_queryset()` and never read `self.queryset` directly: a class-level queryset is evaluated once and its results cached across requests. Scope every queryset to what the requesting user may see.
- Set the owner and other server-controlled fields in `perform_create()` / `perform_update()` with `serializer.save(field=value)`; the keyword arguments are merged into `validated_data`.
- Use `self.get_object()` in custom actions — it applies filtering and object permissions. A plain `Article.objects.get(pk=pk)` skips both.
- Don't call `.as_view()` on viewsets with `@action` methods; register them with a router.

### Routers

```python
from rest_framework.routers import DefaultRouter

from .views import ArticleViewSet

router = DefaultRouter()
router.register(r"articles", ArticleViewSet, basename="article")

urlpatterns = router.urls
```

- No trailing slash in the prefix (`r"articles"`, not `r"articles/"`).
- `basename` is required when the viewset defines `get_queryset()` without a `queryset` attribute, as above.
- `DefaultRouter` adds an API root view and format suffixes; `SimpleRouter` gives just the resource routes.

## Authentication

- **Browser clients on the same site**: `SessionAuthentication`. CSRF is enforced for authenticated requests, so the frontend must send the CSRF token.
- **Third-party or mobile clients**: tokens. The built-in `TokenAuthentication` is "a fairly simple implementation" — one unhashed, non-expiring token per user. The DRF docs recommend django-oauth-toolkit for OAuth 2.0 and describe django-rest-knox as a more secure alternative to the built-in token scheme; djangorestframework-simplejwt is a common choice for JWTs.
- Always serve token and Basic auth over HTTPS.
- The built-in `obtain_auth_token` view has no throttling — add some before exposing it.

The first authentication class on a view determines whether an unauthenticated request gets a 401 (with `WWW-Authenticate`) or a 403.

## Permissions

```python
from rest_framework import permissions


class IsAuthorOrReadOnly(permissions.BasePermission):
    message = "Only the author may change this article."

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author_id == request.user.id
```

Object permissions have sharp edges:

- `has_object_permission()` runs only when the view calls `get_object()` — never for list views. Restrict lists by filtering `get_queryset()`.
- It doesn't run on create either, because there is no object yet. Validate what a user may create in the serializer or `perform_create()`.
- Of the built-in classes, only `DjangoObjectPermissions` implements object checks, and it needs an object-permission backend such as django-guardian.

Compose permissions with `&`, `|`, and `~` instead of writing combination classes: `permission_classes = [IsAuthenticated & (IsAuthorOrReadOnly | IsAdminUser)]`.

`DjangoModelPermissions` maps POST/PUT/PATCH/DELETE to the `add`/`change`/`delete` model permissions but does not restrict GET unless you override `perms_map`.

## Throttling

Throttling is for fair use and cost control. The DRF docs state it should not be considered a security measure against brute-forcing or denial of service, and the built-in throttles are open to race conditions. Protect login and token endpoints with dedicated rate limiting at the proxy or with account lockout.

- Throttle state lives in Django's cache; the default `LocMemCache` is per-process, so use a shared cache (Redis, Memcached) in production.
- Behind a proxy, set `NUM_PROXIES` so the client IP comes from the right `X-Forwarded-For` entry rather than a spoofable one.
- Use `ScopedRateThrottle` with `throttle_scope = "uploads"` on views that need their own rate.

## Pagination

Paginate every list endpoint. `PageNumberPagination` suits most APIs; set `max_page_size` whenever clients can choose the page size:

```python
from rest_framework.pagination import CursorPagination, PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class FeedPagination(CursorPagination):
    ordering = "-created_at"
```

Use `CursorPagination` for large or fast-changing feeds: it stays fast at any depth and doesn't skip or repeat rows when data changes. Its ordering field must be unique or nearly so, unchanging, non-nullable, and indexed. Pagination applies automatically only in generic views and viewsets.

## Filtering, Search, and Ordering

```python
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters


class ArticleViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "author"]
    search_fields = ["title", "=slug"]
    ordering_fields = ["created_at", "title"]
    ordering = ["-created_at"]
```

- `DjangoFilterBackend` requires the `django-filter` package and `"django_filters"` in `INSTALLED_APPS`.
- Always set `ordering_fields` explicitly. Unset, it allows any readable serializer field; `"__all__"` allows any model field, which can leak data through sort order.
- Search with `$` (regex) lets clients send arbitrary regular expressions — avoid it on public endpoints.
- Filter backends also apply to `get_object()`, so a filtered-out object returns 404.

## N+1 Queries

DRF does not optimize querysets passed to serializers. Every nested serializer, `source="relation.field"`, `SerializerMethodField` that touches a relation, and related field is a potential query per row. Load relations in `get_queryset()` — `select_related()` for foreign keys and one-to-one, `prefetch_related()` for reverse and many-to-many — and assert query counts in tests (see [the testing reference](testing.md)). On Django 6.1+, `fetch_mode(models.FETCH_PEERS)` is a useful safety net (see [the ORM reference](orm.md)).

## Versioning

Versioning is off by default (`request.version` is `None`). For public APIs, pick a scheme before the first release — `URLPathVersioning` or `AcceptHeaderVersioning` are the common choices — and set `DEFAULT_VERSION` and `ALLOWED_VERSIONS`. Branch on `request.version` in `get_serializer_class()` rather than duplicating views.

## Errors

Raise DRF exceptions (`NotFound`, `PermissionDenied`, `ValidationError`, `Throttled`, …) rather than returning error responses by hand, so every error has the same shape. Customize the shape globally with `EXCEPTION_HANDLER`, a function taking `(exc, context)` that calls `rest_framework.views.exception_handler` first and returns `None` for unhandled exceptions so they become 500s. For JSON 400/500 pages outside DRF views, set `handler400 = "rest_framework.exceptions.bad_request"` and `handler500 = "rest_framework.exceptions.server_error"` in the root URLconf.

Never put stack traces, SQL, or internal identifiers in error responses.

## OpenAPI Schemas

DRF's built-in OpenAPI generation (`generateschema`, `get_schema_view()`) is deprecated and will be moved out and retired. Use drf-spectacular, which the DRF docs call the recommended way to generate and present OpenAPI schemas. Don't use CoreAPI — support was removed in DRF 3.17.

## Testing

```python
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Article

User = get_user_model()


class ArticleAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("alice", password="secret")
        cls.other = User.objects.create_user("bob", password="secret")

    def test_create_sets_author(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            reverse("article-list"), {"title": "Hello", "body": "World"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Article.objects.get().author, self.user)

    def test_cannot_see_other_users_articles(self):
        Article.objects.create(title="Private", body="...", author=self.other)
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("article-list"))
        self.assertEqual(response.data["count"], 0)

    def test_anonymous_rejected(self):
        response = self.client.get(reverse("article-list"))
        self.assertIn(response.status_code, {401, 403})
```

- Use `APITestCase` and its `APIClient`; `force_authenticate()` skips the auth machinery, so also test the real authentication path once.
- The test client sends multipart by default — pass `format="json"` or set `TEST_REQUEST_DEFAULT_FORMAT = "json"`.
- CSRF checks are off in `APIClient`; use `APIClient(enforce_csrf_checks=True)` to test a session-authenticated frontend.
- Test the permission boundaries — another user's object, anonymous access, read-only methods — not only the happy path, and assert the query count of list endpoints.

## Async

DRF views and serializers are synchronous. The third-party `adrf` package adds async views and serializers; for most APIs, keep DRF views sync and move slow work to the Tasks framework (see [the async reference](async.md)).
