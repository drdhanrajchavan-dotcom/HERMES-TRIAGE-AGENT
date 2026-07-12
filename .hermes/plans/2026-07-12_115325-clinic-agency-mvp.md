# Clinic Patient-Coordination Agency MVP Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build and demonstrate a safe, traceable, multi-agent clinic coordination MVP that handles real inbound messages, grounded information, booking, deposits, escalation, compliance review, scheduled follow-up, evaluation, and live operations visibility.

**Architecture:** A Python FastAPI runner owns ingestion, orchestration, role execution, tools, safety gates, and scheduled jobs. Convex is the durable/reactive system of record. A React/Vite console reads and mutates product state through Convex. Roles remain configuration data, but deterministic application code—not an LLM prompt alone—enforces outbound compliance gating, red-flag escalation, tool permissions, idempotency, and side-effect approval.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, pytest, uv, React, TypeScript, Vite, Vitest, Playwright, Convex, Cloudflare Pages/Worker or Tunnel, Telegram Bot API, Google Calendar or Cal.com, Dodo Payments, ElevenLabs, Linkup, hosted LLM APIs.

---

## 1. Scope and delivery strategy

### Build target

The first build is a **demo-safe vertical slice**, not an immediately production-ready replacement for clinic staff. It must prove these non-negotiable paths:

1. Telegram enquiry → case → manager plan → role steps → grounded response → compliance approval → outbound message.
2. Appointment request → suitable clinician/slot → explicit patient selection → real calendar write → Dodo deposit link.
3. Deliberate overclaim → compliance rejection → revised compliant response, visible in trace.
4. Clinical red flag → immediate deterministic escalation → full context brief → safe acknowledgement only.
5. Scheduled lifecycle task → reviewed outbound message → delivery with duplicate prevention.
6. Prompt publication → eval suite → regression blocks publication.
7. Live console shows case state and trace as it happens.

### Explicitly deferred from the first vertical slice

- Real patient data and production clinic deployment.
- WhatsApp unless the existing approved Cloud API app can be safely repointed in under 15 minutes.
- PSTN calling.
- Automated refunds or irreversible payment actions.
- Embedding infrastructure before metadata/text retrieval proves insufficient.
- Free-form manager-created roles in production. The demo may spawn only pre-approved templates with bounded tools and guardrails.

### Safety interpretation

The Compliance role reviews wording, but it is **not the sole safety mechanism**. These controls must be deterministic application invariants:

- Every outbound patient message has a passed compliance review tied to the exact draft hash.
- Red-flag detection runs before generative planning and again before send.
- Clinical red flags cannot be de-escalated by an LLM.
- Tool access is enforced by a server-side allowlist.
- Calendar writes, payment-link creation, and sends use idempotency keys.
- Unapproved KB content cannot enter answers.
- Own-domain Linkup results are cited and treated as unapproved unless policy permits direct use.
- Compliance autonomy cannot be configured to bypass review.
- No real history-bearing patient PII is used in the event environment.

---

## 2. Decisions and inputs required from the project owner

### Required before implementation starts

1. **Repository destination**
   - New GitHub repository name/owner, or path to an existing repository.
   - Whether it may be public during judging.

2. **Calendar decision—choose one and do not revisit during the sprint**
   - **Recommended:** Google Calendar if a test Workspace/calendar and OAuth credentials are already available.
   - Choose Cal.com if an API key and event type are already ready and Google OAuth is not.
   - Supply a dedicated demo calendar, test clinician names, procedure mapping, working hours, slot duration, timezone, and buffer rules.

3. **Model provider credentials and model IDs**
   - Manager/Compliance model.
   - Fast Triage/Drafter/Lifecycle model.
   - Confirm account limits and expected budget.

4. **Telegram bot**
   - Bot token from BotFather.
   - Admin Telegram chat/user ID for escalation and optional alerts.

5. **Convex**
   - Account/team/project access, or permission for Hermes to create a project.
   - Deployment URL and deploy key if the project already exists.

6. **Cloudflare**
   - Account access/token with Pages and Worker permissions, or approval to use a temporary tunnel first.
   - Desired demo subdomain.

7. **Dodo Payments**
   - Test-mode API key, webhook secret, product/price details, currency, deposit amount or percentage, and success/cancel URLs.
   - Confirm whether the judged flow should stop at checkout or complete a test payment.

8. **Clinic-approved policy pack**
   - Doctor–procedure map.
   - Prices and whether taxes/consult fees are included.
   - Deposit, cancellation, rescheduling, refund, no-show, and financing/EMI policy.
   - Hours, locations, languages, escalation contacts.
   - Approved red-flag list and exact safe interim wording.
   - Claims rules and prohibited phrases.
   - Approved pre-care/post-care content.
   - Source-of-truth URLs for clearskin.in and hairmdindia.com.

9. **Synthetic personas**
   - Approve four fictional patients, or let Hermes generate them.
   - Confirm languages and histories needed for demo scenarios.

10. **External API credentials**
    - ElevenLabs API key and selected STT/TTS voices.
    - Linkup API key.
    - Wispr Flow is operated by the owner; provide dictated content or exported notes/screenshots.

### Needed during implementation

- Fast answers to policy ambiguities, ideally within 5–10 minutes.
- A human to perform OAuth/browser login steps that cannot be delegated.
- Approval of the first 10 KB cards before they become serviceable.
- One real phone for Telegram testing and one browser with microphone permission.
- One clinic representative to approve red-flag behavior and outbound wording.

### Useful but optional

- Brand name, logo, colors, and tone examples.
- Existing FAQ exports, procedure lists, location data, and contact-hours copy.
- Existing WhatsApp Cloud API app details.
- A second person for the volunteer role-wizard test.

### Secrets handling

Provide secrets through local environment variables or platform secret stores—not chat, commits, screenshots, Convex documents, or frontend environment variables. The implementation will create `.env.example` containing names only.

---

## 3. Proposed repository structure

```text
clinic-agency/
├── README.md
├── .env.example
├── .gitignore
├── docs/
│   ├── founding-brief.md
│   ├── architecture.md
│   ├── safety-boundary.md
│   ├── demo-runbook.md
│   └── data-handling.md
├── runner/
│   ├── pyproject.toml
│   ├── src/clinic_agency/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/{health.py,telegram.py,voice.py,jobs.py}.py
│   │   ├── domain/{cases.py,roles.py,plans.py,steps.py,patients.py,kb.py,evals.py}.py
│   │   ├── orchestration/{ingest.py,manager.py,role_runner.py,workflow.py,context.py}.py
│   │   ├── safety/{red_flags.py,compliance_gate.py,claims.py,escalation.py}.py
│   │   ├── tools/{registry.py,calendar.py,dodo.py,knowledge.py,linkup.py,messaging.py}.py
│   │   ├── adapters/{convex.py,telegram.py,models.py,elevenlabs.py}.py
│   │   ├── lifecycle/{scheduler.py,jobs.py}.py
│   │   └── evals/{runner.py,judges.py,assertions.py}.py
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── contract/
│       └── fixtures/
├── console/
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   ├── pages/{Cases,Team,Knowledge,Evals,Settings}.tsx
│   │   ├── components/
│   │   └── lib/
│   └── tests/
├── convex/
│   ├── schema.ts
│   ├── cases.ts
│   ├── steps.ts
│   ├── roles.ts
│   ├── knowledge.ts
│   ├── evals.ts
│   ├── settings.ts
│   └── seed.ts
├── worker/
│   └── src/index.ts
└── scripts/
    ├── seed_demo.py
    ├── reset_demo.py
    ├── smoke_demo.py
    └── verify_env.py
```

The exact structure can be adjusted after inspecting the created framework files, but ownership boundaries must remain: Convex stores state, FastAPI owns agency behavior and privileged tools, React owns operations UI, and the Worker/Tunnel owns public ingress.

---

## 4. Implementation sequence

## Phase 0 — Foundation and walking skeleton (target: 30–60 minutes)

### Task 0.1: Freeze acceptance criteria and policy boundary

**Files:**
- Create `docs/founding-brief.md`
- Create `docs/safety-boundary.md`
- Create `docs/demo-runbook.md`

**Steps:**
1. Save the supplied brief verbatim as the authoritative product document.
2. Add a short MVP acceptance checklist containing the seven vertical-slice paths above.
3. Define prohibited outputs and deterministic escalation behavior.
4. Record the selected calendar and deployment choices.
5. Commit: `docs: establish founding brief and safety boundary`.

**Verification:** Every MUST item has a named demo scenario and an observable pass condition.

### Task 0.2: Scaffold monorepo and quality gates

**Files:**
- Create root files and `runner/`, `console/`, `convex/`, `worker/` projects.
- Create `.env.example` and `.gitignore`.

**Steps:**
1. Initialize Git and the project manifests.
2. Configure Python formatting/linting/type checks and pytest.
3. Configure TypeScript strict mode, linting, Vitest, and Playwright.
4. Add root commands for `dev`, `test`, `lint`, and `typecheck`.
5. Write smoke tests for FastAPI `/health` and console shell rendering.
6. Run all checks; commit only on green.
7. Commit: `chore: scaffold clinic agency monorepo`.

**Verification commands:**
- `uv run --project runner pytest runner/tests -q`
- `uv run --project runner ruff check runner`
- `npm --prefix console test -- --run`
- `npm --prefix console run build`

### Task 0.3: Define Convex schema with demo-safe constraints

**Files:**
- Create `convex/schema.ts`
- Create initial query/mutation modules.

**Steps:**
1. Implement the supplied entities plus missing operational fields: idempotency keys, draft hash, review hash, delivery status, citation IDs, timestamps, environment, and audit actor.
2. Add indexes for live case feed, case steps, role/status filters, scheduled tasks, and unresolved escalations.
3. Store message bodies only in demo mode with synthetic identities; use digests/redacted previews for model/tool traces.
4. Add seed and reset mutations.
5. Add schema-level tests where supported and adapter contract tests in Python.
6. Commit: `feat: add reactive agency data model`.

**Important schema additions:**
- `messages`: direction, channel, content/redacted_content, draft_hash, compliance_review_id, delivery state.
- `reviews`: draft_hash, reviewer role/version, verdict, violations, notes.
- `scheduled_tasks`: due_at, type, case/patient reference, status, idempotency_key.
- `tool_calls`: step, tool, sanitized input/output, status, latency, idempotency_key.

### Task 0.4: Seed policy, roles, personas, and KB

**Files:**
- Create `convex/seed.ts`
- Create `runner/tests/fixtures/*.json`

**Steps:**
1. Seed Manager, Triage, Booking, Knowledge, Drafter, Compliance, and Lifecycle role rows.
2. Seed four clearly synthetic personas.
3. Seed at least 10 clinic-approved KB cards with stable IDs and source metadata.
4. Seed settings and doctor–procedure map.
5. Ensure unapproved cards are excluded by retrieval tests.
6. Commit: `feat: seed demo policy roles personas and knowledge`.

### Task 0.5: Build the walking skeleton

**Files:**
- Create FastAPI app, Convex adapter, Telegram webhook, and minimal console case feed.

**Steps:**
1. Receive a signed/secret Telegram webhook request.
2. Deduplicate by Telegram update ID.
3. Create a case and one manager step.
4. Generate a stub response through the same outbound queue later used by the real system.
5. Record the outbound draft/review/send trace.
6. Display the case and trace row reactively in the console.
7. Send the response back through Telegram.
8. Commit: `feat: deliver telegram to convex walking skeleton`.

**Phase 0 exit test:** A phone message produces one Telegram response and a new live case/trace without duplicate processing when the webhook is replayed.

---

## Phase 1 — Safe core agency loop (target: 2–3 hours)

### Task 1.1: Implement typed role configuration and tool registry

**Files:**
- `runner/src/clinic_agency/domain/roles.py`
- `runner/src/clinic_agency/tools/registry.py`
- Corresponding unit tests.

**Steps:**
1. Define typed role config: mission, prompt version, model, allowlist, guardrails, autonomy.
2. Validate that unknown tools and forbidden autonomy combinations fail closed.
3. Make Compliance mandatory and non-bypassable.
4. Add tests before implementation.
5. Commit: `feat: enforce data-driven role configuration`.

### Task 1.2: Implement plan DAG and role-runner contract

**Files:**
- `orchestration/manager.py`, `role_runner.py`, `workflow.py`
- Unit and contract tests.

**Steps:**
1. Define structured model outputs for plans and task results.
2. Validate DAG nodes, dependencies, role existence, and bounded step count.
3. Execute only ready nodes; record every transition.
4. Retry tool failures at most twice with concrete feedback.
5. Escalate on exhausted retry, repeated bounce, or invalid output.
6. Commit: `feat: add traceable bounded agency workflow`.

### Task 1.3: Build three-layer context assembly

**Files:**
- `orchestration/context.py`
- Tests for case, patient, and policy context.

**Steps:**
1. Fetch current case fields and prior steps.
2. Fetch synthetic patient history by stable patient identity.
3. Fetch applicable approved policy/KB cards.
4. Redact unnecessary identifiers before model calls.
5. Assert handoff context contains citations and policy versions.
6. Commit: `feat: assemble case patient and policy memory`.

### Task 1.4: Implement deterministic red-flag and escalation path first

**Files:**
- `safety/red_flags.py`, `safety/escalation.py`
- Red-flag fixtures and tests.

**Steps:**
1. Encode editable phrases/rules with conservative matching.
2. Run red-flag classification before manager planning.
3. Allow the model to add escalation, never remove a deterministic escalation.
4. Create a structured escalation brief: summary, history, evidence, attempted steps, recommendation, safe patient acknowledgement.
5. Ensure no booking/payment side effect occurs on this path unless explicitly defined as a safe urgent-slot hold.
6. Commit: `feat: add fail-closed red-flag escalation`.

### Task 1.5: Implement Knowledge retrieval with citation enforcement

**Files:**
- `tools/knowledge.py`, `tools/linkup.py`
- Tests for approved card, price mismatch, no-answer, and own-domain restriction.

**Steps:**
1. Retrieve by category/tags/language and text relevance.
2. Return card IDs and source URLs with every fact.
3. Reject unapproved cards.
4. If no answer exists, query Linkup only for allowlisted domains.
5. If still unresolved, draft a deferral, create a KB-gap card, and escalate.
6. Do not invent or normalize prices outside approved policy.
7. Commit: `feat: add cited fail-closed knowledge retrieval`.

### Task 1.6: Implement draft → review → revision → approval invariant

**Files:**
- `safety/compliance_gate.py`, `safety/claims.py`, communications role config.
- Tests for diagnosis, guarantees, price mismatch, missing disclaimer, and altered-after-review draft.

**Steps:**
1. Drafter produces structured text plus citation references.
2. Run deterministic claims and price checks.
3. Run Compliance role with exact policy and cited sources.
4. Tie approval to SHA-256 of exact outbound text.
5. On rejection, send concrete notes back to Drafter, maximum two revisions.
6. Escalate after repeated rejection.
7. At send time, recompute the hash and reject any unreviewed mutation.
8. Commit: `feat: enforce reviewed outbound messages`.

### Task 1.7: Add real booking and deposit tools

**Files:**
- `tools/calendar.py`, `tools/dodo.py`
- Contract tests using fakes plus opt-in sandbox integration tests.

**Steps:**
1. Fetch availability for eligible clinicians only.
2. Offer slots without writing the calendar.
3. Require explicit user slot selection.
4. Recheck availability, create idempotent event, and record external event ID.
5. Create a Dodo test checkout/deposit link with case metadata and idempotency.
6. Process signed Dodo webhook updates.
7. Draft and review confirmation before sending.
8. Add compensation/escalation if calendar succeeds but payment-link creation fails.
9. Commit: `feat: integrate calendar booking and dodo deposit`.

### Task 1.8: Seed and run first 10 eval cases

**Files:**
- `runner/src/clinic_agency/evals/*`
- `runner/tests/fixtures/eval_cases.json`

**Steps:**
1. Encode the supplied cases plus booking, no-answer, duplicate webhook, and altered-draft cases.
2. Add deterministic assertions for route, escalation, tools, citations, and policy flags.
3. Add an LLM judge only for final wording quality, not safety-critical route assertions.
4. Store model/prompt versions and results.
5. Run the suite and retain failures honestly.
6. Commit: `test: establish agency safety and routing eval suite`.

**Phase 1 exit test:** Real Telegram booking reaches a sandbox calendar and Dodo checkout; a deliberate guarantee is rejected and revised; both traces are visible.

---

## Phase 2 — Operations console, evaluation gate, and role spawning (target: 2 hours)

### Task 2.1: Build Cases and trace-tree views

**Files:**
- `console/src/pages/Cases.tsx`
- `console/src/components/TraceTree.tsx`
- UI tests.

**Steps:**
1. Render live case feed with filters.
2. Render plan nodes, steps, tool calls, bounces, costs, latency, and status.
3. Redact sensitive payloads by default.
4. Add escalation inbox and resolution capture.
5. Commit: `feat: add live cases trace and escalation console`.

### Task 2.2: Build Team and Knowledge views

**Steps:**
1. Render role config, prompt version, model, tools, guardrails, and autonomy.
2. Enforce server-side role validation on edits.
3. Render KB cards, approval state, language, tags, source, and KB-gap queue.
4. Add approval/edit flow with audit actor.
5. Commit: `feat: add role and knowledge operations views`.

### Task 2.3: Implement prompt versioning and regression gate

**Steps:**
1. Save drafts separately from published versions.
2. On publish, run the deterministic and judge suites.
3. Compare against a pinned baseline and safety minimum.
4. Block publication on regression; preserve one intentional blocked attempt.
5. Show results and blocked-publish log.
6. Commit: `feat: gate prompt publication on evals`.

### Task 2.4: Implement run diff

**Steps:**
1. Select two version sets and one eval case.
2. Render aligned nodes by semantic task key, not database ID.
3. Highlight route, output, tool, cost, latency, and verdict differences.
4. Commit: `feat: add prompt run trace diff`.

### Task 2.5: Add safe role templates and bounded manager spawn

**Steps:**
1. Create pre-approved Insurance Desk and Marathi Communicator templates.
2. Manager may instantiate only a template; no arbitrary prompt/tool generation on the judged path.
3. Trace creation actor, source template, and first invocation.
4. Add three-step wizard backed by the same validation API.
5. Test that forbidden tools or missing escalation triggers block creation.
6. Commit: `feat: support guarded runtime role creation`.

**Phase 2 exit test:** Red-flag case escalates with a complete brief; eval regression blocks publish; v1/v2 diff renders; a template role created after kickoff handles a matching case.

---

## Phase 3 — Scheduled lifecycle, voice, deployment, and optional channels (target: 2 hours)

### Task 3.1: Implement durable lifecycle jobs

**Steps:**
1. Store scheduled tasks in Convex with due time and idempotency key.
2. Add no-show chase and day-2 check-in generators.
3. Send every generated message through the same compliance gate.
4. Add manual demo trigger and production cron endpoint with authentication.
5. Verify replay does not duplicate delivery.
6. Commit: `feat: add durable reviewed lifecycle messaging`.

### Task 3.2: Add ElevenLabs browser voice path

**Steps:**
1. Capture browser microphone audio with explicit consent state.
2. Send to a protected FastAPI endpoint.
3. Transcribe with ElevenLabs, ingest through the same case loop, synthesize the approved response, and play it.
4. Do not persist raw audio by default.
5. Add timeout and text fallback.
6. Commit: `feat: add elevenlabs voice interaction`.

### Task 3.3: Deploy and secure public surfaces

**Steps:**
1. Deploy Convex functions/schema.
2. Deploy console to Cloudflare Pages.
3. Deploy runner to the selected reachable runtime and place Worker/Tunnel in front if needed.
4. Configure secret stores, webhook secrets, CORS, rate limiting, request-size limits, and health checks.
5. Register Telegram and Dodo webhooks.
6. Run external smoke tests from a separate network/device.
7. Commit: `ops: deploy secured demo environment`.

### Task 3.4: Add WhatsApp only if the cut condition is met

**Condition:** Existing approved app, credentials, and webhook repointing are ready; estimated work remains under 15 minutes.

**Steps:**
1. Add a thin adapter mapping WhatsApp events to canonical ingest.
2. Verify signature and deduplicate message IDs.
3. Send only through the canonical outbound gate.
4. Otherwise document Telegram as the judged channel and skip without destabilizing the build.

**Phase 3 exit test:** Public console works; Telegram and Dodo webhooks are live; voice answers one approved KB question; lifecycle manual trigger sends exactly once.

---

## Phase 4 — Hardening and evidence (target: final 60–90 minutes)

### Task 4.1: Add reset and smoke scripts

**Files:**
- `scripts/reset_demo.py`
- `scripts/smoke_demo.py`
- `scripts/verify_env.py`

**Steps:**
1. Reset synthetic data without deleting configuration or evidence runs.
2. Verify required secrets/resources without printing secret values.
3. Exercise health, message ingestion, safe reply, trace, calendar sandbox, payment checkout, escalation, and scheduled job.
4. Commit: `test: add repeatable demo reset and smoke checks`.

### Task 4.2: Run security, privacy, and failure-mode review

**Checks:**
- No secrets in Git or frontend bundle.
- No real PII in seed data or screenshots.
- Invalid webhook signatures rejected.
- Duplicate webhooks are idempotent.
- Unreviewed/modified drafts cannot send.
- Red flags always escalate.
- Model/tool timeout creates a useful escalation.
- Cost and step-count caps terminate loops.
- Linkup cannot query outside allowlisted domains.
- Browser microphone requires explicit action.

### Task 4.3: Rehearse the judge path twice from cold state

**Run sequence:**
1. Reset demo.
2. Telegram pricing + Saturday booking.
3. Select real slot.
4. Open Dodo test checkout.
5. Show calendar event.
6. Run deliberate overclaim bounce.
7. Run red-flag escalation.
8. Run voice KB question.
9. Show prompt diff and blocked publish.
10. Create Insurance Desk from template and route a case.
11. Trigger no-show job twice and prove only one send.

Record actual timings, failures, and recovery steps in `docs/demo-runbook.md`.

### Task 4.4: Final checkpoint

Run:
- Python unit/integration/contract tests.
- Type checks and linters.
- Console unit tests and production build.
- Playwright happy-path tests.
- Sandbox integration smoke test.
- Secret scan and `git status`.

Commit: `release: harden clinic agency demo`.

---

## 5. Test and validation matrix

| Area | Required proof |
|---|---|
| Ingestion | Valid webhook accepted; invalid signature rejected; replay deduplicated |
| Planning | Different request types produce structurally different bounded DAGs |
| Safety | Red flag escalates before generic response; LLM cannot suppress it |
| Compliance | Overclaim and wrong price rejected; revised exact hash approved |
| Knowledge | Approved cards cited; unapproved card excluded; unresolved query creates KB gap |
| Booking | Eligibility map respected; availability rechecked; duplicate event prevented |
| Payment | Test checkout generated once; signed webhook updates case |
| Memory | Case, synthetic patient history, and policy version survive handoffs |
| Lifecycle | Scheduled message is compliance-reviewed and idempotent |
| Evals | Safety assertions deterministic; prompt regression blocks publish |
| UI | Live trace updates, filters work, escalation resolves, diff highlights divergence |
| Voice | Audio transcription enters canonical loop; only approved response synthesized |
| Privacy | No real patient PII; traces sanitize inputs/outputs; audio not retained by default |
| Reliability | Tool/model timeout retries twice then escalates with blocker |

---

## 6. Build order if time is constrained

### Never cut

1. Deterministic red-flag escalation.
2. Exact-draft compliance gate and visible bounce.
3. Trace tree from the first step.
4. Eval gate with one real blocked publish.
5. Real calendar sandbox and Dodo test checkout.
6. Full escalation brief.
7. Telegram vertical slice.

### Cut in this order

1. WhatsApp.
2. Wizard visual polish.
3. Admin alert ping.
4. One-click captured-failure-to-eval flow.
5. Voice STT; retain a pre-recorded or TTS-only fallback only if clearly disclosed.
6. Advanced embedding retrieval.

Do not claim a power-up as working unless its live integration is exercised successfully.

---

## 7. Key risks and mitigations

1. **Eight-hour scope is highly aggressive.** Treat it as a hackathon MVP and freeze scope after Phase 0. Keep every integration behind an adapter and test against fakes before live credentials.
2. **LLM safety is probabilistic.** Enforce critical rules in deterministic code and use the Compliance model as an additional reviewer.
3. **External API setup may dominate time.** Verify credentials and sandbox resources before coding; skip optional channels early.
4. **Calendar/payment partial failure.** Use idempotency keys, record external IDs, and escalate with a concrete recovery action.
5. **Role spawning can expand privileges.** Permit only approved templates in the demo; require human publication for arbitrary roles.
6. **Public clinic web content may not be approved policy.** Cite it, label provenance, and require approval for pricing/clinical instruction cards.
7. **Logging may expose sensitive data.** Use synthetic identities, redaction, digests, and short retention; never log secrets.
8. **Voice latency may hurt the demo.** Stream or show status, cap timeouts, and provide a text fallback.
9. **Prompt/version comparisons may be noisy.** Pin models/settings and separate deterministic pass/fail from LLM-judge quality scores.
10. **A frontend-only autonomy dial could bypass controls.** Validate all mutations server-side and make compliance bypass impossible in schema/domain logic.

---

## 8. Open questions to resolve in the kickoff

1. Is the goal an eight-hour judged demo, a production pilot, or both? The plan treats eight hours as the demo and production hardening as a later milestone.
2. Which calendar is already credentialed: Google Calendar or Cal.com?
3. Where will FastAPI run publicly? Cloudflare Pages cannot host the Python runner itself.
4. Which hosted model provider and exact models are approved?
5. Is Dodo test mode sufficient, or must a real outsider complete a real payment?
6. Are Linkup-derived pages allowed directly in responses, or must imported content be human-approved first?
7. Who is authorized to approve medical red flags, pre/post-care wording, and claims policy?
8. What exact response should a red-flag patient receive while the human is paged?
9. Should calendar events be created before deposit payment, held tentatively, or created only after payment confirmation?
10. Which languages need full policy-approved demo coverage: English, Hindi, Marathi, or all three?
11. What data-retention period is acceptable for demo messages, traces, and synthesized audio?
12. What is the per-case cost cap and acceptable response latency?

---

## 9. Immediate kickoff checklist

The fastest safe start is:

- [ ] Owner supplies repository destination and confirms eight-hour demo scope.
- [ ] Owner chooses Google Calendar or Cal.com and provides a test resource.
- [ ] Owner provides secrets through secure environment/platform stores.
- [ ] Owner provides or approves the clinic policy pack and red-flag wording.
- [ ] Hermes saves the founding brief and scaffolds the monorepo.
- [ ] Hermes writes the first safety tests before implementing the agent loop.
- [ ] Hermes wires Telegram → Convex → stub-reviewed reply and proves idempotency.
- [ ] Hermes replaces the stub with the bounded role-runner and compliance gate.
- [ ] Hermes integrates calendar and Dodo only after the safety and trace paths pass.
- [ ] Every working checkpoint is tested and committed with a descriptive message.

## Definition of ready to begin

Implementation can start as soon as these six items exist: **repo/path, calendar choice and sandbox, Telegram token, Convex project access, model credentials, and an approved minimum policy pack** (pricing, hours, doctor map, booking/deposit rules, red flags, and safe wording). Cloudflare, Dodo, ElevenLabs, and Linkup can be connected as soon as their credentials arrive; their absence should not block the local walking skeleton.
