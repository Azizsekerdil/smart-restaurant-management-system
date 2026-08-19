# Smart Restaurant Management System

An open-source, self-hosted restaurant management system built with Django.
It brings the point of sale, the kitchen display, recipe-based stock control,
reservations, customers, staff scheduling and financial reporting into one
application and one database.

Turkish documentation: **[README.tr.md](README.tr.md)**

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Django](https://img.shields.io/badge/django-5.2-092E20)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Contents

- [What it does](#what-it-does)
- [What it does not do](#what-it-does-not-do)
- [Maturity and status](#maturity-and-status)
- [Install](#install)
- [Try it with demo data](#try-it-with-demo-data)
- [First account — there are no default credentials](#first-account--there-are-no-default-credentials)
- [Configuration and environment variables](#configuration-and-environment-variables)
- [AI providers, and the local-only option](#ai-providers-and-the-local-only-option)
- [Privacy and the limits of automation](#privacy-and-the-limits-of-automation)
- [Financial, legal and health claims — read this](#financial-legal-and-health-claims--read-this)
- [Screenshots and presentation](#screenshots-and-presentation)
- [Running the tests](#running-the-tests)
- [Project numbers](#project-numbers)
- [License and third-party notices](#license-and-third-party-notices)
- [Reporting a vulnerability](#reporting-a-vulnerability)
- [Known limitations and roadmap](#known-limitations-and-roadmap)

---

## What it does

| Area | Capability |
|---|---|
| Point of sale | Touch order entry, split and merge checks, multiple payment methods, coupons, discounts, voids and refunds — each sensitive action gated by permission or manager approval |
| Kitchen display | Live ticket flow over WebSockets, per-station routing, elapsed-time warnings |
| Stock and recipes | Ingredients, recipes, automatic depletion when an order is sent to the kitchen, stock counts, waste records, purchase orders and suppliers |
| Floor | Table map, areas, table joins, reservations and a waiting list, QR menu |
| Customers | Customer records, loyalty points and tiers, segments, campaigns, consent records, reviews |
| Staff | Employees, shifts, shift assignments, attendance, leave and tasks |
| Reporting | Sales, profitability, day-end closing, expenses, void analysis, statistics with period comparison, Excel/PDF/CSV export |
| Backups | Consistent snapshot of the database and media, integrity hash, guarded restore |
| Training | An in-app guide whose lessons are filtered by the reader's role |
| AI assistant | Optional. Answers questions about *your* data — local model or cloud provider, your choice |
| Security | Role-based permissions (62 permission codes across 12 roles), immutable audit log, manager PIN approval for sensitive POS actions |

It runs on SQLite with no external services, or on PostgreSQL with Redis and
Celery for a multi-terminal deployment. It works with no internet connection.

## What it does not do

Being explicit is more useful than a feature list:

- **It is not certified fiscal software.** It does not talk to a fiscal
  printer, a tax authority, an e-invoice/e-archive provider, or a payment
  terminal. Payments are *recorded*, not *processed* — there is no card
  acquiring, no PCI-DSS scope, and no money movement of any kind.
- **It is not accounting software.** The expense and profitability screens
  are management reporting, not double-entry bookkeeping, and they are not a
  substitute for your accountant or for statutory records.
- **It does not do payroll.** Hourly rates and monthly salary are stored as
  reference figures for labour-cost reporting; no payslip, tax or social
  security calculation is performed.
- **It has no multi-tenant / multi-branch model.** One installation serves
  one business. Several branches means several installations.
- **It has no built-in online-ordering marketplace integration** (delivery
  platforms, aggregators). Delivery orders are entered in the application.
- **It does not provide medical, dietary, legal or financial advice.** See
  [the claims section](#financial-legal-and-health-claims--read-this).
- **It is not hardened for hostile networks out of the box.** The intended
  deployment is a trusted local network or a single machine. Exposing it to
  the public internet requires HTTPS, a reverse proxy, a shared cache for
  rate limiting, and a review of `docs/known-limitations.md` first.

## Maturity and status

This is a **single-maintainer project**, published so that others can read,
run and audit it. It is feature-complete for the workflows listed above and
covered by an automated test suite, but it has **not** been through a
third-party security audit or an independent production pilot. There is no
support contract and no service-level commitment.

Treat it as: *ready to evaluate and to run at your own risk*, not as
*shrink-wrapped commercial software*.

## Install

Requirements: Python 3.11 or newer (3.12 recommended), about 500 MB of disk.

```bash
git clone <your fork or clone url>
cd smart-restaurant-management-system

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env          # Windows: Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000>. Windows users who prefer a guided setup can run
`setup_windows.ps1`; see [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md).
Docker and PostgreSQL instructions are in [README.tr.md](README.tr.md) and
`docker-compose.yml`.

## Try it with demo data

```bash
python manage.py seed_demo            # 30 days of history
python manage.py seed_demo --days 90
python manage.py seed_demo --reset    # wipe demo data first
```

**All demo data is synthetic.** Names are invented; phone numbers begin with
`0000` and cannot be dialled anywhere; e-mail addresses use the reserved
`.invalid` top-level domain and can never resolve. No record in the demo set
describes a real person, business or transaction.

`seed_demo` generates a **random password for that installation** and prints
it, together with the manager-approval PINs, exactly once. Note it down.
There is no fixed, documented demo password anywhere in this repository.

> Do not expose an installation that still contains demo data to a network.
> Clear it with `--reset` and create your own accounts before going live.

## First account — one-time bootstrap credential

On an empty database, run `python manage.py bootstrap_admin`, then sign in once
from the host computer with `admin` / `admin`. The account is confined to the
password-change flow until a new policy-compliant password is selected.

If an administrator creates a staff account and ticks *must change password*,
that account is locked to the password-change screen: every other page — the
dashboard, customer records, financial reports, exports, backups, AI settings
— returns a redirect (or `403` with code `password_change_required` for API
clients) until a new password is set. This is enforced by middleware on every
request, not by a message on the login page, and it is covered by regression
tests in `tests/test_pin_and_bootstrap_security.py`.

POS PINs are a convenience for shift handover on an already-authenticated
terminal, never a login method: PIN switching requires an existing session,
rejects repeated (`1111`), sequential (`1234`) and common PINs, locks the
account and the source address after 5 failed attempts, and is written to the
audit log without the PIN value.

## Configuration and environment variables

Everything environment-specific comes from `.env`. `.env.example` documents
every variable and **contains no real values** — API-key fields are
deliberately empty.

Frequently used:

| Variable | Meaning |
|---|---|
| `DJANGO_SECRET_KEY` | Required in production. Generate with `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"` |
| `DJANGO_ENV` | `development` \| `production` \| `test` |
| `DJANGO_ALLOWED_HOSTS` | Hostnames the application will answer for |
| `DB_ENGINE` | `sqlite` (default) or `postgres` |
| `AI_ROUTING_POLICY` | `local_only`, `local_first`, `cloud_first`, `cloud_only` |
| `AI_MASK_PII` | Strip e-mail, phone, national ID, card number and IBAN from prompts |
| `AI_SENSITIVE_LOCAL_ONLY` | Never send customer/staff data to a cloud model |
| `DEVCENTER_ENABLED` | Developer console. **Off by default**, and it executes commands — leave it off unless you are developing this project on your own machine |
| `RETENTION_*` | Days after which personal-data fields are redacted; `0` disables |
| `BACKUP_ALLOW_SECRETS` | Whether `.env` is included in backups. Off by default |

Never put a real key in `.env.example`, in a fixture, in a commit message or
in a screenshot. `scripts/secret_scan.py` and the CI workflow check for this.

## AI providers, and the local-only option

The AI layer is **entirely optional**; every other feature works without it.

Supported: LM Studio and Ollama (local), and NVIDIA NIM, OpenAI-compatible
endpoints, Anthropic, Google Gemini and OpenRouter (cloud).

- A provider with no API key is reported as **NOT_CONFIGURED**, is shown as
  disabled in the interface, and **makes no network request at all**.
- The interface shows only the provider name, its status and the last four
  characters of a configured key. Keys are never returned by any endpoint,
  never written to logs (a logging filter masks them), and never passed to
  subprocesses.
- *Test connection* runs only when a person clicks it.
- With `AI_ROUTING_POLICY=local_only` no request ever leaves the machine.
- Cloud providers start with their data-region, retention and
  training-use terms marked `REVIEW_REQUIRED`. The application does **not**
  assert a provider's terms on your behalf; you record what you verified from
  the provider's own documentation in `*_GOV_*` variables.

See [AI_TRANSPARENCY.md](AI_TRANSPARENCY.md) for what the AI features do,
what they cannot do, and where a human decision is required.

## Privacy and the limits of automation

- Contact details are masked for any role without the `customer.pii`
  permission. Allergy notes are treated as **health data**: the presence of a
  note is always visible for food-safety reasons, but the text is shown only
  to `customer.pii` holders — in the UI, in the search endpoint and in the
  REST API alike.
- Consent is recorded per purpose with a timestamp.
- `Customer.anonymize()` irreversibly clears personal fields while keeping
  order history attached to an anonymous record, so financial totals stay
  intact. It requires `data.erase` and leaves a critical audit entry.
- `manage.py purge_expired_logs` redacts personal fields whose retention
  window has passed. It previews by default and needs `--apply` to act.
- Retention periods default to **off**. How long you keep personal data is a
  decision for the business and its data-protection adviser; the software
  does not decide it for you.
- Every action that matters is written to an append-only audit log.
- `docs/ROPA_HAZIRLIK.md` and `docs/data_inventory.json` are **preparation
  material** for a record of processing activities. They are not a filed ROPA
  or VERBİS registration, and they are not legal advice.

**Human approval is required, and not simulated.** Voids, refunds, discounts,
price overrides and reopening a closed check require either the acting user's
own permission or a manager's username and PIN, recorded as a
`ManagerApproval`. The AI assistant never performs any of these actions — it
produces text for a person to read. Nothing in this system takes a decision
about a person automatically.

## Financial, legal and health claims — read this

- Reports, margins, forecasts and AI answers are **decision support, not
  advice**. They can be wrong, and they are only as good as the data entered.
- Nothing here is accounting, tax or legal advice, and no output is suitable
  as a statutory record.
- Allergen and allergy information is entered by staff and displayed as
  entered. **It is not verified by the software and must never be the sole
  basis of a food-safety decision.** Confirm allergens with the kitchen.
- The KVKK/GDPR helpers assist compliance work; they do not establish it, and
  they are not a substitute for your own legal assessment.

## Screenshots and presentation

Application screenshots are in `sunum/screenshots/{tr,en}/`. The bilingual
introduction deck is in `docs/presentation/` as HTML, PPTX and PDF
(`*_PUBLIC.*`).

Both are regenerated from source, not edited by hand:

```bash
# 1. screenshots — against an isolated, synthetic database
RESTAURANT_DATA_DIR=/tmp/demo python manage.py migrate
RESTAURANT_DATA_DIR=/tmp/demo python manage.py seed_demo
RESTAURANT_DATA_DIR=/tmp/demo python manage.py runserver 127.0.0.1:8321   # separate shell
RESTAURANT_DATA_DIR=/tmp/demo python scripts/capture_screenshots.py --base-url http://127.0.0.1:8321

# 2. deck
python scripts/make_presentation.py
```

The capture script creates a single-use account whose password exists only in
memory, **denies it the `customer.pii` permission** so contact details and
allergy notes stay masked, strips password fields from the DOM before each
shot, and disables the account afterwards. The deck's numbers come from
`scripts/project_metrics.py`, which measures the repository; a figure that
cannot be measured is omitted rather than guessed.

## Running the tests

```bash
pip install -r requirements-dev.txt

python -m pytest                                   # full suite
python -m pytest --cov=apps --cov-report=term-missing
python -m pytest tests/test_security.py -v
python -m pytest tests/test_pin_and_bootstrap_security.py -v

ruff check .           # lint
black --check .        # formatting
mypy apps              # type checking
bandit -r apps config  # static security analysis
python scripts/secret_scan.py
```

On Windows, `.\test_all.ps1` runs the whole chain.

## Project numbers

Measured from this repository with `python scripts/project_metrics.py` —
re-run it rather than trusting the table below:

| Measure | Value |
|---|---|
| Automated tests collected | 484 |
| Application modules | 14 |
| User roles | 12 |
| Permission codes | 62 |
| Screens (templates) | 88 |
| Database tables | 72 |
| URL routes | 219 |
| Translated strings (EN catalogue) | 1764 |

## License and third-party notices

Released under the [MIT License](LICENSE).

Third-party components, their licenses, and a statement about what was and
was not derived from other projects are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). A machine-readable software
bill of materials is provided as `sbom.spdx.json` and `sbom.cdx.json`.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Follow
[SECURITY.md](SECURITY.md).

## Known limitations and roadmap

Honest, current limitations — including the ones that would bite you in
production — are listed in
[docs/known-limitations.md](docs/known-limitations.md). Planned work is in
[ROADMAP.md](ROADMAP.md). Anything not in either document is not planned.

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
