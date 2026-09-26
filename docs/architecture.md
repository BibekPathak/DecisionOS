# Architecture

DecisionOS is a probabilistic decision runtime. It turns an application's
structured context into a **typed, policy-controlled decision**, records it,
and later measures how well its predictions matched observed outcomes.

## The pipeline

```text
Context
   │
   ▼
Typed Decision Request          validated by Pydantic
   │
   ▼
Probabilistic Provider          Jev / Mock
   │
   ▼
Raw Decision (untrusted)        what the provider returned, verbatim
   │
   ▼  trust boundary: validate + normalize
Validated Decision              probabilities, confidence, risk, action
   │
   ▼
Deterministic Policy Engine     HARD_DENY > HUMAN_REVIEW > MODEL
   │
   ▼
Final Decision                  persisted with a full audit trail
   │
   ▼
Observed Outcome                recorded by the caller
   │
   ▼
Calibration                     Brier, ECE, reliability buckets
```

The rule that shapes everything:

> **The AI provider never directly executes actions.**

A provider produces probabilistic intelligence. The policy engine determines
what is actually permitted. The application executes (or does not execute).

## Components

### Engine (`decisionos.engine`)

Orchestrates evaluation and owns the decision lifecycle.

- `DecisionEvaluator.evaluate()` performs: context-size validation → schema
  resolution → provider resolution → provider call → trust-boundary validation
  → signal derivation → optional policy hand-off.
- `DecisionLifecycle` is the state machine:

```text
CREATED → EVALUATING → EVALUATED → POLICY_EVALUATED
        → ACTION_SELECTED → EXECUTED → OUTCOME_RECORDED
```

Failure states (`FAILED`, `EXPIRED`, `CANCELLED`) are reachable from any active
state and are terminal. Every transition is an audit event.

### Models (`decisionos.models`)

Strongly typed, validated domain objects. `RawDecision` is deliberately a
different type from `Decision` so nothing downstream can consume unvalidated
provider output. Validation covers:

- `0 ≤ confidence ≤ 1`, `0 ≤ risk ≤ 1`
- every probability in `[0, 1]`
- the distribution sums to ≈ 1
- the selected action belongs to the schema

### Providers (`decisionos.providers`)

`DecisionProvider` is a `Protocol`. Implementations:

- `MockProvider` — deterministic fixtures; mandatory for credential-free
  operation and testing.
- `JevProvider` — the primary provider, backed by the TypeSafe System One API.
  All Jev-specific behaviour lives in `providers/jev.py`.
- `ProviderRegistry` resolves providers by name and **always falls back to
  `mock`** when a provider is unknown or unconfigured.

### Policy engine (`decisionos.policies`)

Deterministic YAML rules over the decision context and derived fields.
Precedence is strict and resolved by required action:

```text
HARD_DENY  >  REQUIRED_HUMAN_REVIEW  >  MODEL_DECISION
```

If precedence were flattened, a probabilistic output could bypass a security
rule. It never can. Derived fields (`action`, `confidence`, `risk`) are
authoritative and cannot be spoofed by context.

### Storage (`decisionos.storage`)

- PostgreSQL via SQLAlchemy 2.0 async; eight tables covering schemas, decisions,
  probabilities, policies, policy evaluations, events, outcomes, and provider
  requests.
- Repositories translate between ORM rows and domain models.
- Redis coordinates idempotency (reserve/complete), short-lived caching, and
  rate limiting.

### Calibration (`decisionos.calibration`)

Pure functions over `(predicted, outcome)` pairs: Brier score, expected
calibration error, and reliability buckets. A `CalibrationDataSource` supplies
samples; the database source joins decisions with recorded outcomes, so only
observed decisions contribute.

### API (`apps.api`)

A thin FastAPI layer. Routes depend on a service layer that composes the engine,
policy engine, and repositories. The API adds authentication, idempotency, rate
limiting, request validation, and structured error mapping.

### SDK (`decisionos.sdk`)

`AsyncDecisionOS` and a synchronous `DecisionOS` wrapper over the HTTP API, with
typed results and an error hierarchy mapped to status codes.

### Observability (`decisionos.observability`)

OpenTelemetry tracing, Prometheus metrics, structured JSON logging with request
context, and recursive secret redaction.

## Trust boundaries

1. **Request boundary** — `DecisionRequest` validates shape and context size.
2. **Provider boundary** — `Decision.from_raw()` re-validates all provider
   output. Malformed output raises `ProviderOutputError` and produces no
   decision.
3. **Policy boundary** — the policy engine may only force a *safer* action,
   never a less safe one.
4. **Log boundary** — secrets never reach a log sink.

## What v1 deliberately does not do

- No autonomous model retraining. Outcomes are stored so the data
  infrastructure for future evaluation exists.
- No execution of tools, shell commands, or infrastructure operations.
- No Kubernetes. Docker Compose is the deployment target.
- No fabricated calibration numbers.
