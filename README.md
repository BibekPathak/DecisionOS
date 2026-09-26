# DecisionOS

**A probabilistic decision runtime for AI-native software.**

DecisionOS combines probabilistic intelligence with deterministic policy
enforcement and outcome-based calibration.

> Use AI for ambiguous decisions, deterministic policies for control, and
> observed outcomes for calibration.

```text
Application
     │
     ▼
DecisionOS
     │
     ├── Jev            probabilistic intelligence
     ├── Policy Engine  deterministic control
     ├── Decision Store persistence and audit
     └── Calibration    outcome feedback
     │
     ▼
Final Action
```

DecisionOS is infrastructure, not a chatbot and not an LLM wrapper. A provider
returns a **structured probability distribution**; a deterministic policy
engine decides what is actually permitted; observed outcomes feed calibration.
The provider never executes actions, and a model can never override a policy.

```python
from decisionos import DecisionOS

client = DecisionOS("http://localhost:8000")

decision = await client.decide(
    schema="ToolAuthorization",
    context={
        "tool": "github.merge",
        "repository": "production",
        "tests_passed": False,
    },
)

if decision.action == "allow":
    execute_tool()
elif decision.action == "human_review":
    request_approval()
else:
    deny()
```

---

## Table of contents

- [The problem](#the-problem)
- [How DecisionOS is different](#how-decisionos-is-different)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [The decision model](#the-decision-model)
- [Policy precedence](#policy-precedence)
- [Calibration](#calibration)
- [API](#api)
- [Python SDK](#python-sdk)
- [CLI](#cli)
- [Examples](#examples)
- [Dashboard](#dashboard)
- [Observability](#observability)
- [Configuration](#configuration)
- [Development](#development)
- [Repository layout](#repository-layout)
- [Design decisions](#design-decisions)

---

## The problem

Modern software increasingly asks a model to make judgments: is this tool call
safe, should this deployment roll back, does this document belong in this
category. Three failure modes recur:

1. **Unbounded autonomy.** A model's text output is parsed and acted on
   directly, with no deterministic guardrail.
2. **No notion of uncertainty.** A classification is treated as a fact even
   when the model is nearly guessing.
3. **No feedback loop.** Predictions are never measured against what actually
   happened, so nobody knows whether the system is any good.

DecisionOS addresses all three: typed probabilistic decisions, deterministic
policy control, and calibration against recorded outcomes.

## How DecisionOS is different

| | Traditional rules engine | LLM function calling | AI agents | Classifiers | Guardrails | **DecisionOS** |
|---|---|---|---|---|---|---|
| **Control** | fully deterministic | model decides and acts | model decides and acts | model decides | block/allow only | deterministic policy always outranks the model |
| **Uncertainty** | none | hidden in text | hidden | a score, rarely calibrated | none | a first-class probability distribution |
| **Actions** | you write them | model emits them | model executes tools | you write them | n/a | DecisionOS only returns a decision; never executes |
| **Feedback** | none | none | none | offline training only | none | every decision stores predicted vs. observed for calibration |
| **Provider** | n/a | one vendor | one vendor | your training pipeline | one vendor | pluggable; Jev is primary, Mock requires no credentials |

DecisionOS is not a guardrail that only blocks. It returns a *typed action*
(`allow`, `human_review`, `deny`, …) plus the probability of every alternative,
so the calling system can branch on both the answer and its confidence.

## Architecture

```text
Context
   │
   ▼
Typed Decision Request        validated by Pydantic
   │
   ▼
Probabilistic Provider        Jev / Mock / (future: OpenAI, Local)
   │
   ▼
Structured Probability        choice + probabilities + confidence
Distribution
   │
   ▼
Trust Boundary                provider output is re-validated, never trusted
   │
   ▼
Deterministic Policy Engine   HARD_DENY > HUMAN_REVIEW > MODEL
   │
   ▼
Final Action                  persisted with a full audit trail
   │
   ▼
Observed Outcome              recorded by the caller
   │
   ▼
Calibration                   Brier score, ECE, reliability buckets
```

The architectural rule:

> **The AI provider never directly executes actions.**

Jev produces probabilistic intelligence. The policy engine determines what is
actually permitted.

## Quickstart

The whole stack runs with one command and **requires no credentials**.

```bash
git clone <repo> && cd decisionos
cp .env.example .env
docker compose up
```

This starts the API, PostgreSQL, Redis, Prometheus, Grafana, and the dashboard.
Then evaluate a decision in-process (no server needed):

```bash
decisionos evaluate \
  --schema ToolAuthorization \
  --context examples/agent_guard/merge.json
```

```text
Decision: human_review
Confidence: 91%
Risk: 87%

Probabilities:
  allow       :   8.0%
  deny        :   1.0%
  human_review:  91.0%

Provider: mock
Latency: 84ms
```

The same flow over HTTP:

```bash
# create a decision
curl -X POST http://localhost:8000/v1/decisions \
  -H 'Content-Type: application/json' \
  -d '{
    "decision_type": "tool_authorization",
    "schema_name": "ToolAuthorization",
    "schema_version": 1,
    "context": {
      "tool": "github.merge",
      "repository": "production",
      "environment": "production",
      "tests_passed": false
    }
  }'

# fetch it
curl http://localhost:8000/v1/decisions/<id>

# record what actually happened
curl -X POST http://localhost:8000/v1/decisions/<id>/outcome \
  -H 'Content-Type: application/json' \
  -d '{"actual_outcome": "safe", "success": true}'

# see calibration
curl http://localhost:8000/v1/calibration
```

Open the dashboard at <http://localhost:3000> to see the same data.

## The decision model

A decision request names a **schema** (a closed set of actions) and supplies
**context** (the facts to evaluate):

```json
{
  "decision_type": "tool_authorization",
  "schema_name": "ToolAuthorization",
  "schema_version": 1,
  "context": {
    "agent": "deploy-agent",
    "tool": "github.merge",
    "repository": "org/project",
    "environment": "production",
    "tests_passed": false
  }
}
```

A decision is the validated result:

```json
{
  "decision_id": "dec_123",
  "action": "human_review",
  "model_action": "human_review",
  "confidence": 0.91,
  "probabilities": { "allow": 0.08, "human_review": 0.91, "deny": 0.01 },
  "risk": 0.87,
  "reason_codes": ["production_repository", "merge_operation", "incomplete_tests"],
  "provider": "jev",
  "provider_request_id": "req_01H...",
  "latency_ms": 84
}
```

Every value is validated at the trust boundary: `0 ≤ confidence ≤ 1`,
`0 ≤ risk ≤ 1`, every probability in `[0, 1]`, the distribution sums to ≈ 1, and
the action belongs to the schema. Malformed provider output is rejected rather
than trusted.

**Schemas are immutable.** Changing the action set creates a new version; a
version already used by a decision is never mutated.

## Policy precedence

Policies are deterministic YAML. Given the same decision and context, a policy
always resolves to the same required action. Precedence is strict:

```text
HARD_DENY  >  REQUIRED_HUMAN_REVIEW  >  MODEL_DECISION
```

```yaml
name: production-agent-policy
version: 1
rules:
  - name: dangerous-database-operation
    when:
      tool: database.delete
    action:
      require: deny

  - name: production-merge
    when:
      environment: production
      tool: github.merge
    action:
      require: human_review

  - name: high-risk
    when:
      risk:
        gt: 0.90
    action:
      require: deny

  - name: low-confidence
    when:
      confidence:
        lt: 0.70
    action:
      require: human_review
```

```text
Model says ALLOW
Policy says DENY

Final = DENY
```

A probability distribution can never bypass a deterministic security rule.
Policies support operators (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`,
`not_in`, `regex`, `exists`) and may reference derived fields (`action`,
`confidence`, `risk`) which are authoritative and cannot be spoofed by context.

## Calibration

Every decision stores its predicted distribution and selected action; every
outcome stores ground truth. Calibration measures how well they agree, using
only real recorded data:

- **Brier score** — mean squared error between confidence and observed success.
- **Expected calibration error (ECE)** — weighted gap between confidence and
  accuracy across reliability buckets.
- **Reliability buckets** — count, accuracy, and mean confidence per band.

```json
{
  "sample_count": 12491,
  "brier_score": 0.083,
  "expected_calibration_error": 0.041,
  "buckets": [
    { "lower": 0.8, "upper": 0.9, "count": 2841, "accuracy": 0.85, "avg_confidence": 0.84 }
  ]
}
```

The endpoint answers the question *"when DecisionOS was 90% confident, how often
was it actually correct?"* and supports filtering by decision type, schema,
provider, action, and time range. Empty or insufficient data is reported as
`null` — never fabricated. v1 does not retrain models; it builds the data
infrastructure for future evaluation.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/decisions` | Create a decision (supports `Idempotency-Key`) |
| `GET` | `/v1/decisions` | List decisions (filter by type/schema/provider/action/state) |
| `GET` | `/v1/decisions/{id}` | Fetch a decision |
| `GET` | `/v1/decisions/{id}/explanation` | Structured evidence (no generated prose) |
| `POST` | `/v1/decisions/{id}/outcome` | Record the observed outcome |
| `POST` / `GET` | `/v1/schemas` | Register / list schemas |
| `GET` | `/v1/schemas/{name}/{version}` | Fetch a schema version |
| `POST` / `GET` | `/v1/policies` | Register / list policies |
| `GET` | `/v1/policies/{key}` | Fetch a policy by `name` or `name@version` |
| `GET` | `/v1/calibration` | Calibration report with filters |
| `GET` | `/health`, `/ready`, `/metrics` | Operations |

Interactive docs are served at `/docs`. Requests are protected by API-key
authentication outside development, rate limited, and idempotent when an
`Idempotency-Key` header is supplied.

## Python SDK

```python
from decisionos import DecisionOS          # synchronous
from decisionos import AsyncDecisionOS      # asynchronous

client = AsyncDecisionOS("http://localhost:8000")

# Register a schema and a policy once.
await client.register_schema(
    name="ToolAuthorization",
    actions=["allow", "human_review", "deny"],
)
await client.register_policy(
    name="production-agent-policy",
    rules=[
        {
            "name": "production-merge",
            "when": {"environment": "production", "tool": "github.merge"},
            "action": {"require": "human_review"},
        }
    ],
)

decision = await client.decide(
    schema="ToolAuthorization",
    context={"tool": "github.merge", "environment": "production"},
    policy="production-agent-policy@1",
)

await client.record_outcome(
    decision.decision_id, actual_outcome="safe", success=True
)
```

The SDK covers decisions, outcomes, explanations, schemas, policies, and
calibration, with a typed error hierarchy (`NotFoundError`, `RateLimitError`,
`AuthenticationError`, …) mapped to HTTP status codes.

## CLI

```bash
decisionos evaluate --schema ToolAuthorization --context request.json
decisionos demo agent_guard
decisionos demo deployment_rollback

decisionos decisions list
decisionos decisions get dec_123
decisionos decisions outcome dec_123 --actual-outcome safe --success

decisionos schemas list
decisionos schemas validate schema.json

decisionos policies list
decisionos policies validate policy.yaml

decisionos calibration report
decisionos health
```

`evaluate` and both `demo` commands run entirely in-process on the mock
provider — no server, database, or credentials required.

## Examples

`examples/agent_guard/` is the flagship demo: authorizing an AI agent's tool
calls. The agent asks DecisionOS whether it may use a tool; the provider returns
a distribution over `allow` / `human_review` / `deny`; the policy engine decides
what is permitted.

```text
AI Agent
   │  "merge PR #421"
   ▼
DecisionOS
   ├── Jev evaluation
   ├── policy evaluation
   ▼
HUMAN_REVIEW
```

`examples/deployment_rollback/` is a second example: given error rate, latency,
and deployment age, decide `continue` / `rollback` / `pause` / `human_review`.
**It is a simulator** — DecisionOS returns a decision and the example maps it to
a plain description; it never modifies infrastructure.

## Dashboard

A Next.js dashboard visualizes the same data the API serves:

- **Overview** — decisions, action distribution, human-review rate, average
  latency, calibration ECE, plus charts for volume, confidence/risk, action
  distribution, confidence distribution, provider latency, and policy overrides.
- **Decisions** — filterable list; **Decision detail** with probabilities,
  reason codes, policy rules, and the full lifecycle timeline.
- **Schemas**, **Policies**, **Calibration** (reliability curve), **Settings**.

Every view reads live data and never fabricates statistics.

## Observability

- **OpenTelemetry** traces for requests and the decision pipeline
  (`trace_id`, `request_id`, `decision_id`, `provider`, `schema`,
  `policy_version`, `latency`).
- **Prometheus** metrics: `decisionos_decisions_total`,
  `decisionos_decision_latency_seconds`, `decisionos_provider_latency_seconds`,
  `decisionos_provider_errors_total`, `decisionos_policy_overrides_total`,
  `decisionos_calibration_error`, and HTTP latency histograms. Grafana comes
  provisioned with a DecisionOS dashboard.
- **Structured JSON logging** with request context and secret redaction. API
  keys, authorization headers, and sensitive values are never logged.

## Configuration

All configuration is environment-driven; see `.env.example`.

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` / `test` / `production` |
| `DATABASE_URL` | PostgreSQL async URL |
| `REDIS_URL` | Redis URL (idempotency, cache, rate limiting) |
| `API_KEY` | Enables API-key auth outside development |
| `DEFAULT_PROVIDER` | `mock` (safe default) or `jev` |
| `JEV_API_KEY` / `JEV_BASE_URL` / `JEV_MODEL` | Jev (TypeSafe) provider |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Enables trace export when set |
| `NEXT_PUBLIC_API_BASE_URL` / `DECISIONOS_API_URL` | Dashboard API URLs |

Jev and TypeSafe environment names are both accepted. Secrets are never
committed. **DecisionOS works without Jev credentials** — the MockProvider is
deterministic and always available, and the registry falls back to it whenever
Jev is unconfigured or unreachable.

## Development

```bash
make dev        # docker compose up (full stack)
make test       # full test suite
make lint       # ruff check + format check
make format     # auto-format
make migrate    # apply database migrations
make demo       # AgentGuard flagship demo
make demo-rollback
make evaluate
make dashboard  # Next.js dev server
```

Tests use `pytest`, `pytest-asyncio`, and `Hypothesis`:

- **Unit** — probability validation, schemas, policies, precedence, lifecycle,
  calibration, malformed provider output.
- **Integration** — API → engine → mock provider → policy → PostgreSQL, plus the
  SDK, and skip cleanly when services are unavailable.
- **Property** — distributions (`0 ≤ p ≤ 1`, `sum(p) ≈ 1`) and policies
  (model ALLOW + hard DENY ⇒ DENY).
- **Failure** — Jev timeout/429/500/malformed/network, database/Redis failure,
  duplicate concurrent requests, invalid schema/policy.

## Repository layout

```text
decisionos/
├── apps/
│   ├── api/            thin FastAPI layer over the core
│   └── dashboard/      Next.js dashboard
├── packages/decisionos/
│   ├── engine/         evaluation orchestration + lifecycle
│   ├── models/         validated domain models
│   ├── providers/      DecisionProvider + Jev + Mock + registry
│   ├── policies/       deterministic policy engine
│   ├── calibration/    Brier, ECE, reliability buckets
│   ├── storage/        SQLAlchemy + repositories + Redis
│   ├── observability/  logs, metrics, tracing, context
│   ├── sdk/            Python SDK
│   ├── cli/            command line interface
│   └── examples/       runnable AgentGuard + rollback demos
├── examples/           schemas, policies, context fixtures
├── migrations/         Alembic
├── tests/              unit / integration / property / failure
├── deploy/             Prometheus + Grafana provisioning
├── docker-compose.yml
└── Makefile
```

## Design decisions

- **The provider never executes.** It returns a distribution; the policy engine
  and caller decide what happens.
- **Policy always outranks the model.** Precedence is strict and the model can
  only ever be asked for a safer action, never a less safe one.
- **The trust boundary is a type.** `RawDecision` (untrusted) is distinct from
  `Decision` (validated); nothing downstream consumes raw output.
- **Risk is derived, not invented.** When a provider supplies no risk, it is
  computed as `1 − P[selected action]` — the model's own uncertainty.
- **Schemas and policies are immutable and versioned.** A change is a new
  version. Existing decisions keep their original versions.
- **No Jev specifics outside the provider.** `providers/jev.py` is the only
  module that knows the TypeSafe API; everything else depends on the interface.
- **MockProvider is mandatory.** DecisionOS, its tests, demos, and dashboard run
  with no external credentials.
- **Calibration uses only real data.** Empty or insufficient samples are
  reported honestly rather than replaced with demo numbers.

## License

Apache-2.0. See [LICENSE](LICENSE).
