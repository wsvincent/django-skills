# Django Async and Background Tasks Reference

Async views, the async ORM interface, and the Tasks framework.

## When Async Is Worth It

Async only pays off under an ASGI server, and only for views that spend their time waiting on I/O that Django can await — outbound HTTP calls, other async services, long-lived connections. Under WSGI, an async view runs in its own event loop per request and gains nothing.

Default to synchronous code. A synchronous view served by enough Gunicorn workers is simpler to reason about and to debug, and it is the right answer for ordinary database-backed pages.

## Async Views

Write async views only when the code inside genuinely awaits (async ORM calls, `httpx`, etc.). In case of doubt, or by default, write regular synchronous views:

```python
import httpx
from django.http import JsonResponse


async def proxy_view(request):
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
    return JsonResponse(response.json())
```

Never call blocking code directly inside an async view — the logic will work, but it blocks the event loop and damages performance heavily.

Class-based views become async by defining async handlers; the whole view must be consistently async, not a mix:

```python
from django.views import View


class ProxyView(View):
    async def get(self, request):
        ...
```

Concurrency inside a view comes from `asyncio.gather()` or a task group — that is the main reason to reach for async at all:

```python
import asyncio

profile, activity = await asyncio.gather(fetch_profile(uid), fetch_activity(uid))
```

## Async ORM

Use the async ORM interface inside async code — the `a`-prefixed methods and async iteration:

```python
async def article_detail(request, pk):
    article = await Article.objects.aget(pk=pk)
    return JsonResponse({"title": article.title})


async def article_titles(request):
    titles = [a.title async for a in Article.objects.all()]
    return JsonResponse({"titles": titles})
```

instead of:

```python
# DO NOT DO THIS — blocking ORM call in an async view
async def article_detail(request, pk):
    article = Article.objects.get(pk=pk)  # raises SynchronousOnlyOperation
```

The async methods mirror the sync ones: `aget()`, `acreate()`, `asave()`, `adelete()`, `aupdate()`, `acount()`, `aexists()`, `afirst()`, `aget_or_create()`, `abulk_create()`, `aaggregate()`.

Two traps:

- Lazy attribute access. `article.author` on an unfetched foreign key triggers a *synchronous* query even inside async code. Use `select_related()` up front, or fetch modes (Django 6.1+, see [the ORM reference](orm.md)).
- The database connections themselves are still synchronous, running in a thread executor. Async views do not make the ORM faster; they help when the view waits on something other than the database.

Transactions are not async-native either. Wrap a transactional block in `sync_to_async` around a synchronous function rather than trying to use `async with transaction.atomic()`.

## Mixing Sync and Async

Wrap blocking calls with `sync_to_async()` when they must run inside async code, and `async_to_sync()` for the reverse:

```python
from asgiref.sync import sync_to_async

result = await sync_to_async(legacy_blocking_function)(arg)
```

`sync_to_async` defaults to `thread_sensitive=True`, which runs the call in a single shared thread so ORM state and transactions behave correctly. Do not set it to `False` for anything that touches the database.

## Async Middleware and Tests

Middleware declares which call styles it supports. Mark middleware that can run in both modes so Django does not insert adapter threads around it:

```python
from asgiref.sync import iscoroutinefunction, markcoroutinefunction


class TimingMiddleware:
    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(get_response):
            markcoroutinefunction(self)
    ...
```

Test async views with `async def` test methods and `AsyncClient`:

```python
from django.test import TestCase


class ProxyTests(TestCase):
    async def test_proxy(self):
        response = await self.async_client.get("/proxy/")
        self.assertEqual(response.status_code, 200)
```

## Background Tasks

Use the built-in Tasks framework (Django 6.0+) for fire-and-forget work — sending email, calling webhooks, invalidating caches — instead of running it inline in the request-response cycle:

```python
from django.core.mail import send_mail
from django.tasks import task


@task
def send_welcome_email(to: str):
    send_mail("Welcome!", "Thanks for signing up.", None, [to])


# In a view:
send_welcome_email.enqueue(to=user.email)
```

Task arguments must be JSON-serializable — pass primary keys, not model instances:

```python
send_welcome_email.enqueue(to=user.email)
```

instead of:

```python
# DO NOT DO THIS — model instances are not serializable task arguments
send_welcome_email.enqueue(user=user)
```

Passing a primary key also avoids acting on a stale copy of the object: the task re-reads the current row when it runs.

Enqueue after the surrounding transaction commits, so a rolled-back request doesn't leave orphaned work:

```python
from functools import partial

from django.db import transaction

transaction.on_commit(partial(send_welcome_email.enqueue, to=user.email))
```

Write tasks to be idempotent. Any backend worth deploying can retry or double-deliver, and a task that sends an email twice is a bug the framework cannot fix for you.

`enqueue()` returns a `TaskResult` carrying the task's id and status; store the id if the result needs to be looked up later.

### Backends

Backends are configured via the `TASKS` setting:

```python
TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
    },
}
```

The built-in backends are for development and testing only:

- `ImmediateBackend` runs the task synchronously at `enqueue()` time.
- `DummyBackend` records tasks without running them — useful in tests, where the recorded calls can be asserted on.

Production requires a third-party backend with a worker process (e.g. the `django-tasks` package's database backend). On Django 6.1+, the `@task` decorator forwards extra keyword arguments to the backend's task class, and `Task`/`TaskResult` instances can be pickled.

### When to Use Celery Instead

The Tasks framework is deliberately minimal. Use Celery (or an equivalent) when the project needs periodic scheduling, task chaining and workflows, retries with backoff, rate limiting, or result storage beyond what the chosen backend provides.
