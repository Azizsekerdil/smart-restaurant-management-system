# AI Transparency

What the AI features in this system actually do, what they cannot do, where a
human stays in charge, and how to turn all of it off.

Technical setup instructions are in
[`AI_INTEGRATION.md`](AI_INTEGRATION.md). This page is about behaviour,
limits and accountability.

---

## 1. The AI layer is optional

Every feature in this product works with the AI layer switched off. With no
API key configured and no local model running, the assistant reports
`NOT_CONFIGURED`, the analysis screens show that they need a model, and
**nothing else changes**. Point of sale, kitchen display, stock, reservations,
staff, reporting and backups do not depend on it.

There is no telemetry and no vendor call of any kind other than the provider
you deliberately enable.

## 2. Where AI is used

| Feature | What the model does | What it does **not** do |
|---|---|---|
| Assistant chat | Answers questions about your data in natural language | Change any record |
| Sales / cost analysis | Writes the narrative around figures computed in Python | Compute the figures |
| Menu profitability commentary | Suggests which items to examine | Change prices |
| Demand estimate commentary | Describes a trend derived from your own history | Place a purchase order |
| Review summarisation | Groups and summarises customer reviews | Reply to a customer |
| Waste and void commentary | Points at patterns worth checking | Accuse anyone of anything |
| Developer console | Proposes a code change as a reviewable diff | Apply it without explicit approval |

**Every number the model talks about is calculated deterministically in
Python before the prompt is built.** The model interprets figures; it does not
produce them. If the model is removed, the numbers remain.

## 3. Nothing is decided automatically

No feature in this system takes an automated decision about a person, and
none produces a legal or similarly significant effect.

- The assistant emits **text**. It has no write access to orders, stock,
  customers, staff records, prices or settings.
- Voids, refunds, discounts, price overrides and reopening a closed check
  require the acting user's own permission or a manager's username and PIN,
  recorded as a `ManagerApproval` in the audit log.
- No customer is scored, ranked for eligibility, or profiled for a decision.
  Loyalty tiers are arithmetic on spend, not a model output.
- No employee is scored, disciplined or scheduled by a model. Performance
  screens display recorded facts.
- Developer-console proposals are shown as a diff, need a human approval,
  write to a separate Git branch, take an automatic restore point first, and
  are rejected if the tests were run and failed.

## 4. Providers, and the local-only option

| Provider | Runs where | Default |
|---|---|---|
| LM Studio | Your machine | enabled if reachable |
| Ollama | Your machine | disabled |
| NVIDIA NIM | Cloud | disabled |
| OpenAI-compatible | Cloud | disabled |
| Anthropic | Cloud | disabled |
| Google Gemini | Cloud | disabled |
| OpenRouter | Cloud | disabled |

Routing follows `AI_ROUTING_POLICY`:

- `local_only` — **nothing ever leaves the machine.** The strongest setting.
- `local_first` (default) — try local, fall back to cloud, except for
  sensitive tasks.
- `cloud_first`, `cloud_only` — for installations that have accepted cloud
  processing.

Regardless of policy, with `AI_SENSITIVE_LOCAL_ONLY=True` (the default) any
task carrying customer or staff data goes to a local model or is refused. It
is never sent to a cloud provider.

## 5. What is sent, and what is stripped

Before any prompt is sent, `AI_MASK_PII` (default `True`) removes e-mail
addresses, phone numbers, national identity numbers, card numbers and IBANs —
and the masked form is what gets stored in the conversation history as well,
so the raw values are not retained by the log either.

**Masking is pattern-based and imperfect.** A free-text note that names a
person in prose will not be caught by a regular expression. This is why
`AI_SENSITIVE_LOCAL_ONLY` exists and why it defaults to on.

Prompts also instruct the model not to repeat personal data in its answer.
That is a mitigation, not a guarantee — an instruction to a model is not an
access control.

## 6. Keys and provider terms

- API keys live only in `.env` or your secret manager. They are **never**
  written to the database, never returned by any endpoint, never included in
  logs (a logging filter masks them), and never passed into subprocess
  environments.
- The interface shows only the provider name, its status, and the last four
  characters of a configured key.
- *Test connection* runs only when a person clicks it.
- Each cloud provider's **data region, retention period and training-use
  terms start as `REVIEW_REQUIRED`.** The application deliberately does not
  claim to know a vendor's terms. Read the provider's own documentation, then
  record what you verified — with the source and the date — in the `*_GOV_*`
  environment variables. Until you do, the provider screen keeps warning you.

## 7. Cost and failure behaviour

- Daily and monthly USD budgets (`AI_DAILY_BUDGET_USD`,
  `AI_MONTHLY_BUDGET_USD`) block further cloud calls when exceeded. Local
  models are free and unaffected.
- Cost is an **estimate** from the per-million-token prices in settings.
  Those prices go stale; reconcile against the provider's invoice.
- A circuit breaker disables a provider that fails repeatedly, then retries
  after a cooldown.
- Every call is logged with its provider, model, token counts and estimated
  cost, viewable on the AI usage screen.
- When no provider is available the user gets a plain explanation, not a
  fabricated answer.

## 8. Known weaknesses — read before trusting an answer

- **Language models can be confidently wrong.** They can misread a table,
  invent a causal story, or mis-state a trend. Treat every answer as a
  starting point for your own check.
- Smaller local models generally produce weaker analysis than large cloud
  models. That is the price of the data never leaving the machine.
- The model sees only what the query supplies. Absence of evidence in an
  answer is not evidence of absence in your business.
- Forecasts use the installation's own history only — no weather, no local
  events, no holiday calendar — and carry no calibrated confidence interval.
- Output is **decision support, not advice**. It is not accounting, tax,
  legal, employment, dietary or medical advice, and it is not a basis for a
  food-safety decision. Allergen questions go to the kitchen, not the model.

## 9. Turning it off completely

```dotenv
LMSTUDIO_ENABLED=False
OLLAMA_ENABLED=False
NVIDIA_ENABLED=False
OPENAI_ENABLED=False
ANTHROPIC_ENABLED=False
GEMINI_ENABLED=False
OPENROUTER_ENABLED=False
```

Or remove the `ai.use` permission from every role. The AI screens disappear
from the navigation and nothing else is affected.

Under the automated test suite all providers are force-disabled, so the tests
can never reach a real model.
