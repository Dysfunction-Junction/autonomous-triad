"""Review, consult, debug, and Phase 3.6 triage CLI commands."""

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from triad.procutil import is_trivial_diff, extract_diff_file_paths
    from triad.advisor_manager import query_configured_advisor, get_advisors, advisor_is_ready
    from triad.worktree import clean_git_env
    from triad.competition import query_competition_council
except ImportError:
    from procutil import is_trivial_diff, extract_diff_file_paths
    from advisor_manager import query_configured_advisor, get_advisors, advisor_is_ready
    from worktree import clean_git_env
    from competition import query_competition_council


def _eng(name: str, fallback: Any) -> Any:
    mod = sys.modules.get("triad.triad_engine") or sys.modules.get("triad_engine")
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    return fallback


def _handle_adversarial_session_result(session: Dict[str, Any]) -> None:
    """Enforces consistent adversarial arena exit behavior across review, consult, and debug."""
    quorum_met = bool(session.get("quorum_met", False))
    status = str(session.get("status", "error"))
    verdict = session.get("verdict")
    if not quorum_met:
        print("\n❌ [Adversarial Arena] Quorum failure: insufficient ready advisors for adversarial evaluation.", file=sys.stderr)
        sys.exit(1)
    if status != "ok":
        print(f"\n❌ [Adversarial Arena] Adversarial evaluation failed with status: {status}.", file=sys.stderr)
        sys.exit(1)
    if verdict != "RESILIENT":
        print(f"\n❌ [Adversarial Arena] Red team identified critical vulnerabilities or verdict inconclusive (VERDICT: {verdict or 'UNKNOWN'}).", file=sys.stderr)
        sys.exit(1)
    print("\n✅ [Adversarial Arena] Passed adversarial audit (VERDICT: RESILIENT).")


def _triage_enabled() -> bool:
    return os.environ.get("TRIAD_TRIAGE", "1").strip().lower() not in ("0", "false", "no", "off")


def _classify_diff_with_llama(diff_content: str) -> Optional[str]:
    """Ask local llama to classify diff risk (TRIVIAL|NORMAL|HIGH) when ready; return None if unavailable."""
    try:
        advisors = _eng("get_advisors", get_advisors)(enabled_only=True)
        llama_cfg = next((a for a in advisors if a.get("name") == "llama"), None)
        if not llama_cfg:
            return None
        ready, _ = _eng("advisor_is_ready", advisor_is_ready)(llama_cfg)
        if not ready:
            return None
        files = _eng("extract_diff_file_paths", extract_diff_file_paths)(diff_content)
        files_str = ", ".join(files[:30]) or "<unknown>"
        triage_prompt = (
            "Classify risk: TRIVIAL|NORMAL|HIGH. One word.\n"
            f"FILES: {files_str}\n"
            f"DIFF:\n````diff\n{diff_content[:3600]}\n````"
        )
        resp = _eng("query_configured_advisor", query_configured_advisor)(
            "llama", triage_prompt, mode="passthrough", timeout=15, track_circuit=False
        )
        text = (resp or "").strip()
        exact = re.match(r"^\s*(TRIVIAL|NORMAL|HIGH)\s*\.?\s*$", text, re.IGNORECASE)
        return exact.group(1).upper() if exact else None
    except Exception as e:
        if os.environ.get("TRIAD_DEBUG"):
            print(f"[Triage Debug] llama classification skipped: {e}", file=sys.stderr)
        return None


def _resolve_triage_route(
    diff_content: str,
    high_stakes: bool,
    engine: str,
    competition: bool,
    *,
    allow_downgrade: bool = True,
) -> Tuple[Optional[str], str, bool]:
    """Return (trivial_verdict, engine, competition) applying Phase 3.6 tiered escalation."""
    if high_stakes and engine == "auto":
        return None, engine, True
    if not _eng("_triage_enabled", _triage_enabled)() or engine != "auto" or competition:
        return None, engine, competition
    if _eng("is_trivial_diff", is_trivial_diff)(diff_content):
        return "VERDICT: APPROVED (trivial: docs/format)", engine, False
    risk = _eng("_classify_diff_with_llama", _classify_diff_with_llama)(diff_content)
    if risk == "HIGH":
        return None, engine, True
    if risk == "TRIVIAL" and allow_downgrade and len(diff_content) <= 3600:
        try:
            advisors = _eng("get_advisors", get_advisors)(enabled_only=True)
            nous_cfg = next((a for a in advisors if a.get("name") == "nous"), None)
            if nous_cfg and _eng("advisor_is_ready", advisor_is_ready)(nous_cfg)[0]:
                return None, "nous", False
        except Exception:
            pass
    return None, engine, False


def cmd_review(args, env: Optional[Dict[str, str]] = None):
    """Review git diff with the Advisory Council."""
    diff_file = getattr(args, "diff_file", "")
    diff_content = ""
    if diff_file:
        if diff_file == "-":
            diff_content = sys.stdin.read()
        elif os.path.exists(diff_file):
            with open(diff_file, "r", encoding="utf-8", errors="replace") as f:
                diff_content = f.read()
    elif getattr(args, "_in_worktree", False) and getattr(args, "_review_base", None):
        run_sub = _eng("run_subprocess_tree_safe", None)
        ret, out_diff, err_diff = run_sub(
            ["git", "diff", "--no-color", "--no-ext-diff", "--no-textconv", args._review_base, "--"],
            cwd=Path.cwd(),
            env=clean_git_env(base_env=env)
        )
        if ret != 0:
            print(f"❌ [Triad Error] Failed to extract diff against review base {args._review_base}: {err_diff.strip()}", file=sys.stderr)
            sys.exit(1)
        diff_content = out_diff.strip()
    else:
        try:
            diff_content = _eng("get_git_diff", None)(
                cached=getattr(args, "cached", False),
                head=getattr(args, "head", False),
                env=env
            )
        except Exception as e:
            print(f"[Triad Error] Failed to retrieve git diff: {e}", file=sys.stderr)
            sys.exit(1)

    if not diff_content:
        print("[Triad] No git diff found to review. Stage changes or specify --diff-file.")
        sys.exit(0)

    prompt = getattr(args, "prompt", "")
    if isinstance(prompt, list):
        prompt = " ".join(prompt).strip()
    prompt = prompt or "Review this git diff for edge cases, subtle bugs, type soundness, and architectural regressions."
    engine = getattr(args, "engine", "auto")
    task = getattr(args, "task", "auto")
    if task == "auto":
        task = "coding"
    try:
        from triad.intent_engine import is_high_stakes
    except ImportError:
        from intent_engine import is_high_stakes
    high_stakes = is_high_stakes(f"{prompt}\n{diff_content}")
    if high_stakes and task in ("micro", "scraping", "browsing"):
        task = "coding"
    competition = getattr(args, "competition", False) or getattr(args, "adversarial", False)
    trivial_verdict, engine, competition = _eng("_resolve_triage_route", _resolve_triage_route)(
        diff_content, high_stakes, engine, competition
    )
    if trivial_verdict is not None:
        print(trivial_verdict)
        return
    if competition:
        if engine == "mock":
            adv_pair: Optional[Tuple[str, str]] = ("mock", "mock")
        elif engine == "auto":
            adv_pair = None
        else:
            adv_pair = ("claude", "codex")
        is_adv = bool(getattr(args, "adversarial", False))
        mode_desc = "Adversarial Red/Blue Arena" if is_adv else "Concurrent Dual Advisors"
        pair_label = adv_pair if adv_pair is not None else f"by-lane:{task}"
        print(f"[Triad Competition Mode] Evaluating diff via {mode_desc} ({pair_label})...")
        session = _eng("query_competition_council", query_competition_council)(
            prompt, diff=diff_content, mode="review_diff", advisor_names=adv_pair,
            adversarial=is_adv, task=task,
        )
        synth = session.get("synthesis", "")
        print("\n" + synth)
        if is_adv:
            _handle_adversarial_session_result(session)
        elif session.get("status") == "error":
            print(f"\n❌ [Competition Mode] Review evaluation failed with status: {session.get('status')}", file=sys.stderr)
            sys.exit(1)
        elif session.get("status") == "degraded" or not session.get("quorum_met"):
            print("\n⚠️ [Competition Mode Warning] Review ran in degraded mode (quorum not met; single-advisor fallback)", file=sys.stderr)
        return
    print(f"[Triad] Reviewing {len(diff_content.splitlines())} diff lines via Advisory Council (task={task}, engine={engine})...\n")
    resp = _eng("query_advisory_council", None)(prompt, diff=diff_content, mode="review_diff", engine=engine, task=task)
    print(resp)


def cmd_consult(args):
    """Consult the Advisory Council for architectural / system design."""
    prompt = getattr(args, "prompt", "")
    if isinstance(prompt, list):
        prompt = " ".join(prompt).strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()

    if not prompt:
        print("Usage: triad consult '<prompt>' [--context '...']")
        sys.exit(1)

    context = getattr(args, "context", "") or ""
    context_file = getattr(args, "context_file", "")
    if context_file and os.path.exists(context_file):
        with open(context_file, "r", encoding="utf-8", errors="replace") as f:
            context = f.read()

    engine = getattr(args, "engine", "auto")
    task = getattr(args, "task", "auto")
    if task == "auto":
        task = "architecture"
    try:
        from triad.intent_engine import is_high_stakes
    except ImportError:
        from intent_engine import is_high_stakes
    high_stakes = is_high_stakes(f"{prompt}\n{context}")
    if high_stakes and task in ("micro", "scraping", "browsing"):
        task = "coding"
    competition = getattr(args, "competition", False) or getattr(args, "adversarial", False)
    if high_stakes and engine == "auto":
        competition = True
    if competition:
        if engine == "mock":
            adv_pair: Optional[Tuple[str, str]] = ("mock", "mock")
        elif engine == "auto":
            adv_pair = None
        else:
            adv_pair = ("claude", "codex")
        is_adv = bool(getattr(args, "adversarial", False))
        mode_desc = "Adversarial Red/Blue Arena" if is_adv else "Concurrent Dual Advisors"
        pair_label = adv_pair if adv_pair is not None else f"by-lane:{task}"
        print(f"[Triad Competition Mode] Consulting {mode_desc} ({pair_label})...")
        session = _eng("query_competition_council", query_competition_council)(
            prompt, context=context, mode="architect", advisor_names=adv_pair,
            adversarial=is_adv, task=task,
        )
        print("\n" + session["synthesis"])
        if is_adv:
            _handle_adversarial_session_result(session)
        return

    print(f"[Triad] Consulting Advisory Council (task={task}, engine={engine})...\n")
    resp = _eng("query_advisory_council", None)(prompt, context=context, mode="architect", engine=engine, task=task)
    print(resp)


def cmd_debug(args):
    """Debug an error or stack trace with the Advisory Council."""
    raw_error = getattr(args, "error", "")
    if isinstance(raw_error, list):
        raw_error = " ".join(raw_error).strip()
    error = str(raw_error or "").strip()

    if not error:
        raw_prompt = getattr(args, "prompt", "")
        if isinstance(raw_prompt, list):
            raw_prompt = " ".join(raw_prompt).strip()
        error = str(raw_prompt or "").strip()

    if not error and not sys.stdin.isatty():
        error = sys.stdin.read().strip()

    if not error:
        print("Usage: triad debug '<error description or stacktrace>' [--context '...']")
        sys.exit(1)

    context = getattr(args, "context", "") or ""
    context_file = getattr(args, "context_file", "")
    if context_file and os.path.exists(context_file):
        with open(context_file, "r", encoding="utf-8", errors="replace") as f:
            context = f.read()

    engine = getattr(args, "engine", "auto")
    task = getattr(args, "task", "auto")
    if task == "auto":
        task = "coding"
    try:
        from triad.intent_engine import is_high_stakes
    except ImportError:
        from intent_engine import is_high_stakes
    high_stakes = is_high_stakes(f"{error}\n{context}")
    if high_stakes and task in ("micro", "scraping", "browsing"):
        task = "coding"
    competition = getattr(args, "competition", False) or getattr(args, "adversarial", False)
    if high_stakes and engine == "auto":
        competition = True
    if competition:
        if engine == "mock":
            adv_pair: Optional[Tuple[str, str]] = ("mock", "mock")
        elif engine == "auto":
            adv_pair = None
        else:
            adv_pair = ("claude", "codex")
        is_adv = bool(getattr(args, "adversarial", False))
        mode_desc = "Adversarial Red/Blue Arena" if is_adv else "Concurrent Dual Advisors"
        pair_label = adv_pair if adv_pair is not None else f"by-lane:{task}"
        print(f"[Triad Competition Mode] Diagnosing error via {mode_desc} ({pair_label})...")
        session = _eng("query_competition_council", query_competition_council)(
            error, context=context, mode="debug", advisor_names=adv_pair,
            adversarial=is_adv, task=task,
        )
        print("\n" + session["synthesis"])
        if is_adv:
            _handle_adversarial_session_result(session)
        return

    print(f"[Triad] Diagnosing with Advisory Council (task={task}, engine={engine})...\n")
    resp = _eng("query_advisory_council", None)(error, context=context, mode="debug", engine=engine, task=task)
    print(resp)
