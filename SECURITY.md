# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| `1.4.x` (current `main`) | Yes |
| Anything older | No |

This is a single-maintainer project. Fixes land on `main`; there are no
long-term-support branches and no backports.

## Reporting a vulnerability

**Please do not open a public issue, pull request or discussion for a
security problem, and please do not publish it before it is fixed.** A public
report gives away every unpatched installation at once.

Use one of these instead:

1. **GitHub private vulnerability reporting** — on the repository's
   *Security* tab, choose *Report a vulnerability*. This is the preferred
   route: the report, the discussion and the advisory stay in one place.
2. **A private message to the maintainer**, using the contact details on the
   repository owner's GitHub profile, if private reporting is not available
   to you.

## What to include

The more of this you can give, the faster a fix arrives:

- the version, commit or release you tested;
- how it was deployed — SQLite or PostgreSQL, single machine or server,
  whether it was reachable from a network;
- clear reproduction steps, ideally the shortest sequence that shows it;
- what an attacker gains: data read, data changed, privileges gained,
  availability lost;
- a proof of concept, log excerpt or screenshot **with personal data and
  credentials removed**.

Please do not send real customer data, real staff data, or a real API key.
Redact it or describe it.

## What to expect

| Stage | Target |
|---|---|
| Acknowledgement that your report arrived | within 5 working days |
| Initial assessment and severity judgement | within 10 working days |
| Fix or documented mitigation for a confirmed high-severity issue | within 30 days where practicable |
| Public advisory | once a fix exists, or by agreement with you |

These are targets for a volunteer project, not a contractual commitment. If a
target is going to slip you will be told, rather than left waiting.

You will be credited in the advisory and in the changelog unless you ask not
to be. There is no bug-bounty programme and no monetary reward.

## Scope

**In scope** — the code in this repository: authentication and session
handling, the permission model, the manager-approval and PIN paths, data
masking and export, backup and restore, the developer console and its command
sandbox, dependency handling, and the release scripts.

**Out of scope**

- Findings that require an already-compromised host or an already-privileged
  account, unless they cross a documented privilege boundary.
- Anything already written down in
  [`docs/known-limitations.md`](docs/known-limitations.md). Please read it
  first: it states plainly what this software does not defend against.
- Missing hardening in a deployment you configured yourself — no HTTPS, an
  instance published to the internet, an installation still holding demo
  data, a disabled rate limiter. The checklist is in
  [`docs/hardening-checklist.tr.md`](docs/hardening-checklist.tr.md).
- Vulnerabilities in third-party dependencies: report those upstream. Asking
  here for a dependency bump is a normal issue, not a security report.
- Automated scanner output with no demonstrated impact.

## Safe harbour

Research carried out in good faith against **your own installation** is
welcome. Please do not test against anyone else's system, do not access,
modify or retain data that is not yours, do not degrade availability, and
allow a reasonable window for a fix before publishing.

## Two notes for operators

- The documented `admin/admin` bootstrap pair is restricted to an empty
  installation, local-device sign-in, and mandatory immediate password change.
- `DEVCENTER_ENABLED` executes commands on the host machine. It is **off by
  default**. Leave it off anywhere other than your own development machine.
