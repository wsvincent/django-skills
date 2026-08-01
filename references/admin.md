# Django Admin Reference

`ModelAdmin` configuration, computed columns, inlines, query optimization, actions, and security.

## Register With a Configured `ModelAdmin`

```python
from django.contrib import admin

from .models import Article


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["title", "author__username"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    prepopulated_fields = {"slug": ["title"]}
    autocomplete_fields = ["author"]
    readonly_fields = ["created_at", "updated_at"]
```

instead of:

```python
# DO NOT DO THIS — an unusable list of "Article object (1)" rows
admin.site.register(Article)
```

The `@admin.register()` decorator is preferred over a separate `admin.site.register()` call. `search_fields` supports related lookups with `__`, and prefixes such as `^` (starts with) and `=` (exact).

## Computed Columns

Use `@admin.display` for derived values rather than an unlabeled method:

```python
@admin.display(description="Comments", ordering="comment_count")
def comment_total(self, obj):
    return obj.comment_count
```

Sorting only works when `ordering` names something the database can sort on — usually an annotation added in `get_queryset()`. A column that computes a value in Python cannot be sorted or searched.

Never build HTML by concatenation in a display method; use `format_html()` so arguments are escaped.

## Query Optimization

The change list is a common source of N+1 queries. Annotate and select related data in `get_queryset()`:

```python
def get_queryset(self, request):
    return (
        super()
        .get_queryset(request)
        .select_related("author")
        .annotate(comment_count=Count("comments"))
    )
```

Name the related fields explicitly. On Django 6.1+, setting `list_select_related = True` (and returning `True` from `get_list_select_related()`) is deprecated — pass a list of field names instead. Also in 6.1, when `list_select_related` is `False`, the change list selects only the foreign keys that appear in `list_display` rather than all of them.

Use `autocomplete_fields` for foreign keys to large tables; the default `<select>` renders every row. `autocomplete_fields` requires `search_fields` on the *target* model's admin. `raw_id_fields` is the fallback when the target has no registered admin.

Set `list_per_page` down from the default (100) on heavy models, and prefer `show_facets = admin.ShowFacets.NEVER` when facet counts on filters are expensive.

## Inlines

```python
class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ["author", "body", "approved"]
    autocomplete_fields = ["author"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    inlines = [CommentInline]
```

`extra = 0` avoids rendering blank forms nobody asked for. Inlines load all related rows on the change page, so avoid them for relations that can grow without bound — link to a filtered change list instead.

## Actions

```python
@admin.action(description="Mark selected articles as published")
def make_published(modeladmin, request, queryset):
    queryset.update(status=Article.Status.PUBLISHED)
```

A `queryset.update()` in an action skips `save()` and signals — loop over the objects when those matter. Check permissions inside the action; being able to see the change list doesn't imply being able to run a bulk mutation.

On Django 6.1+, the `location` argument of `@admin.action()` controls where an action appears — the change list (default), the change form, or both — and `description_plural` provides a plural label for change-list actions. Overriding `get_actions()` or `get_action_choices()` now requires accepting the new `action_location` parameter.

## Permissions and Scoping

Override the per-object permission hooks rather than relying on the UI to hide things:

```python
def has_change_permission(self, request, obj=None):
    return obj is None or obj.author == request.user or request.user.is_superuser


def get_queryset(self, request):
    qs = super().get_queryset(request)
    return qs if request.user.is_superuser else qs.filter(author=request.user)
```

Scoping `get_queryset()` is what actually prevents access — `has_*_permission()` alone still leaves objects reachable through the change list and actions.

Use `readonly_fields` for values staff should see but not edit, and `exclude` for fields they shouldn't see at all. Both are enforced server-side.

## Security

The admin is for trusted staff only. It is not an access-control layer for end users, and it should never be the interface a customer touches.

- Change the default `/admin/` URL in production; it removes a large share of automated probing.
- Require staff accounts to use strong authentication, and grant `is_superuser` sparingly.
- Consider restricting the admin by network, or putting it behind a second authentication factor.
- Keep `django.contrib.admin` out of `INSTALLED_APPS` entirely on deployments that don't need it.
- Django's `LogEntry` records admin changes, but only those made through the admin — don't treat it as a complete audit log.

## Customization

Set the header and title so staff can tell environments apart at a glance:

```python
admin.site.site_header = "Example Staff (production)"
admin.site.site_title = "Example"
admin.site.index_title = "Administration"
```

Override admin templates by placing files at `templates/admin/<app>/<model>/change_form.html`, and extend the original with `{% extends "admin/change_form.html" %}` rather than copying it wholesale — copied templates break on upgrade. Django 6.1 reworks change-form markup for accessibility, which is exactly the kind of change a copied template misses.
