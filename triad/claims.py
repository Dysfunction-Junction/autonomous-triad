"""Live claims/presence: who's working on what, right now.

Separate from decision_log.py (which is history/why). This is current
state only — a single JSON file that gets overwritten, not appended —
so agents can check before starting work and avoid colliding, or find
each other and redirect ("they're already on this, I'll help elsewhere
or pick up what they need next").

Basic first pass: a flat JSON dict keyed by claim id. No file locking
(Windows + multiple agents means a lost write is possible but rare and
self-healing via staleness TTL) — pivot later if collisions on the
claims file itself become a real problem.

`contest` logs the Advisory Council's actual verdict text into the
decision ledger (plaintext JSONL) — the secrets warning in
decision_log.py applies to council output here too.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

CLAIMS_FILENAME = "CLAIMS.json"
DEFAULT_TTL_MINUTES = 60


def _default_claims_path() -> Path:
    env_path = os.environ.get("TRIAD_CLAIMS_PATH")
    if env_path:
        return Path(env_path)
    return Path.home() / "projects" / CLAIMS_FILENAME


def _git_root(start: Path) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start, capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return Path(out.stdout.strip()).name
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _git_author(cwd: Path) -> str:
    if os.environ.get("TRIAD_AGENT_NAME"):
        return os.environ["TRIAD_AGENT_NAME"]
    try:
        out = subprocess.run(
            ["git", "config", "user.name"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown-agent"


def _is_explicit_agent(agent: Optional[str]) -> bool:
    """True only if the caller passed --agent or set TRIAD_AGENT_NAME -- i.e.
    identity we can trust to mean "the same agent", not a shared fallback
    like git config user.name (often the same for every agent on a machine)
    or "unknown-agent". Collision checks must not skip same-name claims when
    identity is a weak fallback, or same-named agents never see each other.
    """
    return bool(agent) and agent != "unknown-agent"


def _load(claims_path: Path) -> dict:
    if not claims_path.exists():
        return {}
    try:
        with claims_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _save(claims_path: Path, data: dict) -> None:
    import tempfile
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=claims_path.parent, prefix=claims_path.stem, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        last_err = None
        for _ in range(5):
            try:
                os.replace(tmp_name, claims_path)
                return
            except PermissionError as e:
                last_err = e
                import time
                time.sleep(0.1)
        if last_err:
            raise last_err
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def _is_stale(claim: dict) -> bool:
    try:
        started = datetime.fromisoformat(claim["started"])
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        ttl = max(1, min(int(claim.get("ttl_minutes", DEFAULT_TTL_MINUTES)), 10080))
        return datetime.now(timezone.utc) - started > timedelta(minutes=ttl)
    except (KeyError, ValueError, TypeError, OverflowError):
        return True


def _prune_stale(data: dict) -> dict:
    return {k: v for k, v in data.items() if not _is_stale(v)}


def _strip_control_chars(s: str) -> str:
    return "".join(ch for ch in s if ch == "\t" or ord(ch) >= 32)


def _real_overlap(a: set[str], b: set[str]) -> bool:
    """True if any path in `a` equals or is a parent/child directory of any
    path in `b`. Not substring matching -- "a.py" must not match "data.py".
    Basic path-prefix semantics, not full glob/fnmatch (pivot later if that
    turns out to matter).
    """
    def norm(p: str) -> str:
        return p.strip().replace("\\", "/").rstrip("/")

    a_norm = {norm(p) for p in a if norm(p)}
    b_norm = {norm(p) for p in b if norm(p)}

    for x in a_norm:
        for y in b_norm:
            if x == y or x.startswith(y + "/") or y.startswith(x + "/"):
                return True
    return False


def claim(
    task: str,
    touching: Optional[list[str]] = None,
    project: Optional[str] = None,
    agent: Optional[str] = None,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
    claims_path: Optional[Path] = None,
) -> tuple[dict, list[dict]]:
    """Register a claim. Returns (this claim, list of conflicting active claims)."""
    claims_path = claims_path or _default_claims_path()
    project = project or _git_root(Path.cwd()) or Path.cwd().name
    explicit_agent = _is_explicit_agent(agent) or bool(os.environ.get("TRIAD_AGENT_NAME"))
    agent = agent or _git_author(Path.cwd())
    touching = [t.strip() for t in (touching or []) if t.strip()]
    # Clamp to a sane range: an unclamped huge TTL (e.g. from a typo'd
    # exponent) can overflow timedelta() in every later claim()/status()
    # call, permanently poisoning the shared claims file.
    ttl_minutes = max(1, min(int(ttl_minutes), 10080))

    data = _load(claims_path)
    data = _prune_stale(data)

    conflicts = []
    for existing in data.values():
        if existing.get("project") != project:
            continue
        # Only treat "same agent name" as "same agent" when the CALLER's
        # identity was explicit (we don't know whether the stored claim's
        # name was explicit too, since that isn't recorded). This means a
        # stored fallback-name claim can be skipped by an explicit caller
        # who happens to share that name -- an accepted edge case, not
        # a guarantee that both sides were explicit.
        if existing.get("agent") == agent and explicit_agent:
            continue
        existing_touches = set(existing.get("touching", []))
        if touching and existing_touches and _real_overlap(set(touching), existing_touches):
            conflicts.append(existing)

    claim_id = uuid.uuid4().hex[:12]
    entry = {
        "id": claim_id,
        "agent": agent,
        "project": project,
        "task": task,
        "touching": touching,
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ttl_minutes": ttl_minutes,
        "status": "in_progress",
    }
    data[claim_id] = entry
    _save(claims_path, data)
    return entry, conflicts


def release(claim_id: str, claims_path: Optional[Path] = None) -> bool:
    claims_path = claims_path or _default_claims_path()
    data = _load(claims_path)
    if claim_id not in data:
        return False
    del data[claim_id]
    _save(claims_path, data)
    return True


def status(
    project: Optional[str] = None,
    claims_path: Optional[Path] = None,
) -> list[dict]:
    """Read-only: does not prune or write. Pruning happens on claim()/release()
    so a status() call can never race a concurrent claim() into losing it."""
    claims_path = claims_path or _default_claims_path()
    data = _load(claims_path)
    data = {k: v for k, v in data.items() if not _is_stale(v)}
    entries = list(data.values())
    if project:
        entries = [e for e in entries if e.get("project") == project]
    return sorted(entries, key=lambda e: e.get("started", ""))


def format_claim(c: dict) -> str:
    cid = _strip_control_chars(str(c.get("id", "?")))
    agent = _strip_control_chars(str(c.get("agent", "?")))
    project = _strip_control_chars(str(c.get("project", "?")))
    task = _strip_control_chars(str(c.get("task", "?")))
    touching = ", ".join(_strip_control_chars(str(t)) for t in c.get("touching", [])) or "(unspecified)"
    started = _strip_control_chars(str(c.get("started", "?")))
    return (
        f"[{cid}] {agent} @ {project} - {task}\n"
        f"  touching: {touching}\n"
        f"  started:  {started}"
    )


def _cmd_claim(args: argparse.Namespace) -> int:
    entry, conflicts = claim(
        task=args.task,
        touching=args.touching.split(",") if args.touching else [],
        project=args.project,
        agent=args.agent,
        ttl_minutes=args.ttl,
    )
    if conflicts:
        print("WARNING: possible collision with active claim(s):\n")
        for c in conflicts:
            print(format_claim(c))
            print()
        print(
            "Coordinate via SendMessage. If one of you should yield, log it:\n"
            "  python -m triad.decision_log add --intent \"...\" --reasoning \"...\" \\\n"
            "    --redirect-to <their-agent-name> --redirect-claim <their-claim-id>\n"
            "If neither of you should yield, escalate to the Advisory Council -- include\n"
            "what you're each actually trying to accomplish, not just why you should win:\n"
            "  python -m triad.claims contest --agent-a <you> --task-a \"...\" --reason-a \"...\" \\\n"
            "    --agent-b <them> --task-b \"...\" --reason-b \"...\" --touching \"...\"\n"
        )
    print(format_claim(entry))
    return 0


def _cmd_release(args: argparse.Namespace) -> int:
    ok = release(args.claim_id)
    print("Released." if ok else f"No claim found with id {args.claim_id}")
    return 0 if ok else 1


def _cmd_contest(args: argparse.Namespace) -> int:
    """Neither agent wants to yield on a conflicting claim: ask the Advisory
    Council to decide, and log the verdict as the block that resolves it.

    The council's verdict is an opening position, not binding -- either
    agent can contest it with --rebut (a counter-argument) and --rebutting
    (the prior verdict's block id). The rebuttal reopens the question with
    the full prior exchange as context, and the new verdict supersedes the
    old one, so the whole debate -- not just the final answer -- is in the
    ledger chain.

    This is not a new resolution mechanism -- `triad consult` already exists
    (triad_engine.py cmd_consult) and is used elsewhere for architecture
    decisions. This just routes a claims conflict through the same path.
    """
    import importlib

    decision_log = importlib.import_module("triad.decision_log")

    prior_block = None
    if args.rebutting:
        prior_block = decision_log.get_block(args.rebutting)
        if prior_block is None:
            print(f"Error: --rebutting references unknown block id: {args.rebutting}", file=sys.stderr)
            return 2
    elif not (args.task_a and args.agent_b and args.task_b and args.reason_b):
        print(
            "Error: --task-a, --agent-b, --task-b, and --reason-b are required for a new "
            "contest (only --rebutting + --reason-a are needed to contest a prior verdict).",
            file=sys.stderr,
        )
        return 2

    if prior_block:
        prompt = (
            f"You previously ruled on this conflict (reproduced below). One of the agents "
            f"is contesting that verdict -- take the rebuttal seriously; you may have "
            f"missed something, but don't reverse just because someone pushed back.\n\n"
            f"--- Your prior verdict ---\n{prior_block['reasoning']}\n"
            f"(See that block's full council output in the ledger if you logged it; this "
            f"is only the summary.)\n\n"
            f"--- Rebuttal from {args.agent_a} ---\n{args.reason_a}\n\n"
            f"Overlapping scope: {args.touching}\n\n"
            f"Re-evaluate: does the rebuttal change the answer? Stand by your prior verdict "
            f"and explain why the rebuttal doesn't change it, or revise and explain what "
            f"changed your mind."
        )
    else:
        prompt = (
            f"Two agents both claim they should proceed on overlapping work and "
            f"neither wants to yield.\n\n"
            f"Agent A ({args.agent_a})\n"
            f"  task:      {args.task_a}\n"
            f"  reasoning: {args.reason_a}\n\n"
            f"Agent B ({args.agent_b})\n"
            f"  task:      {args.task_b}\n"
            f"  reasoning: {args.reason_b}\n\n"
            f"Overlapping scope: {args.touching}\n\n"
            f"Before picking a winner, evaluate the actual tasks and reasoning above, not just "
            f"who sounds more confident:\n"
            f"1. Is this conflict even real? Could both tasks be done without touching the same "
            f"scope (e.g. one is a subset, or they're conceptually separable)?\n"
            f"2. Is either agent's stated reasoning actually a valid basis for priority, or is it "
            f"just a justification (e.g. 'I started first' is usually not a real tie-breaker)?\n"
            f"3. Is there a third approach neither agent proposed -- a different split, a different "
            f"order, a different boundary -- that resolves this better than picking a winner?\n"
            f"Only if the conflict is real and no better split exists, decide who should proceed "
            f"and say why.\n\n"
            f"This verdict is an opening position, not binding. Either agent may contest it with "
            f"a rebuttal; say so is possible."
        )

    try:
        triad_engine = importlib.import_module("triad.triad_engine")
    except ImportError as e:
        print(f"Could not load triad_engine for consult: {e}", file=sys.stderr)
        return 1

    consult_args = argparse.Namespace(
        prompt=prompt, context="", context_file="", engine="auto",
        competition=False, adversarial=False, task="architecture",
    )
    verb = "Re-evaluating (rebuttal)" if prior_block else "Asking the Advisory Council to resolve this conflict"
    print(f"[Contest] {verb}...\n")

    # Capture the actual verdict text -- it must be the real ruling, not
    # boilerplate, or a --rebutting follow-up has nothing real to argue
    # against and the "whole debate is in the ledger" claim is false.
    import contextlib
    import io

    class _Tee(io.TextIOBase):
        def __init__(self, *streams):
            self._streams = streams

        def write(self, s):
            for stream in self._streams:
                stream.write(s)
            return len(s)

        def flush(self):
            for stream in self._streams:
                stream.flush()

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            rc = triad_engine.cmd_consult(consult_args)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    verdict = buf.getvalue().strip()

    if rc not in (0, None) or not verdict:
        print("\nConsult failed or returned no output; not logging a verdict.", file=sys.stderr)
        return 1

    intent = (
        f"Advisory Council re-evaluated claim conflict after rebuttal from {args.agent_a}"
        if prior_block else
        f"Advisory Council resolved claim conflict between {args.agent_a} and {args.agent_b}"
    )
    reasoning = (
        f"Rebuttal from {args.agent_a} on prior verdict [{args.rebutting}] "
        f"(scope: {args.touching}).\n\nCouncil re-evaluation:\n{verdict}"
        if prior_block else
        f"A ({args.agent_a}): {args.task_a} / {args.reason_a}\n"
        f"B ({args.agent_b}): {args.task_b} / {args.reason_b}\n\n"
        f"Council verdict:\n{verdict}"
    )
    # Model output now lands in the plaintext log -- the secrets warning at
    # the top of decision_log.py applies to council verdicts too.
    block = decision_log.add_block(
        intent=intent,
        reasoning=reasoning,
        touches=[t.strip() for t in args.touching.split(",") if t.strip()],
        project=args.project,
        agent="advisory-council",
        supersedes=args.rebutting,
    )
    print(f"\nLogged as [{block['id']}]. Reference this block id when either agent proceeds.")
    if not prior_block:
        print(f"If either agent disagrees with this verdict, contest it:\n"
              f"  python -m triad.claims contest --agent-a <you> --reason-a \"<rebuttal>\" "
              f"--rebutting {block['id']} --touching \"{args.touching}\" --project \"{args.project or ''}\"")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    entries = status(project=args.project)
    if not entries:
        print("No active claims.")
        return 0
    for c in entries:
        print(format_claim(c))
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claims", description="Live agent task claims (who's working on what, right now)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_claim = sub.add_parser("claim", help="Register that you're starting a task (warns on overlap)")
    p_claim.add_argument("--task", required=True, help="Short description of the task")
    p_claim.add_argument("--touching", default="", help="Comma-separated file/area globs you'll be working in")
    p_claim.add_argument("--project", default=None)
    p_claim.add_argument("--agent", default=None)
    p_claim.add_argument("--ttl", type=int, default=DEFAULT_TTL_MINUTES, help="Minutes before a claim is considered stale")
    p_claim.set_defaults(func=_cmd_claim)

    p_release = sub.add_parser("release", help="Clear your claim when done")
    p_release.add_argument("claim_id")
    p_release.set_defaults(func=_cmd_release)

    p_status = sub.add_parser("status", help="See who's working on what right now")
    p_status.add_argument("--project", default=None)
    p_status.set_defaults(func=_cmd_status)

    p_contest = sub.add_parser("contest", help="Neither agent yields on a conflict: escalate to the Advisory Council")
    p_contest.add_argument("--agent-a", required=True, help="You -- the agent raising this contest or rebuttal")
    p_contest.add_argument("--task-a", default=None, help="What agent A is actually trying to accomplish (required unless --rebutting)")
    p_contest.add_argument("--reason-a", required=True, help="Why agent A thinks it should proceed, or the rebuttal argument if --rebutting")
    p_contest.add_argument("--agent-b", default=None, help="Required unless --rebutting")
    p_contest.add_argument("--task-b", default=None, help="What agent B is actually trying to accomplish (required unless --rebutting)")
    p_contest.add_argument("--reason-b", default=None, help="Why agent B thinks it should proceed (required unless --rebutting)")
    p_contest.add_argument("--touching", default="", help="Comma-separated overlapping file/area globs")
    p_contest.add_argument("--project", default=None)
    p_contest.add_argument("--rebutting", default=None, help="Block id of a prior verdict you're contesting with a new --reason-a")
    p_contest.set_defaults(func=_cmd_contest)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
