# Amendment 1 — Langfuse owns observability and evaluation

This amendment is authoritative together with `docs/founding-brief.md` and supersedes conflicting observability/evaluation architecture.

## Ownership boundary

- **Convex:** business state only—cases, patients, roles, structured plans, business step status, messages, reviews, knowledge, escalations, scheduled tasks, settings, payment/calendar references.
- **Langfuse:** traces/spans, model and tool telemetry, prompt registry/versions/labels, datasets, experiments, scores, token usage, latency, and detailed cost.

## Required implementation changes

- Remove Convex prompt-version and evaluation tables.
- Replace role prompt-version IDs with `{name, label}` Langfuse prompt references.
- Keep only business-transition step state in Convex plus `langfuseTraceId` and running cost.
- Add `sentToEval` to escalations.
- Instrument manager, generic role runner, and every tool with Langfuse `@observe`.
- Tag observations with case ID, role, and task type.
- Do not build a custom trace tree or trace diff UI. Deep-link cases to Langfuse.
- Store evaluation cases as a Langfuse dataset and runs as experiments with scores.
- Gate prompt production labels on experiment score relative to the production baseline.
- Add bounced/escalated traces to the Langfuse dataset through native/API workflows.

## Console changes

- Cases show a Convex-reactive activity strip, business plan/status, escalation brief, running cost, and a Langfuse deep-link.
- Evals triggers experiments, displays publish-gate status and blocked logs, and links to Langfuse datasets/experiments.

## Non-negotiable evidence

- First manager stub produces a visible Langfuse trace.
- Compliance bounces remain visible in both Langfuse span metadata and Convex business status.
- Baseline dataset has at least 10 cases.
- One prompt publish is genuinely blocked by the experiment gate.
