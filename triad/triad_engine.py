#!/usr/bin/env python3
"""
Autonomous Multi-Agent Triad Engine (triad_engine.py).
Unified Executive Orchestrator & Advisory Bridge:
- Antigravity: Executive Engine, Massive 2M Context, Code Writer & Test Runner
- Advisory Council: Claude 3.7 Sonnet (Claude Pro) with zero-downtime failover to OpenAI Codex (gpt-6-astra via ChatGPT Plus)
- Hermes Agent: Android Phone Automation & Skill Specialist
- Ground Truth Gates: Local TypeScript (tsc) and Vitest/Jest test suites
- 100% Zero-Incremental-Cost Policy: Flat-rate subscriptions only ($0 extra per-token billing)
"""

# Tags: engine, cli, review, verification
# Links: triad/advisor_manager.py, triad/intent_engine.py, bin/triad
# Queries: "where is the command surface defined", "how does review dispatch to advisors", "what does the engine do with a gate result"

import sys
import os
import stat
import re
import subprocess
import argparse
import json
import tempfile
import shutil
import uuid
import time
import hashlib
import ast
import contextlib
from functools import lru_cache
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Union, Set

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TRIAD_DIR = Path(__file__).resolve().parent
EMPTY_MCP = TRIAD_DIR / "empty-mcp.json"

try:
    from triad.paths import (
        CLAUDE_PATH, CODEX_PATH, AGY_PATH, HERMES_PATH, CODEX_AUTH,
        PORT_HERMES_RELAY, PORT_PIECES_OS, PORT_TRIAD_SERVER, local_llm_port,
        PORT_EXOCORTEX_DAEMON, PORT_PIECES_PROXY, PORT_PIECES_FOR_ALL,
        PORT_AGENT_MESH_MCP, PORT_NEO4J_BOLT,
        AGENT_MESH_DIR, AGENT_MESH_SERVER,
    )
    from triad.procutil import (
        kill_process_tree, is_port_open, classify_advisor_response,
        strip_diff_bloat, is_doc_or_asset_file,
        is_trivial_diff, extract_diff_file_paths,
    )
    from triad.circuit import snapshot_circuits, is_circuit_open, reset_circuit
    from triad.advisor_manager import query_configured_advisor, get_advisors, advisor_is_ready
    from triad.worktree import create_worktree, remove_worktree, isolated_worktree, list_worktrees, prune_worktrees, get_repo_root, clean_git_env, provision_worktree_dependencies, capture_directory_snapshot, get_provisioned_manifest_entries, is_reparse_or_link
    from triad.competition import query_competition_council
    from triad.intent_engine import classify_intent, execute_intent
except ImportError:
    from paths import (
        CLAUDE_PATH, CODEX_PATH, AGY_PATH, HERMES_PATH, CODEX_AUTH,
        PORT_HERMES_RELAY, PORT_PIECES_OS, PORT_TRIAD_SERVER, local_llm_port,
        PORT_EXOCORTEX_DAEMON, PORT_PIECES_PROXY, PORT_PIECES_FOR_ALL,
        PORT_AGENT_MESH_MCP, PORT_NEO4J_BOLT,
        AGENT_MESH_DIR, AGENT_MESH_SERVER,
    )
    from procutil import (
        kill_process_tree, is_port_open, classify_advisor_response,
        strip_diff_bloat, is_doc_or_asset_file,
        is_trivial_diff, extract_diff_file_paths,
    )
    from circuit import snapshot_circuits, is_circuit_open, reset_circuit
    from advisor_manager import query_configured_advisor, get_advisors, advisor_is_ready
    from worktree import create_worktree, remove_worktree, isolated_worktree, list_worktrees, prune_worktrees, get_repo_root, clean_git_env, provision_worktree_dependencies, capture_directory_snapshot, get_provisioned_manifest_entries, is_reparse_or_link
    from competition import query_competition_council
    from intent_engine import classify_intent, execute_intent

try:
    from triad.notifier import notify_event
except Exception:
    try:
        from notifier import notify_event
    except Exception:
        def notify_event(*args, **kwargs):
            return False

# Node toolchain launchers: on Windows the npm-provided shims are .cmd files which
# CreateProcess will not execute without the extension.
NPX_CMD = "npx.cmd" if os.name == "nt" else "npx"
NPM_CMD = "npm.cmd" if os.name == "nt" else "npm"

def query_claude(prompt: str, context: str = None, diff: str = None, mode: str = "general", timeout: int = 120, track_circuit: bool = True) -> str:
    """Query Claude advisor via configured advisor manager."""
    return query_configured_advisor("claude", prompt, context=context, diff=diff, mode=mode, timeout=timeout, track_circuit=track_circuit)

def query_codex(prompt: str, context: str = None, diff: str = None, mode: str = "general", timeout: int = 120, track_circuit: bool = True) -> str:
    """Query OpenAI Codex advisor via configured advisor manager."""
    return query_configured_advisor("codex", prompt, context=context, diff=diff, mode=mode, timeout=timeout, track_circuit=track_circuit)

def query_advisory_council(prompt: str, context: str = None, diff: str = None, mode: str = "general", engine: str = "auto", timeout: int = 180, track_circuit: bool = True, *, task: Optional[str] = None) -> str:
    """
    Autonomous Advisory Council with zero-downtime failover and dynamic advisor routing:
    Delegates to configured advisors via advisor_manager.
    """
    target = "claude" if engine == "bare_single" else engine
    return query_configured_advisor(target, prompt, context=context, diff=diff, mode=mode, task=task, timeout=timeout, track_circuit=track_circuit)

def get_git_diff(cached: bool = False, head: bool = False, env: Optional[Dict[str, str]] = None, cwd: Optional[Path] = None, binary: bool = False) -> str:
    """
    Retrieve git diff from current repository, bypassing external diff drivers and textconv filters.

    ``cached`` -> staged changes vs HEAD; ``head`` -> the most recent commit (HEAD~1..HEAD),
    *not* the working tree against HEAD~1 - that would silently fold uncommitted edits into a
    "review the last commit" request.
    """
    # Only sanitize Git env when crossing into ephemeral worktrees or explicitly requested.
    # Preserve caller env (including alternate GIT_INDEX_FILE) for direct workspace operations.
    exec_env = dict(os.environ if env is None else env)
    target_cwd = cwd or Path.cwd()

    if binary:
        cmd = ["git", "diff", "--no-color", "--no-ext-diff", "--no-textconv", "--binary"]
    else:
        try:
            diff_ctx = max(0, int(exec_env.get("TRIAD_DIFF_CONTEXT", "1").strip() or "1"))
        except ValueError:
            diff_ctx = 1
        cmd = [
            "git",
            "diff",
            f"-U{diff_ctx}",
            "--ignore-cr-at-eol",
            "--no-color",
            "--find-renames",
            "--no-ext-diff",
            "--no-textconv",
        ]
    if cached:
        cmd.append("--cached")
    elif head:
        cmd.extend(["HEAD~1", "HEAD"])

    res = subprocess.run(
        cmd,
        cwd=str(target_cwd),
        env=exec_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    if res.returncode != 0:
        raise RuntimeError(f"git diff failed (exit code {res.returncode}): {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout.strip()

try:
    from triad.cli.doctor import (
        CODEX_MAX_REFRESH_AGE,
        _decode_codex_auth,
        collect_doctor_report,
        _render_doctor_report,
        cmd_doctor,
    )
except ImportError:
    from cli.doctor import (
        CODEX_MAX_REFRESH_AGE,
        _decode_codex_auth,
        collect_doctor_report,
        _render_doctor_report,
        cmd_doctor,
    )


try:
    from triad.cli.review import (
        _handle_adversarial_session_result,
        _triage_enabled,
        _classify_diff_with_llama,
        _resolve_triage_route,
        cmd_review,
        cmd_consult,
        cmd_debug,
    )
except ImportError:
    from cli.review import (
        _handle_adversarial_session_result,
        _triage_enabled,
        _classify_diff_with_llama,
        _resolve_triage_route,
        cmd_review,
        cmd_consult,
        cmd_debug,
    )


try:
    from triad.patching import (
        apply_patch_text,
        _modes_match,
        acquire_repo_mutation_lock,
        _is_symlink_or_reparse,
        _validate_and_resolve_contained_path,
        parse_diff_tree_records,
        get_tree_entries,
        _content_matches,
        _restore_entry,
        _rollback,
        apply_verified_patch_to_workspace,
        _exec_subprocess_tree_safe,
        run_subprocess_tree_safe_bytes,
        run_subprocess_tree_safe,
        get_empty_tree_oid,
        query_gate_fix,
        snapshot_worktree_tree,
        _stage_candidate_worktree_changes,
        compute_working_tree_fingerprint,
        fingerprints_match,
        capture_parent_state,
        capture_candidate_tree,
        get_recovery_patch_path,
        write_atomic_patch,
        sanitize_worktree_env,
        _notice_recovery_patch,
    )
except ImportError:
    from patching import (
        apply_patch_text,
        _modes_match,
        acquire_repo_mutation_lock,
        _is_symlink_or_reparse,
        _validate_and_resolve_contained_path,
        parse_diff_tree_records,
        get_tree_entries,
        _content_matches,
        _restore_entry,
        _rollback,
        apply_verified_patch_to_workspace,
        _exec_subprocess_tree_safe,
        run_subprocess_tree_safe_bytes,
        run_subprocess_tree_safe,
        get_empty_tree_oid,
        query_gate_fix,
        snapshot_worktree_tree,
        _stage_candidate_worktree_changes,
        compute_working_tree_fingerprint,
        fingerprints_match,
        capture_parent_state,
        capture_candidate_tree,
        get_recovery_patch_path,
        write_atomic_patch,
        sanitize_worktree_env,
        _notice_recovery_patch,
    )


def _is_ci(env: Optional[Dict[str, str]] = None) -> bool:
    """Return True if running in a Continuous Integration environment (GitHub Actions, GitLab, etc.)."""
    exec_env = os.environ if env is None else env
    return str(exec_env.get("CI", "")).strip().lower() in ("1", "true", "yes")


def _normalize_single_target(raw: str) -> str:
    """Normalize a single target test pattern or file path into a test pattern (e.g. 'test_*.py')."""
    s = (raw or "").strip().replace("\\", "/")
    base = os.path.basename(s)
    if not base or base == "test_*.py":
        return "test_*.py"
    if s.endswith("/") or base in ("tests", "test"):
        return "test_*.py"
    if "*" in base:
        if not base.startswith("test_"):
            return f"test_{base}" if base.endswith(".py") else f"test_{base}.py"
        return base if base.endswith(".py") else f"{base}.py"
    if not base.startswith("test_"):
        stem = base[:-3] if base.endswith(".py") else base
        base = f"test_{stem}.py"
    elif not base.endswith(".py"):
        base = f"{base}.py"
    return base


def _normalize_target(raw: str) -> str:
    """Normalize target test pattern(s) or file paths into test pattern(s) (e.g. 'test_*.py' or 'test_a.py,test_b.py')."""
    if not raw or not raw.strip():
        return "test_*.py"
    raw_str = raw.strip()
    if "," in raw_str:
        parts = [_normalize_single_target(p) for p in raw_str.split(",") if p.strip()]
        if any(p == "test_*.py" for p in parts) or not parts:
            return "test_*.py"
        return ",".join(sorted(set(parts)))
    return _normalize_single_target(raw_str)


def _check_apply_verified_safety(args, env: Optional[Dict[str, str]] = None) -> None:
    exec_env = os.environ if env is None else env
    if _is_ci(exec_env):
        return
    raw_target = getattr(args, "target", "") or exec_env.get("TRIAD_TEST_TARGET", "")
    norm_target = _normalize_target(raw_target)
    is_targeted_req = bool(
        (norm_target != "test_*.py")
        or getattr(args, "targeted", False)
        or exec_env.get("TRIAD_TARGETED_TESTS") == "1"
    )
    if getattr(args, "apply_verified", False) and is_targeted_req:
        env_hint = " (via TRIAD_TARGETED_TESTS environment variable)" if exec_env.get("TRIAD_TARGETED_TESTS") == "1" else ""
        print(
            f"\n[Triad Gate Error] Cannot use --apply-verified with targeted test execution (--target / --targeted){env_hint}.\n"
            "A full test suite run is required before applying verified changes back to parent repository.",
            file=sys.stderr,
        )
        sys.exit(1)


def _run_in_isolated_worktree(
    args,
    env: Optional[Dict[str, str]],
    *,
    repo_root: Union[str, Path],
    prefix: str,
    require_index: bool,
    runner,
    error_label: str,
    phase_label: str,
    nm_phase_label: str,
    enforce_clean_explicit_ref: bool,
    pause_commit_after_apply: bool,
    notify_async: bool,
) -> None:
    """
    Shared orchestration for ``--worktree`` execution used by both ``triad gate`` and
    ``triad auto``. The lifecycle is:

      1. Snapshot the parent repository (HEAD, index tree, working-tree tree).
      2. Spawn an ephemeral worktree, materialize the candidate tree, provision deps.
      3. Run ``runner(isolated_args, isolated_env)`` inside it.
      4. If the run self-healed, extract a binary tree-to-tree patch and persist it to
         a recovery file under ``.git`` *before* the worktree is torn down.
      5. Re-verify the parent did not mutate concurrently (HEAD / index / working tree).
      6. Optionally (``--apply-verified``) apply the patch to the parent working tree.

    Every failure path exits non-zero (fail-closed). Parameters that differ between
    callers are the worktree ``prefix``, whether the candidate is the index
    (``require_index``, commit gating) or the working tree, the user-facing labels,
    whether an explicit ``--ref`` is rejected on a dirty parent, and whether a
    successfully applied patch pauses the commit (gate) or simply continues (auto).
    """
    base_env = env if env is not None else os.environ
    _check_apply_verified_safety(args, base_env)
    ref = getattr(args, "ref", "HEAD") or "HEAD"
    if str(ref).startswith("-"):
        print(f"\n❌ [Triad Worktree Error] Invalid --ref {ref!r}: a ref must not start with '-'.", file=sys.stderr)
        sys.exit(1)
    apply_verified = getattr(args, "apply_verified", False)

    try:
        parent_state = capture_parent_state(repo_root, env=base_env, require_index=require_index)
        candidate_tree = parent_state["candidate_tree"]
        initial_index_tree = parent_state["index_tree"]
        initial_wt_tree = parent_state["wt_tree"]
        initial_head_commit = parent_state.get("head_commit", "UNBORN")
        has_changes = parent_state["has_changes"]
        is_unborn = parent_state["is_unborn"]
    except Exception as e:
        print(f"\n❌ [Triad Worktree Error] Failed to capture candidate parent state: {e}", file=sys.stderr)
        sys.exit(1)

    is_explicit_ref = False
    transfer_local_changes = True
    if enforce_clean_explicit_ref:
        is_explicit_ref = bool(getattr(args, "ref", None) and getattr(args, "ref") != "HEAD")
        if is_explicit_ref and has_changes:
            print(f"\n❌ [Triad Auto Error] Cannot run 'triad auto --ref {ref}' with uncommitted local changes in working directory or staged index.", file=sys.stderr)
            print("To fix: Commit or stash local changes, or omit '--ref' to operate on current working tree state.", file=sys.stderr)
            sys.exit(1)
        transfer_local_changes = has_changes or (not is_explicit_ref and not is_unborn)

    empty_tree_oid = get_empty_tree_oid(Path(repo_root))
    isolated_env = clean_git_env(base_env=env)
    isolated_env = sanitize_worktree_env(isolated_env, repo_root)

    if is_unborn:
        review_base = empty_tree_oid
    elif is_explicit_ref and not has_changes:
        ret_base, base_rev_tree, _ = run_subprocess_tree_safe(["git", "rev-parse", f"{ref}~1^{{tree}}"], cwd=repo_root, env=isolated_env)
        review_base = base_rev_tree.strip() if ret_base == 0 and base_rev_tree.strip() else empty_tree_oid
    else:
        review_base = parent_state.get("head_tree") or ref

    # In an unborn repository, HEAD does not exist, so git worktree add HEAD will fail.
    # We materialize a temporary commit object from candidate_tree to anchor the worktree.
    if is_unborn:
        ret, temp_commit, err = run_subprocess_tree_safe(["git", "commit-tree", candidate_tree, "-m", "triad-temp-unborn-init"], cwd=repo_root, env=isolated_env)
        if ret != 0 or not temp_commit.strip():
            print(f"\n❌ [Triad Worktree Error] Failed to create temporary root commit for unborn repo: {err}", file=sys.stderr)
            sys.exit(1)
        ref_to_use = temp_commit.strip()
    else:
        ref_to_use = ref

    print(f"[Triad Worktree] Spawning isolated ephemeral git worktree from {repo_root} (ref: {ref_to_use[:10]})...")

    verified_patch_to_apply: Optional[bytes] = None
    recovery_path: Optional[Path] = None
    validated_tree: Optional[str] = None

    with isolated_worktree(repo_root, branch_or_commit=ref_to_use, prefix=prefix, cd=True, env=isolated_env) as wt:
        print(f"[Triad Worktree] Active in: {wt}")
        isolated_env = sanitize_worktree_env(isolated_env, repo_root, wt)
        if transfer_local_changes and not is_unborn:
            print(f"[Triad Worktree] Materializing candidate tree snapshot ({candidate_tree[:10]}) into isolated worktree...")
            ret, _, err = run_subprocess_tree_safe(["git", "read-tree", "-u", "--reset", candidate_tree], cwd=wt, env=isolated_env)
            if ret != 0:
                print(f"\n❌ [Triad Worktree Error] Failed to materialize candidate tree in isolated worktree: {err}", file=sys.stderr)
                sys.exit(1)

            # Verify exact tree parity in isolated worktree (fail-closed)
            ret, wt_tree, err = run_subprocess_tree_safe(["git", "write-tree"], cwd=wt, env=isolated_env)
            if ret != 0 or wt_tree.strip() != candidate_tree:
                print(f"\n❌ [Triad Worktree Error] Worktree tree mismatch (expected {candidate_tree}, got {wt_tree.strip()}): {err}", file=sys.stderr)
                sys.exit(1)

        # Set base_tree directly from worktree index write-tree
        ret, base_tree, err = run_subprocess_tree_safe(["git", "write-tree"], cwd=wt, env=isolated_env)
        if ret != 0 or not base_tree.strip():
            print(f"\n❌ [Triad Worktree Error] Failed to capture worktree base tree: {err}", file=sys.stderr)
            sys.exit(1)
        base_tree = base_tree.strip()

        # Preserve symlinks during Node.js resolution to prevent escaping to parent workspace
        isolated_env["NODE_PRESERVE_SYMLINKS"] = "1"

        # Capture parent node_modules baseline to detect unauthorized validator mutations
        parent_nm = Path(repo_root) / "node_modules"
        parent_nm_snapshot = capture_directory_snapshot(parent_nm)

        # Provision non-tracked external dependencies (e.g. node_modules) from parent repository
        prov = provision_worktree_dependencies(repo_root, wt)
        if prov:
            print(f"[Triad Worktree] Provisioned dependencies: {', '.join(prov)}")

        isolated_args = argparse.Namespace(**vars(args))
        setattr(isolated_args, "worktree", False)
        setattr(isolated_args, "_in_worktree", True)
        setattr(isolated_args, "_originating_root", str(Path(repo_root).resolve()))
        setattr(isolated_args, "_review_base", review_base)
        setattr(isolated_args, "_self_healed_patches", [])
        setattr(isolated_args, "_validated_tree", None)

        try:
            runner(isolated_args, isolated_env)
        finally:
            if hasattr(isolated_args, "_active_test_pattern"):
                setattr(args, "_active_test_pattern", getattr(isolated_args, "_active_test_pattern"))
            # Fail closed if parent node_modules was mutated or deleted by validators
            if parent_nm_snapshot is not None:
                post_nm_snapshot = capture_directory_snapshot(parent_nm)
                if post_nm_snapshot != parent_nm_snapshot:
                    print(f"\n❌ [Triad Worktree Error] Parent node_modules was mutated or deleted during {nm_phase_label} in isolated worktree.", file=sys.stderr)
                    sys.exit(1)

        # Generate single cohesive binary tree-to-tree diff from candidate tree to validated final state
        healed = getattr(isolated_args, "_self_healed_patches", [])
        if healed:
            validated_tree = getattr(isolated_args, "_validated_tree", None)
            if not validated_tree:
                print("\n❌ [Triad Worktree Error] Self-healing succeeded but validated tree was not captured.", file=sys.stderr)
                sys.exit(1)

            diff_cmd = [
                "git", "diff",
                "--binary", "--full-index",
                "--no-color",
                "--no-ext-diff", "--no-textconv",
                "--src-prefix=a/", "--dst-prefix=b/",
                base_tree, validated_tree, "--"
            ]
            ret, final_diff, err = run_subprocess_tree_safe_bytes(diff_cmd, cwd=wt, env=isolated_env)
            if ret != 0 or not final_diff.strip():
                err_msg = err.decode("utf-8", errors="replace") if isinstance(err, bytes) else str(err)
                print(f"\n❌ [Triad Worktree Error] Failed to extract verified patch delta from baseline: {err_msg}", file=sys.stderr)
                sys.exit(1)
            verified_patch_to_apply = final_diff if final_diff.endswith(b"\n") else final_diff + b"\n"
            recovery_path = get_recovery_patch_path(Path(repo_root), unique=True)
            try:
                write_atomic_patch(recovery_path, verified_patch_to_apply)
            except Exception as e:
                print(f"\n❌ [Triad Worktree Error] Failed to persist verified recovery patch before teardown: {e}", file=sys.stderr)
                sys.exit(1)

    print("[Triad Worktree] Ephemeral worktree cleanly removed and unlinked.")

    # Concurrency check on parent repository: verify HEAD, index, AND working tree did not mutate
    try:
        current_state = capture_parent_state(repo_root, env=base_env, require_index=require_index)
        if current_state.get("head_commit") != initial_head_commit:
            _notice_recovery_patch(recovery_path)
            print(f"\n❌ [{error_label}] Concurrent modification detected: parent git HEAD changed during {phase_label} (expected {initial_head_commit[:10]}, current {current_state.get('head_commit', '')[:10]}).", file=sys.stderr)
            sys.exit(1)
        if current_state["index_tree"] != initial_index_tree:
            _notice_recovery_patch(recovery_path)
            print(f"\n❌ [{error_label}] Concurrent modification detected: parent git index changed during {phase_label} (expected {initial_index_tree[:10]}, current {current_state['index_tree'][:10]}).", file=sys.stderr)
            sys.exit(1)
        if current_state["wt_tree"] != initial_wt_tree:
            _notice_recovery_patch(recovery_path)
            print(f"\n❌ [{error_label}] Concurrent modification detected: parent working tree modified during {phase_label}.", file=sys.stderr)
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        _notice_recovery_patch(recovery_path)
        print(f"\n❌ [{error_label}] Failed concurrency re-verification of parent state: {e}", file=sys.stderr)
        sys.exit(1)

    if not verified_patch_to_apply:
        return

    if current_state["wt_tree"] != base_tree:
        _notice_recovery_patch(recovery_path)
        print(f"\n❌ [{error_label}] Workspace working tree baseline differs from verified worktree baseline (expected {base_tree[:10]}, current {current_state['wt_tree'][:10]}).", file=sys.stderr)
        sys.exit(1)

    patch_bytes = verified_patch_to_apply if isinstance(verified_patch_to_apply, bytes) else verified_patch_to_apply.encode("utf-8")
    line_count = len(patch_bytes.splitlines())

    if not apply_verified:
        print("\n[Triad Closed Loop Note] A verified self-healing patch was produced in the worktree.")
        if recovery_path and recovery_path.exists():
            print(f"[Triad Notice] Preserved verified recovery patch at {recovery_path}")
        print("Run with '--apply-verified' to automatically merge passing self-healing fixes into your main workspace.")
        sys.exit(1)

    print(f"\n[Triad Closed Loop] Applying verified self-healing patch to main working tree ({line_count} lines)...")
    applied = apply_verified_patch_to_workspace(
        patch_bytes,
        cwd=Path(repo_root),
        expected_baseline_tree=base_tree,
        expected_target_tree=validated_tree
    )
    if not applied:
        print("! Error: Could not cleanly merge verified patch back to main working tree.")
        if recovery_path and recovery_path.exists():
            print(f"[Triad Notice] Preserved verified recovery patch at {recovery_path}")
        notify_event("Patch Merge Conflict", "Could not cleanly merge verified patch back to main working tree.", status="failed", timeout=1.5, async_dispatch=notify_async)
        sys.exit(1)

    try:
        post_apply_state = capture_parent_state(repo_root, env=base_env, require_index=False)
        if post_apply_state["index_tree"] != initial_index_tree:
            print("\n❌ [Triad Closed Loop Error] Git index unexpectedly modified during patch application.", file=sys.stderr)
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n❌ [Triad Closed Loop Error] Failed to verify post-apply repository state: {e}", file=sys.stderr)
        sys.exit(1)

    print("✓ Successfully applied verified patch to working tree!")
    notify_event("Self-Healing Patch Applied", f"Merged {line_count} lines of verified fixes to main workspace.", status="success", timeout=1.5, async_dispatch=notify_async)
    print("\n[Triad Closed Loop Notice] A self-healing patch was applied to your working tree.")
    if pause_commit_after_apply:
        print("To ensure verified code is committed, the commit is paused. Please stage the changes (e.g. 'git add .') and commit again.")
        sys.exit(1)


try:
    from triad.cli.gate import (
        cmd_gate,
        _render_unittest_suite_runner,
        _build_python_isolation_script,
        _build_python_multi_pattern_script,
        IGNORED_SOURCE_DEPENDENCY_DIR_NAMES,
        SOURCE_DEPENDENCY_EXTENSIONS,
        _check_no_uncommitted_source_dependencies,
        _clean_worktree_retry_artifacts,
        _verify_checkout_representation,
        PROPOSED_FIX_PATCH_NAME,
        write_proposed_fix_patch,
        _handle_validation_failure,
        _affects_typescript,
        _affects_code,
        CORE_MODULE_NAMES,
        BUILD_MANIFEST_NAMES,
        SKIP_IMPORT_INDEX_DIRS,
        _FILE_IMPORT_CACHE,
        _MAX_FILE_IMPORT_CACHE_ENTRIES,
        _clear_import_index_caches,
        _import_index,
        _has_importers,
        _resolve_targeted_test_pattern,
        _resolve_gate_python,
        _resolve_pytest_xdist_cmd,
        _run_gate,
        _run_gate_impl,
        _gate_signoff_prompt,
    )
except ImportError:
    from cli.gate import (
        cmd_gate,
        _render_unittest_suite_runner,
        _build_python_isolation_script,
        _build_python_multi_pattern_script,
        IGNORED_SOURCE_DEPENDENCY_DIR_NAMES,
        SOURCE_DEPENDENCY_EXTENSIONS,
        _check_no_uncommitted_source_dependencies,
        _clean_worktree_retry_artifacts,
        _verify_checkout_representation,
        PROPOSED_FIX_PATCH_NAME,
        write_proposed_fix_patch,
        _handle_validation_failure,
        _affects_typescript,
        _affects_code,
        CORE_MODULE_NAMES,
        BUILD_MANIFEST_NAMES,
        SKIP_IMPORT_INDEX_DIRS,
        _FILE_IMPORT_CACHE,
        _MAX_FILE_IMPORT_CACHE_ENTRIES,
        _clear_import_index_caches,
        _import_index,
        _has_importers,
        _resolve_targeted_test_pattern,
        _resolve_gate_python,
        _resolve_pytest_xdist_cmd,
        _run_gate,
        _run_gate_impl,
        _gate_signoff_prompt,
    )


def cmd_bench(args):
    """Run the Triad benchmark suite."""
    suite = getattr(args, "suite", "cases")
    if suite == "swebench":
        try:
            from bench.swebench_runner import run_swebench
        except ImportError:
            from triad.bench.swebench_runner import run_swebench

        run_swebench(
            engine=args.engine,
            limit=args.limit or 5,
            instance_id=args.case,
            mode="debug",
            judge_engine=getattr(args, "judge_engine", "claude"),
            workers=getattr(args, "workers", 2),
            verbose=args.verbose,
            docker_mode=getattr(args, "docker", "off"),
        )
        return

    try:
        from bench.run_bench import run_benchmark, DEFAULT_CASES_DIR
    except ImportError:
        from triad.bench.run_bench import run_benchmark, DEFAULT_CASES_DIR

    cases_dir = Path(args.cases_dir) if args.cases_dir else DEFAULT_CASES_DIR
    bugs_caught, pos_tot, fps, neg_tot, results = run_benchmark(
        cases_dir=cases_dir,
        engine=args.engine,
        limit=args.limit,
        case_id=args.case,
        judge_engine=getattr(args, "judge_engine", "claude"),
        verbose=args.verbose
    )

def cmd_worktree(args):
    """Manage ephemeral git worktrees."""
    action = getattr(args, "wt_action", None)
    if action == "list" or not action:
        wts = list_worktrees()
        print(f"Active Git Worktrees ({len(wts)}):")
        for wt in wts:
            det = " (detached)" if wt.get("detached") else ""
            branch = f" [{wt.get('branch')}]" if wt.get("branch") else ""
            print(f"  - {wt['worktree']} {wt.get('head', '')[:8]}{branch}{det}")
    elif action == "create":
        wt_path = create_worktree(".", branch_or_commit=args.ref, prefix=args.prefix)
        print(f"Created isolated worktree at: {wt_path}")
    elif action == "remove":
        removed = remove_worktree(args.path, force=args.force)
        if removed:
            print(f"Removed worktree at: {args.path}")
        else:
            print(f"Failed to remove worktree at: {args.path}")
    elif action == "prune":
        prune_worktrees(".")
        print("Pruned stale worktree metadata.")

def cmd_auto(args, env: Optional[Dict[str, str]] = None):
    """
    Auto-classify intent and autonomously route to the appropriate subsystem.
    Supports isolated worktree execution via --worktree (-w).
    """
    if getattr(args, "classify_only", False):
        _print_classification_only(args)
        return

    _check_apply_verified_safety(args, env)

    if getattr(args, "worktree", False):
        try:
            repo_root = get_repo_root(".", env=env)
        except Exception as e:
            print(f"[Triad Worktree Error] Not inside a git repository: {e}", file=sys.stderr)
            sys.exit(1)

        _run_in_isolated_worktree(
            args, env,
            repo_root=repo_root,
            prefix="triad-auto",
            require_index=False,
            runner=lambda a, e: _run_auto(a, env=e),
            error_label="Triad Worktree Error",
            phase_label="auto execution",
            nm_phase_label="auto-execution",
            enforce_clean_explicit_ref=True,
            pause_commit_after_apply=False,
            notify_async=False,
        )
        return

    _run_auto(args, env=env)


def _resolve_auto_inputs(args) -> Tuple[str, str, Optional[str]]:
    """Normalize the (prompt, diff, context) triple that ``triad auto`` classifies."""
    diff_file = getattr(args, "diff_file", None)
    stdin_is_diff = diff_file == "-"

    prompt = getattr(args, "prompt", "")
    if isinstance(prompt, list):
        prompt = " ".join(prompt).strip()
    # stdin can only be consumed once: when it carries the diff, never read it as the prompt.
    if not prompt and not stdin_is_diff and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    setattr(args, "prompt", prompt)

    diff_content = ""
    if diff_file:
        if stdin_is_diff:
            diff_content = sys.stdin.read()
        elif os.path.exists(diff_file):
            with open(diff_file, "r", encoding="utf-8", errors="replace") as f:
                diff_content = f.read()

    context = getattr(args, "context", None) or None
    context_file = getattr(args, "context_file", "")
    if context_file and os.path.exists(context_file):
        with open(context_file, "r", encoding="utf-8", errors="replace") as f:
            context = f.read()
    return prompt, diff_content, context


def _print_classification_only(args) -> None:
    """``triad auto --classify-only``: emit the intent decision as JSON without executing it."""
    prompt, diff_content, context = _resolve_auto_inputs(args)
    classification = classify_intent(prompt, context=context, diff=diff_content)
    if getattr(args, "competition", False):
        classification.suggested_engine = "competition"
    payload = {
        "intent": classification.intent,
        "confidence": classification.confidence,
        "reason": classification.reason,
        "suggested_mode": classification.suggested_mode,
        "suggested_engine": classification.suggested_engine,
        "high_stakes": classification.high_stakes,
        "metadata": classification.metadata,
    }
    print(json.dumps(payload, indent=2))


def _run_auto(args, env: Optional[Dict[str, str]] = None):
    prompt, diff_content, context = _resolve_auto_inputs(args)
    classification = classify_intent(prompt, context=context, diff=diff_content)

    # Force competition if user passed flag
    if getattr(args, "competition", False):
        classification.suggested_engine = "competition"

    execute_intent(classification, prompt, args, env=env)


def cmd_listen(args):
    """Start the Triad Ambient HTTP server daemon."""
    try:
        from triad.server import start_server
    except ImportError:
        from server import start_server

    port = getattr(args, "port", 8789)
    host = getattr(args, "host", "127.0.0.1")
    start_server(host=host, port=port)


TRIAD_HOOK_SIGNATURE = "# Triad Autonomous Pre-Commit Gate Hook"
TRIAD_USER_WRAPPER_START = "# --- Triad Execution Wrapper [START] ---"
TRIAD_USER_WRAPPER_END = "# --- Triad Execution Wrapper [END] ---"
TRIAD_USER_BODY_START = "# --- Triad User Hook Body [START] ---"
TRIAD_USER_BODY_END = "# --- Triad User Hook Body [END] ---"


def _render_triad_hook_block(backup_name: Optional[str] = None) -> str:
    owned_tag = f"# TRIAD_BACKUP_OWNED: {backup_name or 'none'}\n"
    return (
        f"# --- {TRIAD_HOOK_SIGNATURE} [START] ---\n"
        f"{owned_tag}"
        f"USER_EXIT=$?\n"
        f"if [ $USER_EXIT -ne 0 ]; then\n"
        f"    exit $USER_EXIT\n"
        f"fi\n"
        f'TRIAD_HOOK_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"\n'
        f'if [ "${{TRIAD_GATE_ACTIVE:-}}" != "1" ]; then\n'
        f"    if command -v triad >/dev/null 2>&1; then\n"
        f"        triad gate --worktree --apply-verified || exit $?\n"
        f"    elif command -v triad.cmd >/dev/null 2>&1; then\n"
        f"        triad.cmd gate --worktree --apply-verified || exit $?\n"
        f'    elif command -v python3 >/dev/null 2>&1 && python3 -c "import triad" >/dev/null 2>&1; then\n'
        f"        python3 -m triad gate --worktree --apply-verified || exit $?\n"
        f'    elif command -v python >/dev/null 2>&1 && python -c "import triad" >/dev/null 2>&1; then\n'
        f"        python -m triad gate --worktree --apply-verified || exit $?\n"
        f"    else\n"
        f'        if [ "${{TRIAD_SKIP_MISSING:-0}}" = "1" ] || [ "${{TRIAD_OPTIONAL:-0}}" = "1" ]; then\n'
        f'            echo "⚠️ [Triad Hook Notice] Triad CLI not detected on this system. Skipping autonomous gate (TRIAD_SKIP_MISSING / TRIAD_OPTIONAL set)."\n'
        f"        else\n"
        f'            echo "❌ [Triad Hook Error] Triad CLI not found on PATH or via python module."\n'
        f'            echo "To fix: Ensure \'triad\' is on PATH, or run: python -m triad hook install"\n'
        f'            echo "To bypass intentionally for this commit, run: git commit --no-verify or set TRIAD_SKIP_MISSING=1"\n'
        f"            exit 1\n"
        f"        fi\n"
        f"    fi\n"
        f"fi\n"
        f"# --- {TRIAD_HOOK_SIGNATURE} [END] ---\n"
    )

TRIAD_HOOK_BLOCK = _render_triad_hook_block("none")


def _render_hook_template(backup_name: Optional[str] = "pre-commit.legacy", should_execute_backup: bool = True) -> str:
    hook_block = _render_triad_hook_block(backup_name)
    owned_val = backup_name or "none"
    owned_tag = f"# TRIAD_BACKUP_OWNED: {owned_val}\n"
    active_val = "1" if should_execute_backup else "0"
    active_tag = f"# TRIAD_BACKUP_ACTIVE: {active_val}\n"
    return f"""#!/bin/sh
{TRIAD_HOOK_SIGNATURE}
{owned_tag}{active_tag}# Automatically verifies type safety, test suites, and Advisory Council review in an isolated worktree.

HOOK_DIR=$(dirname "$0")

# 1. Execute explicitly owned legacy/third-party pre-commit hook first
BACKUP_ACTIVE="{active_val}"
OWNED_BACKUP="{backup_name or ''}"
if [ "$BACKUP_ACTIVE" = "1" ]; then
    if [ -z "$OWNED_BACKUP" ]; then
        if [ -f "$HOOK_DIR/pre-commit.legacy" ] || [ -L "$HOOK_DIR/pre-commit.legacy" ]; then
            OWNED_BACKUP="pre-commit.legacy"
        fi
    fi
    if [ -n "$OWNED_BACKUP" ] && [ "$OWNED_BACKUP" != "none" ]; then
        legacy_hook="$HOOK_DIR/$OWNED_BACKUP"
        if [ ! -e "$legacy_hook" ] && [ ! -L "$legacy_hook" ]; then
            _COMMON_DIR=$(git rev-parse --git-common-dir 2>/dev/null || git rev-parse --git-dir 2>/dev/null || echo "")
            if [ -n "$_COMMON_DIR" ] && ( [ -e "$_COMMON_DIR/hooks/$OWNED_BACKUP" ] || [ -L "$_COMMON_DIR/hooks/$OWNED_BACKUP" ] ); then
                legacy_hook="$_COMMON_DIR/hooks/$OWNED_BACKUP"
            fi
        fi
        if [ ! -e "$legacy_hook" ] && [ ! -L "$legacy_hook" ]; then
            echo "❌ [Triad Hook Error] Expected legacy pre-commit hook '$OWNED_BACKUP' is missing." >&2
            exit 1
        fi
        if [ -L "$legacy_hook" ] && [ ! -e "$legacy_hook" ]; then
            echo "❌ [Triad Hook Error] Legacy pre-commit hook '$OWNED_BACKUP' is a dangling symlink." >&2
            exit 1
        fi
        IS_HUSKY=0
        if [ "$(basename "$HOOK_DIR")" = ".husky" ] || [ -f "$HOOK_DIR/../.husky/_/h" ] || [ -d "$HOOK_DIR/../.husky" ]; then
            IS_HUSKY=1
        fi
        if [ ! -x "$legacy_hook" ] && [ "$IS_HUSKY" -ne 1 ]; then
            echo "❌ [Triad Hook Error] Legacy pre-commit hook '$OWNED_BACKUP' is not executable." >&2
            exit 1
        fi
        if grep -q "Triad Autonomous Pre-Commit Gate Hook" "$legacy_hook" 2>/dev/null; then
            echo "❌ [Triad Hook Error] Circular legacy hook execution detected in '$OWNED_BACKUP'." >&2
            exit 1
        fi

        LEGACY_DIR=$(cd "$(dirname "$legacy_hook")" && pwd)
        legacy_hook="$LEGACY_DIR/$(basename "$legacy_hook")"
        TARGET_HOOK="$HOOK_DIR/pre-commit"
        export TARGET_HOOK
        TRIAD_ORIGINAL_HOOK="$HOOK_DIR/pre-commit"
        export TRIAD_ORIGINAL_HOOK

        if [ $# -gt 16 ]; then
            echo "❌ [Triad Hook Error] Pre-commit hook arguments exceed maximum supported count (16)." >&2
            exit 1
        fi

        _TRIAD_ORIG_COUNT=$#
        _idx=1
        for _a in "$@"; do
            case $_idx in
                1) _TRIAD_ARG_1="$_a" ;; 2) _TRIAD_ARG_2="$_a" ;; 3) _TRIAD_ARG_3="$_a" ;; 4) _TRIAD_ARG_4="$_a" ;;
                5) _TRIAD_ARG_5="$_a" ;; 6) _TRIAD_ARG_6="$_a" ;; 7) _TRIAD_ARG_7="$_a" ;; 8) _TRIAD_ARG_8="$_a" ;;
                9) _TRIAD_ARG_9="$_a" ;; 10) _TRIAD_ARG_10="$_a" ;; 11) _TRIAD_ARG_11="$_a" ;; 12) _TRIAD_ARG_12="$_a" ;;
                13) _TRIAD_ARG_13="$_a" ;; 14) _TRIAD_ARG_14="$_a" ;; 15) _TRIAD_ARG_15="$_a" ;; 16) _TRIAD_ARG_16="$_a" ;;
            esac
            _idx=$((_idx + 1))
        done

        _triad_exec_split_args() {{
            "$@"
            return $?
        }}

        FIRST_LINE=$(head -n 1 "$legacy_hook" 2>/dev/null || true)
        case "$FIRST_LINE" in
            "#!"*)
                RAW_INTERP=$(printf '%s\\n' "$FIRST_LINE" | sed -e 's/^#![[:blank:]]*//')
                ;;
            *)
                RAW_INTERP=""
                ;;
        esac

        _triad_parse_shebang_tokens() {{
            _raw=$(printf '%s\\n' "$1" | tr "\\\\\\\\" "/")
            _TOK_COUNT=0
            _rem="$_raw"
            _cur=""
            _has=0
            _in_sq=0
            _in_dq=0
            _esc=0

            _add_tok() {{
                if [ $_TOK_COUNT -ge 16 ]; then
                    echo "❌ [Triad Hook Error] Legacy shebang exceeds maximum supported token count (16)." >&2
                    exit 1
                fi
                _TOK_COUNT=$((_TOK_COUNT + 1))
                case $_TOK_COUNT in
                    1) _TOK_1="$1" ;; 2) _TOK_2="$1" ;; 3) _TOK_3="$1" ;; 4) _TOK_4="$1" ;;
                    5) _TOK_5="$1" ;; 6) _TOK_6="$1" ;; 7) _TOK_7="$1" ;; 8) _TOK_8="$1" ;;
                    9) _TOK_9="$1" ;; 10) _TOK_10="$1" ;; 11) _TOK_11="$1" ;; 12) _TOK_12="$1" ;;
                    13) _TOK_13="$1" ;; 14) _TOK_14="$1" ;; 15) _TOK_15="$1" ;; 16) _TOK_16="$1" ;;
                esac
            }}

            set -f
            while [ -n "$_rem" ]; do
                _c="${{_rem%"${{_rem#?}}"}}"
                _rem="${{_rem#?}}"
                if [ "$_esc" -eq 1 ]; then
                    _cur="${{_cur}}${{_c}}"
                    _has=1
                    _esc=0
                elif [ "$_in_sq" -eq 1 ]; then
                    if [ "$_c" = "'" ]; then
                        _in_sq=0
                    else
                        _cur="${{_cur}}${{_c}}"
                    fi
                elif [ "$_in_dq" -eq 1 ]; then
                    if [ "$_c" = '\\' ]; then
                        _esc=1
                    elif [ "$_c" = '"' ]; then
                        _in_dq=0
                    else
                        _cur="${{_cur}}${{_c}}"
                    fi
                else
                    if [ "$_c" = '\\' ]; then
                        _has=1
                        _esc=1
                    elif [ "$_c" = "'" ]; then
                        _has=1
                        _in_sq=1
                    elif [ "$_c" = '"' ]; then
                        _has=1
                        _in_dq=1
                    elif [ "$_c" = " " ] || [ "$_c" = "	" ]; then
                        if [ "$_has" -eq 1 ]; then
                            _add_tok "$_cur"
                            _cur=""
                            _has=0
                        fi
                    else
                        _cur="${{_cur}}${{_c}}"
                        _has=1
                    fi
                fi
            done
            if [ "$_has" -eq 1 ]; then
                _add_tok "$_cur"
            fi
            set +f
        }}

        _triad_get_token() {{
            case "$1" in
                1) _TOK_VAL="$_TOK_1" ;; 2) _TOK_VAL="$_TOK_2" ;; 3) _TOK_VAL="$_TOK_3" ;; 4) _TOK_VAL="$_TOK_4" ;;
                5) _TOK_VAL="$_TOK_5" ;; 6) _TOK_VAL="$_TOK_6" ;; 7) _TOK_VAL="$_TOK_7" ;; 8) _TOK_VAL="$_TOK_8" ;;
                9) _TOK_VAL="$_TOK_9" ;; 10) _TOK_VAL="$_TOK_10" ;; 11) _TOK_VAL="$_TOK_11" ;; 12) _TOK_VAL="$_TOK_12" ;;
                13) _TOK_VAL="$_TOK_13" ;; 14) _TOK_VAL="$_TOK_14" ;; 15) _TOK_VAL="$_TOK_15" ;; 16) _TOK_VAL="$_TOK_16" ;;
                *) _TOK_VAL="" ;;
            esac
        }}

        _triad_parse_shebang_tokens "$RAW_INTERP"

        _cur_idx=1
        _use_env=0
        _INTERP_BIN=""
        _ENV_OPT_COUNT=0
        _FLAG_COUNT=0

        _add_env_opt() {{
            if [ $_ENV_OPT_COUNT -ge 16 ]; then
                echo "❌ [Triad Hook Error] Legacy shebang exceeds maximum supported env options (16)." >&2
                exit 1
            fi
            _ENV_OPT_COUNT=$((_ENV_OPT_COUNT + 1))
            case $_ENV_OPT_COUNT in
                1) _ENV_OPT_1="$1" ;; 2) _ENV_OPT_2="$1" ;; 3) _ENV_OPT_3="$1" ;; 4) _ENV_OPT_4="$1" ;;
                5) _ENV_OPT_5="$1" ;; 6) _ENV_OPT_6="$1" ;; 7) _ENV_OPT_7="$1" ;; 8) _ENV_OPT_8="$1" ;;
                9) _ENV_OPT_9="$1" ;; 10) _ENV_OPT_10="$1" ;; 11) _ENV_OPT_11="$1" ;; 12) _ENV_OPT_12="$1" ;;
                13) _ENV_OPT_13="$1" ;; 14) _ENV_OPT_14="$1" ;; 15) _ENV_OPT_15="$1" ;; 16) _ENV_OPT_16="$1" ;;
            esac
        }}

        _add_flag() {{
            if [ $_FLAG_COUNT -ge 16 ]; then
                echo "❌ [Triad Hook Error] Legacy shebang exceeds maximum supported flags (16)." >&2
                exit 1
            fi
            _FLAG_COUNT=$((_FLAG_COUNT + 1))
            case $_FLAG_COUNT in
                1) _FLAG_1="$1" ;; 2) _FLAG_2="$1" ;; 3) _FLAG_3="$1" ;; 4) _FLAG_4="$1" ;;
                5) _FLAG_5="$1" ;; 6) _FLAG_6="$1" ;; 7) _FLAG_7="$1" ;; 8) _FLAG_8="$1" ;;
                9) _FLAG_9="$1" ;; 10) _FLAG_10="$1" ;; 11) _FLAG_11="$1" ;; 12) _FLAG_12="$1" ;;
                13) _FLAG_13="$1" ;; 14) _FLAG_14="$1" ;; 15) _FLAG_15="$1" ;; 16) _FLAG_16="$1" ;;
            esac
        }}

        if [ $_TOK_COUNT -gt 0 ]; then
            _triad_get_token 1
            _first_base=$(basename "$_TOK_VAL" 2>/dev/null || printf '%s\\n' "$_TOK_VAL")
            if [ "$_first_base" = "env" ]; then
                _use_env=1
                _cur_idx=2
                while [ $_cur_idx -le $_TOK_COUNT ]; do
                    _triad_get_token $_cur_idx
                    _cur_idx=$((_cur_idx + 1))
                    case "$_TOK_VAL" in
                        -S|--split-string)
                            ;;
                        -i|--ignore-environment)
                            _add_env_opt "-i"
                            ;;
                        -u)
                            _add_env_opt "-u"
                            if [ $_cur_idx -le $_TOK_COUNT ]; then
                                _triad_get_token $_cur_idx
                                _cur_idx=$((_cur_idx + 1))
                                _add_env_opt "$_TOK_VAL"
                            fi
                            ;;
                        *=*)
                            _add_env_opt "$_TOK_VAL"
                            ;;
                        -*)
                            ;;
                        *)
                            _INTERP_BIN="$_TOK_VAL"
                            break
                            ;;
                    esac
                done
            else
                _INTERP_BIN="$_TOK_VAL"
                _cur_idx=2
            fi
            while [ $_cur_idx -le $_TOK_COUNT ]; do
                _triad_get_token $_cur_idx
                _cur_idx=$((_cur_idx + 1))
                _add_flag "$_TOK_VAL"
            done
        fi

        set -f
        set --
        if [ "$_use_env" -eq 1 ]; then
            set -- "$@" "env"
            _eidx=1
            while [ $_eidx -le $_ENV_OPT_COUNT ]; do
                case $_eidx in
                    1) set -- "$@" "$_ENV_OPT_1" ;; 2) set -- "$@" "$_ENV_OPT_2" ;;
                    3) set -- "$@" "$_ENV_OPT_3" ;; 4) set -- "$@" "$_ENV_OPT_4" ;;
                    5) set -- "$@" "$_ENV_OPT_5" ;; 6) set -- "$@" "$_ENV_OPT_6" ;;
                    7) set -- "$@" "$_ENV_OPT_7" ;; 8) set -- "$@" "$_ENV_OPT_8" ;;
                    9) set -- "$@" "$_ENV_OPT_9" ;; 10) set -- "$@" "$_ENV_OPT_10" ;;
                    11) set -- "$@" "$_ENV_OPT_11" ;; 12) set -- "$@" "$_ENV_OPT_12" ;;
                    13) set -- "$@" "$_ENV_OPT_13" ;; 14) set -- "$@" "$_ENV_OPT_14" ;;
                    15) set -- "$@" "$_ENV_OPT_15" ;; 16) set -- "$@" "$_ENV_OPT_16" ;;
                esac
                _eidx=$((_eidx + 1))
            done
        fi

        _interp_base=$(basename "$_INTERP_BIN" 2>/dev/null || printf '%s\\n' "$_INTERP_BIN")
        _interp_base_lower=$(printf '%s\\n' "$_interp_base" | tr '[:upper:]' '[:lower:]')

        case "$_interp_base_lower" in
            sh|bash|zsh|dash|ash|ksh)
                _cmd="${{_INTERP_BIN:-sh}}"
                set -- "$@" "$_cmd"
                _fidx=1
                while [ $_fidx -le $_FLAG_COUNT ]; do
                    case $_fidx in
                        1) set -- "$@" "$_FLAG_1" ;; 2) set -- "$@" "$_FLAG_2" ;; 3) set -- "$@" "$_FLAG_3" ;; 4) set -- "$@" "$_FLAG_4" ;;
                        5) set -- "$@" "$_FLAG_5" ;; 6) set -- "$@" "$_FLAG_6" ;; 7) set -- "$@" "$_FLAG_7" ;; 8) set -- "$@" "$_FLAG_8" ;;
                        9) set -- "$@" "$_FLAG_9" ;; 10) set -- "$@" "$_FLAG_10" ;; 11) set -- "$@" "$_FLAG_11" ;; 12) set -- "$@" "$_FLAG_12" ;;
                        13) set -- "$@" "$_FLAG_13" ;; 14) set -- "$@" "$_FLAG_14" ;; 15) set -- "$@" "$_FLAG_15" ;; 16) set -- "$@" "$_FLAG_16" ;;
                    esac
                    _fidx=$((_fidx + 1))
                done
                set -- "$@" -c 'script="$1"; shift; . "$script"' "$HOOK_DIR/pre-commit" "$legacy_hook"
                ;;
            python*|pypy*)
                _cmd="${{_INTERP_BIN:-python3}}"
                set -- "$@" "$_cmd"
                _fidx=1
                while [ $_fidx -le $_FLAG_COUNT ]; do
                    case $_fidx in
                        1) set -- "$@" "$_FLAG_1" ;; 2) set -- "$@" "$_FLAG_2" ;; 3) set -- "$@" "$_FLAG_3" ;; 4) set -- "$@" "$_FLAG_4" ;;
                        5) set -- "$@" "$_FLAG_5" ;; 6) set -- "$@" "$_FLAG_6" ;; 7) set -- "$@" "$_FLAG_7" ;; 8) set -- "$@" "$_FLAG_8" ;;
                        9) set -- "$@" "$_FLAG_9" ;; 10) set -- "$@" "$_FLAG_10" ;; 11) set -- "$@" "$_FLAG_11" ;; 12) set -- "$@" "$_FLAG_12" ;;
                        13) set -- "$@" "$_FLAG_13" ;; 14) set -- "$@" "$_FLAG_14" ;; 15) set -- "$@" "$_FLAG_15" ;; 16) set -- "$@" "$_FLAG_16" ;;
                    esac
                    _fidx=$((_fidx + 1))
                done
                set -- "$@" -c 'import os, sys; orig = sys.argv[1]; p = sys.argv[2]; sys.argv = [orig] + sys.argv[3:]; sys.path[0] = os.path.dirname(os.path.abspath(orig)); bp = os.path.dirname(os.path.abspath(p)); sys.path.insert(1, bp) if bp != sys.path[0] else None; m = sys.modules["__main__"]; m.__file__ = orig; f = open(p, "rb"); c = compile(f.read(), orig, "exec"); f.close(); exec(c, m.__dict__)' "$HOOK_DIR/pre-commit" "$legacy_hook"
                ;;
            *)
                if [ -n "$_INTERP_BIN" ]; then
                    set -- "$@" "$_INTERP_BIN"
                    _fidx=1
                    while [ $_fidx -le $_FLAG_COUNT ]; do
                        case $_fidx in
                            1) set -- "$@" "$_FLAG_1" ;; 2) set -- "$@" "$_FLAG_2" ;; 3) set -- "$@" "$_FLAG_3" ;; 4) set -- "$@" "$_FLAG_4" ;;
                            5) set -- "$@" "$_FLAG_5" ;; 6) set -- "$@" "$_FLAG_6" ;; 7) set -- "$@" "$_FLAG_7" ;; 8) set -- "$@" "$_FLAG_8" ;;
                            9) set -- "$@" "$_FLAG_9" ;; 10) set -- "$@" "$_FLAG_10" ;; 11) set -- "$@" "$_FLAG_11" ;; 12) set -- "$@" "$_FLAG_12" ;;
                            13) set -- "$@" "$_FLAG_13" ;; 14) set -- "$@" "$_FLAG_14" ;; 15) set -- "$@" "$_FLAG_15" ;; 16) set -- "$@" "$_FLAG_16" ;;
                        esac
                        _fidx=$((_fidx + 1))
                    done
                    set -- "$@" "$legacy_hook"
                elif [ -x "$legacy_hook" ]; then
                    set -- "$@" "$legacy_hook"
                else
                    set -- "$@" "sh" -c 'script="$1"; shift; . "$script"' "$HOOK_DIR/pre-commit" "$legacy_hook"
                fi
                ;;
        esac

        _idx=1
        while [ $_idx -le $_TRIAD_ORIG_COUNT ]; do
            case $_idx in
                1) set -- "$@" "$_TRIAD_ARG_1" ;; 2) set -- "$@" "$_TRIAD_ARG_2" ;;
                3) set -- "$@" "$_TRIAD_ARG_3" ;; 4) set -- "$@" "$_TRIAD_ARG_4" ;;
                5) set -- "$@" "$_TRIAD_ARG_5" ;; 6) set -- "$@" "$_TRIAD_ARG_6" ;;
                7) set -- "$@" "$_TRIAD_ARG_7" ;; 8) set -- "$@" "$_TRIAD_ARG_8" ;;
                9) set -- "$@" "$_TRIAD_ARG_9" ;; 10) set -- "$@" "$_TRIAD_ARG_10" ;;
                11) set -- "$@" "$_TRIAD_ARG_11" ;; 12) set -- "$@" "$_TRIAD_ARG_12" ;;
                13) set -- "$@" "$_TRIAD_ARG_13" ;; 14) set -- "$@" "$_TRIAD_ARG_14" ;;
                15) set -- "$@" "$_TRIAD_ARG_15" ;; 16) set -- "$@" "$_TRIAD_ARG_16" ;;
            esac
            _idx=$((_idx + 1))
        done

        set +f

        # Dispatch via _triad_exec_split_args compatibility wrapper -- "$@"
        _triad_exec_split_args "$@"
        LEGACY_EXIT=$?
        if [ $LEGACY_EXIT -ne 0 ]; then
            echo "[Triad Hook] Legacy pre-commit hook $(basename "$legacy_hook") failed (exit code $LEGACY_EXIT). Aborting commit."
            exit $LEGACY_EXIT
        fi
    fi
fi

# 2. Pre-commit gate enforcement
{hook_block}
"""

TRIAD_HOOK_TEMPLATE = _render_hook_template("none")


def get_git_common_dir(repo_path: Union[str, Path] = ".") -> Path:
    """Resolve the common git directory for a repo or linked worktree."""
    ret_c, out_c, _ = run_subprocess_tree_safe(["git", "rev-parse", "--git-common-dir"], cwd=repo_path)
    if ret_c == 0 and out_c.strip():
        p = Path(out_c.strip())
        if not p.is_absolute():
            p = (Path(repo_path) / p).resolve()
        return p
    ret_g, out_g, _ = run_subprocess_tree_safe(["git", "rev-parse", "--git-dir"], cwd=repo_path)
    if ret_g == 0 and out_g.strip():
        p = Path(out_g.strip())
        if not p.is_absolute():
            p = (Path(repo_path) / p).resolve()
        return p
    return (Path(repo_path) / ".git").resolve()


def get_git_hooks_dir(repo_path: str = ".") -> Path:
    """Resolve the git hooks directory for a repo or worktree."""
    ret, out, _ = run_subprocess_tree_safe(["git", "rev-parse", "--git-path", "hooks"], cwd=repo_path)
    if ret == 0 and out.strip():
        p = Path(out.strip())
        if not p.is_absolute():
            p = (Path(repo_path) / p).resolve()
        return p
    return (Path(repo_path) / ".git" / "hooks").resolve()


def resolve_target_hook_file(repo_root: Union[str, Path], hook_name: str = "pre-commit") -> Path:
    """
    Resolve the actual hook script to install into or manage.
    Handles standard git hooks, custom core.hooksPath, and modern Husky v9 bootstrap layouts.
    Strictly follows Git's effective hooks directory. Redirects to .husky only when Git's
    active hook entrypoint or core.hooksPath demonstrably delegates to Husky.
    Preserves symlinks on .husky hooks without resolving them to underlying targets.
    """
    repo_root = Path(repo_root).resolve()
    hooks_dir = get_git_hooks_dir(repo_root)
    primary_hook = hooks_dir / hook_name

    # Check for modern Husky layout:
    # Redirect to .husky only when Git's active hook entrypoint or core.hooksPath demonstrably delegates to Husky.
    # 1. hooks_dir is literally within .husky ('_') or is .husky
    if hooks_dir.name == "_" and hooks_dir.parent.name == ".husky":
        return hooks_dir.parent / hook_name
    if hooks_dir.name == ".husky":
        return hooks_dir / hook_name

    # 2. primary_hook delegates to a bootstrap like "${0%/*}/h" or "/_/h" or "husky.sh"
    if primary_hook.exists():
        try:
            content = primary_hook.read_text(encoding="utf-8", errors="replace")
            if "${0%/*}/h" in content or "/_/h" in content or "husky.sh" in content:
                husky_user_hook = repo_root / ".husky" / hook_name
                if husky_user_hook != primary_hook and (husky_user_hook.is_symlink() or husky_user_hook.exists() or (repo_root / ".husky" / "_").exists()):
                    return husky_user_hook
        except Exception:
            pass

    return primary_hook


def is_posix_shell_shebang(first_line: str) -> bool:
    """
    Check if the first line is a valid shebang for a POSIX-compatible shell.
    Strictly allowlists POSIX shells: sh, bash, zsh, dash, ash, ksh.
    Rejects fish, pwsh, python, node, perl, ruby, etc.
    """
    if not first_line.startswith("#!"):
        return False
    m = re.search(r"^#!\s*(?:[^\s]*/env(?:\s+-\S+)*\s+)?([^\s]+)", first_line)
    if not m:
        return False
    interp = Path(m.group(1)).name.lower()
    return interp in {"sh", "bash", "zsh", "dash", "ash", "ksh"}


def _has_top_level_return(content: str) -> bool:
    """
    Detect if a shell script contains a top-level 'return' statement (outside function definitions).
    Scripts containing top-level returns are meant to be sourced, and fail inside subshells.
    """
    if not re.search(r"\breturn\b", content):
        return False

    func_depth = 0
    in_func_header = False

    for line in content.splitlines():
        code_part = re.sub(r"#.*$", "", line).strip()
        if not code_part:
            continue

        if re.search(r"(?:function\s+\w+|\w+\s*\(\s*\))\s*\{?", code_part):
            in_func_header = True

        for char in code_part:
            if char == "{" and in_func_header:
                func_depth += 1
                in_func_header = False
            elif char == "}" and func_depth > 0:
                func_depth -= 1

        if func_depth == 0 and re.search(r"\breturn\b", code_part):
            return True

    return False


def _unwrap_triad_user_body(content: str) -> str:
    """
    Extracts and unwraps the original user hook body from a Triad-wrapped hook.
    Strips any trailing Triad pre-commit gate hook block, then unwraps the execution wrapper.
    Uses explicit TRIAD_USER_BODY_START and TRIAD_USER_BODY_END boundary markers to prevent
    truncation or corruption if the user hook body contains inner subshells with ')' or 'USER_EXIT=$?'.
    Validates that markers appear with unambiguous multiplicity (count == 1).
    Falls back gracefully to legacy wrapper regex if body boundary markers are not present.
    """
    import re
    # 1. Strip any existing Triad pre-commit gate block
    content = re.sub(
        r"\n?# --- # Triad Autonomous Pre-Commit Gate Hook \[START\] ---.*?# --- # Triad Autonomous Pre-Commit Gate Hook \[END\] ---\n?",
        "",
        content,
        flags=re.DOTALL
    )

    if TRIAD_USER_WRAPPER_START not in content:
        return content

    if (
        TRIAD_USER_BODY_START in content
        and TRIAD_USER_BODY_END in content
        and content.count(TRIAD_USER_BODY_START) == 1
        and content.count(TRIAD_USER_BODY_END) == 1
    ):
        wrap_start = content.find(TRIAD_USER_WRAPPER_START)
        wrap_end = content.find(TRIAD_USER_WRAPPER_END)
        body_start = content.find(TRIAD_USER_BODY_START)
        body_end = content.find(TRIAD_USER_BODY_END)

        if 0 <= wrap_start < body_start < body_end and wrap_end > body_end:
            body_inner_start = body_start + len(TRIAD_USER_BODY_START)
            raw_body = content[body_inner_start:body_end]
            if raw_body.startswith("\r\n"):
                raw_body = raw_body[2:]
            elif raw_body.startswith("\n"):
                raw_body = raw_body[1:]
            if raw_body.endswith("\r\n"):
                raw_body = raw_body[:-2]
            elif raw_body.endswith("\n"):
                raw_body = raw_body[:-1]

            prefix = content[:wrap_start]
            wrap_full_end = wrap_end + len(TRIAD_USER_WRAPPER_END)
            suffix = content[wrap_full_end:]
            if suffix.startswith("\r\n"):
                suffix = suffix[2:]
            elif suffix.startswith("\n"):
                suffix = suffix[1:]

            if prefix and not prefix.endswith("\n"):
                prefix += "\n"
            if raw_body and suffix:
                if not raw_body.endswith("\n") and not suffix.startswith("\n"):
                    raw_body += "\n"
            res = prefix + raw_body + suffix
            if res and not res.endswith("\n"):
                res += "\n"
            return res

    # Fallback to regex for legacy wrapper format without explicit body markers
    wrapper_regex = re.compile(
        r"# --- Triad Execution Wrapper \[START\] ---\n.*?\(\n(?::\n)?(.*?)\n\)\nUSER_EXIT=\$\?\n.*?\n# --- Triad Execution Wrapper \[END\] ---\n?",
        flags=re.DOTALL
    )
    res = wrapper_regex.sub(r"\1\n", content)
    if res and not res.endswith("\n"):
        res += "\n"
    return res


def _integrate_triad_into_hook(content: str, triad_block: str) -> str:
    """
    Integrates Triad gate into an existing shell hook script.
    Child-process contract:
    - User hook body executes in an isolated subshell preserving its exit status without trap interference.
    - User hook retains complete ownership of trap state (trap -p is untouched; custom EXIT traps run cleanly).
    - If the user hook calls exec, the child process exits cleanly and returns exit code to USER_EXIT.
    - If the user hook needs to export environment variables to Triad stages, it can write exports to $TRIAD_ENV_FILE.
    - If USER_EXIT != 0, exits immediately with USER_EXIT without running Triad.
    - Otherwise, execution flows seamlessly into Triad.
    Preserves exact user body bytes and boundary whitespace without stripping.
    """
    import re
    # 1. Strip any existing Triad pre-commit block
    cleaned = re.sub(
        r"\n?# --- # Triad Autonomous Pre-Commit Gate Hook \[START\] ---.*?# --- # Triad Autonomous Pre-Commit Gate Hook \[END\] ---\n?",
        "",
        content,
        flags=re.DOTALL
    )

    # 2. Strip any existing user wrapper if previously installed (idempotency)
    cleaned = _unwrap_triad_user_body(cleaned)

    lines = cleaned.splitlines(keepends=True)
    if not lines or not "".join(lines).strip():
        return triad_block.strip() + "\n"

    shebang = ""
    user_body = cleaned
    had_blank_after_shebang = False
    if lines[0].startswith("#!"):
        shebang = lines[0].rstrip("\r\n")
        remaining = "".join(lines[1:])
        if remaining.startswith("\r\n"):
            had_blank_after_shebang = True
            user_body = remaining[2:]
        elif remaining.startswith("\n"):
            had_blank_after_shebang = True
            user_body = remaining[1:]
        else:
            user_body = remaining

    # Remove only the trailing line terminator from user_body for the subshell syntax, preserving boundary whitespace
    if user_body.endswith("\r\n"):
        user_body_clean = user_body[:-2]
    elif user_body.endswith("\n"):
        user_body_clean = user_body[:-1]
    else:
        user_body_clean = user_body

    if not user_body_clean.strip():
        if shebang:
            shebang_sep = "\n\n" if had_blank_after_shebang else "\n"
            return f"{shebang}{shebang_sep}{triad_block.strip()}\n"
        return f"{triad_block.strip()}\n"

    wrapped_block = (
        f"{TRIAD_USER_WRAPPER_START}\n"
        f'TRIAD_ENV_FILE=$(mktemp "${{TMPDIR:-/tmp}}/triad_env.XXXXXX" 2>/dev/null || true)\n'
        f'if [ -n "$TRIAD_ENV_FILE" ] && [ -f "$TRIAD_ENV_FILE" ]; then\n'
        f"    export TRIAD_ENV_FILE\n"
        f"else\n"
        f'    TRIAD_ENV_FILE=""\n'
        f"fi\n"
        f"(\n"
        f":\n"
        f"{TRIAD_USER_BODY_START}\n"
        f"{user_body_clean}\n"
        f"{TRIAD_USER_BODY_END}\n"
        f")\n"
        f"USER_EXIT=$?\n"
        f'if [ -n "$TRIAD_ENV_FILE" ] && [ -f "$TRIAD_ENV_FILE" ]; then\n'
        f"    set -a\n"
        f'    . "$TRIAD_ENV_FILE" 2>/dev/null || true\n'
        f"    set +a\n"
        f'    rm -f "$TRIAD_ENV_FILE"\n'
        f"fi\n"
        f"if [ $USER_EXIT -ne 0 ]; then\n"
        f"    exit $USER_EXIT\n"
        f"fi\n"
        f"{TRIAD_USER_WRAPPER_END}"
    )

    if shebang:
        shebang_sep = "\n\n" if had_blank_after_shebang else "\n"
        return f"{shebang}{shebang_sep}{wrapped_block}\n\n{triad_block.strip()}\n"
    return f"{wrapped_block}\n\n{triad_block.strip()}\n"


_integrate_triad_into_husky = _integrate_triad_into_hook


def _is_standalone_triad_hook(content: str) -> bool:
    """Return True if content represents an unintegrated standalone Triad hook template."""
    return (
        TRIAD_HOOK_SIGNATURE in content
        and ("Automatically verifies type safety, test suites" in content or "pre-commit.legacy" in content)
        and TRIAD_USER_WRAPPER_START not in content
    )


def _is_integrated_triad_hook(content: str) -> bool:
    """Return True if content represents an integrated Triad hook inside a user script."""
    return (
        TRIAD_HOOK_SIGNATURE in content
        and (
            TRIAD_USER_WRAPPER_START in content
            or "# --- # Triad Autonomous Pre-Commit Gate Hook [START] ---" in content
            or "USER_EXIT=$?" in content
        )
    )


def _is_hook_executable(mode: Optional[int], is_husky: bool = False) -> bool:
    """Check whether a hook's file mode is executable according to OS semantics."""
    if is_husky:
        return True
    if mode is None:
        return True
    if os.name != "nt":
        return (mode & 0o111) != 0
    return True


class _HookLock:
    """Exclusive cooperative lock using OS-level locking to serialize Triad hook mutations."""
    def __init__(self, hooks_dir: Path, timeout: float = 10.0):
        self.lock_file = hooks_dir / ".triad_hook.lock"
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        self.fd = os.open(str(self.lock_file), flags, 0o600)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(self.fd, 0, os.SEEK_SET)
                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (OSError, IOError):
                if time.monotonic() >= deadline:
                    try:
                        os.close(self.fd)
                    except Exception:
                        pass
                    self.fd = None
                    raise TimeoutError(f"Timed out acquiring exclusive hook lock on {self.lock_file}")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(self.fd, 0, os.SEEK_SET)
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None


try:
    from triad.cli.hook import (
        _verify_destination_unmodified,
        _allocate_exclusive_backup,
        cmd_hook,
    )
except ImportError:
    from cli.hook import (
        _verify_destination_unmodified,
        _allocate_exclusive_backup,
        cmd_hook,
    )

try:
    from triad.cli.mesh import _mesh_list_tools, cmd_mesh
except ImportError:
    from cli.mesh import _mesh_list_tools, cmd_mesh


def is_plausible_natural_language(first_arg: str, total_args: int, known_commands: set) -> bool:
    """Return True if argument looks like a natural language query or diff rather than a mistyped subcommand."""
    import difflib
    stripped = first_arg.strip()
    if not stripped:
        return False

    # If first_arg is a single word (no spaces inside):
    if " " not in stripped:
        lowered = stripped.lower()
        if lowered not in known_commands:
            near_matches = difflib.get_close_matches(lowered, [c for c in known_commands if not c.startswith("-")], n=1, cutoff=0.75)
            if near_matches:
                return False  # Near-miss typo of a known subcommand (e.g. 'revew', 'gaet', 'docter')

        # If it has path or query punctuation (e.g. 'path/to/file.py' or 'hello?'), allow it
        if any(c in stripped for c in ("?", "\n", "\t", "/", "\\", ":", ".")):
            return True

        # If multiple unquoted arguments were passed (e.g. 'triad why is this failing'), allow it
        if total_args > 2:
            return True

        # Otherwise it's a single bare unknown token like 'foo' -> reject
        return False

    # If first_arg contains spaces (quoted natural language prompt), allow it
    return True


try:
    from triad.cli.sync import cmd_sync
except ImportError:
    from cli.sync import cmd_sync


def cmd_rewrite(args):
    """Expand a sparse prompt into a fully-specified agent brief (local, zero-cost by default)."""
    try:
        from triad.prompt_rewriter import format_output, polish_with_llm, rewrite_prompt
    except ImportError:
        from prompt_rewriter import format_output, polish_with_llm, rewrite_prompt  # type: ignore

    prompt = getattr(args, "prompt", "") or ""
    if isinstance(prompt, list):
        prompt = " ".join(prompt).strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        print("Usage: triad rewrite <prompt> | echo prompt | triad rewrite", file=sys.stderr)
        sys.exit(2)

    context = getattr(args, "context", "") or ""
    context_file = getattr(args, "context_file", "") or ""
    if context_file and os.path.exists(context_file):
        with open(context_file, "r", encoding="utf-8", errors="replace") as f:
            context = f.read()

    diff_content = ""
    diff_file = getattr(args, "diff_file", "") or ""
    if diff_file:
        if diff_file == "-":
            # prompt already consumed stdin unless it came from argv
            if getattr(args, "prompt", None):
                diff_content = sys.stdin.read() if not sys.stdin.isatty() else ""
        elif os.path.exists(diff_file):
            with open(diff_file, "r", encoding="utf-8", errors="replace") as f:
                diff_content = f.read()

    extra = getattr(args, "constraint", None) or []
    style = getattr(args, "style", "brief") or "brief"
    brief = rewrite_prompt(
        prompt,
        context=context or None,
        diff=diff_content or None,
        cwd=os.getcwd(),
        extra_constraints=extra,
        style=style,
    )

    if getattr(args, "llm", False):
        try:
            polished = polish_with_llm(brief, engine=getattr(args, "engine", "auto") or "auto")
            brief.rewritten = polished
            brief.metadata["llm_polished"] = True
        except Exception as exc:
            print(f"[triad rewrite] LLM polish failed ({exc}); emitting local brief.", file=sys.stderr)

    out_path = getattr(args, "output", "") or ""
    text = format_output(
        brief,
        as_json=getattr(args, "json", False),
        include_meta=not getattr(args, "plain", False),
    )
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text if text.endswith("\n") else text + "\n")
        print(f"[triad rewrite] wrote {out_path}")
    else:
        print(text)


def cmd_agent(args):
    """
    Launch Triad Agent: Autonomous zero-cost terminal AI agent with RouteLLM waterfall.
    """
    pkg_root = str(TRIAD_DIR.parent)
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)
    if str(TRIAD_DIR) not in sys.path:
        sys.path.insert(0, str(TRIAD_DIR))

    try:
        from triad.agent.cli import main as agent_cli_main
    except ImportError:
        from agent.cli import main as agent_cli_main

    argv = []
    if getattr(args, "prompt", None):
        argv.extend(["-p", args.prompt])
    if getattr(args, "resume", False):
        argv.append("-c")
    if getattr(args, "auto_approve", False):
        argv.append("-y")
    if getattr(args, "force_heavy", False):
        argv.append("--heavy")
    if getattr(args, "force_free", False):
        argv.append("--free")
    if getattr(args, "force_local", False):
        argv.append("--local")
    if getattr(args, "model", None):
        argv.extend(["--model", args.model])
    if getattr(args, "concise", False):
        argv.append("--concise")

    sys.exit(agent_cli_main(argv))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="triad", description="Autonomous Multi-Agent Triad Orchestrator")
    subparsers = parser.add_subparsers(dest="command", help="Triad command to execute")

    # auto / intent / run
    p_auto = subparsers.add_parser("auto", aliases=["intent", "run"], help="Auto-classify intent and autonomously route across Triad subsystems")
    p_auto.add_argument("prompt", nargs="*", default=[], help="Natural language request, diff, or query")
    p_auto.add_argument("--task", default="auto", choices=["auto", "architecture", "reasoning", "scraping", "browsing", "coding", "micro", "general"], help="Task profile override for efficiency-based model routing")
    p_auto.add_argument("--diff-file", default="", help="Path to diff file or - for stdin")
    p_auto.add_argument("--context", default="", help="Inline context or error snippet")
    p_auto.add_argument("--context-file", default="", help="Path to context file")
    p_auto.add_argument("--competition", action="store_true", help="Force competition mode regardless of auto-stake assessment")
    p_auto.add_argument("--adversarial", action="store_true", help="Execute Red/Blue adversarial arena audit")
    p_auto.add_argument("--engine", default="auto", help="Advisor engine override")
    p_auto.add_argument("--cached", "--staged", action="store_true", help="Review staged changes if routing to review")
    p_auto.add_argument("--head", action="store_true", help="Review the most recent commit (HEAD~1..HEAD) if routing to review")
    p_auto.add_argument("--worktree", "-w", action="store_true", help="Execute in an isolated ephemeral git worktree")
    p_auto.add_argument("--ref", default="HEAD", help="Git ref/branch/commit to base ephemeral worktree on (default: HEAD)")
    p_auto.add_argument("--apply-verified", action="store_true", help="Apply passing self-healing patches back to parent working tree")
    p_auto.add_argument("--test-timeout", type=int, default=600, help="Test runner timeout in seconds (default 600)")
    p_auto.add_argument("--target", default="", help="Targeted test pattern (e.g. test_circuit.py)")
    p_auto.add_argument("--targeted", action="store_true", help="Auto-resolve targeted test pattern from changed files")
    p_auto.add_argument("--parallel", action="store_true", help="Execute test suite in parallel using pytest-xdist when available")
    p_auto.add_argument("--classify-only", action="store_true", help="Print the intent classification as JSON and exit without executing")

    # doctor
    p_doc = subparsers.add_parser("doctor", help="Run comprehensive health and billing audit across all platforms (exit 1 if no advisor is usable)")
    p_doc.add_argument("--quick", action="store_true", help="Skip the live Claude probe (saves a Claude Pro turn)")
    p_doc.add_argument("--json", action="store_true", help="Emit the structured report as JSON")
    p_doc.add_argument("--reset-circuits", action="store_true", help="Clear advisor circuit-breaker cooldowns before the audit")
    p_doc.add_argument("--clear-cache", action="store_true", help="Clear cached advisor responses before the audit")

    # review
    p_rev = subparsers.add_parser("review", help="Review a git diff with the Advisory Council")
    p_rev.add_argument("prompt", nargs="?", default="", help="Specific review instructions or feature intent")
    p_rev.add_argument("--task", default="auto", choices=["auto", "architecture", "reasoning", "scraping", "browsing", "coding", "micro", "general"], help="Task profile override for efficiency-based model routing")
    p_rev.add_argument("--diff-file", default="", help="Path to diff file or - for stdin")
    p_rev.add_argument("--cached", "--staged", action="store_true", help="Review staged changes")
    p_rev.add_argument("--head", action="store_true", help="Review the most recent commit (HEAD~1..HEAD)")
    p_rev.add_argument("--engine", default="auto", help="Advisor engine override (e.g. auto, claude, codex, ollama, mock)")
    p_rev.add_argument("--competition", action="store_true", help="Execute Claude Code & OpenAI Codex concurrently with structured synthesis")
    p_rev.add_argument("--adversarial", action="store_true", help="Execute Red/Blue adversarial arena security and resilience audit")

    # consult
    p_con = subparsers.add_parser("consult", help="Consult Advisory Council on architectural design")
    p_con.add_argument("prompt", nargs="?", default="", help="Architectural question or proposal")
    p_con.add_argument("--task", default="auto", choices=["auto", "architecture", "reasoning", "scraping", "browsing", "coding", "micro", "general"], help="Task profile override for efficiency-based model routing")
    p_con.add_argument("--context", default="", help="Inline context or schema")
    p_con.add_argument("--context-file", default="", help="Path to context file")
    p_con.add_argument("--engine", default="auto", help="Advisor engine override (e.g. auto, claude, codex, ollama, mock)")
    p_con.add_argument("--competition", action="store_true", help="Execute Claude Code & OpenAI Codex concurrently with structured synthesis")
    p_con.add_argument("--adversarial", action="store_true", help="Execute Red/Blue adversarial arena architecture challenge")

    # debug
    p_dbg = subparsers.add_parser("debug", help="Diagnose a stubborn error or bug with Advisory Council")
    p_dbg.add_argument("error", nargs="?", default="", help="Error message or description")
    p_dbg.add_argument("--task", default="auto", choices=["auto", "architecture", "reasoning", "scraping", "browsing", "coding", "micro", "general"], help="Task profile override for efficiency-based model routing")
    p_dbg.add_argument("--context", default="", help="Code snippet or context")
    p_dbg.add_argument("--context-file", default="", help="Path to context file")
    p_dbg.add_argument("--engine", default="auto", help="Advisor engine override (e.g. auto, claude, codex, ollama, mock)")
    p_dbg.add_argument("--competition", action="store_true", help="Execute Claude Code & OpenAI Codex concurrently with structured synthesis")
    p_dbg.add_argument("--adversarial", action="store_true", help="Execute Red/Blue adversarial diagnosis")

    # gate
    p_gate = subparsers.add_parser("gate", help="Run full pre-commit verification (tsc + tests + diff review)")
    p_gate.add_argument("--engine", default="auto", help="Advisor engine override (e.g. auto, claude, codex, ollama, mock)")
    p_gate.add_argument("--competition", action="store_true", help="Execute Claude Code & OpenAI Codex concurrently with structured synthesis")
    p_gate.add_argument("--max-retries", type=int, default=1, help="Max self-healing retries for tsc/tests (default 1)")
    p_gate.add_argument("--timeout", type=int, default=240, help="Advisor signoff timeout in seconds (default 240)")
    p_gate.add_argument("--test-timeout", type=int, default=600, help="Test runner timeout in seconds (default 600)")
    p_gate.add_argument("--target", default="", help="Targeted test pattern (e.g. test_circuit.py)")
    p_gate.add_argument("--targeted", action="store_true", help="Auto-resolve targeted test pattern from changed files")
    p_gate.add_argument("--parallel", action="store_true", help="Execute test suite in parallel using pytest-xdist when available")
    p_gate.add_argument("--worktree", "-w", action="store_true", help="Execute pre-commit gate in an isolated ephemeral git worktree")
    p_gate.add_argument("--ref", default="HEAD", help="Git ref/branch/commit to base ephemeral worktree on (default: HEAD)")
    p_gate.add_argument("--apply-verified", action="store_true", help="Apply passing self-healing patches back to parent working tree")

    # bench
    p_bench = subparsers.add_parser("bench", help="Run benchmark harness to score review accuracy against known bugs")
    p_bench.add_argument("--suite", choices=["cases", "swebench"], default="cases", help="Benchmark suite ('cases' or 'swebench')")
    p_bench.add_argument("--cases-dir", default="", help="Path to cases directory (defaults to triad/bench/cases)")
    p_bench.add_argument("--engine", default="auto", help="Advisor engine override (e.g. auto, claude, codex, bare_single, mock)")
    p_bench.add_argument("--judge-engine", choices=["claude", "auto", "codex", "asymmetric"], default="claude", help="Judge engine (default: claude, then Codex if Claude cannot answer)")
    p_bench.add_argument("--docker", choices=["off", "auto", "on"], default="off", help="Repo-native tests in Docker when a local clone exists (default: off)")
    p_bench.add_argument("--workers", type=int, choices=[1, 2], default=2, help="Number of concurrent evaluation workers (1 or 2, default: 2)")
    p_bench.add_argument("--limit", type=int, default=0, help="Limit number of cases to test")
    p_bench.add_argument("--case", default="", help="Run single case ID (e.g. case_001 or astropy__astropy-12907)")
    p_bench.add_argument("--verbose", "-v", action="store_true", help="Print verbose review output")

    # worktree
    p_wt = subparsers.add_parser("worktree", help="Manage ephemeral git worktrees (create, remove, list, prune)")
    wt_sub = p_wt.add_subparsers(dest="wt_action", help="Worktree action")
    wt_sub.add_parser("list", help="List all active worktrees")
    p_wt_create = wt_sub.add_parser("create", help="Create a new isolated worktree")
    p_wt_create.add_argument("--ref", default="HEAD", help="Commit, branch, or tag (default HEAD)")
    p_wt_create.add_argument("--prefix", default="triad-work", help="Directory prefix")
    p_wt_remove = wt_sub.add_parser("remove", help="Remove an isolated worktree")
    p_wt_remove.add_argument("path", help="Path to worktree directory to remove")
    p_wt_remove.add_argument("--force", "-f", action="store_true", default=False, help="Force removal, including uncommitted changes")
    wt_sub.add_parser("prune", help="Prune orphaned worktree metadata")

    # hook
    p_hook = subparsers.add_parser("hook", help="Manage git hooks (install, uninstall, status)")
    hook_sub = p_hook.add_subparsers(dest="hook_action", help="Hook action")
    p_hook_install = hook_sub.add_parser("install", help="Install Triad pre-commit gate hook")
    p_hook_install.add_argument("--force", "-f", action="store_true", help="Force overwrite existing hook without backup")
    p_hook_uninstall = hook_sub.add_parser("uninstall", help="Uninstall Triad pre-commit gate hook")
    p_hook_uninstall.add_argument("--force", "-f", action="store_true", help="Force removal even if hook was modified")
    hook_sub.add_parser("status", help="Check pre-commit hook installation status")

    # listen / serve
    p_listen = subparsers.add_parser("listen", aliases=["serve"], help="Start Triad Ambient HTTP server daemon")
    p_listen.add_argument("--port", type=int, default=8789, help="HTTP daemon port (default 8789)")
    p_listen.add_argument("--host", default="127.0.0.1", help="HTTP daemon host (default 127.0.0.1)")

    # mesh / swarm
    p_mesh = subparsers.add_parser("mesh", aliases=["swarm"], help="Agent Mesh MCP coordination, status, and health supervision")
    p_mesh.add_argument("mesh_action", nargs="?", default="status", choices=["status", "doctor", "tools", "serve"], help="Mesh action (status, doctor, tools, serve)")
    p_mesh.add_argument("--origin", default="antigravity", help="Origin identity (antigravity, claude, codex, cursor, grok)")
    p_mesh.add_argument("--json", action="store_true", help="Output results in JSON format")

    # sync
    p_sync = subparsers.add_parser("sync", help="Synchronize runtime engine, launchers, skills, and multi-repo git hooks")
    p_sync.add_argument("component", nargs="?", default=None, choices=["engine", "launchers", "skills", "hooks", "all"], help="Optional single component to synchronize")
    p_sync.add_argument("--all", "-a", action="store_true", help="Synchronize all components (engine, launchers, skills, and install missing repo hooks)")
    p_sync.add_argument("--engine", action="store_true", help="Synchronize triad engine to ~/.agents/triad (verify/establish live junction)")
    p_sync.add_argument("--launchers", action="store_true", help="Synchronize triad CLI launchers to ~/.local/bin")
    p_sync.add_argument("--skills", action="store_true", help="Synchronize claude-advisor skill to ~/.agents/skills/claude-advisor")
    p_sync.add_argument("--hooks", action="store_true", help="Audit and install/update pre-commit hooks in active ecosystem repos")
    p_sync.add_argument("--dry-run", action="store_true", help="Preview synchronization actions without modifying filesystem")
    p_sync.add_argument("--check", action="store_true", help="Exit with code 2 if drift is detected in dry-run mode (useful for CI/gates)")
    p_sync.add_argument("--apply", action="store_true", help="Execute synchronization (overrides dry-run default from natural language)")
    p_sync.add_argument("--json", action="store_true", help="Output synchronization audit in structured JSON format")

    # rewrite / prompt
    p_rw = subparsers.add_parser(
        "rewrite",
        aliases=["prompt", "brief"],
        help="Expand a sparse prompt into a detailed agent brief (local/zero-cost; optional --llm polish)",
    )
    p_rw.add_argument("prompt", nargs="*", default=[], help="Raw prompt to expand (or pass via stdin)")
    p_rw.add_argument("--context", default="", help="Inline extra context")
    p_rw.add_argument("--context-file", default="", help="Path to context file")
    p_rw.add_argument("--diff-file", default="", help="Optional diff path (or - for stdin when prompt is on argv)")
    p_rw.add_argument("--constraint", action="append", default=[], help="Extra hard constraint (repeatable)")
    p_rw.add_argument(
        "--style",
        choices=["brief", "markdown", "compact"],
        default="brief",
        help="Output style (default: brief markdown)",
    )
    p_rw.add_argument("--json", action="store_true", help="Emit structured JSON instead of markdown")
    p_rw.add_argument("--plain", action="store_true", help="Omit the meta banner; print only the brief")
    p_rw.add_argument("-o", "--output", default="", help="Write result to a file instead of stdout")
    p_rw.add_argument("--llm", action="store_true", help="Optional paid polish pass via advisory council")
    p_rw.add_argument("--engine", default="auto", help="Engine for --llm polish (default auto)")

    # agent
    p_agent = subparsers.add_parser("agent", help="Launch interactive or single-shot autonomous zero-cost agent")
    p_agent.add_argument("-p", "--print", "--prompt", dest="prompt", type=str, default="", help="Run a single prompt non-interactively")
    p_agent.add_argument("-c", "--continue", dest="resume", action="store_true", help="Resume most recent conversation session")
    p_agent.add_argument("-y", "--auto", "--dangerously-skip-permissions", dest="auto_approve", action="store_true", help="Auto-approve tool modifications")
    p_agent.add_argument("--heavy", "--pro", dest="force_heavy", action="store_true", help="Force high-tier primary model (Claude 3.7 Sonnet / Codex)")
    p_agent.add_argument("--free", "--nous", dest="force_free", action="store_true", help="Force Nous Research cloud tier")
    p_agent.add_argument("--local", "--fast", dest="force_local", action="store_true", help="Force local llama-server (:8080)")
    p_agent.add_argument("--model", dest="model", type=str, default=None, help="Override Nous cloud model ID")
    p_agent.add_argument("--concise", dest="concise", action="store_true", help="Enable answer-first concise mode")

    return parser


def main():
    # Top-level intuitive auto-dispatch: if first arg is not a known command or flag and looks like natural language, route through auto
    known_commands = {
        "doctor", "review", "consult", "debug", "gate",
        "bench", "worktree", "auto", "intent", "run",
        "listen", "serve", "hook", "mesh", "swarm", "sync",
        "agent", "rewrite", "prompt", "brief",
        "-h", "--help"
    }
    known_sync_components = {"engine", "launchers", "skills", "hooks", "all"}
    if len(sys.argv) > 1:
        if sys.argv[1] == "sync" and len(sys.argv) > 2 and not sys.argv[2].startswith("-"):
            sub = sys.argv[2].lower()
            if sub in known_sync_components:
                sys.argv[2] = sub
            elif sub in ("status", "preview", "check", "audit"):
                sys.argv[2] = "--dry-run"
            elif sub in ("apply", "force"):
                sys.argv[2] = "--apply"
            else:
                sys.argv[1:] = ["auto", "triad " + " ".join(sys.argv[1:])]
        elif sys.argv[1] not in known_commands and not sys.argv[1].startswith("-"):
            if is_plausible_natural_language(sys.argv[1], len(sys.argv), known_commands):
                sys.argv.insert(1, "auto")

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "auto": cmd_auto,
        "intent": cmd_auto,
        "run": cmd_auto,
        "doctor": cmd_doctor,
        "review": cmd_review,
        "consult": cmd_consult,
        "debug": cmd_debug,
        "gate": cmd_gate,
        "bench": cmd_bench,
        "worktree": cmd_worktree,
        "hook": cmd_hook,
        "listen": cmd_listen,
        "serve": cmd_listen,
        "mesh": cmd_mesh,
        "swarm": cmd_mesh,
        "sync": cmd_sync,
        "agent": cmd_agent,
        "rewrite": cmd_rewrite,
        "prompt": cmd_rewrite,
        "brief": cmd_rewrite,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)

if __name__ == "__main__":
    sys.modules.setdefault("triad_engine", sys.modules[__name__])
    main()
