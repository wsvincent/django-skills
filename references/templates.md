# Django Templates Reference

Template configuration, inheritance, partials, escaping, custom tags, and fragment caching.

## Configuration

Keep a project-level template directory for overrides and let app templates live in `<app>/templates/<app>/`, so template names are namespaced by app:

```python
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
```

`articles/templates/articles/detail.html` is right; `articles/templates/detail.html` invites another app to shadow it.

In production, the cached loader avoids re-parsing templates on every render. Django enables it automatically when `DEBUG` is `False` and `APP_DIRS` is used; configure `loaders` explicitly only when the default doesn't fit — and note that `loaders` and `APP_DIRS` are mutually exclusive.

## Inheritance

Use a base template with named blocks, and extend it:

```html
{# templates/base.html #}
<!DOCTYPE html>
<html lang="en">
  <head>
    <title>{% block title %}Site{% endblock %}</title>
  </head>
  <body>
    {% block content %}{% endblock %}
  </body>
</html>
```

```html
{# templates/articles/detail.html #}
{% extends "base.html" %}

{% block title %}{{ article.title }} — {{ block.super }}{% endblock %}

{% block content %}
  <h1>{{ article.title }}</h1>
{% endblock %}
```

`{% extends %}` must be the first tag in the file. Use `{% block.super %}` to append to a parent block instead of duplicating it. Prefer inheritance over `{% include %}` for page structure, and `{% include %}` for genuinely reusable components.

## Template Partials

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

This keeps the fragment and the full page in one file, so they can't drift apart. On earlier versions, use the `django-template-partials` package.

## Escaping

Autoescaping is on by default and is the main XSS defense. Do not disable it.

```html
{{ user_comment }}           {# escaped — correct #}
{{ user_comment|safe }}      {# DO NOT DO THIS with user content #}
{% autoescape off %}...{% endautoescape %}  {# DO NOT DO THIS #}
```

`mark_safe()` in Python is the same hazard. Reserve both for markup the application itself generated; for user-supplied rich text, sanitize with a library such as `nh3` or `bleach` on input and store the sanitized result.

Two places autoescaping does not protect:

- Inside `<script>` blocks. Use `{{ value|json_script:"data-id" }}` and read it from JavaScript, rather than interpolating into JS source.
- Unquoted HTML attributes. Always quote attribute values.

Always include `{% csrf_token %}` in POST forms.

## Template Logic

Templates are for presentation. When a template needs data it doesn't have, add it in `get_context_data()` or on the model — don't reach for `{% with %}` chains and filter pipelines to compute it.

- Template calls take no arguments: `{{ obj.method }}` works, `{{ obj.method(arg) }}` doesn't. Add a property or pass the value in.
- A failed lookup renders as `''` rather than raising, so typos fail silently — `string_if_invalid` in `OPTIONS` can surface them during development.
- `{% for %}` supports `{% empty %}`; use it instead of a separate `{% if %}`.
- Calling a queryset in a template executes it, and doing that inside a loop is an N+1 — prefetch in the view.

On Django 6.1+, double-dot lookups (`{{ book..title }}`) are deprecated.

## Context Processors

A context processor runs on every request, so use them only for genuinely global values, and keep them cheap — a query in a context processor is a query on every page:

```python
def site_settings(request):
    return {"support_email": settings.SUPPORT_EMAIL}
```

Register it in `TEMPLATES["OPTIONS"]["context_processors"]`. For anything expensive, prefer an explicit context entry in the views that need it, or a cached custom tag.

## Custom Tags and Filters

Put them in `<app>/templatetags/<name>.py` (with an `__init__.py` in the directory) and load with `{% load <name> %}`:

```python
from django import template

register = template.Library()


@register.filter
def currency(value):
    return f"${value:,.2f}"


@register.simple_tag(takes_context=True)
def active_class(context, url_name):
    return "active" if context["request"].resolver_match.url_name == url_name else ""


@register.inclusion_tag("articles/_byline.html")
def byline(article):
    return {"article": article}
```

Prefer `simple_tag` and `inclusion_tag` over the low-level `Node` API. `simple_tag` autoescapes its output; if a tag must return markup, build it with `format_html()` rather than string concatenation plus `mark_safe()`.

## Fragment Caching

Cache expensive fragments with `{% cache %}`, keyed on everything the fragment varies by:

```html
{% load cache %}
{% cache 600 sidebar request.user.pk %}
  ...
{% endcache %}
```

Omitting a key that the fragment actually depends on is how users end up seeing each other's data. See [the deployment reference](deployment.md) for cache backend configuration.

## Static Files and Assets

Reference assets through `{% static %}` so hashed filenames resolve under `ManifestStaticFilesStorage`:

```html
{% load static %}
<link rel="stylesheet" href="{% static 'css/site.css' %}">
```

On Django 6.1+, `{% csp_nonce_attr %}` renders the CSP nonce attribute on `<script>` and `<link>` elements when the `csp()` context processor is configured — see [the deployment reference](deployment.md).
