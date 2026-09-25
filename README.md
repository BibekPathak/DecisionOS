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
