# Checklists

Step-by-step checklists for multi-step Django tasks. Copy the relevant one and track progress while working through it.

## New project

```
- [ ] `django-admin startproject config .`
- [ ] Create the accounts app and a custom user model BEFORE the first migration
- [ ] Set `AUTH_USER_MODEL` in settings
- [ ] Split settings (base / dev / prod) and move secrets to the environment
- [ ] Add `.gitignore` (`.env`, `db.sqlite3`, `__pycache__/`, `/media/`, `/staticfiles/`)
- [ ] Run the first `makemigrations` and `migrate`
- [ ] Configure `TEMPLATES["DIRS"]` and add a base template
- [ ] Add a `pyproject.toml` with Ruff (or equivalent lint/format config)
- [ ] Write one smoke test and confirm `manage.py test` passes
- [ ] Commit before adding features
```

Getting the custom user model in before the first migration is the only irreversible step on this list.

## New app

```
- [ ] `python manage.py startapp <name>` and add it to `INSTALLED_APPS`
- [ ] Define models with `__str__`, `Meta.ordering`, constraints, and choices enums
- [ ] `makemigrations` and review the generated migration before applying
- [ ] Register a configured `ModelAdmin` (see references/admin.md)
- [ ] Add `<name>/urls.py` with `app_name` and include it from the root URLconf
- [ ] Add views, scoping `get_queryset()` for both data and permissions
- [ ] Add a `ModelForm` with explicit `fields` for any user input
- [ ] Add templates extending the base template
- [ ] Write tests for permissions, form validation, and each view's status code
- [ ] Check the list views with `assertNumQueries` for N+1 regressions
```

## Pre-deploy

```
- [ ] `python manage.py check --deploy` — fix every warning
- [ ] `DEBUG = False` and `ALLOWED_HOSTS` set explicitly
- [ ] `SECRET_KEY` and all credentials read from the environment
- [ ] HTTPS settings on (SSL redirect, HSTS, secure cookies)
- [ ] CSP configured, rolled out report-only first
- [ ] `makemigrations --check` passes (no unapplied model changes)
- [ ] Migrations reviewed for locking / table rewrites on large tables
- [ ] `collectstatic` runs clean with `ManifestStaticFilesStorage`
- [ ] Cache and email backends are production backends, not console/locmem
- [ ] Logging or error tracking confirmed to receive events
- [ ] Full test suite green
```

Deploy order: migrate → `collectstatic` → restart. See references/deployment.md.

## Upgrading Django

```
- [ ] Confirm the current version is on the latest patch release first
- [ ] Read the release notes for EVERY version being skipped, not just the target
- [ ] Check the deprecation timeline for the target version
- [ ] Run the suite with `-W error::DeprecationWarning` to surface removals (from 6.2, warnings are named for calendar versions, e.g. `RemovedInDjango2028Warning`)
- [ ] Verify Python and database versions meet the new minimums
- [ ] Check third-party packages for compatibility before bumping
- [ ] Upgrade one minor version at a time (e.g. 5.2 → 6.0 → 6.1)
- [ ] Run `makemigrations` — new versions sometimes change field defaults
- [ ] Re-run `check --deploy`; new checks appear in most releases
```

Upgrade to each LTS along the way rather than jumping between distant versions.

Moving to Django 6.1 specifically:

```
- [ ] Go straight to the latest 6.1.x — 6.1.2 and 6.1.3 are security releases that also change behavior
- [ ] PostgreSQL 15+, MySQL 8.4+, MariaDB 10.11+, SQLite 3.37+
- [ ] Expect cache misses after deploy: `cache_page` / `vary_on_*` keys changed
- [ ] Check `first()` / `last()` calls that relied on implicit pk ordering
- [ ] Replace deprecated email settings with `MAILERS`
- [ ] Replace `select_related()` with no arguments, `list_select_related = True`, and `values_list(flat=True)` without a field
- [ ] Re-check any copied admin templates against the new change-form markup
```

### Preparing for Django 6.2 LTS

Django 6.2 is due in April 2027 and is still in development; nothing here applies until it is released, but writing code this way now avoids churn:

- Set `async_capable` and `sync_capable` explicitly on middleware; the default becomes `async_capable = False`.
- Don't rely on `JsonResponse`'s `safe` argument — it is deprecated and its default becomes `False`.
- Use `functools.cached_property`; `django.utils.functional.cached_property` is deprecated.
- Use `django.VERSION.feature` / `.patch` / `.status` instead of indexing past the first two components of `django.VERSION`.
- Plan for PostgreSQL 16+.
- Template tags may span multiple lines, so a literal `{%` and `%}` on separate lines can now parse as a tag; use `{% templatetag openblock %}` / `{% templatetag closeblock %}` for literal delimiters.
- New features to expect: the HTTP `QUERY` method (`query()` view handler, `Client.query()`) and the `listurls` management command; `django-admin` is renamed `django`, with the old name kept as an alias.

## Reviewing Django code

```
- [ ] Access control: is every queryset scoped to the requesting user?
- [ ] `get_object_or_404` used instead of bare `.get()`
- [ ] No data mutated in a GET request; POST redirects afterward
- [ ] Forms validate all user input; no `fields = "__all__"`
- [ ] `ModelChoiceField` querysets limited to what the user may select
- [ ] No `|safe` / `mark_safe()` on user-supplied content
- [ ] No f-strings or `%` formatting inside raw SQL
- [ ] N+1 checked: `select_related` / `prefetch_related` on anything iterated
- [ ] Secrets read from the environment, not literals
- [ ] Migrations included and reviewed
- [ ] Tests cover the permission boundaries, not just the happy path
- [ ] DRF APIs: explicit serializer `fields`, `get_queryset()` scoped to the user, no `AllowAny` default, list endpoints paginated, `ordering_fields` set (see [the DRF reference](drf.md))
```
