# Contributing to DecisionOS

Thanks for your interest. DecisionOS is a small piece of AI infrastructure, and
the bar for contributions is simple: typed, tested, and honest.

## Getting set up

```bash
git clone <repo> && cd decisionos
cp .env.example .env
docker compose up            # api, postgres, redis, prometheus, grafana, dashboard
```

For host-based development you need Python 3.13+, Node 20+, PostgreSQL, and
Redis. Dependencies are managed with `uv`:

```bash
uv venv --python 3.13
uv pip install -e ".[dev]"
```

## Before you open a pull request

```bash
make lint     # ruff check + ruff format --check
make test     # pytest (integration tests skip without services)
make format   # auto-fix formatting and lint
```

Dashboard changes should also pass:

```bash
cd apps/dashboard
npm run typecheck
npm run lint
npm run build
```

## Engineering rules

These are non-negotiable and reviewed in every change:

1. **Do not over-engineer v1.** Prefer simple, typed, testable code.
2. **Do not introduce microservices unnecessarily.**
3. **Do not hard-code Jev behaviour outside `providers/jev.py`.** The rest of
   DecisionOS depends only on the `DecisionProvider` interface.
4. **Do not let model output bypass deterministic policies.** Precedence is
   `HARD_DENY > REQUIRED_HUMAN_REVIEW > MODEL_DECISION`, always.
5. **Do not fabricate Jev API details.** Verify them against the official
   TypeSafe documentation before changing the provider.
6. **Do not require Jev credentials for local development.** The MockProvider
   must keep everything runnable.
7. **Do not build a chatbot UI.**
8. **Do not implement fake calibration numbers.** Report `null` when data is
   insufficient.
9. **Do not hide model uncertainty.** Distributions and confidence are
   first-class.
10. **Prefer typed, testable code.** Domain models are validated; the provider
    trust boundary is explicit (`RawDecision` → `Decision`).
11. **Document important architectural decisions.**
12. **Run tests after each change.**

## Tests

- **Unit** — pure logic: models, validators, policy operators, calibration
  math, lifecycle.
- **Integration** — API → engine → provider → policy → PostgreSQL, plus the SDK.
  These auto-skip when no database is reachable.
- **Property** — Hypothesis invariants for probability distributions and policy
  precedence.
- **Failure** — provider timeouts/rate limits/malformed output, database and
  Redis failures, duplicate concurrent requests, invalid schemas and policies.

When adding a provider, add both success and failure tests using
`httpx.MockTransport` — never hit a live API in tests.

## Commit style

Write concise, imperative commit messages that explain the *why*. Keep secrets
out of commits; `.env` is git-ignored and must never contain real credentials.

## Licence

By contributing you agree your contributions are licensed under Apache-2.0.
