# Privacy

This document describes how the **software** handles personal data. It is not
a privacy notice for any particular restaurant, and it is not legal advice.

**You are the data controller.** This project is self-hosted: the maintainer
operates nothing, receives nothing and can see nothing. Whoever installs and
runs it decides what is collected, why, and for how long, and is responsible
for meeting KVKK, GDPR or whichever regime applies.

---

## 1. The software phones no one home

There is **no telemetry, no analytics, no crash reporting, no licence check
and no update ping**. The application makes exactly one class of outbound
network request: a call to an AI provider you configured and enabled. With
`AI_ROUTING_POLICY=local_only`, or with no provider configured, nothing
leaves the machine at all.

All front-end assets (Bootstrap, Alpine, HTMX, Chart.js, icons, fonts) are
served from the installation. No CDN, no web font fetch, no tracking pixel —
which is also why the Content Security Policy can be as strict as it is.

## 2. What data the software stores

| Category | Fields | Subject |
|---|---|---|
| Staff account | Name, username, e-mail, phone, employee code, role, avatar, password hash, PIN hash | Employee |
| Employment | Hire date, hourly rate, monthly salary, shifts, attendance, leave, tasks, performance notes | Employee |
| Customer | Name, phone, e-mail, address, birth date, company, preferences, **allergy notes**, internal notes, loyalty points, visit history | Customer |
| Reservation | Guest name, phone, e-mail, party size, special requests, **allergy notes**, occasion | Guest |
| Order | Items, totals, payments, the staff member who acted, optional customer link | Customer / employee |
| Consent | Consent type, granted/withdrawn, timestamp, source, IP address | Customer |
| Audit log | Action, timestamp, username snapshot, object, description, changes, IP address, user agent | User |
| AI usage | Prompt metadata, token counts, cost estimate, and conversation content **after PII masking** | User |

A field-level inventory, kept in sync with the models by a CI check, is in
[`docs/data_inventory.json`](docs/data_inventory.json).

Allergy notes are **health data** — a special category under KVKK Article 6
and GDPR Article 9. They are handled accordingly: see section 4.

## 3. What the software does not store

- No card numbers, no PAN, no CVV, no bank credentials. Payments are recorded
  as a method and an amount.
- No national identity numbers as a modelled field.
- No biometrics, no geolocation tracking, no device fingerprinting.
- No plaintext password or PIN, anywhere, ever — only salted hashes.
- No third-party cookies. The only cookies are the session cookie, the CSRF
  token and a language preference.

## 4. Access controls over personal data

- Contact details are masked (`0000***42`, `d***@example.invalid`) for every
  role without the `customer.pii` permission — in the interface, in the
  search endpoint and in the REST API alike.
- **Allergy notes**: the *existence* of a note is always visible, because a
  server needs to know to ask the kitchen. The *text* is restricted to
  `customer.pii` holders. If your front-of-house staff must read the detail
  directly, grant that permission explicitly per user — the RBAC layer
  supports per-user additions — and record why.
- Salary and employment data require staff permissions.
- Exports (`report.export`) and backup downloads (`backup.download`) are
  separate permissions from viewing, because a file leaves the building in a
  way a screen does not.
- Every access-control decision that matters is written to an append-only
  audit log.

## 5. Consent

`ConsentRecord` stores one row per purpose per customer: the type, whether it
was granted, when, from where, and the source. Withdrawal is recorded as a
new state rather than by deleting the evidence, so you can still show what
was true at a given time.

The software records consent. It does not decide whether you needed it.

## 6. Retention and erasure

- **Retention is off by default.** Every `RETENTION_*` variable starts at
  `0`. Choosing a period is a decision for the business and its
  data-protection adviser; the software will not invent one.
- `manage.py purge_expired_logs` redacts personal fields whose period has
  passed — audit IP and user agent, consent IP, guest details on concluded
  reservations and closed waiting-list entries. It **previews by default**
  and needs `--apply` to write. Each run leaves an audit record.
- Erasure requests: `Customer.anonymize()` irreversibly clears name, phone,
  e-mail, address, birth date, preferences and allergy notes, and removes
  consent records. **Order history is not deleted** — it is re-pointed at an
  anonymous record, so financial and tax totals stay intact while the person
  becomes unidentifiable. It requires the `data.erase` permission and leaves
  a critical-severity audit entry.
- Redaction is not the same as deletion, and masking is not anonymisation.
  Both are stated plainly in [`docs/known-limitations.md`](docs/known-limitations.md).

## 7. Data given to AI providers

- With no key configured, or `local_only` routing, no data leaves the machine.
- With `AI_MASK_PII=True` (the default), e-mail addresses, phone numbers,
  national ID numbers, card numbers and IBANs are stripped from the prompt
  before it is sent — and the masked form is what gets stored in the
  conversation history too.
- With `AI_SENSITIVE_LOCAL_ONLY=True` (the default), any task carrying
  customer or staff data is routed to a local model or refused, never to a
  cloud provider.
- Masking is pattern-based and therefore imperfect. A free-text note that
  names someone will not be caught by a regular expression.
- Each cloud provider's data region, retention and training-use terms start
  as `REVIEW_REQUIRED`. Verify them from the provider's own documentation,
  and record the source and date in the `*_GOV_*` environment variables. The
  software will not assert a provider's terms on your behalf.

If you enable a cloud provider, that provider becomes a processor in your
processing chain. That relationship — the contract, the transfer basis, the
notice to data subjects — is yours to establish.

## 8. Backups

A backup archive contains customer and staff personal data. Treat it as you
would the database:

- `BACKUP_ALLOW_SECRETS` is `False` by default, so `.env` (and therefore your
  API keys) is excluded — backups travel by e-mail and cloud drive more often
  than anyone admits.
- Downloading a backup is a distinct permission (`backup.download`).
- Backup directories are excluded from version control.
- Store backups encrypted and restrict who can read them.

## 9. Data subject requests

The software gives you the tools; the process is yours.

| Right | Tool |
|---|---|
| Access / portability | Customer detail screen, report exports (Excel, PDF, CSV) |
| Rectification | Customer and staff edit screens; changes are audited |
| Erasure | `Customer.anonymize()` with `data.erase` |
| Restriction | Deactivate the record (`is_active`) |
| Objection to marketing | Withdraw the marketing `ConsentRecord` |
| Evidence of handling | The append-only audit log |

## 10. Demo data

Everything produced by `seed_demo` is synthetic. Names are invented; phone
numbers start with `0000` and are undialable in any country; e-mail addresses
use the reserved `.invalid` domain and can never resolve. Screenshots in this
repository were captured from that synthetic data using an account that is
explicitly denied the `customer.pii` permission, so masking is in force in
every image.

## 11. Reporting a privacy problem

If you find a way to read personal data without the right permission, treat
it as a security vulnerability and follow [`SECURITY.md`](SECURITY.md). Please
do not include real personal data in the report.
