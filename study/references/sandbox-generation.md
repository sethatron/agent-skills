# Sandbox Practice Environments

## Overview

Sandboxes are self-contained practice environments generated on-demand during LEARN mode. They give users hands-on challenges to reinforce understanding through doing.

## Sandbox Types

### Real Environment

Use when the topic involves tools/primitives available on the user's system. Creates actual resources the user interacts with directly. Examples: Docker containers, local DNS, file permissions, process management.

Platform note: detect OS via `uname`. If on macOS/Darwin and the topic requires Linux-specific primitives (network namespaces, iptables), check for Docker availability. If Docker is available, use a container-based sandbox. If neither Linux nor Docker, fall back to simulated.

### Simulated Environment

Use when the topic involves cloud services, distributed systems, or protocols that can't be reproduced locally. A Python-based mock simulates the relevant behavior and accepts user input. Examples: CIDR/subnetting mock VPC planner, NAT simulated connection tracker, BGP mock router, TLS simulated handshake, IAM/RBAC mock policy engine.

## File Structure

Each sandbox lives in `{sandbox_dir}/{topic-slug}/`:

- `challenge.sh` — Entry point the user runs. Sets up the environment, displays the challenge prompt, starts engine.py if needed. Must be executable. Two lifecycle patterns:
  - **Setup/teardown pattern** (preferred): Sets up resources, prints challenge instructions, exits. User works in the environment. User runs `bash challenge.sh --cleanup` to tear down. Suitable for most topics.
  - **Persistent pattern**: Stays running (interactive session). Cleanup via trap on Ctrl+C or exit. Suitable for interactive simulations.
- `engine.py` — Backend simulation. Only present for simulated environments. Started by challenge.sh as a background process or imported directly. Communicates via stdin/stdout, files, or local socket.
- `README.md` — Challenge description: what to accomplish, success criteria, hints (calibrated to difficulty). Written by the agent and presented to the user inline.
- `verify.sh` — Checks the user's solution. Returns specific feedback on what was correct and what was missed. Must work while the sandbox environment is still active (before cleanup).

Slug rule: same as guide generation — lowercase topic name, remove `()`, `/`, `&`, replace spaces with hyphens, collapse consecutive hyphens, strip leading/trailing hyphens.

## Difficulty Calibration

| Level | Name | Description |
|-------|------|-------------|
| 1 | Guided | Step-by-step with hints. One clear task. README includes approach outline. |
| 2 | Structured | Clear objective, some hints. 2-3 related tasks. README describes the goal but not the steps. |
| 3 | Applied | Real-world scenario. Multiple tasks that build on each other. Minimal hints. |
| 4 | Complex | Multi-faceted problem. Requires combining concepts. No hints. May involve troubleshooting a broken setup. |
| 5 | Expert | Adversarial or edge-case scenario. Requires deep understanding. May have intentional red herrings or subtle misconfigurations. |

### Default Difficulty Mapping

When the user says "sandbox" without specifying a level:

| User Status on Topic | Default Difficulty |
|-----------------------|-------------------|
| not_started | 1 |
| exposed | 2 |
| conceptual | 3 |
| applied | 4 |
| proficient / mastered | 5 |

## Generation Instructions

When generating a sandbox:

1. Read the topic's KB entry (description, difficulty, prerequisites, related)
2. Read the topic's guide if `source_context` points to a `.md` file — use "Practical Application" and "Failure Modes" sections for challenge ideas
3. Determine sandbox type:
   - Run `uname` to detect OS
   - If topic uses locally-available primitives AND they're available on this platform → real environment
   - If topic requires cloud/distributed/protocol resources OR platform lacks required primitives → simulated
   - If Docker is available and could provide a real environment → Docker-based real environment
4. Design the challenge calibrated to the requested difficulty level
5. Generate all files (challenge.sh, engine.py if needed, README.md, verify.sh)
6. **MANDATORY — Make scripts executable immediately after writing them:** `chmod +x {sandbox_dir}/{topic-slug}/challenge.sh {sandbox_dir}/{topic-slug}/verify.sh` — Do NOT skip this step. The user runs these scripts directly with `./challenge.sh` and `./verify.sh`.
7. Syntax-check: `bash -n challenge.sh` and (if engine.py exists) `python3 -c "import ast; ast.parse(open('engine.py').read())"`
8. Register in knowledge base: Add or update `resources.sandbox` in the topic's
   KB entry with value `sandbox/{topic-slug}/`. Follow yaml-editing-patterns.md
   Pattern 5a (if topic has level_up_evidence) or 5b (if not). If the topic
   already has a `resources` block, use Pattern 5c to add the sandbox entry.

## Challenge Design Principles

- The challenge must test the SAME concepts covered in the LEARN session
- At difficulty 1-2, reinforce core concepts
- At difficulty 3-4, require application and troubleshooting
- At difficulty 5, require creative problem-solving or edge-case handling
- Every challenge must have a clear, verifiable success condition
- The README must explain what "done" looks like
- verify.sh must give specific feedback, not just pass/fail
- Target completion time: 5-15 minutes (difficulty 1-3), 15-30 minutes (difficulty 4-5)
- challenge.sh must include cleanup logic (trap or --cleanup flag) to restore system state
- verify.sh must work while the sandbox is still active (before cleanup)
- All generated code should have minimal comments, per user preferences

## Status Effect

Sandbox completion does NOT affect topic status or trigger level promotions. It is purely for practice and reinforcement. No evidence is recorded for sandbox activities.
