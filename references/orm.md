# Django ORM Reference

Detailed patterns for models, managers, querysets, transactions, and migrations.

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

Enum members are usable directly in queries and comparisons, which keeps magic strings out of the codebase:

```python
Article.objects.filter(status=Article.Status.PUBLISHED)
```

Other conventions:

- Business logic belongs on the model (or a manager/service layer), not in views or templates.
- Give a model `get_absolute_url()` when it has a canonical detail page, and use `reverse()` inside it.
- `blank=True` controls form-level optionality and `null=True` controls database nullability — they are not interchangeable.
- Prefer `DecimalField` over `FloatField` for money.
- Override `save()` sparingly, and remember that neither `save()` nor signals run for `bulk_create()` or `queryset.update()`.

### Model Validation

`full_clean()` runs field validators, `clean()`, and `validate_unique()` — but Django only calls it from forms, not from `save()`. Rely on forms for user input and on database constraints for invariants that must always hold, rather than assuming model validation runs on every write path.

## Constraints and Indexes

Express invariants as database constraints so they hold regardless of the code path that writes the data:

```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=["author", "slug"], name="unique_author_slug"),
        models.UniqueConstraint(
            fields=["slug"],
            condition=models.Q(status="PU"),
            name="unique_published_slug",
        ),
        models.CheckConstraint(
            condition=models.Q(price__gte=0), name="price_non_negative"
        ),
    ]
    indexes = [
        models.Index(fields=["-created_at"], name="article_created_idx"),
    ]
```

Prefer `UniqueConstraint` over the older `unique_together`, and `Meta.indexes` over per-field `db_index` when the index spans multiple fields or needs a condition. The `CheckConstraint` keyword is `condition`; the older `check` argument was removed in Django 6.0, so code carrying it over from an older project will raise `TypeError`.

## `on_delete` Options

Choose `on_delete` deliberately — `CASCADE` is a common default but often wrong for the domain. `PROTECT` prevents accidental deletion; `RESTRICT` allows the delete only when another cascading path covers the object; `SET_NULL` requires `null=True`; `SET_DEFAULT` requires a default.

### Database-Level Delete Options

On Django 6.1+, prefer the database-level options `DB_CASCADE`, `DB_SET_NULL`, and `DB_SET_DEFAULT` when signals are not needed. They run entirely in the database via the SQL `ON DELETE` clause, so Django does not need to load objects before deleting them — much more efficient for large cascades:

```python
class Comment(models.Model):
    article = models.ForeignKey(Article, on_delete=models.DB_CASCADE)
```

`DB_CASCADE` does not trigger `pre_delete` or `post_delete` signals. If code relies on those signals — for file cleanup, search index updates, or audit rows — keep the Python-level `CASCADE`.

## Custom Managers and QuerySets

Put reusable query logic on a `QuerySet` subclass and expose it as the manager with `as_manager()`, so the methods stay chainable:

```python
class ArticleQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Article.Status.PUBLISHED)

    def with_author(self):
        return self.select_related("author")


class Article(models.Model):
    # ...
    objects = ArticleQuerySet.as_manager()


Article.objects.published().with_author()
```

instead of:

```python
# DO NOT DO THIS — a plain Manager method can't be chained onto
class ArticleManager(models.Manager):
    def published(self):
        return self.filter(status="PU")
```

A custom *default* manager that filters rows out also affects related-object access and the admin. When a filtered manager is needed alongside the full one, declare the unfiltered manager first so it becomes `Meta.base_manager_name`, or set `Meta.default_manager_name` explicitly.

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

Use `Prefetch` when the prefetched queryset itself needs filtering, ordering, or its own `select_related()`:

```python
from django.db.models import Prefetch

Article.objects.prefetch_related(
    Prefetch(
        "comments",
        queryset=Comment.objects.filter(approved=True).select_related("author"),
        to_attr="approved_comments",
    )
)
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

Prefer explicit `select_related()`/`prefetch_related()` when the needed relations are known; use `FETCH_PEERS` as a safety net for code paths where they aren't, and `RAISE` in hot paths to make accidental queries fail loudly.

## Use the Database, Not Python

- `queryset.exists()` instead of `if queryset:` or `len(queryset) > 0`
- `queryset.count()` instead of `len(queryset)`
- `bulk_create()` / `bulk_update()` instead of saving in a loop
- `update()` / `delete()` on querysets for mass changes (note: these skip `save()` and signals)
- `F()` expressions for atomic field updates: `Article.objects.filter(pk=pk).update(views=F("views") + 1)`
- `Q()` objects for OR and complex lookups
- `.only()` / `.defer()` or `.values()` / `.values_list()` when full model instances aren't needed
- `aggregate()` / `annotate()` instead of computing sums and counts in Python
- `Case`/`When`, `Coalesce`, and `Subquery`/`OuterRef` instead of post-processing rows in Python
- `iterator()` for large result sets that don't need to be cached in memory

`bulk_create()` does not call `save()` or send `pre_save`/`post_save` signals. Use its `update_conflicts` / `ignore_conflicts` arguments for upserts rather than a get-then-create loop.

Pass an explicit field name to `values_list()` with `flat=True` — omitting it is deprecated as of Django 6.1:

```python
Article.objects.values_list("pk", flat=True)
```

### Getting or Creating Rows

Use `get_or_create()` and `update_or_create()` instead of a check-then-write race:

```python
tag, created = Tag.objects.get_or_create(slug=slug, defaults={"name": name})
```

Back them with a `UniqueConstraint` on the lookup fields; without one, concurrent requests can still create duplicates.

### Newer Query Features

On Django 6.1+:

- `UUID4()` and `UUID7()` database functions generate UUIDs in the database; `UUID7()` values sort by creation time, which indexes far better than random UUIDs.
- `JSONNull` expresses a JSON `null` in `JSONField` queries — passing `None` as a top-level scalar is deprecated.
- `BitAnd`, `BitOr`, and `BitXor` are available from `django.db.models`; the `contrib.postgres` versions are deprecated.
- `QuerySet.totally_ordered` reports whether the ordering is deterministic — useful before paginating.
- `in_bulk()` is chainable after `values()` / `values_list()`.

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

The same rule applies to `cursor.execute()` — pass parameters as the second argument, and use `connection.ops.quote_name()` for identifiers that must be dynamic. Prefer ORM expressions over `RawSQL` and `extra()`; on Django 6.1+, SQL aliases are systematically quoted, so mixed-case identifiers inside `RawSQL` may need quoting after an upgrade.

## Transactions

Wrap multi-step writes that must succeed or fail together in `transaction.atomic()`:

```python
from django.db import transaction


with transaction.atomic():
    order.save()
    inventory.decrement(order.quantity)
```

Use `transaction.on_commit()` to defer side effects (sending email, enqueueing tasks) until the transaction commits. On Django 6.1+, use `transaction.savepoint_create()` instead of the deprecated `transaction.savepoint()`.

Other points:

- Catch database errors *outside* the `atomic()` block. Inside a broken transaction every further query fails, so catching `IntegrityError` in place and carrying on is a common bug.
- `select_for_update()` locks the selected rows for the rest of the transaction and must run inside `atomic()`.
- `ATOMIC_REQUESTS = True` wraps every request in a transaction. It is a reasonable default for write-heavy apps, but it holds a transaction open for the whole view; prefer explicit `atomic()` blocks in performance-sensitive code.
- Keep external calls — HTTP requests, task enqueues, emails — out of transactions; defer them with `on_commit()`.

## Migrations

- Always commit migration files to version control.
- Never edit a migration that has been applied to a shared or production database.
- Use `python manage.py makemigrations --check` in CI to catch missing migrations.
- Review generated migrations before committing, especially after renames — the autodetector guesses, and a wrong guess drops a column and its data.
- Give meaningful data migrations a `reverse_code`, or `migrations.RunPython.noop` when reversal is a no-op.
- Squash long migration chains periodically with `squashmigrations`.
- Inspect the SQL for a risky migration with `python manage.py sqlmigrate app_label 0004`.

In data migrations, use the historical model from the migration state, never the imported model:

```python
from django.db import migrations
from django.utils.text import slugify


def backfill_slugs(apps, schema_editor):
    Article = apps.get_model("articles", "Article")
    for article in Article.objects.filter(slug="").iterator():
        article.slug = slugify(article.title)
        article.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [("articles", "0003_article_slug")]
    operations = [
        migrations.RunPython(backfill_slugs, migrations.RunPython.noop),
    ]
```

instead of:

```python
# DO NOT DO THIS — the current model may not match the schema at this point in history
from articles.models import Article
```

Historical models expose fields and managers but not custom methods, so keep data-migration logic self-contained.

For zero-downtime deploys, split destructive changes across releases: add the new nullable column and backfill it, deploy code that writes both, then drop the old column in a later migration. Adding a column with a non-null default can rewrite the whole table — add it nullable, backfill in batches, then add the constraint.
