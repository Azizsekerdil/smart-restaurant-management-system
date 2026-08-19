# Known Limitations

This page is written to be useful rather than reassuring. Everything below is
a real constraint of the current code. If a limitation you hit is not listed
here, that is a documentation bug worth reporting.

Planned work is in [`../ROADMAP.md`](../ROADMAP.md). A limitation appearing
here does **not** imply it is scheduled.

---

## 1. Deployment and scale

| Limitation | What it means in practice | What to do |
|---|---|---|
| **SQLite is the default database** | Concurrent writes serialise. With several POS terminals plus a kitchen display hammering the same file you will see lock waits and occasional timeouts. | Switch to PostgreSQL (`DB_ENGINE=postgres`) for anything beyond one or two terminals. |
| **Rate limiting is per process** | `RateLimitMiddleware` and the PIN lockout counters use the Django cache, which defaults to in-process memory. Behind several workers, each worker counts separately, so the effective limit is multiplied by the worker count. | Configure a shared cache (Redis or Memcached) before running multiple workers, and keep a reverse proxy rate limit in front. |
| **WebSockets use an in-memory channel layer** | The kitchen display only receives events produced by the same process. | Set `CHANNEL_LAYER=redis` and install `channels-redis` for multi-process or multi-server deployments. |
| **No multi-tenancy** | One installation serves one business. There is no branch, tenant or organisation boundary in the data model. | Run one installation per site. |
| **Backups are local by default** | A backup on the same disk does not survive a disk failure. | Point `BACKUP_DIR` at a second disk or a network share, and **test a restore** — an untested backup is a hope, not a backup. |
| **No first-class HA or migration story** | There is no blue/green deployment, no zero-downtime migration tooling, no read replica support. | Schedule maintenance windows. |

## 2. Security boundaries

| Limitation | What it means | Mitigation |
|---|---|---|
| **The Content Security Policy allows `unsafe-inline` and `unsafe-eval`** | Alpine.js requires them. If an XSS hole ever existed, CSP would not fully contain it. | All assets are bundled locally, so `default-src 'self'` still blocks exfiltration to another origin. A nonce-based CSP would require replacing the front-end library. |
| **`CSRF_COOKIE_HTTPONLY` is `False`** | Deliberate: the front end reads the token from the cookie. It slightly widens the impact of an XSS hole. | Keep the CSP strict; treat any XSS report as high severity. |
| **The developer console can execute commands** | `DEVCENTER_ENABLED` / `DEVCENTER_TERMINAL_ENABLED` run allow-listed programs in a path-jailed sandbox with an approval gate. It is still, by design, code execution. | **Off by default.** Do not enable it on a shared or production host. It is force-disabled in the packaged executable. |
| **PIN switching is a convenience, not an authentication factor** | A PIN is 4–8 digits. Locking (5 attempts, 15-minute lockout on both the username and the source address) is what makes it safe; the entropy alone is not. | It requires an existing authenticated session, targets only accounts with `pos.use`, and refuses accounts owing a password change. Do not raise `pin_security.MAX_FAILURES`. |
| **No 2FA / MFA** | Passwords and session cookies are the only account factors. | Put the application behind an authenticating reverse proxy or VPN if you need MFA today. |
| **No end-to-end encryption at rest** | The database file and backups are stored unencrypted unless the underlying volume is encrypted. | Use full-disk encryption; restrict file permissions; keep `BACKUP_ALLOW_SECRETS=False`. |
| **Session revocation is coarse** | There is no "sign out all my other devices" screen. Deactivating the account is the blunt instrument that works. | Deactivate then reactivate the user to invalidate sessions. |

## 3. Privacy and data protection

| Limitation | What it means |
|---|---|
| **Retention periods default to off** | `RETENTION_*` is `0` out of the box: nothing is redacted automatically. How long personal data is kept is a decision for the business and its data-protection adviser, and the software refuses to decide it for you. Schedule `manage.py purge_expired_logs --apply` once you have decided. |
| **`docs/ROPA_HAZIRLIK.md` is preparation, not a filing** | It is a template with bracketed placeholders. It is not a registered ROPA, not a VERBİS registration, and not legal advice. |
| **`legal_basis` values in `docs/data_inventory.json` are candidates** | They are drafting aids. The final legal classification is a human decision by the data controller. |
| **Allergy notes are stored as free text** | The presence of a note is visible to all staff for food safety; the text is restricted to `customer.pii` holders. The software does not validate, normalise or verify allergen content, and it must never be the sole basis of a food-safety decision. |
| **Masking is not anonymisation** | `masked_phone` and `masked_email` hide characters from a screen. They are a display control, not a de-identification technique — the full value is still in the database. Use `Customer.anonymize()` for an erasure request. |
| **Audit logs contain personal data** | IP address, user agent and a username snapshot are retained deliberately for accountability, and the log is append-only, so entries cannot be edited. `purge_expired_logs` redacts the fields rather than deleting rows. |

## 4. AI features

| Limitation | What it means |
|---|---|
| **Language models can be confidently wrong** | Narrative interpretation comes from a model. Every figure it discusses is computed deterministically in Python first; the model explains numbers, it does not produce them. Verify before acting. |
| **No automated decisions about people** | The assistant never voids, refunds, discounts, schedules, disciplines or scores anyone. It emits text. Every consequential action needs a human with the right permission, and sensitive POS actions additionally need a manager PIN. |
| **PII masking is pattern-based** | `AI_MASK_PII` strips e-mail addresses, phone numbers, national ID numbers, card numbers and IBANs by regular expression. A free-text note naming a person will not be caught. Keep `AI_SENSITIVE_LOCAL_ONLY=True` for anything involving customer or staff data. |
| **Cloud provider terms are unverified by default** | Region, retention and training-use fields start as `REVIEW_REQUIRED`. The application will not assert a provider's terms for you — you record what you verified, with a source and a date, in the `*_GOV_*` variables. |
| **Cost estimates are estimates** | Budget tracking uses the per-million-token prices in `settings.AI_PROVIDERS`. Those prices go stale. Reconcile against your provider's invoice. |
| **Local model quality varies widely** | A small local model may produce a weaker analysis than a cloud model. That is the trade for data never leaving the machine. |

## 5. Business scope

- **No fiscal integration**: no fiscal printer, no e-invoice or e-archive
  provider, no tax-authority reporting. Output is not a statutory document.
- **No payment processing**: card payments are *recorded* after the fact.
  There is no acquirer integration, no terminal driver, no PCI-DSS scope.
- **No payroll**: hourly rate and monthly salary exist for labour-cost
  reporting only. No payslip, tax or social-security calculation happens.
- **No delivery-platform integrations**: delivery orders are entered by hand.
- **Forecasting is simple**: demand estimates are derived from the
  installation's own history. There is no external signal — no weather, no
  local events, no holidays calendar — and no confidence interval you should
  bet the purchase order on.

## 6. Internationalisation

- Two languages ship: Turkish and English.
- **The English catalogue is incomplete in places.** Some screen titles,
  seeded demo strings and enum labels still render in Turkish while the
  interface language is English. This is cosmetic, not functional.
- Currency, tax rate and service-charge behaviour are configurable, but the
  tax model is a single rate per product. Multi-rate or compound tax regimes
  are not modelled.
- Dates and numbers follow the active locale; there is no per-user override
  separate from the language choice.

## 7. Testing and quality

- The automated suite covers the domain logic, permissions, privacy masking
  and the security paths. Run `python scripts/project_metrics.py` for the
  current count — no number is written by hand into the documentation.
- **There is no browser-driven end-to-end suite in CI.** Playwright is used
  only to capture screenshots. Front-end behaviour is not automatically
  regression-tested.
- **There has been no third-party security audit** and no independent
  production pilot.
- Dependency scanning is a snapshot in time. A clean scan today says nothing
  about tomorrow; re-run `pip-audit` after every upgrade.
- Load and soak testing has not been performed. The scale guidance above is
  reasoned from the architecture, not measured.

## 8. Packaging

- The single-file Windows build is produced with PyInstaller. Antivirus
  software sometimes flags unsigned PyInstaller executables; the build is not
  code-signed.
- In the packaged build the developer console is force-disabled and the
  application directory is read-only, so data lives beside the executable.
- macOS and Linux are supported as source installs only; there is no bundled
  installer for them.
