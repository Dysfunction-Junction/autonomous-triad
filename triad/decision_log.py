"""Decision ledger: append-only JSONL log of agent decisions across projects.

Each block records what an agent decided, why, what it touched, and what
came before it (`parent`) — so a regression can be traced back to the
decision that caused it, not just the commit that happened to surface it.

WARNING: `--intent` and `--reasoning` are free text, stored in plain JSON.
Never paste secrets, tokens, or credentials into them. On POSIX, the log
file is created with restrictive permissions (0o600) as a baseline
mitigation; on Windows, os.chmod cannot restrict read access (it only
toggles the read-only bit), so this mitigation does not apply there.
Either way, this is not a substitute for not logging secrets in the
first place.

Basic first pass. Pivot later: SQLite index for fast --touches/--since
queries once the log is large enough that linear scan is slow.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

LOG_FILENAME = "ACTIVITY_LOG.jsonl"
BLOCK_STATUSES = ("proposed", "done", "failed", "abandoned")


def _default_log_path() -> Path:
    env_path = os.environ.get("TRIAD_LOG_PATH")
    if env_path:
        return Path(env_path)
    return Path.home() / "projects" / LOG_FILENAME


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


def _git_author(cwd: Optional[Path] = None) -> str:
    if os.environ.get("TRIAD_AGENT_NAME"):
        return os.environ["TRIAD_AGENT_NAME"]
    try:
        out = subprocess.run(
            ["git", "config", "user.name"],
            cwd=cwd or Path.cwd(), capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown-agent"


def _last_block(log_path: Path, project: Optional[str]) -> Optional[dict]:
    if not log_path.exists():
        return None
    last = None
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                block = json.loads(line)
            except json.JSONDecodeError:
                continue
            if project is None or block.get("project") == project:
                last = block
    return last


def get_block(block_id: str, log_path: Optional[Path] = None) -> Optional[dict]:
    """Direct id lookup -- unlike query_blocks(), not subject to `limit`
    truncation, so it finds a block regardless of how old it is."""
    log_path = log_path or _default_log_path()
    if not log_path.exists():
        return None
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                block = json.loads(line)
            except json.JSONDecodeError:
                continue
            if block.get("id") == block_id:
                return block
    return None


def _block_exists(log_path: Path, block_id: str) -> bool:
    return get_block(block_id, log_path=log_path) is not None


def add_block(
    intent: str,
    reasoning: str,
    *,
    touches: Optional[list[str]] = None,
    actions: Optional[list[dict]] = None,
    verification: Optional[str] = None,
    supersedes: Optional[str] = None,
    redirect_to: Optional[str] = None,
    redirect_claim: Optional[str] = None,
    project: Optional[str] = None,
    agent: Optional[str] = None,
    commit: Optional[str] = None,
    trace_id: Optional[str] = None,
    status: str = "proposed",
    log_path: Optional[Path] = None,
) -> dict:
    """redirect_to/redirect_claim: use when you saw another agent's claim and
    decided to step aside, hand off, or offer to help instead of colliding.
    redirect_to is the other agent's name; redirect_claim is their claim id
    (from `triad.claims status`). The reasoning field should say why.

    trace_id: shared id across a multi-step task's blocks (claim -> edits ->
    commit -> release), so `query --trace-id <id>` finds everything for that
    task without walking the parent chain. If omitted, a new one is minted
    and returned in the block -- reuse it on subsequent calls for the same
    task.

    status: proposed (default) -> done | failed | abandoned. Close it with
    `resolve_block(block_id, status, ...)` once the outcome is known; an
    open-ended "proposed" with no resolution is itself a signal something
    stalled.
    """
    if status not in BLOCK_STATUSES:
        raise ValueError(f"status must be one of {BLOCK_STATUSES}, got: {status!r}")

    log_path = log_path or _default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cwd = Path.cwd()
    project = project or _git_root(cwd) or cwd.name
    parent = _last_block(log_path, project)

    if supersedes and not _block_exists(log_path, supersedes):
        raise ValueError(f"--supersedes references unknown block id: {supersedes}")

    actions = list(actions or [])
    if commit:
        actions.append({"type": "commit", "sha": commit})
    if redirect_to or redirect_claim:
        actions.append({"type": "redirect", "to_agent": redirect_to, "their_claim": redirect_claim})

    block = {
        "id": uuid.uuid4().hex[:12],
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": agent or _git_author(cwd),
        "project": project,
        "parent": parent["id"] if parent else None,
        "trace_id": trace_id or uuid.uuid4().hex[:12],
        "status": status,
        "intent": intent,
        "reasoning": reasoning,
        "actions": actions,
        "verification": verification,
        "touches": touches or [],
        "supersedes": supersedes,
    }

    # Create atomically with restrictive mode (POSIX) rather than write-then-chmod,
    # which leaves a window where the file exists with default permissions.
    fd = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(block, ensure_ascii=False) + "\n")

    return block


def resolve_block(
    block_id: str,
    status: str,
    outcome: Optional[str] = None,
    project: Optional[str] = None,
    log_path: Optional[Path] = None,
) -> dict:
    """Close a 'proposed' block by appending a new block that supersedes it
    with the final status. Append-only -- never mutates the original line.

    Reuses the target block's own trace_id and project rather than the
    caller's cwd/args, so `query --trace-id <id>` returns the resolution
    too, and resolving from a different directory doesn't misfile it under
    the wrong project.
    """
    if status not in BLOCK_STATUSES or status == "proposed":
        raise ValueError(f"status must be one of {[s for s in BLOCK_STATUSES if s != 'proposed']}, got: {status!r}")

    log_path = log_path or _default_log_path()
    target = get_block(block_id, log_path=log_path)
    if target is None:
        raise ValueError(f"unknown block id: {block_id}")
    if target.get("status") not in (None, "proposed"):
        raise ValueError(f"block {block_id} is already resolved as {target.get('status')!r}")
    already = next(
        (b for b in query_blocks(log_path=log_path, limit=10**9) if b.get("supersedes") == block_id),
        None,
    )
    if already is not None:
        raise ValueError(f"block {block_id} was already resolved by [{already['id']}]")

    return add_block(
        intent=f"resolve {block_id} as {status}",
        reasoning=outcome or f"marked {status}, no further detail given",
        supersedes=block_id,
        project=project or target.get("project"),
        trace_id=target.get("trace_id"),
        status=status,
        log_path=log_path,
    )


def query_blocks(
    log_path: Optional[Path] = None,
    project: Optional[str] = None,
    touches: Optional[str] = None,
    since: Optional[str] = None,
    trace_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    log_path = log_path or _default_log_path()
    if not log_path.exists():
        return []

    results = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                block = json.loads(line)
            except json.JSONDecodeError:
                continue
            if project and block.get("project") != project:
                continue
            if touches and not any(touches in t for t in block.get("touches", [])):
                continue
            if since and block.get("ts", "") < since:
                continue
            if trace_id and block.get("trace_id") != trace_id:
                continue
            if status and block.get("status") != status:
                continue
            results.append(block)

    return results[-limit:]


def format_block(block: dict) -> str:
    status_suffix = f"  [{block['status']}]" if block.get("status") and block["status"] != "proposed" else ""
    lines = [
        f"[{block['id']}] {block['ts']}  {block['agent']} @ {block['project']}{status_suffix}",
        f"  intent:  {block['intent']}",
        f"  why:     {block['reasoning']}",
    ]
    if block.get("trace_id"):
        lines.append(f"  trace:   {block['trace_id']}")
    if block.get("touches"):
        lines.append(f"  touches: {', '.join(block['touches'])}")
    if block.get("actions"):
        for a in block["actions"]:
            lines.append(f"  action:  {a}")
    if block.get("verification"):
        lines.append(f"  verify:  {block['verification']}")
    if block.get("supersedes"):
        lines.append(f"  supersedes: {block['supersedes']}")
    if block.get("parent"):
        lines.append(f"  parent:  {block['parent']}")
    return "\n".join(lines)


def _cmd_add(args: argparse.Namespace) -> int:
    try:
        block = add_block(
            intent=args.intent,
            reasoning=args.reasoning,
            touches=args.touches.split(",") if args.touches else [],
            verification=args.verification,
            supersedes=args.supersedes,
            redirect_to=args.redirect_to,
            redirect_claim=args.redirect_claim,
            project=args.project,
            agent=args.agent,
            commit=args.commit,
            trace_id=args.trace_id,
            status=args.status,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    print(format_block(block))
    if not args.commit:
        print(
            f"\nTip: tag the commit that implements this with a trailer so git and the "
            f"ledger point at each other:\n  Decision-Ledger: {block['id']}"
        )
    if not args.trace_id:
        print(f"Tip: reuse this task's trace id on later steps: --trace-id {block['trace_id']}")
    if block["status"] == "proposed":
        print(f"Tip: close this out once you know the outcome: triad.decision_log resolve {block['id']} --status done|failed|abandoned")
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    try:
        block = resolve_block(args.block_id, args.status, outcome=args.outcome, project=args.project)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    print(format_block(block))
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    blocks = query_blocks(
        project=args.project,
        touches=args.touches,
        since=args.since,
        trace_id=args.trace_id,
        status=args.status,
        limit=args.limit,
    )
    if not blocks:
        print("No matching blocks.")
        return 0
    for block in blocks:
        print(format_block(block))
        print()
    return 0


def _cmd_tail(args: argparse.Namespace) -> int:
    blocks = query_blocks(project=args.project, limit=args.n)
    for block in blocks:
        print(format_block(block))
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="decision_log", description="Append-only agent decision ledger")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Append a new decision block")
    p_add.add_argument("--intent", required=True, help="What this decision/action does")
    p_add.add_argument("--reasoning", required=True, help="Why this decision was made")
    p_add.add_argument("--touches", default="", help="Comma-separated file/area globs affected")
    p_add.add_argument("--verification", default=None, help="How this was verified (tests, typecheck, etc.)")
    p_add.add_argument("--supersedes", default=None, help="ID of a prior block this corrects")
    p_add.add_argument("--project", default=None, help="Project name override")
    p_add.add_argument("--agent", default=None, help="Agent name override")
    p_add.add_argument("--commit", default=None, help="Commit SHA this block corresponds to (links block -> commit)")
    p_add.add_argument("--redirect-to", default=None, help="Agent name you're handing off to / stepping aside for (explain why in --reasoning)")
    p_add.add_argument("--redirect-claim", default=None, help="The other agent's claim id (from `triad.claims status`) this redirect relates to")
    p_add.add_argument("--trace-id", default=None, help="Shared id across this task's blocks; omit to mint a new one (printed in the result)")
    p_add.add_argument("--status", default="proposed", choices=BLOCK_STATUSES, help="Default: proposed. Close later with `resolve`.")
    p_add.set_defaults(func=_cmd_add)

    p_resolve = sub.add_parser("resolve", help="Close a 'proposed' block with its final outcome")
    p_resolve.add_argument("block_id")
    p_resolve.add_argument("--status", required=True, choices=[s for s in BLOCK_STATUSES if s != "proposed"])
    p_resolve.add_argument("--outcome", default=None, help="What happened (why it failed/was abandoned, or confirmation it worked)")
    p_resolve.add_argument("--project", default=None)
    p_resolve.set_defaults(func=_cmd_resolve)

    p_query = sub.add_parser("query", help="Search the decision ledger")
    p_query.add_argument("--project", default=None)
    p_query.add_argument("--touches", default=None, help="Substring match against touches globs")
    p_query.add_argument("--since", default=None, help="ISO timestamp lower bound")
    p_query.add_argument("--trace-id", default=None, help="Find every block for one multi-step task")
    p_query.add_argument("--status", default=None, choices=BLOCK_STATUSES)
    p_query.add_argument("--limit", type=int, default=20)
    p_query.set_defaults(func=_cmd_query)

    p_tail = sub.add_parser("tail", help="Show the most recent N blocks (read-first entry point)")
    p_tail.add_argument("-n", type=int, default=10)
    p_tail.add_argument("--project", default=None)
    p_tail.set_defaults(func=_cmd_tail)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
