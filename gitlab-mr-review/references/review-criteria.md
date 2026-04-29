# Extended Review Methodology

## Depth Over Surface

The codebase is largely AI-generated. Surface-level style feedback is insufficient.
Prioritize:

- **Pattern Consistency**: Does the change follow patterns in adjacent/related code?
- **Behavioral Correctness**: Does it do what the MR description claims?
- **Regression Risk**: Does it modify shared utilities, base classes, middleware, or config?
- **API Contract Fidelity**: If an interface changes, are all consumers accounted for?
- **Idempotency & Safety**: For infra/migration code, is it safe to apply multiple times?

## Security Review Criteria

Every MR evaluated against:

- **Secrets**: No hardcoded tokens, passwords, or keys
- **Input validation**: All external data validated before use
- **Least privilege**: IAM roles, RBAC, service accounts don't over-grant
- **Injection vectors**: No unsanitized data reaches SQL, shell, or template contexts
- **Dependency risk**: New third-party deps noted; known CVEs flagged

## Infrastructure-Specific Criteria

### Terraform
- State locking considerations
- Resource destruction risk (flag any destroy/replace)
- Variable hygiene and provider version pinning

### Kubernetes
- Resource limits/requests on all workloads
- RBAC correctness
- Image tag pinning (no :latest)
- Liveness/readiness probes present
- No plaintext secrets in manifests

### Helm
- Values override hygiene
- Chart version pinning
- Templating correctness

## Finding Severity Levels

| Level | Description | Action |
|-------|-------------|--------|
| **CRITICAL** | Security, data loss, credential exposure, breaks functionality | Must fix before merge |
| **MAJOR** | Logic errors, poor error handling, deviates from norms | Should fix before merge |
| **MINOR** | Code quality, naming, clarity, testing gaps | Fix if possible |
| **SUGGESTION** | Performance, elegance, future-proofing | Optional improvement |

## No Hallucination Rule

All commentary must be grounded in: observed diff content, retrieved API data,
cloned repo content, or retrieved external sources. Speculation not grounded in
these sources must be labeled `[UNVERIFIED INFERENCE]`.
