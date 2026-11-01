"""Decision ledger: append-only JSONL log of agent decisions across projects.

Each block records what an agent decided, why, what it touched, and what
came before it (`parent`) — so a regression can be traced back to the
decision that caused it, not just the commit that happened to surface it.

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


def _git_author() -> str:
    for key in ("TRIAD_AGENT_NAME",):
        if os.environ.get(key):
            return os.environ[key]
    try:
        out = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=5,
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


def add_block(
    intent: str,
    reasoning: str,
    touches: Optional[list[str]] = None,
    actions: Optional[list[dict]] = None,
    verification: Optional[str] = None,
    supersedes: Optional[str] = None,
    project: Optional[str] = None,
    agent: Optional[str] = None,
    log_path: Optional[Path] = None,
) -> dict:
    log_path = log_path or _default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    project = project or _git_root(Path.cwd()) or Path.cwd().name
    parent = _last_block(log_path, project)

    block = {
        "id": uuid.uuid4().hex[:12],
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": agent or _git_author(),
        "project": project,
        "parent": parent["id"] if parent else None,
        "intent": intent,
        "reasoning": reasoning,
        "actions": actions or [],
        "verification": verification,
        "touches": touches or [],
        "supersedes": supersedes,
    }

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(block, ensure_ascii=False) + "\n")

    return block


def query_blocks(
    log_path: Optional[Path] = None,
    project: Optional[str] = None,
    touches: Optional[str] = None,
    since: Optional[str] = None,
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
            results.append(block)

    return results[-limit:]


def format_block(block: dict) -> str:
    lines = [
        f"[{block['id']}] {block['ts']}  {block['agent']} @ {block['project']}",
        f"  intent:  {block['intent']}",
        f"  why:     {block['reasoning']}",
    ]
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
    block = add_block(
        intent=args.intent,
        reasoning=args.reasoning,
        touches=args.touches.split(",") if args.touches else [],
        verification=args.verification,
        supersedes=args.supersedes,
        project=args.project,
        agent=args.agent,
    )
    print(format_block(block))
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    blocks = query_blocks(
        project=args.project,
        touches=args.touches,
        since=args.since,
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
    p_add.set_defaults(func=_cmd_add)

    p_query = sub.add_parser("query", help="Search the decision ledger")
    p_query.add_argument("--project", default=None)
    p_query.add_argument("--touches", default=None, help="Substring match against touches globs")
    p_query.add_argument("--since", default=None, help="ISO timestamp lower bound")
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
