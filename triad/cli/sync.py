"""Ecosystem synchronization CLI command (`triad sync`)."""

import json
import sys


def cmd_sync(args):
    """
    Synchronize Triad runtime engine, CLI launchers, skills, and multi-repo pre-commit hooks.
    Ensures zero drift between repository development and the live user execution environment.
    """
    try:
        from triad.sync_manager import run_full_sync
    except ImportError:
        from sync_manager import run_full_sync

    apply_flag = getattr(args, "apply", False)
    dry_run = getattr(args, "dry_run", False) or not apply_flag
    sync_all = getattr(args, "all", False)
    is_json = getattr(args, "json", False)

    include_engine = getattr(args, "engine", False)
    include_launchers = getattr(args, "launchers", False)
    include_skills = getattr(args, "skills", False)
    include_hooks = getattr(args, "hooks", False)

    comp = getattr(args, "component", None)
    if comp == "all":
        sync_all = True
    elif comp == "engine":
        include_engine = True
    elif comp == "launchers":
        include_launchers = True
    elif comp == "skills":
        include_skills = True
    elif comp == "hooks":
        include_hooks = True

    if not (sync_all or include_engine or include_launchers or include_skills or include_hooks):
        include_engine = True
        include_launchers = True
        include_skills = True

    report = run_full_sync(
        dry_run=dry_run,
        sync_all=sync_all,
        include_engine=include_engine,
        include_launchers=include_launchers,
        include_skills=include_skills,
        include_hooks=include_hooks,
    )

    if is_json:
        print(json.dumps(report, indent=2))
        if report.get("has_error"):
            sys.exit(1)
        return

    print("================================================================================")
    print("               AUTONOMOUS MULTI-AGENT TRIAD: ECOSYSTEM SYNCHRONIZATION           ")
    print("================================================================================")
    mode_str = "[DRY-RUN PREVIEW]" if dry_run else "[ACTIVE SYNCHRONIZATION]"
    print(f"Status: {mode_str}\n")

    e = report["engine"]
    if e.get("status") != "skipped":
        print(f"[1] Runtime Engine: {e['status'].upper()}")
        print(f"    - Target:  {e.get('target', '')}")
        print(f"    - Source:  {e.get('source', '')}")
        print(f"    - Details: {e.get('detail', '')}\n")

    l = report["launchers"]
    if l.get("status") != "skipped":
        path_badge = "OK (on PATH)" if l.get("path_ok") else "WARNING: not on PATH"
        print(f"[2] CLI Launchers: {l['status'].upper()} | {path_badge}")
        print(f"    - Target:  {l.get('target', '')}")
        print(f"    - Details: {l.get('detail', '')}\n")

    s = report["skills"]
    if s.get("status") != "skipped":
        print(f"[3] Claude Advisor Skill Bridge: {s['status'].upper()}")
        print(f"    - Target:  {s.get('target', '')}")
        print(f"    - Details: {s.get('detail', '')}\n")

    if report.get("hooks"):
        print("[4] Active Repository Pre-Commit Hooks:")
        for h in report["hooks"]:
            status_tag = f"[{h['hook_status'].upper()}]"
            action_note = f" -> {h['action_taken']}" if h.get("action_taken") != "none" else ""
            print(f"    - {h['repo']:<22} {status_tag:<16} {h['detail']}{action_note}")
        print()

    print("================================================================================")
    statuses = [report[k]["status"] for k in ("engine", "launchers", "skills") if report.get(k)]
    hook_actions = [h.get("action_taken") for h in report.get("hooks", [])]
    has_drift = (
        any(st in ("drift_detected", "warning", "degraded") for st in statuses)
        or any(a in ("would_install", "installed") for a in hook_actions)
        or any(h.get("hook_status") != "installed" for h in report.get("hooks", []))
    )

    has_warning = any(st in ("warning", "degraded") for st in statuses)
    check_mode = getattr(args, "check", False)

    if report.get("has_error"):
        print("[ERROR] TRIAD SYNC FAILED: Errors encountered during synchronization.")
        print("================================================================================\n")
        sys.exit(1)
    elif has_drift and dry_run:
        print("TRIAD SYNC: DRIFT DETECTED (Run with --apply to synchronize ecosystem)")
        print("================================================================================\n")
        if check_mode:
            sys.exit(2)
    elif has_warning:
        print("TRIAD SYNC WARNING: Synchronization completed with warnings (e.g. junction failed, copied fallback).")
        print("================================================================================\n")
    else:
        print("TRIAD SYNC COMPLETE: Zero drift maintained across development and runtime.")
        print("================================================================================\n")
