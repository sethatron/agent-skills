# Study Buddy — User Guide

An adaptive study companion for DevOps and Platform Engineering, covering 200+ topics across networking, cryptography, identity/auth, Kubernetes internals, EKS/AWS, infrastructure, and more.

## Getting Started

Activate the study buddy with any of these phrases:

- "study", "/study"
- "teach me", "explain [topic]", "what is [topic]"
- "quiz me", "test me"
- "give me a scenario"
- "mastery challenge", "level up"
- "study status", "what should I study next"
- "learning path", "study path"

On first interaction, you'll get a summary of your current progress — topics engaged, level distribution, and priority gaps. From there the study buddy detects which mode fits your request and jumps in.

You don't always need an explicit trigger. If you ask a question that maps to a knowledge base topic, the study buddy recognizes it and can teach it in context, then offer to formalize the learning.

## Modes

| Mode | Trigger Phrases | What It Does |
|------|----------------|--------------|
| LEARN | "teach me", "explain", "what is", "learn about" | Teach a topic from first principles, calibrated to current level |
| QUIZ | "quiz me", "test me", "check my knowledge" | Test knowledge with targeted questions |
| SCENARIO | "give me a scenario", "practice scenario", "troubleshoot" | Multi-topic real-world exercise |
| PROJECT | "assign me a project", "give me a project", "hands-on" | Hands-on buildable artifact |
| MASTERY CHALLENGE | "mastery challenge", "I'm ready to level up", "challenge me" | Formal 5-component assessment for proficient/mastered |
| STATUS | "study status", "progress", "how am I doing", "what should I study next" | Progress dashboard with recommendations |
| PATH | "learning path", "study path", "study plan", "prep for" | Sequenced learning plan for a goal |

For detailed behavioral specs, prerequisites, and status update criteria for each mode, see [interaction-modes.md](../references/interaction-modes.md).

## Mastery Levels

| Level | Name | What It Feels Like |
|-------|------|--------------------|
| 0 | not_started | You haven't encountered this yet. |
| 1 | exposed | You've heard about it and could recognize it in context, but couldn't explain it cold. |
| 2 | conceptual | You could whiteboard the concept and explain why it exists to a colleague. |
| 3 | applied | You've used it in a realistic scenario and understand the operational mechanics. |
| 4 | proficient | You can troubleshoot problems involving this, explain tradeoffs, and make design decisions. |
| 5 | mastered | You could teach a workshop on it, handle edge-case questions, and apply it creatively in unfamiliar contexts. |

**Key rules:**

- Levels must be reached in order (exception: LEARN can jump 2 levels max)
- `proficient` and `mastered` require a formal MASTERY CHALLENGE — they can't be reached through LEARN, QUIZ, or SCENARIO alone
- Every promotion records evidence with a timestamp and summary of what was demonstrated
- Topics are never demoted

Real-world experience counts. If you share work you've done — a script you wrote, an incident you debugged, infrastructure you built — and it demonstrates understanding of KB topics, the study buddy can record it as level-up evidence.

For complete promotion criteria, pass thresholds per transition, anti-gaming rules, and the evidence schema, see [level-system.md](../references/level-system.md).

## Learning Philosophy

**Understand, don't memorize.** The goal is understanding deep enough to whiteboard the entire system and defend every design decision. If you can't explain *why*, you don't understand it yet.

**Build a web, not a list.** Topics connect through prerequisites and relationships. Isolated knowledge decays faster than connected knowledge — the study buddy emphasizes these links constantly.

**Apply immediately.** Reading about something is not the same as understanding it. Scenarios and projects push you to use what you've learned in realistic contexts.

**Spaced practice beats cramming.** Short daily sessions outperform marathon study blocks. The system is designed for steady, sustainable progress.

## Recommended Workflows

| Workflow | Best For | Timing |
|----------|----------|--------|
| Daily Study Sprint | Steady, sustainable progress | 30-45 min |
| Deep Dive | Mastering a topic cluster or preparing for a specific goal | 2-3 hours |
| Interview/Certification Prep | CKA, AWS certs, or job interview preparation | 1-2 weeks |
| Opportunistic Learner | Context-driven learning when you encounter something in real work | Ad hoc |

For step-by-step sequences, tips, and the KB coverage table, see [study-guide.md](../references/study-guide.md).

## Tools

### Stats Dashboard

```bash
python3 /Users/sethallen/agent-skills/study/scripts/kb-stats.py
```

Outputs a summary of your knowledge base state: level distribution across all topics, priority breakdown, per-category engagement numbers, and recent promotions. The study buddy runs this automatically on session start, but you can run it directly anytime.

### DAG Visualizer

```bash
python3 /Users/sethallen/agent-skills/study/scripts/kb-dag.py
```

Launches an interactive graph visualization of the knowledge base in your browser. The prerequisite DAG is rendered with topics colored by status, priority, or category. Useful for exploring topology, finding clusters of related topics, and understanding learning paths visually.

Use `--no-serve` to generate the HTML file without launching a local server:

```bash
python3 /Users/sethallen/agent-skills/study/scripts/kb-dag.py --no-serve
```

Both scripts require `pyyaml` (`pip install pyyaml`).

## Knowledge Base

The knowledge base lives at `/Users/sethallen/agent-skills/study/knowledge-base.yaml`.

Each topic has: name, description, difficulty (1-5), priority (critical/high/medium/low), prerequisites (forming a DAG), related topics, tags, status (one of the 6 mastery levels), and source_context.

### Categories

| Category | Description |
|----------|-------------|
| networking | veth pairs, namespaces, NAT, BGP, TLS, Envoy, xDS |
| cryptography | X.509, JWT, JWS/JWE, JWKS, RSA, ECDSA |
| identity | SAML, OAuth 2.0, OIDC, SCIM, MFA, AWS IAM |
| serialization | Protocol Buffers, proto files, K8s envelope |
| kubernetes_control_plane | API server, etcd, ServiceAccount, admission control |
| kubernetes_node | kubelet, kube-proxy, containerd, CRI, CNI |
| kubernetes_controllers | SharedInformers, DeltaFIFO, reconcile loops |
| kubernetes_networking | ClusterIP, EndpointSlice, iptables/IPVS modes |
| aws_networking | VPC, ALB/NLB, Route 53, Direct Connect, WAF |
| eks_and_aws | IRSA, Pod Identity, aws-iam-authenticator |
| infrastructure | Proxmox, MetalLB, Traefik, kubeconfig |
| scheduler | Filtering, scoring, binding |

For topic counts per category and key topics, see the coverage table in [study-guide.md](../references/study-guide.md).

New topics can be added during study sessions — mention something not in the KB and the study buddy will offer to add it.

## Reference Material

- [**study-guide.md**](../references/study-guide.md) — Recommended workflows (step-by-step sequences), KB coverage table with topic counts, study tips
- [**interaction-modes.md**](../references/interaction-modes.md) — Detailed flow, prerequisites, and status update criteria for all 7 modes
- [**level-system.md**](../references/level-system.md) — Promotion rules, pass criteria per transition, anti-gaming rules, evidence schema
