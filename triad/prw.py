#!/usr/bin/env python
"""prw - expand a rough prompt into a detailed agent brief (local/zero-cost).

Usage:
  prw fix the login bug in src/auth.ts
  prw -c add caching to server.py
  prw -j debug TypeError in foo.py
  echo prompt | prw
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

AGENTS = Path.home() / ".agents"
if str(AGENTS) not in sys.path:
    sys.path.insert(0, str(AGENTS))
os.environ.setdefault("PYTHONPATH", str(AGENTS))

from triad.prompt_rewriter import format_output, polish_with_llm, rewrite_prompt  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prw",
        description="Expand a sparse prompt into a detailed agent brief (local/zero-cost).",
    )
    parser.add_argument("prompt", nargs="*", help="Rough prompt words")
    parser.add_argument("-c", "--compact", action="store_true", help="Compact one-block style")
    parser.add_argument("-j", "--json", action="store_true", help="JSON output")
    parser.add_argument("--llm", action="store_true", help="Optional paid advisor polish")
    parser.add_argument("--engine", default="auto", help="Advisor engine for --llm")
    parser.add_argument("-o", "--output", default="", help="Write to file instead of stdout")
    parser.add_argument("--context", default="", help="Extra inline context")
    parser.add_argument("--constraint", action="append", default=[], help="Extra hard constraint")
    args = parser.parse_args(argv)

    prompt = " ".join(args.prompt).strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        parser.print_help()
        return 2

    style = "compact" if args.compact else "brief"
    brief = rewrite_prompt(
        prompt,
        context=args.context or None,
        extra_constraints=args.constraint or None,
        style=style,
        cwd=os.getcwd(),
    )

    if args.llm:
        try:
            brief.rewritten = polish_with_llm(brief, engine=args.engine)
            brief.metadata["llm_polished"] = True
        except Exception as exc:
            print(f"[prw] LLM polish failed ({exc}); emitting local brief.", file=sys.stderr)

    text = format_output(brief, as_json=args.json, include_meta=False)
    if not text.endswith("\n"):
        text += "\n"

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[prw] wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
