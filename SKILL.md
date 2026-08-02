---
name: django
description: "Django best practices and conventions. Use when creating, refactoring, or reviewing Django projects, apps, models, views, templates, forms, admin, tests, or settings. Keeps Django code secure, idiomatic, and up to date with the latest features and patterns. Triggers on starting a Django project or app, writing models/migrations/querysets, class-based or function-based views, forms and validation, templates, the admin, tests, async views and background tasks, deployment and security settings, N+1 and slow-query debugging, and Django version upgrades."
---

# Django

An unofficial skill for writing Django code with best practices, based on the official Django documentation and community conventions, keeping up to date with new versions and features.

Target Django 6.x and Python 3.12+ for new projects. Django 5.2 is the current LTS; do not write code for versions older than the LTS unless the project requires it. Features new in Django 6.0 and 6.1 are marked below.

## Quick Reference

* Custom user model: always define one before the first migration; see [Always Start With a Custom User Model](#always-start-with-a-custom-user-model).
* Settings and secrets: read from the environment, never commit them, `DEBUG = False` in production; see [Settings](#settings) and [the deployment reference](references/deployment.md).
* Models, queries, N+1, transactions, migrations: see [the ORM reference](references/orm.md). On 6.1+, `fetch_mode(models.FETCH_PEERS)` fixes most N+1 problems.
* URLs, views, and forms: named URL patterns, generic class-based views, `ModelForm` with explicit `fields`; see [the views and forms reference](references/views-and-forms.md).
* Templates: inheritance, autoescaping, and `{% partialdef %}` (6.0+); see [the templates reference](references/templates.md).
* Async views, the async ORM, and the Tasks framework: see [the async reference](references/async.md).
* Testing: `TestCase` with `setUpTestData()`; see [the testing reference](references/testing.md).
* Admin: a configured `ModelAdmin`, never a bare `register()`; see [the admin reference](references/admin.md).
* Deployment, HTTPS, CSP, static files, caching, email: see [the deployment reference](references/deployment.md).
* Multi-step tasks — new project, new app, pre-deploy, version upgrade, code review: see [the checklists](references/checklists.md).

## Use `django-admin` and `manage.py`

Create a new project and app:

```bash
django-admin startproject config .
python manage.py startapp accounts
```

Run the development server, create and apply migrations, and run tests:

```bash
python manage.py runserver
python manage.py makemigrations
python manage.py migrate
python manage.py test
```

Before deploying, always run the deployment checklist:

```bash
python manage.py check --deploy
```

## Settings

Never hardcode secrets. Read `SECRET_KEY`, database credentials, and API keys from environment variables, and never commit them:

```python
import os

SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = os.environ.get("DEBUG", "") == "True"
```

instead of:

```python
# DO NOT DO THIS
SECRET_KEY = "django-insecure-hardcoded-value"
DEBUG = True  # left on in production
```

`DEBUG` must be `False` in production, with `ALLOWED_HOSTS` set explicitly. See [the deployment reference](references/deployment.md) for settings layout, production settings, security headers, CSP, static files, caching, and email configuration.

## Always Start With a Custom User Model

For any new project, define a custom user model before running the first migration, even if the default behavior is all that's needed. Changing the user model mid-project is painful; the official docs strongly recommend this.

```python
# accounts/models.py
from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    pass
```

```python
# settings.py
AUTH_USER_MODEL = "accounts.CustomUser"
```

Reference the user model via `settings.AUTH_USER_MODEL` in `ForeignKey` declarations and `get_user_model()` everywhere else:

```python
from django.conf import settings
from django.db import models


class Article(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
```

instead of:

```python
# DO NOT DO THIS
from django.contrib.auth.models import User


class Article(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE)
```

## Models and QuerySets

See [the ORM reference](references/orm.md) for detailed patterns: model conventions, choices enums, constraints and indexes, `on_delete` options (including the database-level `DB_CASCADE` family in 6.1), custom managers and querysets, queryset performance, fetch modes, transactions, and migrations.

The essentials:

- Give every model a `__str__` method and use `TextChoices`/`IntegerChoices` for choices.
- Avoid N+1 queries with `select_related("field")` and `prefetch_related("field")` — always pass explicit field names. On Django 6.1+, `QuerySet.fetch_mode(models.FETCH_PEERS)` solves most N+1 problems without maintaining a field list.
- Use the database, not Python: `exists()`, `count()`, `bulk_create()`, `F()` expressions.
- Put business logic on models, managers, or a service layer — not in views or templates.
- Never interpolate values into raw SQL — pass parameters.

## URLs

Use `path()` with converters, name every URL pattern, and namespace apps with `app_name`. Never hardcode URLs; use `reverse()`, `reverse_lazy()`, and the `{% url %}` template tag:

```python
# articles/urls.py
from django.urls import path

from .views import ArticleDetailView, ArticleListView

app_name = "articles"
urlpatterns = [
    path("", ArticleListView.as_view(), name="list"),
    path("<int:pk>/", ArticleDetailView.as_view(), name="detail"),
]
```

```html
<a href="{% url 'articles:detail' article.pk %}">{{ article.title }}</a>
```

instead of:

```html
<!-- DO NOT DO THIS -->
<a href="/articles/{{ article.pk }}/">{{ article.title }}</a>
```

## Views

Use generic class-based views for standard CRUD patterns; function-based views are fine for one-off logic. Use `get_object_or_404()` instead of catching `DoesNotExist` manually, and `LoginRequiredMixin` / `@login_required` for authentication:

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView

from .models import Article


class ArticleListView(ListView):
    model = Article
    context_object_name = "articles"

    def get_queryset(self):
        return Article.objects.select_related("author")


class ArticleDetailView(LoginRequiredMixin, DetailView):
    model = Article
```

instead of:

```python
# DO NOT DO THIS
def article_detail(request, pk):
    try:
        article = Article.objects.get(pk=pk)
    except Article.DoesNotExist:
        return HttpResponse(status=404)
```

Redirect after a successful POST. Never mutate data in a GET request. To preserve the HTTP method and body through a redirect, use `RedirectView.preserve_request = True` (Django 6.1+), which issues 307/308 instead of 302/301.

See [the views and forms reference](references/views-and-forms.md) for URL patterns, view customization hooks, permissions, pagination, and the messages framework. Write async views only when the code inside genuinely awaits; see [the async reference](references/async.md).

## Forms

Always validate user input through Django forms. Use `ModelForm` for model-backed input, list `fields` explicitly, and access data via `cleaned_data`:

```python
from django import forms

from .models import Article


class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "status"]
```

instead of:

```python
# DO NOT DO THIS
fields = "__all__"  # can silently expose new sensitive fields

# DO NOT DO THIS — bypasses all validation
Article.objects.create(title=request.POST["title"])
```

See [the views and forms reference](references/views-and-forms.md) for validation hooks, formsets, and file uploads.

## Templates

Use template inheritance with a base template and `{% block %}` tags. Always include `{% csrf_token %}` in POST forms. Rely on autoescaping — never pass user-generated content through `|safe` or `mark_safe()`.

### Template Partials

Use `{% partialdef %}` and `{% partial %}` (Django 6.0+) to define and reuse named fragments within a template file, instead of splitting tiny components into separate files:

```html
{% partialdef article-card %}
  <article>
    <h2>{{ article.title }}</h2>
  </article>
{% endpartialdef %}

{% for article in articles %}
  {% partial article-card %}
{% endfor %}
```

Partials can be rendered directly from views with the `template_name#partial_name` syntax — useful for htmx-style partial page updates:

```python
return render(request, "articles/list.html#article-card", {"article": article})
```

On earlier versions, use the `django-template-partials` package.

See [the templates reference](references/templates.md) for template configuration, context processors, custom tags and filters, fragment caching, and escaping rules.

## Security

Django's defaults protect against SQL injection (ORM), XSS (autoescaping), CSRF (middleware), and clickjacking — don't work around them. Use the built-in Content Security Policy support (Django 6.0+) instead of the third-party `django-csp` package.

See [the deployment reference](references/deployment.md) for production security settings, HTTPS configuration, and CSP setup including nonces.

## Background Tasks

Use the built-in Tasks framework (Django 6.0+) for fire-and-forget work like sending email, instead of running it inline in the request-response cycle:

```python
from django.core.mail import send_mail
from django.tasks import task


@task
def send_welcome_email(to: str):
    send_mail("Welcome!", "Thanks for signing up.", None, [to])


# In a view:
send_welcome_email.enqueue(to=user.email)
```

See [the async reference](references/async.md) for backend configuration and production requirements. For periodic scheduling, chaining, retries, or rate limiting, use Celery.

## Testing

Use `TestCase` with `setUpTestData()` for shared fixtures (created once per class, not per test), and the test client for view tests:

```python
from django.test import TestCase
from django.urls import reverse

from .models import Article


class ArticleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.article = Article.objects.create(title="Testing")

    def test_list_view(self):
        response = self.client.get(reverse("articles:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Testing")
```

instead of:

```python
# DO NOT DO THIS — recreates objects for every test method
def setUp(self):
    self.article = Article.objects.create(title="Testing")
```

`pytest` with `pytest-django` is a fine alternative when the project already uses it. See [the testing reference](references/testing.md) for choosing a test case class, Django-specific assertions, query-count tests, and async tests.

## Admin

Register models with a `ModelAdmin` that configures `list_display`, `list_filter`, and `search_fields` rather than a bare `admin.site.register()`. The admin is for trusted staff only — never expose it as a public-facing interface, and consider changing the default `/admin/` URL in production.

On Django 6.1+, use the `location` argument of the `@admin.action()` decorator to make actions available on change forms as well as the change list, and prefer explicit field names over `list_select_related = True` (setting it to `True` is deprecated).

See [the admin reference](references/admin.md) for inlines, computed columns, query optimization, custom actions, and permissions.

## Check the Docs, Don't Guess

Django ships a feature release roughly every eight months, and each one deprecates something. When a question turns on version-specific behavior — whether an argument exists, when something was deprecated, what a setting defaults to — fetch the docs instead of answering from memory:

- Current stable docs: <https://docs.djangoproject.com/en/stable/> (redirects to the current version)
- Release notes for every version: <https://docs.djangoproject.com/en/stable/releases/>
- Deprecation timeline: <https://docs.djangoproject.com/en/stable/internals/deprecation/>
- Unreleased version, when a feature is newer than the stable docs: <https://docs.djangoproject.com/en/dev/>

Check the project's installed version before recommending a feature, and say so when a suggestion requires an upgrade:

```bash
python -c "import django; print(django.get_version())"
```

Prefer `/en/stable/` over a pinned version number in links so they don't go stale.
