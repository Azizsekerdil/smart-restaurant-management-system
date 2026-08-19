# Contributing

Thank you for considering a contribution. This is a single-maintainer
project, so please read this before spending time on a change — it will save
us both some.

## Before you start

- **Security problems do not go here.** Follow [SECURITY.md](SECURITY.md).
  Never open a public issue for a vulnerability.
- For anything larger than a bug fix, **open an issue first** and get a "yes,
  that fits" before writing the code. Scope is deliberately narrow; see
  *What is out of scope* below.
- By contributing you agree your work is released under the
  [MIT License](LICENSE), and that you have the right to contribute it.

## Setting up

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements-dev.txt
cp .env.example .env

python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo        # optional synthetic data
python manage.py runserver
```

## The checks your change must pass

```bash
python -m pytest          # all tests
ruff check .              # lint
black --check .           # formatting
mypy apps                 # types
bandit -r apps config     # static security analysis
python scripts/secret_scan.py
```

On Windows, `.\test_all.ps1` runs all of it. CI runs the same set.

## Standards

**Tests.** A bug fix comes with a test that fails before it and passes after.
A feature comes with tests for the happy path and the interesting failures.
Never delete or weaken a test to make a build green — if a test is wrong,
say so in the pull request and explain why.

**Permissions.** Every new view, endpoint and template action states its
permission explicitly (`@require_permission`, `HasPermissionCode`,
`{% if perms %}`). A screen with no permission check will not be merged.

**Personal data.** If your change touches a model field that could identify a
person, update [`docs/data_inventory.json`](docs/data_inventory.json) — a CI
check compares it against the models and fails if a new candidate field is
missing. Contact details and health data (allergy notes) must respect the
`customer.pii` boundary in *every* surface: template, JSON endpoint and REST
serializer.

**Secrets.** No key, token, password or real personal data in code, tests,
fixtures, commit messages, screenshots or documentation. `.env.example`
carries empty values only.

**Numbers in documentation.** Do not hand-write a count of tests, permissions,
modules or translated strings. Measure it with
`python scripts/project_metrics.py`; the presentation generator already does.

**Comments and docstrings.** Explain *why*, not *what*. A docstring on a
security-relevant function should say what an attacker could do if the
function were wrong. Existing code comments are in Turkish; match the file
you are editing.

**Migrations.** One migration per logical change, with a descriptive name.
Never edit a migration that has been released.

**Translations.** User-visible strings go through `gettext`. After adding
strings run `python scripts/i18n_tools.py` and update the English catalogue.

## Commit and pull request

- Present-tense, imperative commit subjects; explain the reasoning in the
  body when it is not obvious.
- One logical change per pull request. A 2000-line refactor mixed with a bug
  fix will be sent back.
- In the description: what changed, why, how you tested it, and anything a
  reviewer should look at sceptically.
- If the change affects behaviour users can see, update `CHANGELOG.md` under
  *Unreleased*.

## What is out of scope

These have been considered and deliberately excluded. A pull request adding
one will be declined regardless of quality:

- Fiscal-device, e-invoice or tax-authority integration
- Payment processing or card handling of any kind
- Payroll calculation
- Multi-tenancy or a branch/organisation hierarchy
- Telemetry, analytics or crash reporting
- Any feature that takes an automated decision about a person
- Any default account or default credential
- External CDN or web-font dependencies (assets stay local, so the CSP stays
  strict)

## Reporting a bug

Include: what you did, what you expected, what happened, the version or
commit, your Python version and operating system, the database engine, and
the relevant log excerpt **with personal data removed**.
