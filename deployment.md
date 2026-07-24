# Django Deployment Reference

Production settings, security configuration, static files, and email.

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

## HTTPS and Security Settings

Serve everything over HTTPS and enable the related protections:

```python
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 2_592_000  # start low, then increase
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

If the app runs behind a proxy or load balancer that terminates TLS, set `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` — and only then.

On Django 6.1+, leave `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` at its new default of `False` unless legacy signed cookies must remain valid through the upgrade.

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

On Django 6.1+, use the `{% csp_nonce_attr %}` template tag to render the nonce attribute on `<script>` and `<link>` elements (a `security.W027` system check warns when `CSP.NONCE` is configured without the context processor).

Roll out new policies with `SECURE_CSP_REPORT_ONLY` first to log violations without breaking the site, then move to `SECURE_CSP` to enforce:

```python
SECURE_CSP_REPORT_ONLY = {
    "default-src": [CSP.SELF],
    "report-uri": "/csp-reports/",
}
```

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

WhiteNoise is the standard choice for serving static files directly from the application server; use a CDN or object storage (via `django-storages`) for user-uploaded media. Never serve media through Django views in production.

## Application Server

Never use `runserver` in production. Use Gunicorn for WSGI or Uvicorn workers under Gunicorn for ASGI:

```bash
gunicorn config.wsgi
# or, for async support:
gunicorn config.asgi -k uvicorn_worker.UvicornWorker
```

Only deploy under ASGI when the project actually uses async features; WSGI remains simpler and entirely sufficient for synchronous projects.

## Database

Use PostgreSQL in production. Set `CONN_MAX_AGE` (or `"pool"` options with psycopg 3) to avoid reconnecting on every request. Django 6.1 supports PostgreSQL 15+, MySQL 8.4+, and MariaDB 10.11+ — check the supported database versions before upgrading Django.

## Email

Send email through a transactional provider, not a local SMTP daemon, and send it from background tasks rather than inline in request handling.

On Django 6.1+, configure email with the new `MAILERS` setting, which follows the same pattern as `CACHES`, `DATABASES`, `STORAGES`, and `TASKS`:

```python
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {"host": "smtp.example.com", "use_tls": True},
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

A deployment-only `mail.E001` system check prevents shipping a development-only email backend (console, dummy, file-based) as the default mailer.

## Errors and Monitoring

Configure `ADMINS` and logging, or better, an error-tracking service. Django logs unhandled exceptions to the `django.request` logger; make sure something is listening in production.
