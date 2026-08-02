# Django Agent Skill

A [skill](https://code.claude.com/docs/en/skills) that teaches coding agents to write idiomatic, secure, up-to-date Django.

It is **not** an official Django project, but the content is based on the official Django documentation and established community conventions.

## Usage

The skill triggers automatically when a task involves Django:

```
> Add a Comment model with an admin and tests
> Review this view for security problems
> Why is this list page slow?
> Get this project ready to deploy
```

## What's Inside

`SKILL.md` is the entry point and stays loaded; the files in `references/` are read on demand, so depth costs nothing until it's needed.

| File | Covers |
|---|---|
| `SKILL.md` | Project setup, settings, custom user model, URLs, views, forms, templates, security, tasks, testing, admin |
| `references/admin.md` | `ModelAdmin` config, inlines, query optimization, actions, permissions |
| `references/async.md` | Async views, the Tasks framework |
| `references/checklists.md` | Step-by-step checklists for setup, deploys, upgrades, and reviews |
| `references/deployment.md` | Settings layout, HTTPS, CSP, static files, caching, email, monitoring |
| `references/orm.md` | Models, constraints, managers, N+1 and fetch modes, transactions, migrations |
| `references/templates.md` | Configuration, inheritance, partials, escaping, custom tags, fragment caching |
| `references/testing.md` | Test case classes, fixtures, the test client, assertions, async tests |
| `references/views-and-forms.md` | Routing, class-based views, permissions, pagination, form validation, uploads |

## Versions

Targets Django 6.x and Python 3.12+. Django 5.2 is the current LTS, and the skill does not recommend patterns older than the LTS unless a project requires them. Features specific to Django 6.0 and 6.1 are labeled inline so the guidance stays usable on older versions.

## Contributing

Skills are a new and developing space. You are welcome to copy these or fork them. I'm open to any suggestions raised as Issues.

Before opening a pull request, check that every internal link, heading anchor, and reference file still resolves:

```sh
python scripts/check_links.py
```

CI runs the same script on every push and pull request, and checks external URLs weekly.

## License

[MIT](LICENSE)
