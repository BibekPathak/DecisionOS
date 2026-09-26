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
     ├── Jev (probabilistic intelligence)
     ├── Policy Engine (deterministic control)
     ├── Decision Store
     └── Calibration (outcome feedback)
     │
     ▼
Final Action
```

The AI provider never directly executes actions. A provider produces a
probability distribution, the policy engine determines what is actually
permitted, and observed outcomes feed calibration.

Full documentation is added in later phases. See `docs` and the project
specification for the architecture and roadmap.

## Examples

Both examples run entirely in-process on the mock provider. No credentials,
database, or network access are required.

```bash
# The flagship AgentGuard demo: authorize AI agent tool calls.
make demo

# The deployment rollback simulator (simulation only; no infrastructure
# is modified).
make demo-rollback

# Evaluate a single context, matching the acceptance criteria.
make evaluate
```

`decisionos demo agent_guard --case merge` runs a single tool. The rollback
simulator accepts `--case rolling_back`, `--case healthy`, or
`--case no_rollback_available`.

See `examples/agent_guard` and `examples/deployment_rollback` for the schemas,
policies, and context fixtures.

## Dashboard

A Next.js dashboard (App Router, TypeScript, Tailwind, Recharts) visualizes the
same data the API serves. Start the full stack:

```bash
docker compose up
```

Then open:

- Dashboard — http://localhost:3000
- API docs — http://localhost:8000/docs
- Prometheus — http://localhost:9090
- Grafana — http://localhost:3001

Pages: Overview, Decisions, Decision detail, Schemas, Policies, Calibration,
and Settings. Every view reads live data from the API and never fabricates
statistics; empty states are shown honestly.

For local development against a running API:

```bash
cd apps/dashboard
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

The dashboard container uses `DECISIONOS_API_URL` for server-side rendering and
`NEXT_PUBLIC_API_BASE_URL` for browser requests (see `.env.example`).

