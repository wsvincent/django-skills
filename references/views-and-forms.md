# Django URLs, Views, and Forms Reference

Routing, class-based and function-based views, permissions, pagination, and form handling.

## URL Patterns

Use `path()` with converters, name every pattern, and namespace each app:

```python
# articles/urls.py
from django.urls import path

from . import views

app_name = "articles"
urlpatterns = [
    path("", views.ArticleListView.as_view(), name="list"),
    path("<slug:slug>/", views.ArticleDetailView.as_view(), name="detail"),
]
```

```python
# config/urls.py
from django.urls import include, path

urlpatterns = [
    path("articles/", include("articles.urls")),
]
```

Points to keep in mind:

- Use `re_path()` only when a converter cannot express the pattern; a custom path converter is usually cleaner and keeps `reverse()` working.
- Prefer `slug` or `uuid` converters over `int` for public URLs when sequential ids leak information.
- Reverse with `reverse()`, `reverse_lazy()` (for class attributes and module-level values), and `{% url %}`. Never build URLs by string concatenation.
- Give models a `get_absolute_url()` so views and templates have one canonical link.

## Choosing a View Style

Use generic class-based views for standard CRUD; write function-based views for one-off logic that doesn't map onto a generic view. Neither is universally better — the failure mode to avoid is subclassing a generic view and overriding so much of it that the inheritance obscures what the view does.

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView

from .forms import ArticleForm
from .models import Article


class ArticleListView(ListView):
    model = Article
    context_object_name = "articles"
    paginate_by = 25

    def get_queryset(self):
        return Article.objects.published().select_related("author")


class ArticleDetailView(DetailView):
    model = Article


class ArticleCreateView(LoginRequiredMixin, CreateView):
    model = Article
    form_class = ArticleForm
    success_url = reverse_lazy("articles:list")

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)
```

The hooks worth knowing, in the order they matter:

- `get_queryset()` — scope the data, and add `select_related()`/`prefetch_related()` here.
- `get_context_data()` — add extra context; always call `super()` first.
- `get_form_kwargs()` — pass the request or user into the form.
- `form_valid()` / `form_invalid()` — act on the submitted form.
- `get_success_url()` — when the redirect target depends on the object.

Never filter by primary key from `self.kwargs` without also scoping ownership. `get_object_or_404(Article, pk=pk, author=request.user)` is a one-line fix for a whole class of access-control bugs.

## Function-Based Views

```python
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ArticleForm
from .models import Article


def article_edit(request, pk):
    article = get_object_or_404(Article, pk=pk, author=request.user)
    if request.method == "POST":
        form = ArticleForm(request.POST, instance=article)
        if form.is_valid():
            form.save()
            return redirect(article)
    else:
        form = ArticleForm(instance=article)
    return render(request, "articles/edit.html", {"form": form})
```

Use `get_object_or_404()` rather than catching `DoesNotExist`, and always redirect after a successful POST so a refresh doesn't resubmit. `redirect()` accepts a model instance (using `get_absolute_url()`), a view name, or a URL.

Restrict methods explicitly with `@require_http_methods(["GET", "POST"])` or `@require_POST`. Never mutate data in a GET request — it bypasses CSRF protection and gets triggered by prefetchers and crawlers.

On Django 6.1+, `RedirectView.preserve_request = True` issues 307/308 instead of 302/301, preserving the method and body through the redirect.

## Authentication and Permissions

- `LoginRequiredMixin` / `@login_required` for authentication.
- `PermissionRequiredMixin` / `@permission_required` for model permissions.
- `UserPassesTestMixin` with `test_func()` for object-level rules.

```python
class ArticleUpdateView(UserPassesTestMixin, UpdateView):
    model = Article

    def test_func(self):
        return self.get_object().author == self.request.user
```

Mixins must come before the generic view in the MRO — `class V(LoginRequiredMixin, ListView)`, not the reverse, or the check never runs. `raise_exception = True` returns 403 instead of redirecting to the login page, which is what API-ish endpoints want.

Checking permissions in the template only hides UI; the view must enforce them.

## Pagination

Use `paginate_by` on `ListView`, or `Paginator` directly:

```python
from django.core.paginator import Paginator

paginator = Paginator(Article.objects.order_by("-created_at"), 25)
page = paginator.get_page(request.GET.get("page"))
```

`get_page()` clamps invalid and out-of-range values instead of raising, which is what a public view wants. Paginating an unordered queryset produces inconsistent pages — always order it.

## Messages

Use the messages framework for one-off feedback across a redirect:

```python
from django.contrib import messages

messages.success(request, "Article published.")
return redirect("articles:list")
```

In class-based views, `SuccessMessageMixin` handles the common case.

## Forms

Validate all user input through a form. Use `ModelForm` for model-backed input and list `fields` explicitly:

```python
from django import forms

from .models import Article


class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "status", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 10})}
```

instead of:

```python
# DO NOT DO THIS
fields = "__all__"  # can silently expose new sensitive fields
exclude = ["author"]  # same problem, inverted
```

Never write model fields straight from `request.POST` — that skips validation, type coercion, and every constraint the form encodes.

### Validation Hooks

Put field-specific checks in `clean_<field>()` and cross-field checks in `clean()`:

```python
class ArticleForm(forms.ModelForm):
    def clean_title(self):
        title = self.cleaned_data["title"]
        if title.isupper():
            raise forms.ValidationError("Title must not be all caps.")
        return title

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == Article.Status.PUBLISHED and not cleaned.get("body"):
            raise forms.ValidationError("Published articles need a body.")
        return cleaned
```

Read values from `self.cleaned_data`, not `self.data`. A `clean_<field>()` method must return the value. Raise `ValidationError` with a message (and a `code` when the caller needs to distinguish cases) rather than returning `False`.

To keep request state out of the form's globals, pass it in:

```python
class ArticleForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["category"].queryset = Category.objects.for_user(user)
```

Limiting a `ModelChoiceField` queryset this way is a security control, not a UI nicety: without it, a user can post any primary key.

### Saving

`form.save(commit=False)` returns an unsaved instance when fields must be set from the request:

```python
article = form.save(commit=False)
article.author = request.user
article.save()
form.save_m2m()  # required after commit=False when the form has m2m fields
```

### Formsets and File Uploads

Use `modelformset_factory` / `inlineformset_factory` for editing several related objects at once, and always render `{{ formset.management_form }}`.

For uploads, bind both POST data and files, and validate the file rather than trusting it:

```python
form = DocumentForm(request.POST, request.FILES)
```

Check size and content, generate the stored filename server-side, and never place uploads inside the static root or anywhere they could be served as executable content.
