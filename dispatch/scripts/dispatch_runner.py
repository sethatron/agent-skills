#!/usr/bin/env python3
"""
Main dispatch workflow runner.

Reads workflow.yaml, drives the step execution loop, manages checkpoints,
and orchestrates sub-skill invocations.

Usage:
    python scripts/dispatch_runner.py --mode=morning
    python scripts/dispatch_runner.py --mode=eod
    python scripts/dispatch_runner.py --mode=step --step mr_review_personal
    python scripts/dispatch_runner.py --mode=status
    python scripts/dispatch_runner.py --dry-run --mode=morning
    python scripts/dispatch_runner.py test

Modes:
    morning  -- full morning workflow (default steps in order)
    eod      -- end-of-day summary and carry-forward generation
    step     -- run a single workflow step by ID
    status   -- display current day summary without running steps
"""

import argparse
import glob as globmod
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent


def _resolve_workflow_path() -> Path:
    repo_path = SKILL_DIR / "workflow.yaml"
    if repo_path.exists():
        return repo_path
    return Path(os.path.expanduser("~/.zsh/dispatch")) / "workflow.yaml"
STATE_ROOT = Path(os.path.expanduser("~/.zsh/dispatch"))
WORKFLOW_PATH = _resolve_workflow_path()

try:
    import yaml
except ImportError:
    yaml = None


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class VerifySpec:
    file_exists: Optional[str] = None
    min_file_size_bytes: Optional[int] = None
    session_field: Optional[str] = None


@dataclass
class WorkflowStep:
    id: str
    name: str
    enabled: bool = True
    skill: Optional[str] = None
    runner: Optional[str] = None
    command: Optional[str] = None
    args: Optional[str] = None
    on_blocker: str = "log_and_continue"
    timeout_minutes: int = 5
    tags: List[str] = field(default_factory=list)
    verify: Optional[VerifySpec] = None
    blocking: bool = False
    cwd: Optional[str] = None
    description: str = ""


@dataclass
class StepResult:
    step_id: str
    outcome: str  # success|partial|failed|skipped
    artifacts: List = field(default_factory=list)
    verify_result: str = ""
    error: Optional[str] = None
    tool_calls: int = 0
    duration_ms: int = 0


@dataclass
class RunnerState:
    session_id: str
    mode: str
    workflow_steps: List[WorkflowStep] = field(default_factory=list)
    completed_step_ids: List[str] = field(default_factory=list)
    active_task_id: Optional[str] = None
    drift_score: float = 0.0
    tool_calls_since_check: int = 0
    _disabled_step_ids: List[str] = field(default_factory=list)


class DispatchRunner:
    """Workflow execution engine for dispatch."""

    def __init__(self, store, mode: str, no_slack: bool = False, dry_run: bool = False):
        self.store = store
        self.mode = mode
        self.no_slack = no_slack
        self.dry_run = dry_run
        self._human_gates = {}
        self._workflow_config = {}
        self._notify_on = []

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from log_writer import LogWriter
        from slack_notifier import SlackNotifier
        from bottleneck_detector import BottleneckDetector
        from optimus_runner import OptimusRunner

        self.writer = LogWriter(store)
        self.notifier = SlackNotifier(store)
        self.detector = BottleneckDetector(store, self.notifier)
        self.optimus = OptimusRunner(store, self.writer)

    def load_workflow(self) -> List[WorkflowStep]:
        if not WORKFLOW_PATH.exists():
            return []
        if not yaml:
            return []

        with open(WORKFLOW_PATH) as f:
            data = yaml.safe_load(f) or {}

        self._workflow_config = {
            "operator": data.get("operator", {}),
            "defaults": data.get("defaults", {}),
        }
        self._notify_on = data.get("defaults", {}).get("slack_notify_on", [])

        steps = []
        for s in data.get("steps", []):
            verify = None
            if "verify" in s and s["verify"]:
                verify = VerifySpec(
                    file_exists=s["verify"].get("file_exists"),
                    min_file_size_bytes=s["verify"].get("min_file_size_bytes"),
                    session_field=s["verify"].get("session_field"),
                )
            steps.append(WorkflowStep(
                id=s["id"],
                name=s.get("name", s["id"]),
                enabled=s.get("enabled", True),
                skill=s.get("skill"),
                runner=s.get("runner"),
                command=s.get("command"),
                args=s.get("args"),
                on_blocker=s.get("on_blocker", "log_and_continue"),
                timeout_minutes=s.get("timeout_minutes", 5),
                tags=s.get("tags", []),
                verify=verify,
                blocking=s.get("blocking", False),
                cwd=s.get("cwd"),
                description=s.get("description", ""),
            ))

        self._human_gates = {}
        for gate in data.get("human_gates", []):
            self._human_gates[gate["after"]] = gate["message"]

        return steps

    def start_session(self) -> RunnerState:
        session = self.store.create_session(self.mode)
        steps = self.load_workflow()

        state = RunnerState(
            session_id=session["session_id"],
            mode=self.mode,
            workflow_steps=steps,
        )

        self.store.append_checkpoint(state.session_id, {
            "step_id": "__init",
            "outcome": "success",
            "timestamp": _now(),
        })

        if not self.no_slack:
            step_names = [s.name for s in steps if s.enabled]
            carry = self.store.generate_carry_forward()
            try:
                self.notifier.send_template("session_start", {
                    "mode": self.mode,
                    "step_count": len(step_names),
                    "carry_forward_count": len(carry),
                    "step_names": ", ".join(step_names[:6]),
                })
            except Exception as e:
                print(f"Warning: session_start notification failed: {e}", file=sys.stderr)

        return state

    def resume_session(self) -> Optional[RunnerState]:
        existing = self.store.get_today_session()
        if not existing or existing.get("ended_at"):
            return None
        if existing.get("mode") != self.mode:
            return None

        completed = self.get_completed_step_ids(existing["session_id"])
        if not completed:
            return None

        steps = self.load_workflow()
        next_step = None
        for s in steps:
            if s.id not in completed:
                next_step = s.name
                break

        print(
            f"\nFound incomplete {self.mode} session with {len(completed)} completed steps."
            f"\nResume from '{next_step or 'end'}'? [Y/n] ",
            end="", flush=True,
        )

        try:
            response = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            response = "y"

        if response in ("", "y", "yes"):
            return RunnerState(
                session_id=existing["session_id"],
                mode=self.mode,
                workflow_steps=steps,
                completed_step_ids=list(completed),
            )

        self.store.update_session(existing["session_id"], checkpoints=[])
        return None

    def end_session(self, state: RunnerState) -> None:
        tasks = self.store.list_tasks(date=_today())
        self.store.update_session(
            state.session_id,
            ended_at=_now(),
            step_count=len(state.completed_step_ids),
            task_count=len(tasks),
        )
        try:
            self.writer.write_session_yaml(state.session_id)
        except Exception:
            pass

        if not self.no_slack:
            closed = sum(1 for t in tasks if t["status"] == "COMPLETE")
            deferred = sum(1 for t in tasks if t["status"] == "DEFERRED")
            in_progress = sum(1 for t in tasks if t["status"] == "IN_PROGRESS")
            bottlenecks = len(self.store.get_open_bottlenecks())
            self.notifier.send_template("session_end", {
                "closed": closed,
                "deferred": deferred,
                "in_progress": in_progress,
                "bottleneck_count": bottlenecks,
                "carry_forward_summary": f"{deferred + in_progress} tasks carry forward",
            })

    def run(self) -> List[StepResult]:
        state = self.resume_session() or self.start_session()
        results = []

        if self.mode == "eod":
            results = self._run_eod_sequence(state)
        else:
            steps = [
                s for s in state.workflow_steps
                if s.enabled
                and self._mode_matches(s, state)
                and s.id not in state._disabled_step_ids
            ]
            for step in steps:
                if self.should_skip(step.id, state):
                    continue

                result = self.run_step(step, state)
                results.append(result)
                self.write_checkpoint(step.id, result, state)

                if result.outcome == "failed" and step.blocking:
                    break

                if self._step_failure_count(step.id) >= 3:
                    self._disable_step(step.id, state)

                state.tool_calls_since_check += result.tool_calls
                if state.tool_calls_since_check >= 20:
                    state.drift_score = self.compute_drift_score(state)
                    state.tool_calls_since_check = 0
                    if state.drift_score > 0.3:
                        self.inject_reorientation(state)

                gate_msg = self._human_gates.get(step.id)
                if gate_msg and result.outcome in ("success", "partial"):
                    print(json.dumps({
                        "gate": step.id,
                        "message": gate_msg,
                        "completed_steps": list(state.completed_step_ids),
                        "remaining_steps": [s.id for s in steps[steps.index(step)+1:]],
                    }))
                    return results

        self.end_session(state)
        return results

    def run_step(self, step: WorkflowStep, state: RunnerState) -> StepResult:
        log_id = self.store.log_step(state.session_id, step.id, started_at=_now())
        start_ms = int(time.time() * 1000)

        if self.dry_run:
            result = StepResult(step_id=step.id, outcome="skipped",
                                error="dry-run mode")
        elif step.skill:
            result = self.invoke_sub_skill(step, state)
        elif step.runner:
            result = self._run_script(step, state)
        elif step.command:
            result = self._run_command(step, state)
        else:
            result = StepResult(step_id=step.id, outcome="failed",
                                error="No execution type defined")

        result.duration_ms = int(time.time() * 1000) - start_ms

        if step.verify and result.outcome in ("success", "partial"):
            result.verify_result = self.verify_step(step, result)

        step_status = ("SKIPPED" if result.outcome == "skipped" else
                       "FAILED" if result.outcome == "failed" else "COMPLETED")
        self.store.update_step_log(
            log_id,
            status=step_status,
            completed_at=_now(),
            ended_at=_now(),
            outcome=result.outcome,
            error_detail=result.error,
            tool_calls=result.tool_calls,
            artifacts_produced=[str(a) for a in result.artifacts],
            verify_result=result.verify_result,
        )

        if not self.no_slack:
            if result.outcome == "failed":
                self.notifier.send_template("step_failed", {
                    "step_name": step.name,
                    "error": result.error or "Unknown error",
                    "retry_count": 0,
                })
            elif "step_complete" in self._notify_on:
                self.notifier.send_template("step_complete", {
                    "step_name": step.name,
                    "duration": f"{result.duration_ms / 1000:.1f}s",
                    "summary": result.verify_result or result.outcome,
                })

        return result

    def _run_script(self, step: WorkflowStep, state: RunnerState) -> StepResult:
        if step.runner and "bottleneck_detector" in step.runner:
            try:
                findings = self.detector.run()
                for f in findings:
                    if f.severity in ("CRITICAL", "HIGH"):
                        print(f"\n[BOTTLENECK] {f.description}")
                        print(f"[NOTEBOOK] Query BC-01: Prior resolution for {f.type}")
                        print(f"[NOTEBOOK] Query BC-02: Prevention for {f.type}")
                desc = f"{len(findings)} findings" if findings else "No bottlenecks"
                return StepResult(
                    step_id=step.id,
                    outcome="success",
                    artifacts=[],
                    verify_result=desc,
                )
            except Exception as e:
                return StepResult(step_id=step.id, outcome="failed", error=str(e))

        script_path = SKILL_DIR / step.runner if step.runner else None
        if not script_path or not script_path.exists():
            return StepResult(step_id=step.id, outcome="failed",
                              error=f"Script not found: {step.runner}")
        try:
            result = subprocess.run(
                ["python3", str(script_path)],
                capture_output=True, text=True,
                timeout=step.timeout_minutes * 60,
            )
            if result.returncode == 0:
                return StepResult(step_id=step.id, outcome="success")
            return StepResult(step_id=step.id, outcome="failed",
                              error=result.stderr[:500] if result.stderr else f"Exit {result.returncode}")
        except subprocess.TimeoutExpired:
            return StepResult(step_id=step.id, outcome="failed",
                              error=f"Timeout after {step.timeout_minutes}m")

    def _run_command(self, step: WorkflowStep, state: RunnerState) -> StepResult:
        cwd = os.path.expanduser(step.cwd) if step.cwd else None
        try:
            result = subprocess.run(
                step.command, shell=True,
                capture_output=True, text=True,
                timeout=step.timeout_minutes * 60,
                cwd=cwd,
            )
            if result.returncode == 0:
                return StepResult(step_id=step.id, outcome="success")
            return StepResult(
                step_id=step.id, outcome="failed",
                error=result.stderr[:500] if result.stderr else f"Exit {result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return StepResult(step_id=step.id, outcome="failed",
                              error=f"Timeout after {step.timeout_minutes}m")
        except Exception as e:
            return StepResult(step_id=step.id, outcome="failed", error=str(e))

    SKILL_RUNNERS = {
        "/mr-review": {
            "script": Path(os.path.expanduser("~/.claude/skills/mr-review/scripts/mr_review_runner.py")),
            "cwd": Path(os.path.expanduser("~/.claude/skills/mr-review")),
        },
        "/jira": {
            "script": Path(os.path.expanduser("~/.claude/skills/jira/scripts/jiratui_runner.py")),
            "cwd": Path(os.path.expanduser("~/.claude/skills/jira")),
        },
        "/dispatch-notebook": {
            "script": Path(os.path.expanduser("~/.claude/skills/dispatch-notebook/scripts/briefing_loader.py")),
            "cwd": Path(os.path.expanduser("~/.claude/skills/dispatch-notebook")),
        },
    }

    def _try_skill_runner(self, step: WorkflowStep, state: RunnerState) -> Optional[StepResult]:
        config = self.SKILL_RUNNERS.get(step.skill)
        if not config or not config["script"].exists():
            return None
        cmd = [sys.executable, str(config["script"])]
        if step.args:
            cmd.extend(shlex.split(step.args))
        timeout = (step.timeout_minutes or 10) * 60
        env = os.environ.copy()
        if step.skill == "/jira":
            env["JIRA_CALLER"] = "dispatch"
        env["DISPATCH_SKILL_CONTEXT"] = "dispatch"
        try:
            print(f"  Running: {' '.join(cmd)}", file=sys.stderr)
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, cwd=str(config["cwd"]), env=env,
            )
            if result.stdout:
                print(result.stdout.strip())
            if result.stderr:
                print(result.stderr.strip(), file=sys.stderr)
            if result.returncode == 0:
                artifact = self.collect_artifact(step)
                if artifact:
                    if state.active_task_id:
                        try:
                            self.writer.symlink_artifact(
                                state.active_task_id, str(artifact), artifact.name
                            )
                        except Exception:
                            pass
                    return StepResult(step_id=step.id, outcome="success", artifacts=[artifact])
                return StepResult(step_id=step.id, outcome="partial",
                                  error="Runner succeeded but no artifact found")
            else:
                return StepResult(step_id=step.id, outcome="failed",
                                  error=result.stderr[:500] if result.stderr else f"Exit {result.returncode}")
        except subprocess.TimeoutExpired:
            return StepResult(step_id=step.id, outcome="failed",
                              error=f"Timeout after {step.timeout_minutes}m")
        except Exception:
            return None

    def invoke_sub_skill(self, step: WorkflowStep, state: RunnerState) -> StepResult:
        runner_result = self._try_skill_runner(step, state)
        if runner_result:
            return runner_result

        handoff_path = self.write_handoff(step, state)

        env_vars = {}
        if step.skill == "/jira":
            env_vars["JIRA_CALLER"] = "dispatch"
        env_vars["DISPATCH_SKILL_CONTEXT"] = "dispatch"

        print(f"\n--- SUB-SKILL INVOCATION (handoff-only) ---")
        print(f"Skill: {step.skill}")
        print(f"Args: {step.args or ''}")
        print(f"Handoff: {handoff_path}")
        if env_vars:
            print(f"Env: {', '.join(f'{k}={v}' for k, v in env_vars.items())}")
        print(f"---\n")

        artifact = self.collect_artifact(step)
        if artifact:
            if state.active_task_id:
                try:
                    self.writer.symlink_artifact(
                        state.active_task_id, str(artifact), artifact.name
                    )
                except Exception:
                    pass
            return StepResult(
                step_id=step.id, outcome="success",
                artifacts=[artifact],
            )

        return StepResult(
            step_id=step.id, outcome="partial",
            error="No artifact found — run skill manually",
        )

    def write_handoff(self, step: WorkflowStep, state: RunnerState) -> Path:
        carry = self.store.generate_carry_forward()
        active_task = None
        if state.active_task_id:
            active_task = self.store.get_task(state.active_task_id)

        lines = [
            f"# Handoff: {step.name}",
            f"\nSkill: {step.skill}",
            f"Args: {step.args or 'none'}",
            f"Session: {state.session_id}",
            f"Mode: {state.mode}",
        ]
        if active_task:
            lines.append(f"\n## Active Task")
            lines.append(f"- {active_task['task_id']}: {active_task['title']} ({active_task['status']})")
        if carry:
            lines.append(f"\n## Carry Forward ({len(carry)} tasks)")
            for t in carry[:10]:
                lines.append(f"- [{t['priority']}] {t['task_id']}: {t['title']} ({t['status']})")

        content = "\n".join(lines) + "\n"
        return self.writer.write_handoff(step.id, content)

    def _is_fresh(self, path: Path, max_age_minutes: int = 30) -> bool:
        try:
            return (time.time() - path.stat().st_mtime) < (max_age_minutes * 60)
        except OSError:
            return False

    def collect_artifact(self, step: WorkflowStep) -> Optional[Path]:
        today = _today()
        max_age = (step.timeout_minutes or 10) + 5
        if step.skill == "/mr-review":
            pattern = os.path.expanduser(f"~/.zsh/review/{today.replace('-', '/')}/**/review.md")
            matches = sorted(globmod.glob(pattern, recursive=True),
                             key=os.path.getmtime, reverse=True)
            if matches:
                return Path(matches[0])
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
            pattern = os.path.expanduser(f"~/.zsh/review/{yesterday.replace('-', '/')}/**/review.md")
            matches = sorted(globmod.glob(pattern, recursive=True),
                             key=os.path.getmtime, reverse=True)
            if matches:
                print(f"[STALE] Using yesterday's MR review data ({yesterday})")
                return Path(matches[0])
            return None
        elif step.skill == "/jira":
            mentions_path = Path(os.path.expanduser("~/.zsh/jira/exports/mentions_latest.md"))
            if mentions_path.exists() and self._is_fresh(mentions_path, max_age):
                return mentions_path
            pattern = os.path.expanduser("~/.zsh/jira/exports/jira_export_*")
            matches = sorted(globmod.glob(pattern),
                             key=os.path.getmtime, reverse=True)
            if matches and self._is_fresh(Path(matches[0]), max_age):
                return Path(matches[0])
            return None
        elif step.skill == "/dispatch-notebook":
            cache_dir = STATE_ROOT / "notebook"
            if cache_dir.exists():
                files = sorted(cache_dir.iterdir(), key=lambda p: p.stat().st_mtime,
                                reverse=True)
                if files and self._is_fresh(files[0], max_age):
                    return files[0]
        return None

    def verify_step(self, step: WorkflowStep, result: StepResult) -> str:
        if not step.verify:
            return "no_verify"
        spec = step.verify
        if spec.file_exists:
            p = Path(os.path.expanduser(spec.file_exists))
            if not p.exists():
                return f"fail:file_missing:{spec.file_exists}"
            if spec.min_file_size_bytes and p.stat().st_size < spec.min_file_size_bytes:
                return f"fail:file_too_small:{p.stat().st_size}<{spec.min_file_size_bytes}"
        if spec.session_field:
            session = self.store.get_session(result.step_id)
            if not session or not session.get(spec.session_field):
                return f"fail:session_field_missing:{spec.session_field}"
        return "pass"

    def should_skip(self, step_id: str, state: RunnerState) -> bool:
        return step_id in state.completed_step_ids

    def write_checkpoint(self, step_id: str, result: StepResult,
                         state: RunnerState) -> None:
        checkpoint = {
            "step_id": step_id,
            "outcome": result.outcome,
            "timestamp": _now(),
        }
        self.store.append_checkpoint(state.session_id, checkpoint)
        if result.outcome in ("success", "partial", "skipped"):
            state.completed_step_ids.append(step_id)

    def get_completed_step_ids(self, session_id: str) -> List[str]:
        session = self.store.get_session(session_id)
        if not session:
            return []
        checkpoints = session.get("checkpoints", [])
        if isinstance(checkpoints, str):
            import json as j
            checkpoints = j.loads(checkpoints)
        return [
            cp["step_id"] for cp in checkpoints
            if cp.get("outcome") in ("success", "partial", "skipped")
            and cp["step_id"] != "__init"
        ]

    def compute_drift_score(self, state: RunnerState) -> float:
        enabled = [s for s in state.workflow_steps
                   if s.enabled and self._mode_matches(s, state)]
        if not enabled:
            return 0.0
        total_expected = sum(s.timeout_minutes for s in enabled)
        if total_expected == 0:
            return 0.0

        session = self.store.get_session(state.session_id)
        if not session or not session.get("started_at"):
            return 0.0

        started = session["started_at"]
        try:
            start_dt = datetime.strptime(started[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return 0.0

        elapsed = (datetime.utcnow() - start_dt).total_seconds() / 60.0
        expected_progress = min(elapsed / total_expected, 1.0)
        actual_progress = len(state.completed_step_ids) / len(enabled)
        return min(abs(expected_progress - actual_progress), 1.0)

    def inject_reorientation(self, state: RunnerState) -> None:
        enabled = [s for s in state.workflow_steps
                   if s.enabled and self._mode_matches(s, state)]
        remaining = [s.name for s in enabled if s.id not in state.completed_step_ids]
        print(f"\n--- DRIFT DETECTION ---")
        print(f"Drift score: {state.drift_score:.2f} (threshold: 0.3)")
        print(f"Completed: {len(state.completed_step_ids)}/{len(enabled)} steps")
        print(f"Active task: {state.active_task_id or 'none'}")
        print(f"Remaining: {', '.join(remaining[:5])}")
        print(f"---\n")

    def rehydrate_from_db(self, state: RunnerState) -> None:
        session = self.store.get_session(state.session_id)
        if session:
            state.completed_step_ids = self.get_completed_step_ids(state.session_id)

    def generate_priority_queue(self, state: RunnerState) -> List[str]:
        carry = self.store.generate_carry_forward()
        today_tasks = self.store.list_tasks(date=_today())
        all_tasks = {t["task_id"]: t for t in carry}
        for t in today_tasks:
            all_tasks[t["task_id"]] = t
        sorted_tasks = sorted(all_tasks.values(), key=lambda t: t.get("priority", 3))
        lines = []
        for t in sorted_tasks:
            p = t.get("priority", 3)
            label = {1: "CRITICAL", 2: "HIGH", 3: "NORMAL", 4: "LOW"}.get(p, "NORMAL")
            blocker = f" [BLOCKED: {t['blocker']}]" if t.get("blocker") else ""
            lines.append(f"P{p} {label}: {t['task_id']} — {t['title']} ({t['status']}){blocker}")
        return lines

    def _get_status(self) -> Dict:
        session = self.store.get_today_session()
        tasks = self.store.list_tasks(date=_today())
        bottlenecks = self.store.get_open_bottlenecks()
        return {
            "date": _today(),
            "session": session,
            "tasks": tasks,
            "task_counts": {
                "total": len(tasks),
                "complete": sum(1 for t in tasks if t["status"] == "COMPLETE"),
                "in_progress": sum(1 for t in tasks if t["status"] == "IN_PROGRESS"),
                "blocked": sum(1 for t in tasks if t["status"] == "BLOCKED"),
                "deferred": sum(1 for t in tasks if t["status"] == "DEFERRED"),
            },
            "bottlenecks": bottlenecks,
            "priority_queue": self.generate_priority_queue(
                RunnerState(session_id="", mode=self.mode)
            ),
        }

    def _mode_matches(self, step: WorkflowStep, state: RunnerState) -> bool:
        return state.mode in step.tags

    def _step_failure_count(self, step_id: str) -> int:
        history = self.store.get_step_history(step_id, days=7)
        count = 0
        for entry in history:
            if entry.get("outcome") == "failed":
                count += 1
            else:
                break
        return count

    def _disable_step(self, step_id: str, state: RunnerState) -> None:
        state._disabled_step_ids.append(step_id)
        for s in state.workflow_steps:
            if s.id == step_id:
                s.enabled = False
                break
        if not self.no_slack:
            self.notifier.send_template("step_disabled", {
                "step_name": step_id,
                "failure_count": 3,
            })

    def _run_eod_sequence(self, state: RunnerState) -> List[StepResult]:
        results = []

        eod_steps = [
            s for s in state.workflow_steps
            if s.enabled and "eod" in s.tags and s.id not in state._disabled_step_ids
        ]
        for step in eod_steps:
            if not self.should_skip(step.id, state):
                result = self.run_step(step, state)
                results.append(result)
                self.write_checkpoint(step.id, result, state)

        try:
            self.writer.write_carry_forward(state.session_id)
        except Exception:
            pass
        try:
            self.writer.write_task_yaml()
        except Exception:
            pass

        self._trigger_telemetry_builder()

        from optimus_runner import _today as opt_today
        if not self.optimus.check_already_reviewed(opt_today()):
            try:
                report = self.optimus.run()
                results.append(StepResult(
                    step_id="optimus_nightly", outcome="success",
                    artifacts=[report],
                ))
            except Exception as e:
                results.append(StepResult(
                    step_id="optimus_nightly", outcome="failed",
                    error=str(e),
                ))

        pending = self.notifier.flush_queue()
        if pending:
            try:
                notifications = self.store.get_pending_notifications()
                self.writer.write_slack_queue_fallback(notifications)
            except Exception:
                pass

        if not self.no_slack:
            tasks = self.store.list_tasks(date=_today())
            closed = sum(1 for t in tasks if t["status"] == "COMPLETE")
            deferred = sum(1 for t in tasks if t["status"] == "DEFERRED")
            bottlenecks = len(self.store.get_open_bottlenecks())
            self.notifier.send_template("eod_summary", {
                "tasks_closed": closed,
                "tasks_deferred": deferred,
                "bottlenecks_count": bottlenecks,
            })

        return results

    def _trigger_telemetry_builder(self) -> None:
        script = Path.home() / "agent-skills" / "dispatch-harness" / "scripts" / "telemetry_builder.py"
        if not script.exists():
            return
        try:
            subprocess.run(
                ["python3", str(script)], timeout=60,
                capture_output=True,
            )
        except Exception:
            pass


def _run_tests():
    import tempfile
    import shutil

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from state_store import StateStore
    from log_writer import LogWriter

    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS: {name}")
        else:
            failed += 1
            print(f"  FAIL: {name}")

    tmpdir = tempfile.mkdtemp(prefix="dispatch_runner_test_")
    db_path = os.path.join(tmpdir, "test.db")

    wf_content = """
version: '1.0'
operator:
  gitlab_username: '@test'
  slack_channel_id: C0TEST
  timezone: UTC
defaults:
  git_permission: false
  require_human_gate: true
  slack_notify_on:
  - step_complete
steps:
- id: step_a
  name: Step A
  command: "echo hello"
  timeout_minutes: 1
  tags: [morning]
  enabled: true
- id: step_b
  name: Step B
  command: "echo world"
  timeout_minutes: 1
  tags: [morning]
  enabled: true
  blocking: true
- id: step_c
  name: Step C
  command: "echo eod"
  timeout_minutes: 1
  tags: [eod]
  enabled: true
- id: step_disabled
  name: Disabled Step
  command: "echo no"
  timeout_minutes: 1
  tags: [morning]
  enabled: false
human_gates:
- after: step_a
  message: "Continue after step A?"
schedule: {}
"""

    global WORKFLOW_PATH, STATE_ROOT
    old_wp = WORKFLOW_PATH
    old_sr = STATE_ROOT
    WORKFLOW_PATH = Path(tmpdir) / "workflow.yaml"
    STATE_ROOT = Path(tmpdir)

    (Path(tmpdir) / "workflow.yaml").write_text(wf_content)

    old_day_dir = LogWriter.day_dir
    def patched_day_dir(self_lw, date=None):
        d = date or self_lw._date
        parts = d.split("-")
        return Path(tmpdir) / parts[0] / parts[1] / parts[2]
    LogWriter.day_dir = patched_day_dir

    with StateStore(db_path=db_path) as store:
        store.schema_init()

        try:
            # Test 1: load_workflow parses steps
            runner = DispatchRunner(store, "morning", no_slack=True)
            steps = runner.load_workflow()
            check("load_workflow_count", len(steps) == 4)

            # Test 2: WorkflowStep fields
            step_a = next((s for s in steps if s.id == "step_a"), None)
            check("step_fields", step_a and step_a.name == "Step A" and step_a.timeout_minutes == 1)

            # Test 3: WorkflowStep defaults
            check("step_defaults", step_a and step_a.blocking is False and step_a.on_blocker == "log_and_continue")

            # Test 4: human gates parsed
            check("human_gates", runner._human_gates.get("step_a") == "Continue after step A?")

            # Test 5: mode_matches - morning
            state = RunnerState(session_id="test", mode="morning")
            check("mode_morning", runner._mode_matches(step_a, state))

            # Test 6: mode_matches - eod
            step_c = next((s for s in steps if s.id == "step_c"), None)
            check("mode_eod_no_match", not runner._mode_matches(step_c, state))
            state_eod = RunnerState(session_id="test", mode="eod")
            check("mode_eod_match", runner._mode_matches(step_c, state_eod))

            # Test 7: start_session creates DB row
            runner2 = DispatchRunner(store, "morning", no_slack=True)
            state2 = runner2.start_session()
            check("start_session", state2.session_id and state2.mode == "morning")
            db_session = store.get_session(state2.session_id)
            check("start_session_db", db_session is not None)

            # Test 8: resume_session returns None when no open session
            store.update_session(state2.session_id, ended_at=_now())
            runner3 = DispatchRunner(store, "morning", no_slack=True)
            runner3.load_workflow()
            resumed = runner3.resume_session()
            check("resume_none_when_ended", resumed is None)

            # Test 9: should_skip
            state3 = RunnerState(session_id="test", mode="morning",
                                 completed_step_ids=["step_a"])
            check("should_skip_completed", runner.should_skip("step_a", state3))
            check("should_not_skip_new", not runner.should_skip("step_b", state3))

            # Test 10: write_checkpoint
            session4 = store.create_session("morning")
            state4 = RunnerState(session_id=session4["session_id"], mode="morning")
            result_ok = StepResult(step_id="step_a", outcome="success")
            runner.write_checkpoint("step_a", result_ok, state4)
            check("checkpoint_added", "step_a" in state4.completed_step_ids)

            # Test 11: failed steps not in completed
            result_fail = StepResult(step_id="step_b", outcome="failed")
            runner.write_checkpoint("step_b", result_fail, state4)
            check("failed_not_completed", "step_b" not in state4.completed_step_ids)

            # Test 12: _run_command success
            cmd_step = WorkflowStep(id="cmd_test", name="cmd test",
                                    command="echo ok", timeout_minutes=1, tags=["morning"])
            cmd_result = runner._run_command(cmd_step, state4)
            check("run_command_success", cmd_result.outcome == "success")

            # Test 13: _run_command failure
            fail_step = WorkflowStep(id="fail_test", name="fail test",
                                     command="exit 1", timeout_minutes=1, tags=["morning"])
            fail_result = runner._run_command(fail_step, state4)
            check("run_command_failure", fail_result.outcome == "failed")

            # Test 14: timeout
            timeout_step = WorkflowStep(id="timeout_test", name="timeout test",
                                        command="sleep 10", timeout_minutes=0,
                                        tags=["morning"])
            timeout_step.timeout_minutes = 0
            # We set timeout_minutes to 0 which means 0 seconds timeout
            # Need a custom approach: just check the error message pattern
            # Actually timeout_minutes * 60 = 0, so subprocess will timeout immediately
            to_result = runner._run_command(timeout_step, state4)
            check("timeout_produces_failed",
                  to_result.outcome == "failed" and "imeout" in (to_result.error or ""))

            # Test 15: step failure count
            session5 = store.create_session("morning")
            store.log_step(session5["session_id"], "flaky_step", outcome="failed")
            store.log_step(session5["session_id"], "flaky_step", outcome="failed")
            store.log_step(session5["session_id"], "flaky_step", outcome="failed")
            count = runner._step_failure_count("flaky_step")
            check("failure_count_3", count == 3)

            # Test 16: disable step
            state5 = RunnerState(session_id="test", mode="morning",
                                 workflow_steps=list(steps))
            runner._disable_step("step_a", state5)
            check("disable_step",
                  "step_a" in state5._disabled_step_ids
                  and not next(s for s in state5.workflow_steps if s.id == "step_a").enabled)

            # Test 17: get_completed_step_ids
            session6 = store.create_session("morning")
            store.append_checkpoint(session6["session_id"],
                                    {"step_id": "s1", "outcome": "success", "timestamp": _now()})
            store.append_checkpoint(session6["session_id"],
                                    {"step_id": "s2", "outcome": "failed", "timestamp": _now()})
            store.append_checkpoint(session6["session_id"],
                                    {"step_id": "s3", "outcome": "partial", "timestamp": _now()})
            completed = runner.get_completed_step_ids(session6["session_id"])
            check("completed_ids", "s1" in completed and "s2" not in completed and "s3" in completed)

            # Test 18: priority queue
            store.create_task("T-PQ1", "Critical task", priority=1)
            store.create_task("T-PQ2", "Low task", priority=4)
            pq = runner.generate_priority_queue(RunnerState(session_id="", mode="morning"))
            check("priority_queue", len(pq) >= 2 and "P1 CRITICAL" in pq[0])

        finally:
            WORKFLOW_PATH = old_wp
            STATE_ROOT = old_sr
            LogWriter.day_dir = old_day_dir

    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"\n{passed} passed, {failed} failed out of {passed + failed}")
    return failed == 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        success = _run_tests()
        sys.exit(0 if success else 1)

    parser = argparse.ArgumentParser(description="Dispatch workflow runner")
    parser.add_argument("--mode", choices=["morning", "eod", "step", "status"],
                        default="morning", help="Execution mode")
    parser.add_argument("--step", help="Step ID (required for --mode=step)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without executing")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Force cache refresh on sub-skills")
    parser.add_argument("--no-slack", action="store_true",
                        help="Suppress Slack notifications")
    args = parser.parse_args()

    if args.mode == "step" and not args.step:
        parser.error("--step is required when --mode=step")

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from state_store import StateStore

    with StateStore() as store:
        store.schema_init()
        runner = DispatchRunner(store, args.mode,
                                no_slack=args.no_slack, dry_run=args.dry_run)

        if args.mode == "status":
            print(json.dumps(runner._get_status(), indent=2, default=str))
        elif args.mode == "step":
            state = runner.resume_session() or runner.start_session()
            step = next((s for s in state.workflow_steps if s.id == args.step), None)
            if not step:
                print(f"Step '{args.step}' not found in workflow")
                sys.exit(1)
            result = runner.run_step(step, state)
            runner.end_session(state)
            print(json.dumps(asdict(result), indent=2, default=str))
        else:
            results = runner.run()
            summary = {
                "mode": args.mode,
                "steps_executed": len(results),
                "outcomes": {r.step_id: r.outcome for r in results},
            }
            print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
