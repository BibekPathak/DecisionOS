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
