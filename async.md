# Django Async and Background Tasks Reference

Async views, the async ORM interface, and the Tasks framework.

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

Never call blocking code directly inside an async view — the logic will work, but it blocks the event loop and damages performance heavily. Under WSGI, async views run in their own event loop per request; they only pay off under an ASGI server.

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

Beware of lazy attribute access: `article.author` on an unfetched foreign key triggers a synchronous query even inside async code. Use `select_related()` up front, `aget()` with the relation, or fetch modes (Django 6.1+, see [the ORM reference](orm.md)).

## Mixing Sync and Async

Wrap blocking calls with `sync_to_async()` when they must run inside async code, and `async_to_sync()` for the reverse:

```python
from asgiref.sync import sync_to_async

result = await sync_to_async(legacy_blocking_function)(arg)
```

Decorate sync functions that touch the database with `sync_to_async(thread_sensitive=True)` semantics in mind — the default is correct for ORM safety; don't override it without reason.

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

Enqueue after the surrounding transaction commits, so a rolled-back request doesn't leave orphaned work:

```python
from functools import partial

from django.db import transaction

transaction.on_commit(partial(send_welcome_email.enqueue, to=user.email))
```

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
- `DummyBackend` records tasks without running them — useful in tests.

Production requires a third-party backend with a worker process (e.g. the `django-tasks` package's database backend). On Django 6.1+, the `@task` decorator forwards extra keyword arguments to the backend's task class, and `Task`/`TaskResult` instances can be pickled.

### When to Use Celery Instead

The Tasks framework is deliberately minimal. Use Celery (or an equivalent) when the project needs periodic scheduling, task chaining and workflows, retries with backoff, rate limiting, or result storage beyond what the chosen backend provides.
