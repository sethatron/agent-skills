# Interaction Modes Reference

## Table of Contents

1. [LEARN Mode](#learn-mode)
2. [QUIZ Mode](#quiz-mode)
3. [SCENARIO Mode](#scenario-mode)
4. [PROJECT Mode](#project-mode)
5. [MASTERY CHALLENGE Mode](#mastery-challenge-mode)
6. [STATUS Mode](#status-mode)
7. [PATH Mode](#path-mode)

---

## LEARN Mode

**Purpose:** Teach a topic from first principles, calibrated to the user's current level.

### Prerequisites

None — any topic can be learned at any time, though the mode will flag unmet prerequisites.

### Flow

1. **Look up the topic** in the knowledge base (Grep for the name, Read the topic block).
2. **Check the user's current status** on the topic.
3. **Check prerequisites:** if any prerequisite topic is below `conceptual`, flag it and offer to teach the prerequisite first. List which prerequisites are gaps. If the user wants to proceed anyway, continue but note where prerequisite knowledge would help.
4. **Teach the topic** calibrated to current status:
   - `not_started`: Start from the description. Explain WHY it exists, what problem it solves. Use `source_context` to ground the explanation. Connect to prerequisites the user has already learned. Use analogies and concrete examples.
   - `exposed`: Deepen understanding. Focus on mechanics, not just concepts. Connect to `related` topics. Introduce common misconceptions.
   - `conceptual` or higher: Focus on internals, tradeoffs, edge cases. When NOT to use it. Implementation details. Failure modes.
5. **Ask 1-2 open-ended verification questions.** NEVER yes/no. NEVER multiple choice. Questions must require the user to demonstrate understanding in their own words.
6. **Evaluate the user's response:**
   - **Correct and demonstrates understanding:** Update status. Record evidence.
   - **Partially correct:** Identify the specific gap. Re-explain that part. Ask a targeted follow-up.
   - **Incorrect:** Do not give the answer immediately. Identify the misconception. Re-approach from a different angle. Ask again.
7. **Summarize:** "You're now at [level] on [topic]. Related topics you might explore next: [related]."

### Status Update Criteria

| Current Status | Promotion | Condition |
|---------------|-----------|-----------|
| not_started | exposed | Completed the teaching interaction; user engaged with the explanation |
| exposed | conceptual | User correctly answered verification questions demonstrating understanding beyond restating definitions |
| not_started | conceptual | User demonstrated deep understanding during verification (skip exposed) — allowed as a 2-level jump |

A single LEARN session can advance at most 2 levels (not_started to conceptual).

### Output Format

Teaching content followed by verification questions. After evaluation, a summary line with the new level and suggested next topics.

---

## QUIZ Mode

**Purpose:** Test knowledge with targeted questions calibrated to the user's current level.

### Scope Selection

The user can specify scope by:
- **Topic:** "quiz me on veth pairs"
- **Category:** "quiz me on networking"
- **Tag:** "quiz me on linux topics"
- **Difficulty range:** "quiz me on difficulty 4+ topics"
- **Status level:** "quiz me on my conceptual topics"
- **Weakest topics:** "quiz me on my weakest areas" (lowest status + highest priority)

### Question Calibration

| User Status | Question Types | Examples |
|-------------|---------------|----------|
| exposed | Definitional, recognition | "What is X? Why does it exist? What problem does it solve?" |
| conceptual | Application, compare/contrast | "When would you choose X over Y? How does X relate to Z?" |
| applied | Troubleshooting, debugging | "A user reports X error after deploying Y. Walk through your investigation." |
| proficient | Edge cases, tradeoffs, architecture | "What are the security implications of X at scale? When does X break down?" |

Do not quiz topics at `not_started` — direct to LEARN mode instead.

### Flow

1. Select 3-5 questions calibrated to the specified scope and user's level on each topic.
2. Ask questions **one at a time** — wait for the user's response before asking the next question.
3. After each answer:
   - Assess correctness (correct / partially correct / incorrect).
   - Provide specific feedback explaining what was right and what was missed.
   - Note partial credit where applicable.
4. After all questions, summarize performance:
   - Score: X/Y correct
   - Topics covered
   - Areas of strength
   - Areas of weakness (specific gaps identified)
5. Recommend next action: "Consider LEARN mode on [topic] to fill this gap" or "You're ready for a SCENARIO involving [topic]."

### Status Update Criteria

If the user answers 3+ questions correctly at a difficulty level ABOVE their current status (i.e., answering conceptual-level questions while at exposed), promote 1 level. Never promote more than 1 level per quiz session. Record evidence.

### Output Format

Questions presented one at a time. Final summary with score, strengths, weaknesses, and recommended next step.

---

## SCENARIO Mode

**Purpose:** Multi-topic real-world exercise that tests applied understanding.

### Topic Selection

Scenarios involve 3-7 topics, selected by:
- **User request:** "give me a scenario about K8s auth" or "scenario involving OIDC and RBAC"
- **Agent recommendation:** based on topics at `conceptual` that need `applied` practice

### Difficulty Calibration

Match difficulty to the LOWEST-status topic involved. The scenario should be achievable but stretching.

### Flow

1. **Select topics** and generate a realistic scenario (troubleshooting, design, or incident response).
2. **Present the scenario** with enough context to reason about: cluster config, symptoms, error messages, architecture details.
3. **Ask:** "Walk me through your approach" or "What's happening and how do you fix it?"
4. **Evaluate holistically:**
   - What was correct (specific praise with topic attribution)
   - What was missed (specific topics and what the user should have considered)
   - What was partially right (what the user got and what they didn't)
   - What misconceptions were revealed (with corrections)
5. **Provide the model answer** after evaluation — show the complete reasoning chain.

### Status Update Criteria

For each topic involved: if the user demonstrated correct understanding and application of that topic within the scenario, promote to `applied` (if currently below `applied`). Topics at `applied` or above are not promoted by scenarios alone — `proficient` and `mastered` require a formal MASTERY CHALLENGE.

### Example Scenarios

**Scenario 1: The Broken Service Mesh** (networking, CNI, kube-proxy, ClusterIP)
A developer reports that their new microservice can reach the Kubernetes API server but cannot communicate with other pods in the same namespace. The service was deployed with a standard ClusterIP Service. `kubectl get endpoints` shows the expected pod IPs. Walk through your troubleshooting approach.

**Scenario 2: The Unauthorized Token** (JWT, OIDC, RBAC, ServiceAccount)
After a cluster upgrade, a CI/CD pipeline that authenticates via a projected ServiceAccount token starts receiving 401 errors from the API server. The token was working before the upgrade. The OIDC discovery endpoint responds normally. What could cause this?

**Scenario 3: The Mysterious Evictions** (Scheduler, kubelet, resource management)
Pods on a specific node keep getting evicted with "The node was low on resource: ephemeral-storage." The node has 100GB of disk and the pods request only 500Mi each. No other workloads run on this node. Investigate.

**Scenario 4: Certificate Chain Failure** (X.509, TLS, Certificate Authority, mutual TLS)
A gRPC service configured with mutual TLS rejects connections from a client that was working yesterday. Both client and server certificates were issued by the same internal CA. The server logs show "certificate verify failed." The certificates have not expired. Diagnose.

---

## PROJECT Mode

**Purpose:** Hands-on buildable artifacts that integrate multiple topics.

### Project Sizes

| Size | Duration | Topics | Target Level-Up |
|------|----------|--------|----------------|
| Sprint | 1-2 hours | 2-4 | applied |
| Build | Half day | 4-8 | applied (proficient eligible via mastery challenge) |
| Capstone | 1-2 days | Full category | proficient (mastered eligible via mastery challenge) |

### Entry Points

- **"Assign me a project"** — Select based on: highest-priority topics below `applied`, clustered by category for coherence.
- **"Give me a project using [topic1, topic2, ...]"** — Generate using the specified topics.

### Project Brief Format

Every project brief must include:

1. **Topics involved:** list with the user's current status on each
2. **Objective:** what the user will build (concrete artifact)
3. **Deliverables:** what "done" looks like
4. **Acceptance criteria:** specific conditions that must be met
5. **Implementation outline:** suggested approach (3-5 high-level steps, not a full solution)
6. **Level-ups on completion:** which topics will advance and to what level

### Status Update Criteria

On completion, promote involved topics to `applied` (if below). For topics already at `applied`, note that proficient requires a MASTERY CHALLENGE. Record evidence for each promoted topic.

### Example Projects

**Sprint: Network Namespace Lab** (veth pair, network namespace, NAT)
Build a bash script that creates two network namespaces, connects them with a veth pair, assigns IP addresses, enables communication between them, and sets up NAT so one namespace can reach the internet through the host.

**Build: OIDC Auth Flow Simulator** (OAuth 2.0, OIDC, JWT, JWKS)
Build a minimal OIDC provider and relying party that demonstrates the authorization code flow. The provider issues JWTs signed with RSA. The relying party validates them using a JWKS endpoint. Include token refresh.

**Build: Custom Kubernetes Controller** (SharedInformer, DeltaFIFO, reconcile loop, CRD)
Write a Kubernetes controller in Go that watches a custom resource and reconciles state. Must use SharedInformers, implement proper error handling with requeue, and include a DeltaFIFO work queue.

**Capstone: Production-Ready Service Mesh** (Full networking + identity categories)
Design and document a service mesh architecture for a multi-tenant Kubernetes cluster. Include: mTLS between services, RBAC policies, network policies, ingress configuration, certificate rotation strategy, and monitoring. Produce architecture diagrams and YAML manifests.

---

## MASTERY CHALLENGE Mode

**Purpose:** Formal assessment for promotion to proficient or mastered levels.

### Prerequisites

| Target Level | Required Current Level |
|-------------|----------------------|
| proficient | applied or higher |
| mastered | proficient |

If the topic does not meet the prerequisite, explain what is needed and suggest the appropriate mode to get there.

### Format — 5 Components

Each component tests a different dimension of mastery:

1. **Depth:** "Walk me through exactly what happens when [topic mechanism triggers]." Tests internal mechanics and implementation details.

2. **Edge Cases:** "What happens when [failure mode]? What are the security implications of [edge case]?" Tests awareness of failure modes, edge cases, and security considerations.

3. **Teaching:** The agent plays a confused junior engineer. The user must teach the concept clearly and correctly. Tests explanatory ability and depth of understanding.

4. **Integration:** "How does [topic] interact with [prerequisite or related topic]?" Tests cross-topic understanding and system-level thinking.

5. **Creative Application:** The agent presents a novel problem requiring creative use of the concept in an unfamiliar context. Tests generalization and transfer.

### Difficulty Tiers

- **Proficient challenge:** Questions at difficulty 4. Expects solid operational knowledge, troubleshooting ability, and clear explanations.
- **Mastered challenge:** Questions at difficulty 5. Expects protocol-level knowledge, novel applications, and ability to teach advanced nuances.

### Scoring

- Pass threshold: 4 out of 5 components.
- Each component is pass/fail — no partial credit on individual components.
- Assessment is holistic: a strong performance on one component does not compensate for a clear failure on another.

### On Success

- Promote the topic to the target level.
- Record evidence with a summary covering which dimensions were demonstrated.
- Suggest related topics that could benefit from the user's new depth.

### On Failure

- Do NOT promote. The topic stays at its current level.
- Identify which dimensions failed.
- For each failed dimension, suggest a specific learning activity:

| Failed Dimension | Recommended Activity |
|-----------------|---------------------|
| Depth | LEARN mode focused on internals and implementation details |
| Edge Cases | QUIZ at proficient level with emphasis on failure modes |
| Teaching | Practice explaining to a rubber duck; revisit foundational understanding |
| Integration | LEARN the related topics, then SCENARIO combining them |
| Creative Application | PROJECT involving the topic in an unfamiliar context |

### Retry Policy

Cannot retry in the same conversation. If the user asks to retry, explain they should study the identified gaps first and attempt again in a new session. Check `level_up_evidence` timestamps to enforce this within the conversation.

---

## STATUS Mode

**Purpose:** Progress dashboard showing overall and filtered views of mastery.

### Default View (Summary)

```
Knowledge Base: X/156 topics engaged

By Level:
  mastered:    X  [bar]
  proficient:  X  [bar]
  applied:     X  [bar]
  conceptual:  X  [bar]
  exposed:     X  [bar]
  not_started: X  [bar]

By Category:
  networking              X/14 engaged
  cryptography            X/18 engaged
  identity                X/44 engaged
  serialization           X/7 engaged
  kubernetes_control_plane X/29 engaged
  kubernetes_node         X/11 engaged
  kubernetes_controllers  X/15 engaged
  kubernetes_networking   X/4 engaged
  eks_aws                 X/5 engaged
  infrastructure          X/6 engaged
  scheduler               X/3 engaged

Priority Gaps (critical/high topics below proficient):
  1. [topic] (critical, not_started)
  2. [topic] (critical, exposed)
  [up to 10]
```

### Filtered Views

Supports filters like:
- "status for kubernetes topics"
- "all mastered topics"
- "exposed topics in identity"
- "critical priority topics"

### "What Should I Study Next?" Recommendation Logic

Priority order:
1. `critical` priority topics at `not_started` or `exposed` — immediate gaps
2. Topics that are prerequisites for 3+ other topics (high DAG fan-out) — unblocking multipliers
3. Topics at `conceptual` that could advance to `applied` with one SCENARIO — low-hanging fruit
4. Topics clustering with others the user is already strong in — momentum and efficiency

### Learning Velocity

Only display if 5+ promotions exist with timestamps. Calculate promotions per week. If insufficient data, omit this section entirely.

### Implementation

Run `python3 /Users/sethallen/agent-skills/study/scripts/kb-stats.py` for summary numbers, then format the output. For filtered views and recommendation logic, use Grep on the knowledge base directly.

---

## PATH Mode

**Purpose:** Generate a sequenced learning plan for a specific goal.

### Accepted Goals

Examples:
- "CKA prep"
- "Deeply understand K8s auth"
- "DevOps interview prep"
- "Understand the kubectl apply lifecycle"
- "Master the identity category"

### Flow

1. **Map goal to relevant topics** by category, tags, or domain knowledge.
2. **Check current status** on all relevant topics.
3. **Filter** to topics that need work (below the target level for the goal).
4. **Topologically sort by prerequisites.** If a cycle is detected, warn the user and break it arbitrarily to continue.
5. **Group into study sessions:** 3-5 topics per session, approximately 1-2 hours each. Ensure each session's prerequisites are covered by prior sessions.
6. **For each session, specify:**
   - Topics to cover
   - Mode for each topic (LEARN for not_started/exposed, QUIZ for conceptual, SCENARIO for applied, MASTERY CHALLENGE for proficient)
   - Target level-up for each topic
7. **Include estimated total sessions and time.**

### Output Format

```
Learning Path: [Goal]
Sessions: X | Estimated time: X-Y hours

Session 1: [Theme]
  1. [Topic] (currently: not_started) -> LEARN -> target: exposed
  2. [Topic] (currently: not_started) -> LEARN -> target: exposed
  3. [Topic] (currently: exposed) -> QUIZ -> target: conceptual

Session 2: [Theme]
  1. [Topic] (currently: conceptual) -> SCENARIO -> target: applied
  2. [Topic] (currently: not_started) -> LEARN -> target: exposed
  [...]
```

### Notes

- Sessions should have thematic coherence — group related topics together.
- Always respect the prerequisite DAG: if topic B requires topic A, topic A must appear in an earlier session (or the user must already have it at `conceptual` or above).
- For certification-focused paths, align sessions with exam domains and weight toward high-priority topics.
- Adjust the path if the user has already made progress — skip topics at or above the target level.
