# Design decisions

A short record of the choices that shape DecisionOS and why they were made.

## 1. The provider never executes actions

**Decision.** A provider returns a probability distribution. The policy engine
and the calling application decide what happens.

**Why.** Executing from model output couples probabilistic judgment directly to
side effects. Separating "what is likely" from "what is permitted" lets security
rules stay deterministic and auditable.

## 2. `RawDecision` and `Decision` are distinct types

**Decision.** Provider output is a `RawDecision`; it becomes a `Decision` only
after passing `Decision.from_raw()`.

**Why.** The trust boundary should be a type, not a convention. A function that
accepts a `Decision` cannot accidentally receive unvalidated output.

## 3. Policy always outranks the model

**Decision.** Precedence is `HARD_DENY > REQUIRED_HUMAN_REVIEW >
MODEL_DECISION`. A model can never downgrade a required action.

**Why.** Probabilistic output must never bypass deterministic security rules.
A rule requiring `deny` wins even when the model is 99% confident in `allow`.

## 4. Risk is derived, not invented

**Decision.** When a provider supplies no risk, DecisionOS computes
`1 − P[selected action]`.

**Why.** Provider APIs often return confidence but not risk. Rather than
fabricating a number or leaving it null, we derive risk from the model's own
distribution — the same uncertainty, computed locally and documented.

## 5. Schemas and policies are immutable and versioned

**Decision.** A schema or policy version is never mutated. A change creates a
new version.

**Why.** Decisions reference specific versions. Immutability keeps historical
decisions reproducible and audits meaningful.

## 6. The mock provider is mandatory

**Decision.** `MockProvider` ships as first-class infrastructure, and the
registry falls back to it when Jev is unconfigured or unreachable.

**Why.** Local development, tests, demos, and the dashboard must all run with no
external credentials. A product that requires a paid API key to try is a product
nobody tries.

## 7. Jev-specific code lives only in `providers/jev.py`

**Decision.** The rest of DecisionOS depends solely on the `DecisionProvider`
interface.

**Why.** Provider-specific logic leaking into the engine or API makes providers
hard to add and reason about. The verified TypeSafe API shape (endpoint,
request, response, errors) is confined to one module.

## 8. Context is typed but bounded

**Decision.** Decision context is a JSON object with a serialized size limit
(default 64 KiB, per-request override).

**Why.** Context is the payload sent to a provider. Bounding it protects latency
and cost and prevents accidental data exfiltration.

## 9. Calibration uses only observed outcomes

**Decision.** A decision contributes to calibration only after an outcome is
recorded. Empty or insufficient samples report `null`.

**Why.** Calibration without ground truth is meaningless. Reporting fabricated
or placeholder numbers would undermine the entire feature.

## 10. Redis for coordination, PostgreSQL for truth

**Decision.** Redis handles idempotency keys, short-lived caching, and rate
limiting. Durable state lives in PostgreSQL.

**Why.** The two have different guarantees. Idempotency reservations are
short-lived and cross-process; decisions, audit events, and outcomes must
survive restarts and be queryable.

## 11. The API is thin

**Decision.** FastAPI routes depend on a service layer; no domain logic lives in
route handlers.

**Why.** The engine, policy engine, SDK, and CLI all share the same core. A thin
API keeps that core the single source of truth.

## 12. Structured logging with redaction at the edge

**Decision.** Logs are JSON; a structlog processor redacts secrets (keys,
authorization headers, sensitive values) before rendering.

**Why.** Request context is often sensitive. Redaction at the logging boundary
means a developer cannot accidentally log a credential.

## 13. Docker Compose, not Kubernetes

**Decision.** v1 deploys with Docker Compose.

**Why.** The project is a small but legitimate piece of infrastructure. Compose
is enough to run and evaluate it; Kubernetes would be premature.
