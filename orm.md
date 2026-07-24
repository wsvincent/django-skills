# Django ORM Reference

Detailed patterns for models, querysets, transactions, and migrations.

## Model Conventions

Give every model a `__str__` method. Use `TextChoices`/`IntegerChoices` enums for choices, database constraints for data integrity, and avoid `null=True` on string-based fields:

```python
from django.db import models


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DR", "Draft"
        PUBLISHED = "PU", "Published"

    title = models.CharField(max_length=200)
    status = models.CharField(
        max_length=2, choices=Status.choices, default=Status.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["title"], name="unique_article_title"),
        ]

    def __str__(self):
        return self.title
```

instead of:

```python
# DO NOT DO THIS
class Article(models.Model):
    STATUS_CHOICES = [("DR", "Draft"), ("PU", "Published")]
    title = models.CharField(max_length=200, null=True)  # null on CharField
    status = models.CharField(max_length=2, choices=STATUS_CHOICES)
```

Business logic belongs on the model (or a manager/service layer), not in views or templates.

## `on_delete` Options

Choose `on_delete` deliberately — `CASCADE` is a common default but often wrong for the domain. `PROTECT` prevents accidental deletion; `SET_NULL` requires `null=True`.

### Database-Level Delete Options

On Django 6.1+, prefer the database-level options `DB_CASCADE`, `DB_SET_NULL`, and `DB_SET_DEFAULT` when signals are not needed. They run entirely in the database via the SQL `ON DELETE` clause, so Django does not need to load objects before deleting them — much more efficient for large cascades:

```python
class Comment(models.Model):
    article = models.ForeignKey(Article, on_delete=models.DB_CASCADE)
```

`DB_CASCADE` does not trigger `pre_delete` or `post_delete` signals. If code relies on those signals, keep the Python-level `CASCADE`.

## Avoid N+1 Queries

Use `select_related()` for `ForeignKey`/`OneToOneField` and `prefetch_related()` for `ManyToManyField` and reverse relations whenever related objects are accessed:

```python
articles = Article.objects.select_related("author").prefetch_related("tags")
```

instead of:

```python
# DO NOT DO THIS — one query per article in the loop
articles = Article.objects.all()
for article in articles:
    print(article.author.username)
```

Always pass explicit field names. Calling `select_related()` with no arguments is deprecated as of Django 6.1:

```python
Article.objects.select_related("author")
```

instead of:

```python
# DO NOT DO THIS — deprecated in Django 6.1
Article.objects.select_related()
```

### Fetch Modes

On Django 6.1+, use fetch modes to control how the ORM loads data when an unfetched field is accessed:

- `FETCH_ONE` (default): fetch the missing field for the current instance only — the classic N+1 behavior.
- `FETCH_PEERS`: fetch the missing field for all instances from the same `QuerySet` — an on-demand `prefetch_related()` that reduces most N+1 problems to two queries with no field list to maintain.
- `RAISE`: raise `FieldFetchBlocked` — use in performance-critical code to prevent unintentional queries.

```python
from django.db import models

books = Book.objects.fetch_mode(models.FETCH_PEERS)
for book in books:
    print(book.author.name)  # two queries total, not N+1
```

Prefer explicit `select_related()`/`prefetch_related()` when the needed relations are known; use `FETCH_PEERS` as a safety net for code paths where they aren't.

## Use the Database, Not Python

- `queryset.exists()` instead of `if queryset:` or `len(queryset) > 0`
- `queryset.count()` instead of `len(queryset)`
- `bulk_create()` / `bulk_update()` instead of saving in a loop
- `update()` / `delete()` on querysets for mass changes (note: these skip `save()` and signals)
- `F()` expressions for atomic field updates: `Article.objects.filter(pk=pk).update(views=F("views") + 1)`
- `Q()` objects for OR and complex lookups
- `.only()` / `.defer()` or `.values()` / `.values_list()` when full model instances aren't needed
- `aggregate()` / `annotate()` instead of computing sums and counts in Python

Pass an explicit field name to `values_list()` with `flat=True` — omitting it is deprecated as of Django 6.1:

```python
Article.objects.values_list("pk", flat=True)
```

## Raw SQL

Never interpolate values into raw SQL:

```python
Article.objects.raw("SELECT * FROM articles_article WHERE title = %s", [title])
```

instead of:

```python
# DO NOT DO THIS — SQL injection
Article.objects.raw(f"SELECT * FROM articles_article WHERE title = '{title}'")
```

## Transactions

Wrap multi-step writes that must succeed or fail together in `transaction.atomic()`:

```python
from django.db import transaction


with transaction.atomic():
    order.save()
    inventory.decrement(order.quantity)
```

Use `transaction.on_commit()` to defer side effects (sending email, enqueueing tasks) until the transaction commits. On Django 6.1+, use `transaction.savepoint_create()` instead of the deprecated `transaction.savepoint()`.

## Migrations

- Always commit migration files to version control.
- Never edit a migration that has been applied to a shared or production database.
- Use `python manage.py makemigrations --check` in CI to catch missing migrations.
- Give meaningful data migrations a `reverse_code`, or `migrations.RunPython.noop` when reversal is a no-op.
- Squash long migration chains periodically with `squashmigrations`.
