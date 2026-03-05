# Study Guide

Reference material for advising on study strategy, workflows, and effective use of the study buddy system.

## Recommended Workflows

### The Daily Study Sprint (30-45 min)

Best for: steady, sustainable progress.

1. Start with STATUS: "What should I study next?"
2. Pick the top recommendation (or a topic that interests you today)
3. If `not_started` — LEARN mode (15 min to understand, answer verification questions)
4. If `exposed` — QUIZ mode on that topic (10 min, 3-5 questions)
5. If `conceptual` — SCENARIO mode involving that topic (15 min)
6. End with STATUS to see what moved

### The Deep Dive (2-3 hours)

Best for: mastering a topic cluster or preparing for a specific goal.

1. Start with PATH: "Create a learning path for [goal]"
2. Follow the generated session plan sequentially
3. Don't rush — if a prerequisite gap appears, address it before moving forward
4. Take the MASTERY CHALLENGE when you reach proficient on the target topic
5. End with a PROJECT that integrates everything you learned

### The Interview/Certification Prep (1-2 weeks)

Best for: CKA, AWS certs, or job interview preparation.

1. Start with PATH: "Create a learning path for [CKA/interview/cert]"
2. Block 1-2 hours daily following the session plan
3. Use QUIZ mode between sessions to retain what you learned
4. Use SCENARIO mode for realistic practice (2-3 scenarios per week)
5. Attempt MASTERY CHALLENGES on critical topics before the exam
6. Track velocity via STATUS — aim for 3-5 topic level-ups per week

### The Opportunistic Learner

Best for: when you encounter something in real work you want to understand deeper.

1. Describe what you encountered: "I just saw X in a pod spec and I don't understand it"
2. The study buddy maps it to a KB topic and teaches it in context
3. Do a quick QUIZ to lock in the understanding
4. Move on — the level-up is recorded and you can come back later

## Knowledge Base Coverage

| Category | Topics | Covers |
|----------|--------|--------|
| Networking | 18 | veth pairs, namespaces, NAT, BGP, TLS, Envoy, xDS |
| Cryptography | 18 | X.509, JWT, JWS/JWE, JWKS, RSA, ECDSA |
| Identity & Auth | 46 | SAML, OAuth 2.0, OIDC, SCIM, MFA, AWS IAM |
| Serialization | 7 | Protocol Buffers, proto files, K8s envelope |
| K8s Control Plane | 31 | API server, etcd, ServiceAccount, admission control |
| K8s Node | 11 | kubelet, kube-proxy, containerd, CRI, CNI |
| K8s Controllers | 15 | SharedInformers, DeltaFIFO, reconcile loops |
| K8s Networking | 4 | ClusterIP, EndpointSlice, iptables/IPVS modes |
| AWS Networking | 32 | VPC, ALB/NLB, Route 53, Direct Connect, WAF |
| EKS & AWS | 5 | IRSA, Pod Identity, aws-iam-authenticator |
| Infrastructure | 6 | Proxmox, MetalLB, Traefik, kubeconfig |
| Scheduler | 3 | Filtering, scoring, binding |

The knowledge base grows over time. New topics can be added during study sessions when you encounter something not yet covered.

## Tips for Maximum Effectiveness

- Start with critical-priority topics — they're critical for a reason.
- Don't skip prerequisites even if you think you know them — a quick QUIZ confirms or reveals gaps.
- When you get something wrong, that's the most valuable moment — the study buddy identifies the exact misconception.
- Use SCENARIO mode generously — it's the closest thing to on-the-job learning.
- After a SCENARIO or PROJECT, review which topics you struggled with and do targeted LEARN sessions.
- Check STATUS weekly to see your velocity and adjust your study time.
- When you hit mastered on a topic, challenge yourself to connect it to something unrelated — that's when real expertise forms.
