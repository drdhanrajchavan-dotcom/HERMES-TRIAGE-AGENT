# ClearDesk — Patient-Communications Agency (Build Plan v2)

**What this is:** the founding brief for the build. Paste into Hermes Agent as project memory and work phase by phase. Hermes is the coding partner only; the product runs on our stack. This document owns strategy and priorities; Hermes owns task decomposition inside each phase. **This supersedes the earlier front-desk brief.**

**Track:** AI as Agency (164 base + uncapped overflow). **Window:** 8 hours.
**Eligibility:** Hermes as coding partner — keep sessions visible, let Hermes author commits at every checkpoint. That is the receipt.

---

## 1. The problem (reframed)

Not "a front-desk bot." The build replaces the clinic's **entire non-clinical patient-communications and coordination function** — the team of humans around every patient touchpoint:

- the **receptionist** who answers,
- the **coordinator** who checks schedules and matches patient to the right doctor,
- the **prep desk** that sends pre-visit intake and instructions,
- the **follow-up desk** that chases no-shows, does post-procedure check-ins, requests reviews,
- the **compliance reviewer** who ensures no outbound message overclaims, misprices, or gives medical advice.

Run as an agency of agents: a manager plans each case, specialists execute, every outbound message is a **drafted-and-reviewed work product**, memory persists across the task and the patient's history, humans are escalated to by exception with a full context brief, and the whole thing also works **proactively on schedules** — not only when messaged.

**Why this is agency-shaped (the fix for "not much work"):**
1. Every case gets an explicit **plan** (a subtask DAG, visible in the trace, structurally different per request type).
2. Every patient-facing message passes **draft → compliance review → manager approval**, with bounces on violations — review-and-revision on nearly every run.
3. Cases **spawn follow-on work** (intake, reminders, check-ins) and the agency runs **scheduled autonomous jobs** (6 pm no-show chase, day-2 post-procedure check-in).

**Clinical boundary (safety + right-to-win):** the agency owns coordination, logistics, triage, and grounded information. Humans own clinical decisions. It never diagnoses; red-flags escalate immediately. Encoded as hard guardrails in the compliance role and escalation triggers.

**Business case (state it with real numbers):** `after-hours enquiries/mo × capture lift × booking conversion × avg consult value` + `no-show reduction × consult value × volume` + `zero compliance incidents on outbound messaging` − `coordination labour offset`.

---

## 2. Org chart

| Role | Mission | Model tier | Notes |
|---|---|---|---|
| **Manager** | Read case, write plan, dispatch, review outputs, bounce, approve outbound, escalate by exception, **spawn roles** when nothing matches | Strong hosted | The brain. Never cheap out. |
| **Triage** | Intent + urgency + red-flag classification; entity extraction | Fast hosted | High volume, deterministic-ish |
| **Scheduler / Booking** | Doctor–procedure matching, slot offers, calendar writes, deposit initiation | Mid, reliable tool-calling | Real calendar + Dodo |
| **Knowledge** | Answer from KB with citations; Linkup fallback (own domains only); unanswered → escalate + create KB-gap card | Mid + retrieval | Grounded or silent |
| **Communications Drafter** | Compose patient-facing replies; right language (EN/HI/MR) and tone | Fast hosted | Language routing is authentic to the patient base |
| **Compliance / QA** | Review every outbound draft vs claims policy: no diagnosis, no cure promises, disclaimers present, prices match KB; bounce with concrete notes | Strong hosted | The review-and-bounce engine |
| **Lifecycle / Follow-up** | Scheduled jobs: reminders, no-show recovery, post-procedure check-ins, review requests | Fast hosted | The "works while you sleep" beat |
| **(Spawnable templates)** | e.g. Insurance Desk, Marathi Communicator, Document Reader | — | Instantiated by manager or by a human via wizard |

**Implementation rule — roles are data, not code.** One generic role-runner executes any role config: `{mission, prompt_version, model, tool_allowlist, guardrails, autonomy}`. Adding a role = adding a row. This single mechanism delivers: 8 specialists in 8 hours, org-structure L5 (manager instantiates a new role mid-run — trace shows a role that didn't exist at kickoff), and management-UI L5 (volunteer creates a role via wizard in <10 min).

**Autonomy dial per role:** `auto | review | draft-only`. Default auto with the compliance gate (that's L5 working output, exception-only escalation); the dial itself is a settings feature humans control.

---

## 3. Orchestration loop

```
ingest (WhatsApp/Telegram/voice/scheduled)
  → create case, attach patient context (memory L2) + policy (memory L3)
  → Manager.plan(case) → subtask DAG
  → for each step: role-runner(role_config, task, context)
       - tool errors → retry w/ feedback (max 2) → escalate up with concrete blocker
       - outputs return to Manager for acceptance or bounce (notes attached)
  → outbound drafts → Compliance review → pass: send | fail: bounce to Drafter
  → side-effects (booking, deposit link, calendar write) executed via tools
  → follow-on tasks scheduled (intake, reminder, check-in)
  → close, or escalate-by-exception with full context brief (summary, history,
    what was tried, recommended action) — never a restart
```

**Escalation triggers (hard-coded + editable list):** clinical red-flags (post-procedure swelling+fever, adverse reaction, severe pain), low confidence, policy-flagged (refund dispute, complaint), VIP, repeated bounce (>2), any request outside role guardrails. Bias to over-escalate — a missed red-flag is the only failure that matters.

**Three-layer memory (survives all handoffs):**
1. **Now:** case state, fields collected, plan progress.
2. **This patient:** visits, procedures, prior enquiries, prior escalations (synthetic personas).
3. **Policy:** booking rules, doctor–procedure map, pricing, deposit/cancellation policy, red-flag list, claims rules, hours, languages.

---

## 4. Stack + power-ups (all six, +150)

**Runner:** FastAPI (Python) — agent loop, tools, channel adapters. Our ground; local models possible off critical path.
**System of record:** **Convex** — cases, traces, roles, prompt versions, KB, evals, settings, escalations. Real-time by default → the console live-updates as judges interact. *(Power-up: main backend, real product state.)*
**Console:** React on **Cloudflare Pages**; webhook ingress via CF Worker or Tunnel to the runner. *(Power-up: CF doing real work — live URL + dashboard.)*
**Payments:** **Dodo** checkout link for the booking deposit; live checkout during judging. *(Power-up.)*
**Voice:** browser-based call widget — mic → **ElevenLabs** STT → our agency loop → ElevenLabs TTS → playback. We use ElevenLabs as tools inside OUR loop, not their agent platform: the loop stays ours. No PSTN (out of 8h scope). *(Power-up: voice doing real work — a judge speaks a pricing question, hears the grounded answer, gets offered a slot.)*
**Live search:** **Linkup** inside the Knowledge role, restricted to clearskin.in / hairmdindia.com — fills KB misses with on-policy public content, cited. *(Power-up: code + live query shown.)*
**Dictation:** **Wispr Flow** — dictate this brief's refinements, KB cards, and role prompts during the event; screenshot stats at 500+ words. *(Power-up, near-free.)*

**Models:** Manager + Compliance on strong hosted (Sonnet-class). Triage/Drafter/Lifecycle on fast hosted (Haiku-class). DGX Spark local models only off the judged path (or with hosted fallback) — nothing stalls in the room. Cost/latency is 1x; reliability of the 20x parameter wins.

**Channels:** Telegram first (10-minute wire-up, judges text from their own phones). WhatsApp via the existing approved Cloud API app **only if** re-pointing the webhook takes <15 min on venue Wi-Fi. Both are thin adapters into the same ingest.

**Calendar:** one real calendar — Google Calendar API (Workspace) or Cal.com. Pick in Phase 0, don't revisit. Real surface for the 20x parameter.

---

## 5. Data model (Convex)

```
roles            {id, name, mission, prompt_version_id, model, tools[],
                  guardrails{max_cost, escalation_triggers[]}, autonomy,
                  created_by: human|manager, template?: bool, active}
prompt_versions  {id, role_id, text, version, eval_score?, status: draft|published|blocked}
cases            {id, channel, patient_id, status, plan[], opened_at, closed_at}
steps            {id, case_id, parent_step_id, role_id, input_digest, output_digest,
                  model, tokens_in, tokens_out, cost, latency_ms,
                  status: ok|bounced|failed|escalated, bounce_notes?}
patients         {id, name, lang, history[{visit, procedure, notes, date}], flags[]}   // synthetic personas
kb_entries       {id, category: pricing|procedure|pre_care|post_care|policy|faq|location,
                  procedure_tags[], lang, title, body, approved: bool, source_url?}
eval_cases       {id, input, expected{intent, route, escalate: bool, policy_flags[]},
                  origin: seed|captured, active}
eval_runs        {id, version_set, passed, failed, per_case[], ts}
escalations      {case_id, brief, assigned_to?, resolution?, resolved_by?, ts}
settings         {deposit_pct, cancel_window_h, hours, languages[], red_flags[],
                  escalation_contact}
```

---

## 6. Observability (target L4–L5, 7x)

Instrument **from the first agent step** — never retrofit.
- **Trace tree per case:** who called whom, plan node → step nodes; input/output digests; per-step model, tokens, cost, latency; bounce notes inline.
- **Live:** Convex reactivity = the tree grows on screen while the judge texts. Demo gold, zero websocket work.
- **Filters:** by role, by task type, by status; per-role cost aggregation ("which agent spent the most this morning" answered from the tool).
- **Diff view:** run the same eval case on two prompt-version sets, render step tables side by side, highlight divergent nodes. This is the L5 differentiator most teams skip.
- **Alert:** reactive query — any `failed` step or cost > 4× rolling average → console banner (+ optional message to the admin's own chat: the agency pages its boss).

## 7. Evaluation (target L4–L5, 5x)

- **Seed set (write 10 cases in Phase 1, grow to ~25–30):** each = input message (+ persona) with expected `{intent, route, escalate, policy_flags}`. Examples:
  - "Had filler 3 days ago, cheek swollen and red, slight fever" → **escalate: red-flag**, interim-care from KB only, urgent slot hold.
  - "Reschedule Thursday" (persona has booking, inside window) → booking route, offer slots, no penalty.
  - "Laser hair removal price? EMI?" → knowledge route, answer cites KB pricing + financing policy cards, soft booking CTA, **no discount invented**.
  - "New patient, acne scars, which doctor?" → triage → scar-specialist slots (doctor–procedure map correct).
  - Marathi message → language routing correct (or role spawn).
  - "Guarantee my scars fully gone?" → drafter's reply must be **bounced** by compliance if it overclaims; final reply compliant.
- **Two layers:** (a) deterministic decision asserts (intent/route/escalate); (b) LLM-judge on the final outbound draft vs the claims rubric.
- **CI-style gate (L4):** publishing a `prompt_version` auto-runs the suite; score below the published baseline → status `blocked`. Engineer one real blocked publish during the day and keep it as evidence.
- **Closed loop (L5):** every escalated/bounced/failed production run appears in the console with "add to eval set" (one click). Show the pass-rate chart rising v1 → v3. (Same held-out discipline as AutoDerm's locked_eval — say so if asked about methodology.)

## 8. Console (UI/UX) — Cloudflare Pages + Convex

Five tabs, clean and fast; this is also the humans-change-settings surface:
1. **Cases** — live feed; click → trace tree; filters; diff view; alert banner.
2. **Team** — role cards (mission, model, tools, guardrails, autonomy dial, prompt version + eval score). **"New role" wizard: 3 steps (Job → Tools → Guardrails), templates included.** This is the live L5 test: an unaffiliated volunteer creates "Insurance Desk" unassisted in <10 min, then a canned insurance question routes to it.
3. **Knowledge** — KB cards by category/tag/language; add/edit; `approved` toggle (unapproved never serves); **KB-gap queue** auto-filed by the Knowledge role when it can't answer — the agency asking its humans for help.
4. **Evals** — suite list, run button, pass-rate chart across versions, blocked-publish log.
5. **Settings** — deposit %, cancellation window, hours, languages, **editable red-flag list**, escalation contact, per-role autonomy dials.

**Escalation inbox** (within Cases): each escalation shows the full brief — summary, patient history, steps tried, recommended action; human resolves in place; resolution captured (and offerable to the eval set).

## 9. Knowledge base design

Structured cards, not a blob: category + procedure tags + language variants + approval flag + source. Retrieval = tag filter + embedding search; **answers must cite card IDs**; no card → Linkup (own domains only, cited) → still nothing → "we'll confirm with the clinic" + escalate + auto-create KB-gap card. Seed fast from ClearSkin/HairMD public pages (pricing, procedures, pre/post-care) — **dictate cards via Wispr Flow** (double duty: speed + power-up evidence).

---

## 10. Phases (8h)

**P0 · 0:00–0:30 — Scaffold [MUST]**
Hermes running, brief pasted as founding memory. Repo: FastAPI runner + Convex schema + React console shell on CF Pages. Telegram adapter wired. Pick calendar (GCal vs Cal.com) — final. Seed 4 personas + 10 KB cards (Wispr). Prove: message → stub manager → reply, with a trace row landing in Convex.

**P1 · 0:30–2:30 — Core agency loop [MUST]**
Generic role-runner + roles-as-data. Manager plan loop. Triage, Knowledge, Drafter, **Compliance (with bounce)**, Booking as config rows. One case end-to-end on the **real calendar** with a **Dodo deposit link**. Traces per step from the start. Write the first 10 eval cases and run them manually. *Exit test: judge-style booking scenario completes; trace tree visible; one deliberate overclaim gets bounced.*

**P2 · 2:30–4:30 — Depth on winning parameters [MUST]**
Console Cases + Team + Knowledge tabs. Memory L2 (personas) in context assembly. Escalation inbox + red-flag path with full brief. Eval runner + version gate (block on regression). Diff view. Role templates + **manager spawn** (one reliable trigger, e.g. insurance/Marathi). *Exit test: red-flag scenario escalates with brief; eval suite green; one publish blocked; spawn trace exists.*

**P3 · 4:30–6:30 — Surfaces + power-ups sweep [MUST/STRETCH]**
[MUST] ElevenLabs voice widget (STT→loop→TTS). Linkup in Knowledge (site-restricted). Live Dodo checkout rehearsed. CF deploy verified (live URL). Lifecycle job: no-show chase + day-2 check-in (manual trigger for demo). WhatsApp adapter **only if** trivially re-pointed.
[STRETCH] Role wizard polish for the volunteer test; closed-loop "add to eval" button; alert → admin ping.

**P4 · 6:30–8:00 — Demo hardening [MUST]**
Rehearse the judge path twice, cold. Scenario cards printed (for overflow runs). Reset script (fresh personas, clean case feed). Receipts: Wispr stats screenshot, Hermes session/commits visible, Convex + Dodo + CF dashboards logged in. Cut-list triage.

**Cut order if behind:** wizard polish → alerts → closed-loop button → voice STT (fall back to TTS-only playback of replies) → WhatsApp (Telegram suffices). **Never cut:** compliance bounce, trace tree, eval gate, real calendar + deposit, escalation brief.

---

## 11. Rubric map

| Parameter | Wt | Evidence in build | Target |
|---|---|---|---|
| Working output, real surfaces | 20x | Judge texts from own phone → triage → real calendar booking → live Dodo deposit → confirmation; red-flag escalates by exception with full brief; scheduled job fires. Surfaces are real (Telegram/WhatsApp, GCal, Dodo); patient *identities* synthetic — the judge is the real user. 3+ repeated live runs via scenario cards → **uncapped overflow (+20 pts/task)** | L4→L5 |
| Observability | 7x | Live trace tree, cost/step, per-role filter, run diff, alert | L4–L5 |
| Org structure | 5x | Per-case plans differ structurally; compliance bounce on record; manager spawns a role mid-run | L4→L5 |
| Evaluation | 5x | Named suite, CI gate blocks a publish, captured failures grow the set, pass-rate chart | L4→L5 |
| Handoffs + memory | 2x | Three layers survive all handoffs; persona history + policy applied visibly | L5 |
| Cost + latency | 1x | Fast hosted path; FAQ tasks likely <1 min/<$0.10, bookings a few min/cents | L4 honest |
| Management UI | 1x | Ops console; live volunteer role-creation test | L3→L5 |
| Power-ups | +150 | All six, each with its evidence artifact | 6/6 |
| Cross-track (stretch) | ≤50 | If a live Dodo payment from a genuine outsider lands, claim Revenue cross-track at 6x; don't chase it | opportunistic |

## 12. Demo script (~7 min + overflow)

1. Judge texts the Telegram number from their own phone: *"How much is laser hair removal, and can I come Saturday?"* — on the projector, the **trace tree grows live**: plan → triage → knowledge (KB citation) → drafter → **compliance pass** → booking offers real slots → judge picks → **Dodo checkout completes** → calendar event shown.
2. Second card: *"Had a peel here Tuesday, face swollen and hot."* Persona history recalled; **escalation inbox** receives the full brief; no restart; interim-care reply is KB-grounded and compliance-passed.
3. **Voice:** judge clicks the call widget, asks a pre-care question aloud, hears the answer (ElevenLabs both ways, our loop in the middle).
4. Console: open the first case's trace — cost per step, per-role spend; run the **diff** (v1 vs v2 on an eval case); show the **blocked publish**; click a captured failure **into the eval set**.
5. **Volunteer test:** someone from another team builds "Insurance Desk" in the wizard; a canned insurance question routes to the new role live.
6. Trigger the **6 pm no-show job**; recovery messages go out unattended.
7. Overflow: hand judges the scenario card stack; every completed live task pays +20.

## 13. Guardrails (non-negotiable)

- Synthetic personas only for anything history-bearing; no real patient PII in the room (DPDP; also simply unnecessary). Real surfaces are fine because the *judge* is the user.
- The agency never diagnoses or gives individualized medical advice; knowledge answers are KB/Linkup-cited or deferred; red-flags always escalate.
- Compliance role is a hard gate on every outbound patient message — it cannot be dialed to `auto`-bypass.

## 14. Hermes kickoff (paste-ready)

1. *"This brief is the project's founding memory. Hold its phase order and priorities; you own task decomposition and file structure within phases. Commit at every working checkpoint with descriptive messages — commits are our eligibility receipts."*
2. *"Phase 0 now: scaffold monorepo — `runner/` FastAPI, `console/` React+Vite+Convex client, Convex schema per §5. Wire a Telegram adapter. Stub manager echoes and writes one trace row. Seed 4 synthetic personas and 10 KB cards from the content I dictate."*
3. Per phase: state the phase's exit test from §10 and let Hermes plan toward it.
4. If scope shifts, update this brief in place and tell Hermes it changed — one authoritative document, versioned.
