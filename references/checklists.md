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
- [ ] Run the suite with `-W error::DeprecationWarning` to surface removals
- [ ] Verify Python and database versions meet the new minimums
- [ ] Check third-party packages for compatibility before bumping
- [ ] Upgrade one minor version at a time (e.g. 5.2 → 6.0 → 6.1)
- [ ] Run `makemigrations` — new versions sometimes change field defaults
- [ ] Re-run `check --deploy`; new checks appear in most releases
```

Upgrade to each LTS along the way rather than jumping between distant versions.

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
```
