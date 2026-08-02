# Django Testing Reference

Choosing a test case class, fixtures, the test client, Django-specific assertions, and async tests.

## Choosing a Test Case Class

Pick the cheapest class that works — the differences are about database access and transaction behavior, and they dominate suite runtime:

- `SimpleTestCase` — no database. For pure functions, form validation without model queries, and template rendering.
- `TestCase` — the default. Wraps each test in a transaction and rolls it back, so tests are isolated and fast.
- `TransactionTestCase` — real commits, truncating tables between tests. Needed only to test `on_commit()` callbacks, `select_for_update()`, or code that inspects transaction state. Much slower.
- `LiveServerTestCase` — runs a real server for browser-driven tests.

## Fixtures

Use `setUpTestData()` for objects shared across the test methods of a class. It runs once per class, inside the class-wide transaction, instead of once per test:

```python
from django.test import TestCase
from django.urls import reverse


class ArticleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("author")
        cls.article = Article.objects.create(title="Testing", author=cls.author)

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

Class attributes set in `setUpTestData()` are isolated per test, so mutating `self.article` in one test won't leak into the next. Use `setUp()` only for objects a test actually modifies in ways that need re-creating, or for non-database state.

Prefer factories (`factory_boy`) or plain helper functions over JSON/YAML fixture files. Fixture files drift from the models and fail in ways that are tedious to debug; a factory is code, and it fails at the point of change.

## The Test Client

```python
response = self.client.get(reverse("articles:detail", args=[article.pk]))
response = self.client.post(reverse("articles:create"), {"title": "New"})
self.client.force_login(self.author)
```

Use `force_login()` rather than posting to the login view; it's faster and doesn't couple the test to the login form. Use `reverse()` for URLs so route changes don't silently break coverage.

Useful attributes on the response: `status_code`, `context`, `templates`, `content`, `json()`, and `redirect_chain` when called with `follow=True`.

## Django-Specific Assertions

- `assertContains(response, text)` / `assertNotContains` — checks the status code and the body together.
- `assertRedirects(response, url)` — checks the redirect and that the target resolves.
- `assertTemplateUsed(response, name)`
- `assertFormError(response.context["form"], "field", "message")` — takes the form instance, not the response:

```python
# DO NOT DO THIS — the response-based signature was removed in Django 5.0
self.assertFormError(response, "form", "title", "This field is required.")
```

- `assertQuerySetEqual(qs, expected)`
- `assertNumQueries(n)` — the practical guard against N+1 regressions:

```python
with self.assertNumQueries(2):
    self.client.get(reverse("articles:list"))
```

Add `assertNumQueries` to list views specifically; it's the only assertion that fails when someone drops a `select_related()`.

## What to Test

Cover the behavior that breaks in production: view status codes and permissions, form validation rules, model methods and constraints, and URL resolution. Test that a logged-out user is redirected and that a non-owner gets a 403 — access-control tests catch the bugs that matter most and are cheap to write.

Don't test the framework itself. A test that asserts `CharField` rejects a too-long value is testing Django.

## Isolation

- `@override_settings(...)` (or `self.settings(...)`) for per-test settings; `@modify_settings` to add or remove a single list entry.
- `override_settings` does not affect settings read at import time — pass those through the code path instead.
- Use `mail.outbox` to assert on sent email; the locmem backend is enabled automatically during tests.
- Mock outbound HTTP; never let the suite hit the network.
- Use `django.test.override_settings(STORAGES=...)` or `tempfile` directories for uploads so tests don't write into the real media root.
- Freeze time with a library (`time-machine`, `freezegun`) rather than sleeping.

## Async Tests

Async views need async test methods and the async client:

```python
class ProxyTests(TestCase):
    async def test_proxy(self):
        response = await self.async_client.get("/proxy/")
        self.assertEqual(response.status_code, 200)
```

See [the async reference](async.md).

## Running Tests

```bash
python manage.py test                    # everything
python manage.py test articles.tests     # one module
python manage.py test --parallel         # split across processes
python manage.py test --keepdb           # reuse the test database
python manage.py test --failfast --shuffle
```

`--keepdb` skips the migration run and saves the most time locally; `--shuffle` surfaces tests that depend on each other's ordering. In CI, also run `python manage.py makemigrations --check` so a missing migration fails the build.

## pytest

`pytest` with `pytest-django` is a fine alternative when the project already uses it. The Django-specific pieces still apply: `django_db` marks database access, `django_assert_num_queries` replaces `assertNumQueries`, and `client` / `admin_client` are fixtures. Mixing `TestCase` subclasses and pytest-style function tests in one suite works but is worth avoiding — pick one style per project.
