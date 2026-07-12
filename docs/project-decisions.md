# Project Decisions

Last updated: 2026-07-12

## Confirmed

- This existing workspace is the project repository location.
- The repository may be public during judging.
- The target is a full live working product, not an eight-hour-only prototype.
- Google Calendar is the scheduling system.
- Appointments are held tentatively pending deposit.
- Own-domain Linkup results may be answered immediately with citations, subject to deterministic policy conflict checks.
- The initial product language is English only.
- The project owner is the final approver for red flags, clinical-boundary wording, claims policy, and structured KB policy cards.
- The recommended FastAPI host is Google Cloud Run in `asia-south1`, behind Cloudflare Worker ingress.
- Convex stores business state only; Langfuse owns traces, prompt registry, datasets, experiments, scores, token usage, latency, and detailed cost.
- The console deep-links to Langfuse rather than implementing a custom trace tree or trace diff.
- Synthetic personas are used until privacy, consent, retention, access-control, and production-readiness reviews authorize real patient data.

## Production implications

The original eight-hour phases are retained only as the order for the first demonstrable vertical slice. Production release additionally requires:

1. Authentication and role-based access for the console.
2. Separate development, staging, and production environments.
3. Formal clinic policy approval/versioning workflow.
4. DPDP-focused privacy review, consent/notice, retention, deletion, and incident procedures.
5. Encryption, secret rotation, audit logs, rate limits, backups, and disaster recovery.
6. Provider contracts and data-processing review for every model/tool vendor.
7. Staged rollout with shadow mode, human approval mode, limited automation, and monitored expansion.
8. Load, latency, failure, replay, and cost tests.
9. On-call ownership, service-level objectives, alerting, and runbooks.
10. Clinical safety acceptance tests signed off by the owner before live patient use.

## Pending

- Public GitHub owner/repository name and whether this folder should be initialized as Git.
- Google Cloud project and dedicated Calendar details.
- Model provider and pinned model IDs.
- Initial cost ceiling and latency SLO.
- Clinic locations, hours, clinician map, pricing, and booking policies.
- Final domain names for console and API.
- Production retention period.
- Production escalation contact and operating hours.
