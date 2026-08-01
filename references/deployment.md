# Django Deployment Reference

Production settings, security configuration, static files, caching, and email.

## Deployment Checklist

Always run the built-in checklist before deploying and fix every warning:

```bash
python manage.py check --deploy
```

Non-negotiables in production:

```python
DEBUG = False
ALLOWED_HOSTS = ["example.com", "www.example.com"]
SECRET_KEY = os.environ["SECRET_KEY"]  # never committed
```

A deploy runs, in order: apply migrations, `collectstatic`, then restart the application server. Run `check --deploy` in CI so a misconfiguration fails the build rather than the release.

## Settings Layout

Keep one settings module per environment in a package, sharing a common base:

```
config/settings/__init__.py
config/settings/base.py
config/settings/dev.py
config/settings/prod.py
```

Select it with `DJANGO_SETTINGS_MODULE`, and read every environment-specific value from the environment. Fail loudly on missing production values — `os.environ["SECRET_KEY"]` raising at startup is better than a silent insecure default.

```python
# prod.py
from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = os.environ["ALLOWED_HOSTS"].split(",")
```

A single settings module driven entirely by environment variables is also fine; what matters is that production values are never defaults and never committed.

## HTTPS and Security Settings

Serve everything over HTTPS and enable the related protections:

```python
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 2_592_000  # start low, then increase
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
```

HSTS is hard to undo: browsers honor `SECURE_HSTS_SECONDS` for its full duration even after the header stops being sent. Start with a short max-age, confirm every subdomain serves HTTPS, then raise it.

If the app runs behind a proxy or load balancer that terminates TLS, set `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` — and only then. Setting it when the header can be spoofed by a client defeats the redirect and the secure-cookie logic.

Set `CSRF_TRUSTED_ORIGINS` when POSTs arrive from other subdomains or origins, and keep `SESSION_COOKIE_SAMESITE` / `CSRF_COOKIE_SAMESITE` at `"Lax"` unless a cross-site flow requires otherwise.

On Django 6.1+, leave `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` at its new default of `False` unless legacy signed cookies must remain valid through the upgrade; the setting itself is transitional and deprecated.

Django 6.1 also raises the default PBKDF2 iteration count, so existing password hashes upgrade transparently on next login — no action needed beyond expecting a slightly slower login.

## Content Security Policy

Use Django's built-in CSP support (Django 6.0+) instead of the third-party `django-csp` package. Add the middleware and configure a nonce-based policy:

```python
# settings.py
from django.utils.csp import CSP

MIDDLEWARE = [
    # ...
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    # ...
]

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
}
```

When using `CSP.NONCE`, also add the `csp()` context processor so templates can render the nonce:

```python
TEMPLATES = [
    {
        # ...
        "OPTIONS": {
            "context_processors": [
                # ...
                "django.template.context_processors.csp",
            ],
        },
    },
]
```

On Django 6.1+, use the `{% csp_nonce_attr %}` template tag to render the nonce attribute on `<script>` and `<link>` elements, and on a `Media` object's assets. A `security.W027` system check warns when `CSP.NONCE` is configured without the context processor.

Roll out new policies with `SECURE_CSP_REPORT_ONLY` first to log violations without breaking the site, then move to `SECURE_CSP` to enforce:

```python
SECURE_CSP_REPORT_ONLY = {
    "default-src": [CSP.SELF],
    "report-uri": "/csp-reports/",
}
```

Avoid `'unsafe-inline'`. Inline handlers and inline `<script>` blocks are exactly what CSP exists to stop; move them to static files or give them the nonce.

## Static Files

Run `collectstatic` at deploy time and serve static files with hashed filenames for cache busting:

```python
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}
```

Hashed names let static responses be served with a long `max-age` safely. Always refer to static assets through `{% static %}` so the hashed name is used; hardcoded paths under `/static/` will 404 with manifest storage.

WhiteNoise is the standard choice for serving static files directly from the application server; use a CDN or object storage (via `django-storages`) for user-uploaded media. Never serve media through Django views in production, and never trust the filename or content type of an upload.

## Application Server

Never use `runserver` in production. Use Gunicorn for WSGI or Uvicorn workers under Gunicorn for ASGI:

```bash
gunicorn config.wsgi
# or, for async support:
gunicorn config.asgi -k uvicorn_worker.UvicornWorker
```

Only deploy under ASGI when the project actually uses async features; WSGI remains simpler and entirely sufficient for synchronous projects. See [the async reference](async.md).

Put the app behind a reverse proxy that terminates TLS and enforces request size and timeout limits. Size the worker count to the host's CPU count and the workload, and set a request timeout so a hung upstream call cannot pin a worker forever.

## Database

Use PostgreSQL in production. Set `CONN_MAX_AGE` (or `"pool"` options with psycopg 3) to avoid reconnecting on every request, and enable `CONN_HEALTH_CHECKS` so a stale persistent connection is replaced rather than raising:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        # ...
    }
}
```

Persistent connections and an external pooler (PgBouncer) interact badly in transaction-pooling mode — pick one. Django 6.1 supports PostgreSQL 15+, MySQL 8.4+, MariaDB 10.11+, and SQLite 3.37+; check the supported database versions before upgrading Django.

## Caching

Configure a real cache backend in production — Redis or Memcached — rather than the per-process local-memory default:

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ["REDIS_URL"],
    },
}
```

Cache expensive computed values and rendered fragments (see [the templates reference](templates.md)) rather than reaching for the whole-site cache middleware, which is easy to get wrong for authenticated pages. Always set a timeout, and always namespace keys with `KEY_PREFIX` when several environments share one cache server.

Sessions default to the database backend, which is durable and usually correct. Only move sessions to the cache if losing them on a cache restart is acceptable.

## Email

Send email through a transactional provider, not a local SMTP daemon, and send it from background tasks rather than inline in request handling — see [the async reference](async.md).

On Django 6.1+, configure email with the new `MAILERS` setting, which follows the same pattern as `CACHES`, `DATABASES`, `STORAGES`, and `TASKS`:

```python
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {"host": "smtp.example.com", "use_tls": True},
    },
    "marketing": {
        "BACKEND": "example.third_party.EmailBackend",
        "OPTIONS": {"region": "africa-1"},
    },
}
```

Select a non-default mailer with the `using` argument to `send_mail()` and friends.

The legacy `EMAIL_BACKEND` and `EMAIL_*` settings, `mail.get_connection()`, and the `connection`/`fail_silently`/`auth_user`/`auth_password` arguments to mail functions are all deprecated in Django 6.1 and will be removed in Django 7.0 — do not write new code with them:

```python
# DO NOT DO THIS — deprecated in Django 6.1
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.example.com"
```

A deployment-only `mail.E001` system check prevents shipping a development-only email backend (console, dummy, file-based) as the default mailer, and `mail.W001` warns when `MAILERS` has no `"default"` entry.

## Errors and Monitoring

Configure `ADMINS` and logging, or better, an error-tracking service. Django logs unhandled exceptions to the `django.request` logger; make sure something is listening in production:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"level": "ERROR", "propagate": True},
    },
}
```

Log to stdout and let the platform collect it. Never log secrets, session keys, or full request bodies; Django's error reports scrub settings that look sensitive, and `@sensitive_variables` / `@sensitive_post_parameters` extend that to view locals and POST data.

Expose a cheap health-check URL that does not hit the database for load-balancer probes, and a separate readiness check that does.
