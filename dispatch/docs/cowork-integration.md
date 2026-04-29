# Cowork × Dispatch Harness — Integration Reference

> **Status:** Design reference, not yet implemented.
> **Audience:** Operator (Seth) + future agents extending the dispatch ecosystem.
> **Last refreshed:** 2026-04-28
> **Format:** Six scenario specs, grounded → stretch.

---

## 1. Context

The Dispatch Harness already coordinates the operator's daily workflow through tightly-integrated sub-skills (`/mr-review`, `/jira`, `/dispatch-notebook`, `/beads`, `/agenteer`, etc.) connected via well-defined contracts: YAML frontmatter on `review.md`, JSON sidecars on `mentions_latest.*`, and a SQLite state store at `~/.zsh/dispatch/dispatch.db`. Every step writes durable artifacts to `~/.zsh/dispatch/{dashboards,briefings,…}/` and `~/.zsh/review/YYYY/MM/DD/`.

Claude Cowork is Anthropic's desktop autonomous-knowledge-work agent — it operates a local sandbox folder, drives the operator's screen via computer-use, runs scheduled tasks, and produces polished knowledge-work deliverables (Word, Excel, PowerPoint, formatted markdown). It is **not** a programmatic platform: there is no public REST API, MCP server, webhook surface, or service-account auth. Cowork runs as the logged-in user on a desktop that must be unlocked when scheduled tasks fire.

The integration this document describes is therefore deliberately **loose**. Dispatch will not call Cowork. Cowork will not call dispatch. Instead, both halves of the workflow agree on a shared sandbox directory and a small frontmatter contract, exactly the way `/mr-review` and `/dispatch` already cooperate today — except the consumer (Cowork) is a UI, not a script.

## 2. Cowork Constraints That Shape The Design

The integration must be designed around these realities, not around a wished-for SDK:

| Constraint | Implication for dispatch integration |
|---|---|
| **No programmatic API** | Hand-off is file-based only. Dispatch writes; Cowork reads. No webhooks, no callbacks, no "wait for completion." |
| **Desktop-only execution; computer must be unlocked for scheduled tasks** | Cowork is unsuitable for unattended/cron-style work. Treat it as a co-worker who clocks in when the laptop opens. |
| **OAuth tied to a single user; no service accounts** | All Cowork output is "from Seth," not "from a bot." Audit trail lives in Cowork's project, not in dispatch.db, unless dispatch later ingests Cowork outputs. |
| **Quota-heavy: complex sessions cost dozens of message-equivalents** | Use Cowork for high-leverage synthesis (memos, slides, briefings) — not for things dispatch already produces (dashboards, finding lists). Don't double up. |
| **Sandbox is a single local folder per project** | Pick one canonical hand-off path (proposed: `~/Cowork/dispatch/`). Subdirectory per scenario. Idempotent writes. |
| **Outputs live in Cowork's project; no export API** | If dispatch needs to ingest a Cowork deliverable (e.g., re-attach a memo to a Jira ticket), the operator must drop the file back into a watched directory. |
| **Cowork has enterprise connectors (Drive, Gmail, DocuSign, FactSet)** that dispatch lacks | Use Cowork to *bridge* dispatch outputs to systems dispatch can't reach. This is the most underrated capability. |

The asymmetry is the design: **dispatch is the factory, Cowork is the delivery vehicle**.

## 3. The Hand-Off Contract

A single new dispatch step (`cowork_packet_render`) produces a structured packet under `~/Cowork/dispatch/<YYYY-MM-DD>/<scenario>/`. Each packet directory contains:

```
~/Cowork/dispatch/2026-04-28/stakeholder-replies/
├── BRIEF.md                  ← Cowork's instructions, written for a human-readable agent
├── inputs/
│   ├── mentions.json         ← Verbatim copy from ~/.zsh/jira/exports/mentions_latest.json
│   ├── mr_findings.json      ← Filtered subset of findings.json (only relevant MRs)
│   └── tasks.json            ← Filtered subset of dispatch.db tasks (only relevant tickets)
├── context/
│   ├── ticket_DSP-8154.md    ← Optional: full ticket text + recent comments
│   └── ticket_DSP-8172.md
└── outputs/                  ← Cowork writes its deliverables here; dispatch doesn't touch
```

**Frontmatter contract on `BRIEF.md`** (deliberately mirrors the dispatch dashboard frontmatter so future automation can introspect it):

```yaml
---
date: 2026-04-28
scenario: stakeholder-replies
generated_by: dispatch.cowork_packet_render
generated_at: 06:30 MST
expires_at: 2026-04-30
inputs:
  - inputs/mentions.json
  - inputs/mr_findings.json
expected_outputs:
  - outputs/replies.docx        # Cowork is asked to produce this
  - outputs/audit.md            # Required: a one-line summary of what Cowork did
guardrails:
  - "Never auto-send. All outputs are drafts for operator review."
  - "Do not invent ticket numbers, customer names, or commit hashes."
  - "If a reply requires information not in inputs/, mark [NEEDS-INFO] and stop."
---
```

The `outputs/audit.md` requirement is non-negotiable: it is what enables a later dispatch step to fold Cowork's contribution back into the morning dashboard's "Since Yesterday" section and into knowledge entries.

## 4. Six Workflow Scenarios

The first three are grounded in the operator's current dispatch records. The last three imagine Abacus Insights' product evolving over the next 2–3 years and stretch the integration accordingly.

---

### Scenario 1 (Grounded): Stakeholder Reply Drafter

**Problem this solves.** The 2026-04-27 dashboard surfaces 7 unreplied Jira @mentions older than 48 h, with stakeholders waiting up to 132 h (Jeena Budhachhetri on DSP-8013). Composing context-aware replies to seven different stakeholders across DSP-8013/8070/8151/8154/8172/MOON-152 is the highest-ROI action of the morning, but it's also the kind of repetitive, low-novelty cognitive work that consumes the most operator time.

**The flow.**
1. New dispatch step `cowork_packet_render --scenario=stakeholder-replies` runs after `jira_mentions` in the morning workflow.
2. It writes a packet to `~/Cowork/dispatch/2026-04-28/stakeholder-replies/`. `inputs/mentions.json` is the verbatim `mentions_latest.json`. `context/ticket_<KEY>.md` is fetched per-ticket via `jiratui issue show` for the most recent 5 comments + description.
3. `BRIEF.md` instructs Cowork to draft one reply per unreplied mention, in the operator's voice (style sample provided), in Word format with `[NEEDS-INFO]` placeholders for facts not in the packet.
4. Cowork — when the operator opens the laptop — fires its scheduled task or is launched manually. It writes `outputs/replies.docx` and `outputs/audit.md`.
5. Operator reviews each reply, pastes into Jira, marks the ticket. A subsequent `dispatch.cowork_ingest` step reads `audit.md`, marks the corresponding tasks as touched in `dispatch.db`, and folds a "Replied to N stakeholders via Cowork" entry into tomorrow's "Since Yesterday."

**Why this is the right shape.** Reply drafting requires reading three places (Jira ticket, mention context, prior exchanges), holding tone, and producing seven discrete artifacts. Dispatch already aggregates the inputs; Cowork is unusually good at the synthesis-into-prose step. Critically, **nothing is auto-sent** — the integration is read-only on Jira's side, and the operator stays the accountable communicator.

**Best-practice notes.** Idempotent packet name (date + scenario), `expires_at` so old packets are auto-cleaned, `[NEEDS-INFO]` discipline so Cowork doesn't fabricate.

---

### Scenario 2 (Grounded): Weekly Team-MR Triage Memo

**Problem this solves.** The 2026-04-27 dashboard counts 27 team MRs, 11 non-draft, with 4 failed pipelines and 4 conflicts. The dashboard is excellent for the operator's own consumption but is a poor artifact to bring to a team huddle, an EM 1:1, or a "what's blocking us this week" Slack thread. The information density is wrong for those audiences.

**The flow.**
1. A new EOD-Friday step (or a `/dispatch step cowork_triage_memo` on demand) packages the week's `~/.zsh/review/2026/04/*/team/*/findings.json` plus the relevant `review.md` frontmatter.
2. `BRIEF.md` instructs Cowork to produce **two** deliverables: a one-page Word memo grouping MRs by *blocker class* (pipeline, conflict, stale-review, awaiting-approval, awaiting-author) with author callouts, and a 6–8 slide PowerPoint suitable for a 10-minute walk-through. The slides should embed deep-links to GitLab pipelines and MRs (Cowork can construct these from the JSON).
3. Cowork's enterprise Google Drive connector (if enabled) drops the deliverables in the team's shared drive at a known path.
4. `audit.md` summary is folded back into dispatch knowledge with category=`pattern`, key=`weekly_triage_topics_<YYYY-WW>`, value=top 3 blocker classes — so Optimus can see whether the same blockers recur week over week.

**Why this is the right shape.** Dashboards are diagnostic; memos are persuasive. Producing a polished, audience-shaped artifact from the same underlying data is exactly Cowork's strength, and it removes a recurring 30–45 minute task from the operator's week. The blocker-class taxonomy fed back into dispatch.db starts producing quantitative trend evidence Optimus can reason about.

**Guardrails.** No customer names in the memo unless they appear in MR titles already. The Drive upload step is opt-in per run via `BRIEF.md`. If `findings.json` is empty for a given week, the step short-circuits.

---

### Scenario 3 (Grounded): Idle-P1 Decision Memo Drafter

**Problem this solves.** Two P1 tasks have been IN_PROGRESS without movement for over a week — DSP-6199 (Helm Chart OCI caching, 7 d) and DSP-8109 (region-aware repo URL mismatch, 9 d). The dashboard's SLA Watchlist surfaces them but doesn't help unblock them. Often these tasks stall because the operator is one decision (or one stakeholder ask) away from progress, but writing the formal "what we know / options / recommendation" memo is the friction.

**The flow.**
1. New step `cowork_packet_render --scenario=p1-decision-memo --ticket=<KEY>` triggered ad-hoc when the SLA Watchlist flags an idle P1.
2. The packet includes: full Jira ticket export, the relevant `briefings/YYYY-MM-DD.md` sequencing-risks subsection, any related MR review.md files, and dispatch knowledge entries tagged with the ticket.
3. `BRIEF.md` requests a 1–2 page decision memo in the structure *Context · What We Know · Open Questions · Options A/B/C with tradeoffs · Recommendation · Asks*. Word format. Cowork is told who the audience is (e.g., infrastructure lead, principal engineer, customer success).
4. Cowork's Gmail connector (if scoped) drafts an email with the memo attached, but **leaves it as a draft** in the operator's outbox. Auto-send is forbidden.
5. The decision memo's existence and audience are recorded in `dispatch.db` knowledge as `category=decision`, so a future Optimus run can correlate "memo written → ticket moved within N days?" and tune SLA thresholds.

**Why this is the right shape.** The idle-P1 anti-pattern is well-documented in the dispatch records (multiple tasks > 7 d). The bottleneck is rarely technical understanding — it's the cost of formalizing a stakeholder ask. Cowork's structured-document output and Gmail connector remove almost all of that friction while leaving the actual decision to send firmly with the operator.

**Failure mode to design for.** If the packet contains a `[NEEDS-INFO]` flag (e.g., "we don't know whether us-west-2 has the same DNS pattern as us-east-1"), Cowork must surface that as the *first* line of the memo, not bury it. `BRIEF.md` instructs explicitly.

---

### Scenario 4 (Stretch, ~2027): Multi-Project Portfolio Briefing for Leadership

**Imagined product evolution.** By 2027, Abacus Insights has expanded its NextGen platform across three platform-suites (kitchen / lunatic-dove / abacus-v2) and the operator's role has grown to coordinator-of-coordinators across multiple sub-teams. Each sub-team runs its own dispatch instance against its own GitLab group and its own Jira project. The operator's morning dashboard is still personal-scope; it doesn't roll up portfolio-level signal.

**The flow.**
1. Each sub-team's dispatch instance emits its dashboard + a sanitized `portfolio_packet.json` to a shared `~/Cowork/portfolio/<YYYY-MM-DD>/<team>/` directory (sanitization strips PII, customer names, security findings — same redaction the dispatch-notebook skill already does for NotebookLM uploads).
2. A new Cowork scheduled task — fired weekly — synthesizes all three teams' packets into a single executive briefing: a 3-page memo plus a 12-slide deck. It includes cross-team sequencing risks (Helm releases that affect both kitchen and lunatic-dove), shared incident postmortems, and cumulative SLA performance against agreed-upon thresholds.
3. The deck is auto-uploaded to a leadership-shared Google Drive folder. Slack notifications go to the leadership channel **only** with a link, never the content.
4. After leadership reviews, follow-ups are captured in dispatch as `category=decision` knowledge entries with `ticket=PORTFOLIO-<week>`, providing the Optimus pipeline with cross-team optimization signal it currently lacks.

**Why this stretches the integration.** Today's dispatch is single-operator. This scenario assumes (a) multiple dispatch instances writing to a shared location, (b) Cowork operating across multiple sandboxes — which Anthropic has signaled is plausible — and (c) a redaction contract that gives the integration a defensible answer to "how do we share signal across teams without leaking customer-bound information." The redaction layer is the hard, valuable part of the design and is worth building even before Cowork can fully consume it.

**Guardrails worth designing now.** The redaction contract should ship with a test fixture (`redaction_golden_set.yaml`) so any drift is caught. The leadership deliverable contains a versioned hash so regressions are detectable.

---

### Scenario 5 (Stretch, ~2027): Customer-Facing Release Communications Desk

**Imagined product evolution.** Abacus's deployment cadence has moved from quarterly to weekly. The `/bacon` skill already automates the release-mechanics half (Jira CMD ticket, GitLab MR, Slack comms internal); but each release also needs a customer-shaped artifact: a Gainwell-flavored release note, an Optum-flavored impact summary, a Moonshot-flavored migration callout. Today this is hand-crafted by CSMs from the internal release notes. By 2027 Abacus has 30+ customers.

**The flow.**
1. The bacon skill's release-completion artifact (today: an internal Slack post) is extended with a `customer_packet.json` mapping each customer org to the components they consume (already inferable from Helmsman manifests + airflow-provision configs).
2. Cowork is scoped a customer-comms project per customer — e.g., `~/Cowork/customer-comms/gainwell/`, `…/optum/`, `…/moonshot/` — each pre-loaded with that customer's contract terminology, prior release notes (style sample), and contact list.
3. On bacon completion, dispatch writes a single multi-customer packet; Cowork — when fired — produces one tailored deliverable per customer (Word doc + suggested email subject/body) with the **customer-specific impact statements** computed from the manifest diff.
4. A CSM (or the operator) reviews and sends. Cowork's Gmail connector handles the actual send only after explicit click-through; no auto-send.
5. Sent / not-sent / customer-replied status is folded back into dispatch.db as a new `customer_comms` table so Optimus can detect "we keep failing to communicate XYZ component changes to Optum on time."

**Why this stretches the integration.** This scenario is plausible only if Cowork by 2027 supports either (a) cross-project orchestration or (b) a more usable per-customer scope-switching primitive. Neither exists today, but both are natural product evolutions. The integration's design value is that it **forces the manifest-to-customer mapping to become first-class data** — that mapping is already implicit in the operator's head and in airflow-provision; surfacing it as a JSON contract is itself worth the build, even before Cowork can fully leverage it.

**Critical guardrail.** A customer-comms send is the highest-blast-radius action in the entire ecosystem. Auto-send must remain forbidden. The integration design should make sending *strictly more friction* than reviewing-then-sending, not less, until trust is earned over many manual cycles.

---

### Scenario 6 (Stretch, ~2028): Self-Service Insights Lab — Dispatch As Public-API Producer

**Imagined product evolution.** Abacus offers customers a "self-service insights lab" — a hosted environment where customers' analysts can use AI to interrogate their own data alongside Abacus-curated reference data. The lab runs on each customer's infrastructure and uses Cowork (or a successor) as the analyst-facing surface. Internally, dispatch's role evolves: it becomes the **factory that produces sanitized, customer-shaped intelligence packets** that the lab consumes.

**The flow.**
1. Dispatch grows a new mode `--mode=lab-pack`: it runs nightly per customer, queries Optimus for findings tagged for that customer's verticals (CMS-FFS, Medicaid, FITE, etc.), gathers anonymized deployment-risk signals from `bottlenecks` and `optimus_findings` tables, and writes a `lab_pack/<customer>/<YYYY-MM-DD>.json` artifact.
2. Each customer's Cowork lab session has read access to its own lab pack (and only its own) via a sandbox isolation that the lab's runtime guarantees. Customer analysts query their data, optionally pulling in the lab pack's intelligence as context.
3. Cowork produces customer-side deliverables — KPI dashboards, predictive deployment-risk reports, regulatory-compliance attestations — directly to the customer's tooling (Looker, Power BI, Sigma).
4. Anonymized usage telemetry comes back into Abacus's internal Optimus pipeline (which features the customer most-asked-about, which signals are most consumed) — strictly aggregated, never per-analyst — and informs Abacus's product roadmap.

**Why this stretches the integration.** This is dispatch evolving from "personal workflow tool" to "internal data product." Doing it well requires building, today, the discipline of treating dispatch outputs as **versioned, schema-validated artifacts with strict redaction contracts** — exactly the hygiene the earlier scenarios already start enforcing. The PII boundary, the customer-isolation boundary, and the "what does dispatch know that we'd let a customer see, ever?" question are the architectural questions worth answering early, even if the lab itself is years away.

**Failure modes that must be designed against.** Cross-customer leakage (sandbox isolation, cryptographic per-customer keys), training-data contamination (customer queries must not influence Abacus's internal Optimus weights), and brittle schema evolution (lab packs must remain backward-compatible across multiple customer-side Cowork versions). Each of these is a real engineering investment, not a "nice to have."

---

## 5. Operational Best Practices

Across all six scenarios, the same disciplines apply. Build them in once; reap them six times.

- **One sandbox per scenario, dated subdirectory, idempotent writes.** Never mutate a packet after it's written; if regeneration is needed, write a new dated dir.
- **`BRIEF.md` is a contract, not a chat prompt.** Use frontmatter, named output paths, explicit guardrails. Cowork should fail loudly if `BRIEF.md` is malformed.
- **Every Cowork hand-off requires `outputs/audit.md`.** This is dispatch's only signal that work happened. Without it, Optimus is blind.
- **`expires_at` on every packet** so a janitor step can prune stale sandboxes. Default: 14 days for grounded scenarios, 30 days for stretch.
- **No auto-send anywhere.** Cowork can draft into Gmail and Slack; sending stays operator-driven until trust is earned over many manual cycles.
- **Redaction lives in dispatch, not in Cowork.** Anything sensitive must be stripped *before* it lands in `~/Cowork/`. Treat Cowork's sandbox as semi-public.
- **Knowledge fold-back is the integration's compounding value.** Each Cowork action that gets folded into `dispatch.db` knowledge — "drafted reply on DSP-8154," "decision memo sent to platform lead" — gives Optimus more signal next cycle.
- **Versioned schemas.** `lab_pack` v1, v2; `customer_packet` v1, v2. Bump explicitly; don't break consumers silently.
- **Test fixtures for every contract.** A redaction golden set, a frontmatter validator, a `BRIEF.md` linter. Without these, the integration drifts.

## 6. What Not To Build

A short, deliberate list of things that would *seem* like good integrations but aren't:

- **Don't try to wrap Cowork in an MCP server.** Anthropic doesn't expose one. Community shims exist; they break with every Cowork release.
- **Don't try to drive Cowork via computer-use from dispatch.** It's the wrong abstraction layer and creates an unauditable double-agent loop.
- **Don't put `dispatch.db` itself into a Cowork sandbox.** Pull only what's needed per scenario, redacted, in JSON. The DB has secrets, internal IDs, and operator-private state.
- **Don't let Cowork modify any dispatch artifact.** The arrow points one direction only: dispatch → packet → Cowork → outputs. If Cowork output needs to influence dispatch, the operator drops a file into a watched directory and a dispatch step ingests it explicitly.
- **Don't build per-scenario glue if the contract can be generic.** One `cowork_packet_render` step parameterized by `--scenario` is better than six separate steps.

## 7. Suggested Next Steps (when ready)

1. **Stand up `~/Cowork/dispatch/` and the `cowork_packet_render` step for Scenario 1.** It's the highest-ROI per the current dashboard and exercises the whole contract end-to-end.
2. **Write the `BRIEF.md` linter** as a `scripts/cowork_brief_lint.py` in dispatch, before the first packet ships. Cheap to write, prevents an entire class of silent failures.
3. **Add a `cowork_audits` table** to `dispatch.db` schema and an `ingest_cowork_audits` step that reads `~/Cowork/dispatch/*/*/outputs/audit.md` files. This closes the loop and makes Optimus aware of Cowork contributions.
4. **Author a redaction module** (`scripts/redact.py`) covering customer names, PII patterns, internal-only ticket prefixes. Use it from Scenario 1 onward, even if minimally — the muscle memory is the point.
5. **Defer Scenarios 4–6 until at least one grounded scenario has run for 30+ days.** Stretch scenarios are valuable as architectural compass points, not as immediate work.

---

*This document should be revisited when (a) Cowork ships a programmatic API or MCP server, (b) the operator's role expands to multi-team coordination, or (c) Abacus's product roadmap commits publicly to a customer-facing AI lab. Each of those events significantly changes the design space.*
