"""Ground-truth verification gate (`triad gate`)."""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    from triad.procutil import classify_advisor_response, strip_diff_bloat, is_doc_or_asset_file
    from triad.notifier import notify_event
except ImportError:
    from procutil import classify_advisor_response, strip_diff_bloat, is_doc_or_asset_file
    from notifier import notify_event

NPM_CMD = "npm.cmd" if os.name == "nt" else "npm"
NPX_CMD = "npx.cmd" if os.name == "nt" else "npx"


def _te():
    mod = sys.modules.get("triad.triad_engine") or sys.modules.get("triad_engine")
    if mod is None:
        try:
            from triad import triad_engine as mod
        except ImportError:
            import triad_engine as mod
    return mod


def _eng(name: str, fallback: Any) -> Any:
    mod = sys.modules.get("triad.triad_engine") or sys.modules.get("triad_engine")
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    return fallback


def _eng_call(name: str):
    return lambda *a, **kw: getattr(_te(), name)(*a, **kw)


_check_apply_verified_safety = _eng_call("_check_apply_verified_safety")
_content_matches = _eng_call("_content_matches")
_is_ci = _eng_call("_is_ci")
_normalize_target = _eng_call("_normalize_target")
_resolve_triage_route = _eng_call("_resolve_triage_route")
_run_in_isolated_worktree = _eng_call("_run_in_isolated_worktree")
_stage_candidate_worktree_changes = _eng_call("_stage_candidate_worktree_changes")
apply_patch_text = _eng_call("apply_patch_text")
compute_working_tree_fingerprint = _eng_call("compute_working_tree_fingerprint")
fingerprints_match = _eng_call("fingerprints_match")
get_empty_tree_oid = _eng_call("get_empty_tree_oid")
get_repo_root = _eng_call("get_repo_root")
get_tree_entries = _eng_call("get_tree_entries")
query_advisory_council = _eng_call("query_advisory_council")
query_gate_fix = _eng_call("query_gate_fix")
run_subprocess_tree_safe = _eng_call("run_subprocess_tree_safe")
run_subprocess_tree_safe_bytes = _eng_call("run_subprocess_tree_safe_bytes")
snapshot_worktree_tree = _eng_call("snapshot_worktree_tree")


def cmd_gate(args, env: Optional[Dict[str, str]] = None):
    """
    Ground-Truth Verification Gate with self-healing retry loop:
    1. TypeScript compilation (tsc --noEmit)
    2. Test suites (npm test, Python unittests)
    3. Advisory Council diff review & pre-commit signoff
    If Step 1 or Step 2 fails, queries Advisory Council in debug mode for surgical fix,
    applies patch via git apply, and retries up to --max-retries times.
    Supports isolated worktree execution via --worktree (-w).
    """
    try:
        repo_root = get_repo_root(".", env=env)
    except Exception as e:
        print(f"[Triad Gate Error] Not inside a git repository: {e}", file=sys.stderr)
        sys.exit(1)

    exec_env = os.environ if env is None else env
    _check_apply_verified_safety(args, exec_env)

    if getattr(args, "worktree", False):
        _run_in_isolated_worktree(
            args, env,
            repo_root=repo_root,
            prefix="triad-gate",
            require_index=True,
            runner=lambda a, e: _eng("_run_gate", _run_gate)(a, env=e, in_worktree=True, review_base=a._review_base),
            error_label="Triad Gate Error",
            phase_label="validation",
            nm_phase_label="gate validation",
            enforce_clean_explicit_ref=False,
            pause_commit_after_apply=True,
            notify_async=True,
        )
    else:
        _run_gate(args, env=env, in_worktree=False, cwd=Path(repo_root))

    active_pat = getattr(args, "_active_test_pattern", None)
    pat_detail = f" (targeted: {active_pat})" if active_pat and active_pat != "test_*.py" else ""
    notify_event("Pre-Commit Gate Passed", f"Type safety, test suites{pat_detail}, and Advisory Council review approved.", status="success", timeout=1.5, async_dispatch=True)


def _render_unittest_suite_runner(target_repr: str, patterns_repr: str, pattern_desc_repr: str) -> str:
    """Generate shared unittest discovery, test ID deduplication, and runner execution block."""
    return (
        "import unittest\n"
        "loader = unittest.defaultTestLoader\n"
        "suite = unittest.TestSuite()\n\n"
        "def _iter_tests(suite_or_case):\n"
        "    if hasattr(suite_or_case, '__iter__'):\n"
        "        for _s in suite_or_case:\n"
        "            yield from _iter_tests(_s)\n"
        "    else:\n"
        "        yield suite_or_case\n\n"
        "seen_ids = set()\n"
        "unmatched = []\n"
        f"for _pat in {patterns_repr}:\n"
        f"    _sub = loader.discover(start_dir={target_repr}, pattern=_pat)\n"
        "    _matched = False\n"
        "    for _case in _iter_tests(_sub):\n"
        "        _tid = getattr(_case, 'id', lambda: str(_case))()\n"
        "        if _tid not in seen_ids:\n"
        "            seen_ids.add(_tid)\n"
        "            suite.addTest(_case)\n"
        "            _matched = True\n"
        "    if not _matched:\n"
        "        unmatched.append(_pat)\n\n"
        "if suite.countTestCases() == 0:\n"
        f"    print('[Triad Test Error] No tests matched pattern(s) ' + {pattern_desc_repr} + ' in ' + {target_repr}, file=sys.stderr)\n"
        "    sys.exit(5)\n"
        "if unmatched:\n"
        f"    print('[Triad Test Warning] Pattern(s) with 0 matches in ' + {target_repr} + ': ' + ', '.join(unmatched), file=sys.stderr)\n\n"
        "runner = unittest.TextTestRunner(verbosity=2)\n"
        "result = runner.run(suite)\n"
        "sys.exit(0 if result.wasSuccessful() else 1)\n"
    )


def _build_python_isolation_script(cwd: Path, py_test_target: str, excluded_roots: List[Path], pattern: Union[str, List[str], Set[str]] = "test_*.py") -> str:
    """Generate isolation script for running Python tests in worktree without leaking parent or originating checkouts."""
    if isinstance(pattern, str):
        if "," in pattern:
            patterns = [p.strip() for p in pattern.split(",") if p.strip()]
        else:
            patterns = [pattern.strip()]
    elif isinstance(pattern, (list, tuple, set)):
        patterns = [str(p).strip() for p in pattern if str(p).strip()]
    else:
        patterns = ["test_*.py"]
    if not patterns:
        patterns = ["test_*.py"]

    excluded_roots_repr = repr([str(r.resolve()) for r in excluded_roots])
    cwd_root_repr = repr(str(cwd.resolve()))
    test_target_repr = repr(py_test_target)
    patterns_repr = repr(patterns)
    pattern_desc_repr = repr(", ".join(patterns))
    return (
        "import sys\n\n"
        f"_ex_roots_raw = tuple({excluded_roots_repr})\n"
        f"_cwd_root_raw = {cwd_root_repr}\n\n"
        "def _norm_path(p):\n"
        "    if not p:\n"
        "        return ''\n"
        "    p = p.replace('\\\\', '/').rstrip('/')\n"
        "    return p.lower() if sys.platform == 'win32' else p\n\n"
        "_ex_norms = tuple(_norm_path(r) for r in _ex_roots_raw if _norm_path(r))\n"
        "_cwd_norm = _norm_path(_cwd_root_raw)\n\n"
        "def _is_boot_venv(p):\n"
        "    np = _norm_path(p)\n"
        "    if '/site-packages' not in np and '/dist-packages' not in np:\n"
        "        return False\n"
        "    import os\n"
        "    cur = p\n"
        "    for _ in range(10):\n"
        "        if os.path.isfile(os.path.join(cur, 'pyvenv.cfg')):\n"
        "            return True\n"
        "        parent = os.path.dirname(cur)\n"
        "        if parent == cur:\n"
        "            break\n"
        "        cur = parent\n"
        "    return False\n\n"
        "_boot_path = []\n"
        "for _p in sys.path:\n"
        "    if not _p:\n"
        "        continue\n"
        "    _np = _norm_path(_p)\n"
        "    if (_np == _cwd_norm) or (_cwd_norm and _np.startswith(_cwd_norm + '/')):\n"
        "        _boot_path.append(_p)\n"
        "    elif any(_np == _ex or _np.startswith(_ex + '/') for _ex in _ex_norms):\n"
        "        if _is_boot_venv(_p):\n"
        "            _boot_path.append(_p)\n"
        "        else:\n"
        "            continue\n"
        "    else:\n"
        "        _boot_path.append(_p)\n"
        "sys.path = [_cwd_root_raw] + [p for p in _boot_path if _norm_path(p) != _cwd_norm]\n\n"
        "import os, pathlib, site, sysconfig\n\n"
        f"excluded_roots = [pathlib.Path(p).resolve() for p in {excluded_roots_repr}]\n"
        f"cwd_root = pathlib.Path({cwd_root_repr}).resolve()\n\n"
        "allowed_dep_dirs = set()\n"
        "try:\n"
        "    for p in site.getsitepackages():\n"
        "        allowed_dep_dirs.add(pathlib.Path(p).resolve())\n"
        "except Exception:\n"
        "    pass\n"
        "try:\n"
        "    usp = site.getusersitepackages()\n"
        "    if usp:\n"
        "        allowed_dep_dirs.add(pathlib.Path(usp).resolve())\n"
        "except Exception:\n"
        "    pass\n"
        "try:\n"
        "    for k in ('stdlib', 'platstdlib', 'purelib', 'platlib'):\n"
        "        pth = sysconfig.get_path(k)\n"
        "        if pth:\n"
        "            allowed_dep_dirs.add(pathlib.Path(pth).resolve())\n"
        "except Exception:\n"
        "    pass\n"
        "def _is_allowed_dep(p: pathlib.Path) -> bool:\n"
        "    if any(dep == p or dep in p.parents for dep in allowed_dep_dirs):\n"
        "        return True\n"
        "    for a in [p] + list(p.parents):\n"
        "        if a.name in ('site-packages', 'dist-packages') and any((v / 'pyvenv.cfg').is_file() for v in a.parents):\n"
        "            return True\n"
        "    return False\n\n"
        "for mod_name, mod in list(sys.modules.items()):\n"
        "    if mod is None:\n"
        "        continue\n"
        "    try:\n"
        "        f = getattr(mod, '__file__', None)\n"
        "        spec = getattr(mod, '__spec__', None)\n"
        "        origin = getattr(spec, 'origin', None) if spec else None\n"
        "        cand = f or origin\n"
        "        if cand and cand not in ('built-in', 'frozen'):\n"
        "            cp = pathlib.Path(cand).resolve()\n"
        "            if cp.is_absolute():\n"
        "                is_venv = _is_allowed_dep(cp)\n"
        "                if not is_venv:\n"
        "                    for ex in excluded_roots:\n"
        "                        if (cp == ex or ex in cp.parents) and not (cp == cwd_root or cwd_root in cp.parents):\n"
        "                            sys.modules.pop(mod_name, None)\n"
        "                            break\n"
        "        if mod_name in sys.modules and hasattr(mod, '__path__'):\n"
        "            for loc in (getattr(mod, '__path__', None) or []):\n"
        "                try:\n"
        "                    lp = pathlib.Path(loc).resolve()\n"
        "                    if lp.is_absolute():\n"
        "                        is_venv = _is_allowed_dep(lp)\n"
        "                        if not is_venv:\n"
        "                            for ex in excluded_roots:\n"
        "                                if (lp == ex or ex in lp.parents) and not (lp == cwd_root or cwd_root in lp.parents):\n"
        "                                    sys.modules.pop(mod_name, None)\n"
        "                                    break\n"
        "                except Exception:\n"
        "                    pass\n"
        "                if mod_name not in sys.modules:\n"
        "                    break\n"
        "    except Exception:\n"
        "        pass\n\n"
        "filtered = []\n"
        "for p in sys.path:\n"
        "    if not p:\n"
        "        continue\n"
        "    try:\n"
        "        rp = pathlib.Path(p).resolve()\n"
        "        is_venv_dep = _is_allowed_dep(rp)\n"
        "        is_excluded = any(rp == ex or ex in rp.parents for ex in excluded_roots)\n"
        "        if is_excluded and not (rp == cwd_root or cwd_root in rp.parents) and not is_venv_dep:\n"
        "            continue\n"
        "    except Exception:\n"
        "        pass\n"
        "    filtered.append(p)\n"
        "sys.path = [str(cwd_root)] + [p for p in filtered if p != str(cwd_root)]\n\n"
        "class _IsolatingFinder:\n"
        "    def __init__(self, original_finder):\n"
        "        self._orig = original_finder\n\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if not hasattr(self._orig, 'find_spec'):\n"
        "            return None\n"
        "        spec = self._orig.find_spec(fullname, path, target)\n"
        "        if spec is None:\n"
        "            return None\n"
        "        if spec.origin and spec.origin not in ('built-in', 'frozen'):\n"
        "            try:\n"
        "                op = pathlib.Path(spec.origin).resolve()\n"
        "                if op.is_absolute():\n"
        "                    is_venv = _is_allowed_dep(op)\n"
        "                    if not is_venv:\n"
        "                        for ex in excluded_roots:\n"
        "                            if (op == ex or ex in op.parents):\n"
        "                                if not (op == cwd_root or cwd_root in op.parents):\n"
        "                                    return None\n"
        "            except Exception:\n"
        "                pass\n"
        "        if getattr(spec, 'submodule_search_locations', None):\n"
        "            valid_locs = []\n"
        "            for loc in spec.submodule_search_locations:\n"
        "                try:\n"
        "                    lp = pathlib.Path(loc).resolve()\n"
        "                    if lp.is_absolute():\n"
        "                        is_venv = _is_allowed_dep(lp)\n"
        "                        if not is_venv:\n"
        "                            blocked = False\n"
        "                            for ex in excluded_roots:\n"
        "                                if (lp == ex or ex in lp.parents):\n"
        "                                    if not (lp == cwd_root or cwd_root in lp.parents):\n"
        "                                        blocked = True\n"
        "                                        break\n"
        "                            if blocked:\n"
        "                                continue\n"
        "                except Exception:\n"
        "                    pass\n"
        "                valid_locs.append(loc)\n"
        "            if not valid_locs and spec.submodule_search_locations:\n"
        "                return None\n"
        "            spec.submodule_search_locations = valid_locs\n"
        "        return spec\n\n"
        "    def find_module(self, fullname, path=None):\n"
        "        if not hasattr(self._orig, 'find_module'):\n"
        "            return None\n"
        "        loader = self._orig.find_module(fullname, path)\n"
        "        if loader is None:\n"
        "            return None\n"
        "        if hasattr(loader, 'get_filename'):\n"
        "            try:\n"
        "                fn = loader.get_filename(fullname)\n"
        "                if fn:\n"
        "                    op = pathlib.Path(fn).resolve()\n"
        "                    if op.is_absolute():\n"
        "                        is_venv = any(seg.lower() in ('site-packages', 'dist-packages') for seg in op.parts)\n"
        "                        if not is_venv:\n"
        "                            for ex in excluded_roots:\n"
        "                                if (op == ex or ex in op.parents):\n"
        "                                    if not (op == cwd_root or cwd_root in op.parents):\n"
        "                                        return None\n"
        "            except Exception:\n"
        "                pass\n"
        "        return loader\n\n"
        "    def invalidate_caches(self):\n"
        "        if hasattr(self._orig, 'invalidate_caches'):\n"
        "            self._orig.invalidate_caches()\n\n"
        "    def __getattr__(self, name):\n"
        "        return getattr(self._orig, name)\n\n"
        "sys.meta_path = [_IsolatingFinder(f) for f in sys.meta_path if not isinstance(f, _IsolatingFinder)]\n\n"
    ) + _render_unittest_suite_runner(test_target_repr, patterns_repr, pattern_desc_repr)


def _build_python_multi_pattern_script(cwd: Path, py_test_target: str, patterns: List[str]) -> str:
    """Generate simple multi-pattern discovery script for local non-worktree test execution."""
    patterns_repr = repr(patterns)
    target_repr = repr(py_test_target)
    pattern_desc_repr = repr(", ".join(patterns))
    return "import sys\n" + _render_unittest_suite_runner(target_repr, patterns_repr, pattern_desc_repr)


IGNORED_SOURCE_DEPENDENCY_DIR_NAMES = {
    "node_modules", ".venv", "venv", "env", ".git", ".pytest_cache",
    "__pycache__", "build", "dist", ".next", ".turbo", ".tox",
    ".cache", ".mypy_cache", ".ruff_cache", ".claude", ".cursor",
    ".vscode", ".idea", ".vercel", ".hermes", "supabase", ".temp",
    "android", "ios", "capacitor", "logs"
}
SOURCE_DEPENDENCY_EXTENSIONS = (
    ".py", ".ts", ".js", ".tsx", ".jsx", ".json", ".env",
    ".mjs", ".cjs", ".mts", ".cts", ".pyi"
)


def _check_no_uncommitted_source_dependencies(cwd: Path, exec_env: dict, in_worktree: bool = False, stage_name: str = "validation"):
    """
    Ensure no uncommitted or untracked source dependencies exist that could allow tests to pass
    falsely on uncommitted local files instead of the committed candidate tree.
    Uses NUL-terminated byte parsing (-z) to accurately handle spaces, special characters, and non-ASCII paths.
    """
    # 1. Untracked files
    ret, untracked_bytes, err_untracked = run_subprocess_tree_safe_bytes(
        ["git", "ls-files", "-z", "--others", "--exclude-standard"],
        cwd=cwd, env=exec_env
    )
    if ret != 0:
        err_msg = os.fsdecode(err_untracked).strip() if err_untracked else "Unknown git ls-files error"
        print(f"\n❌ [Triad Gate Error] Failed to enumerate untracked files: {err_msg}", file=sys.stderr)
        sys.exit(1)

    untracked_entries = [os.fsdecode(e) for e in untracked_bytes.split(b"\0") if e]
    untracked_list = [f for f in untracked_entries if not (f == ".git" or f.startswith(".git/"))]

    if untracked_list:
        if not in_worktree:
            print("\n❌ [Triad Gate BLOCKED] Untracked files present in working directory outside isolation:\n" + "\n".join(untracked_list), file=sys.stderr)
            print("Direct gate validation cannot certify the staged index when untracked files exist (tests could pass via uncommitted dependencies).", file=sys.stderr)
            print("Run with 'triad gate --worktree' for isolated ephemeral verification, or stage/ignore the untracked files.", file=sys.stderr)
            sys.exit(1)
        else:
            # In isolated worktree: block if untracked source files or dependencies were created
            untracked_sources = []
            for f in untracked_list:
                p_parts = Path(f).parts
                if any(part in IGNORED_SOURCE_DEPENDENCY_DIR_NAMES for part in p_parts[:-1]):
                    continue
                if f.endswith(SOURCE_DEPENDENCY_EXTENSIONS):
                    untracked_sources.append(f)
            if untracked_sources:
                print(f"\n❌ [Triad Gate BLOCKED] Untracked source files present in isolated worktree ({stage_name}):\n" + "\n".join(f"  - {f}" for f in untracked_sources[:10]), file=sys.stderr)
                print("Gate validation cannot certify the candidate tree when untracked source dependencies exist.", file=sys.stderr)
                sys.exit(1)

    # 2. Ignored files
    ret_ig, ignored_bytes, err_ignored = run_subprocess_tree_safe_bytes(
        ["git", "ls-files", "-z", "--others", "--ignored", "--exclude-standard"],
        cwd=cwd, env=exec_env
    )
    if ret_ig != 0:
        err_msg = os.fsdecode(err_ignored).strip() if err_ignored else "Unknown git ls-files error"
        print(f"\n❌ [Triad Gate Error] Failed to enumerate ignored files: {err_msg}", file=sys.stderr)
        sys.exit(1)

    ignored_entries = [os.fsdecode(e) for e in ignored_bytes.split(b"\0") if e]
    ignored_list = [f for f in ignored_entries if not (f == ".git" or f.startswith(".git/"))]

    if ignored_list:
        potential_deps = []
        for f in ignored_list:
            p_parts = Path(f).parts
            if any(part in IGNORED_SOURCE_DEPENDENCY_DIR_NAMES for part in p_parts[:-1]):
                continue
            if f.endswith(SOURCE_DEPENDENCY_EXTENSIONS):
                potential_deps.append(f)
        if potential_deps:
            env_desc = "isolated worktree" if in_worktree else "working directory outside isolation"
            print(f"\n❌ [Triad Gate BLOCKED] Ignored uncommitted source files present in {env_desc} ({stage_name}):\n" + "\n".join(f"  - {f}" for f in potential_deps[:10]), file=sys.stderr)
            print("Gate validation cannot certify the candidate tree when ignored source files exist (tests could pass via uncommitted dependencies).", file=sys.stderr)
            sys.exit(1)


def _clean_worktree_retry_artifacts(cwd: Path, candidate_tree: str, exec_env: dict) -> bool:
    """Reset tracked files and clean untracked/ignored validator side-effects between retries."""
    ret1, _, _ = run_subprocess_tree_safe(["git", "read-tree", "-u", "--reset", candidate_tree], cwd=cwd, env=exec_env)
    ret2, _, _ = run_subprocess_tree_safe(["git", "clean", "-fdx", "-e", "node_modules", "-e", "node_modules/**", "-e", ".venv", "-e", "venv"], cwd=cwd, env=exec_env)
    return ret1 == 0 and ret2 == 0


def _verify_checkout_representation(
    cwd: Path,
    candidate_tree: str,
    exec_env: Optional[Dict[str, str]] = None
) -> List[str]:
    """
    Certifies that every tracked file in candidate_tree matches its expected checkout representation.
    - Uses NUL-delimited get_tree_entries() to handle non-ASCII, spaces, tabs, and special characters.
    - Branches on Git mode:
      * Mode 120000 (symlink): verifies is_symlink() and compares os.readlink() target against the blob.
      * Mode 100644 / 100755 (regular file): verifies is_file() and not is_symlink(), compares file bytes
        against 'git cat-file --filters <candidate_tree>:<rel_path>' (accounting for smudge/clean filters),
        and verifies executable permissions / Git index mode parity across POSIX and Windows.
    - Fails closed: raises RuntimeError or reports mismatch on any inspection failure or cat-file error.
    Returns list of mismatch description strings (empty if 100% certified).
    """
    try:
        entries = get_tree_entries(candidate_tree, cwd, env=exec_env)
    except Exception as e:
        return [f"! Failed to enumerate tree {candidate_tree}: {e}"]

    # Query index stage modes to verify mode changes when core.fileMode=false
    stage_modes: Dict[str, str] = {}
    ret_st, out_st, _ = run_subprocess_tree_safe_bytes(["git", "ls-files", "-z", "--stage"], cwd=cwd, env=exec_env)
    if ret_st == 0 and out_st:
        for entry in out_st.split(b"\x00"):
            if not entry:
                continue
            try:
                meta, path_b = entry.split(b"\t", 1)
                st_mode_str = meta.split(b" ")[0].decode("ascii", errors="replace")
                stage_modes[os.fsdecode(path_b)] = st_mode_str
            except Exception:
                pass

    mismatches = []
    for rel_path, (mode, obj_type, sha) in entries.items():
        file_path = cwd / rel_path

        if mode == "160000" or obj_type == "commit":
            # Submodule / gitlink certification
            if not file_path.is_dir():
                mismatches.append(f"M\t{rel_path} (submodule directory missing)")
                continue
            ret_sub, sub_head, err_sub = run_subprocess_tree_safe(["git", "-C", str(file_path), "rev-parse", "HEAD"], cwd=cwd, env=exec_env)
            if ret_sub != 0 or not sub_head.strip():
                mismatches.append(f"M\t{rel_path} (submodule rev-parse failed: {err_sub.strip()})")
                continue
            if sub_head.strip() != sha.strip():
                mismatches.append(f"M\t{rel_path} (submodule commit mismatch: {sub_head.strip()} != {sha.strip()})")
                continue
            ret_stat, out_stat, err_stat = run_subprocess_tree_safe(["git", "-C", str(file_path), "status", "--porcelain"], cwd=cwd, env=exec_env)
            if ret_stat != 0:
                mismatches.append(f"M\t{rel_path} (submodule status inspection failed: {err_stat.strip()})")
                continue
            if out_stat.strip():
                mismatches.append(f"M\t{rel_path} (submodule working tree has uncommitted modifications)")
            continue

        if obj_type != "blob":
            continue

        if mode == "120000":
            # Symlink certification
            if not file_path.is_symlink():
                mismatches.append(f"M\t{rel_path} (expected symlink)")
                continue

            ret_cat, exp_target_bytes, err = run_subprocess_tree_safe_bytes(
                ["git", "cat-file", "blob", sha],
                cwd=cwd, env=exec_env
            )
            if ret_cat != 0:
                mismatches.append(f"! Failed to inspect symlink target for {rel_path}: {err}")
                continue

            try:
                actual_target = os.readlink(str(file_path))
                expected_target = os.fsdecode(exp_target_bytes)
                if actual_target != expected_target:
                    mismatches.append(f"M\t{rel_path} (symlink target mismatch: {actual_target} != {expected_target})")
            except Exception as e:
                mismatches.append(f"M\t{rel_path} (symlink read error: {e})")

        elif mode in ("100644", "100755"):
            # Regular file certification
            if file_path.is_symlink():
                mismatches.append(f"M\t{rel_path} (expected regular file, found symlink)")
                continue
            if not file_path.is_file():
                mismatches.append(f"D\t{rel_path}")
                continue

            # Verify executable mode parity
            if os.name != "nt":
                try:
                    st = os.lstat(str(file_path))
                    is_exec = (st.st_mode & 0o111) != 0
                    if mode == "100755" and not is_exec:
                        mismatches.append(f"M\t{rel_path} (mode mismatch: expected executable 100755, file is not executable)")
                    elif mode == "100644" and is_exec:
                        mismatches.append(f"M\t{rel_path} (mode mismatch: expected non-executable 100644, file is executable)")
                except Exception as e:
                    mismatches.append(f"M\t{rel_path} (mode inspection error: {e})")
            else:
                # Windows handling: check stage mode recorded in index when core.fileMode=false
                if rel_path in stage_modes and stage_modes[rel_path] != mode:
                    mismatches.append(f"M\t{rel_path} (mode mismatch: index has {stage_modes[rel_path]}, candidate tree has {mode})")

            ret_cat, exp_bytes, err = run_subprocess_tree_safe_bytes(
                ["git", "cat-file", "--filters", f"{candidate_tree}:{rel_path}"],
                cwd=cwd, env=exec_env
            )
            if ret_cat != 0:
                mismatches.append(f"! Failed to get expected checkout bytes for {rel_path}: {err}")
                continue

            try:
                cur_bytes = file_path.read_bytes()
                if not _content_matches(cur_bytes, exp_bytes):
                    mismatches.append(f"M\t{rel_path}")
            except Exception as e:
                mismatches.append(f"M\t{rel_path} (read error: {e})")

    return mismatches


PROPOSED_FIX_PATCH_NAME = "triad-review/triad_proposed_fix.patch"


def write_proposed_fix_patch(repo_root: Path, text: str) -> Optional[Path]:
    """Persist an advisor-proposed fix under the repo's git dir (never the working tree).

    The destination is ``<git dir>/triad-review/triad_proposed_fix.patch``. The data is written to an
    exclusively-created temp file (O_EXCL|O_NOFOLLOW) in the same directory and moved into
    place with ``os.replace``, so a pre-planted symlink at the destination is replaced
    rather than followed. Returns the path, or None if the git dir cannot be resolved.
    """
    ret, out, _ = run_subprocess_tree_safe(["git", "rev-parse", "--git-path", PROPOSED_FIX_PATCH_NAME], cwd=repo_root)
    if ret != 0 or not out.strip():
        return None
    dest = Path(out.strip())
    if not dest.is_absolute():
        dest = Path(repo_root) / dest
    dest = dest.parent.resolve() / dest.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{uuid.uuid4().hex[:8]}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(str(tmp), flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
        os.replace(str(tmp), str(dest))
    except BaseException:
        try:
            os.unlink(str(tmp))
        except OSError:
            pass
        raise
    return dest


def _handle_validation_failure(
    *,
    stage_label: str,
    exhausted_label: str,
    diag_output: str,
    cwd: Path,
    exec_env: Dict[str, str],
    args,
    in_worktree: bool,
    candidate_tree: str,
    attempt: int,
    max_retries: int,
) -> Tuple[int, str]:
    """
    Shared self-healing path for a failed validation stage (tsc / npm test / python tests).

    Behaviour:
      * In an isolated worktree, validator side-effects are rolled back to ``candidate_tree``
        first so a retry starts from a clean baseline.
      * If the retry budget is exhausted the gate fails closed (exit 1).
      * Otherwise the Advisory Council is asked for a surgical unified diff.
          - Direct (non-worktree) execution never mutates the user's files: the proposed
            patch is persisted to ``<git dir>/triad-review/triad_proposed_fix.patch``
            and the gate exits 1.
          - Worktree execution applies the patch, stages it, records it in
            ``args._self_healed_patches`` and returns the new ``(attempt, candidate_tree)``
            so the caller can restart the validation sequence.
    """
    if in_worktree:
        if not _clean_worktree_retry_artifacts(cwd, candidate_tree, exec_env):
            print("\n❌ [Triad Gate Error] Failed to restore worktree baseline before retry.", file=sys.stderr)
            sys.exit(1)

    print(f"\n❌ [Triad Gate: {stage_label}:\n{diag_output}")

    if attempt >= max_retries:
        print(f"\n❌ [Triad Gate FAILED] {exhausted_label}")
        sys.exit(1)

    attempt += 1
    print(f"\n[Self-Healing Safety Net: Retry {attempt}/{max_retries}] Consulting Advisory Council in debug mode for surgical fix...")
    advisor_fix = query_gate_fix(diag_output, args)
    print(f"[Advisory Council Proposed Fix]:\n{advisor_fix}\n")

    if not in_worktree:
        patch_file = None
        try:
            patch_file = write_proposed_fix_patch(cwd, advisor_fix)
        except Exception:
            patch_file = None
        if patch_file is not None:
            print(f"\n[Triad Direct Execution Notice] Self-healing fix proposed by Advisory Council persisted to:\n  {patch_file}")
        else:
            print("\n[Triad Direct Execution Notice] Could not persist the proposed fix under the git directory; see the output above.")
        print("Direct execution preserves working directory files without uncoordinated in-place mutation.")
        if patch_file is not None:
            print(f"To review or apply the fix: git apply \"{patch_file}\"")
        print("Or run with 'triad gate --worktree --apply-verified' for isolated verification and atomic application.")
        sys.exit(1)

    if not apply_patch_text(advisor_fix, cwd=cwd, env=exec_env, allow_3way=True):
        print("! Could not automatically apply patch via git apply. Aborting gate.")
        sys.exit(1)

    try:
        _stage_candidate_worktree_changes(cwd=cwd, exec_env=exec_env, head_tree=candidate_tree)
    except Exception as stage_err:
        print(f"\n❌ [Triad Gate Error] Failed to stage healed changes: {stage_err}", file=sys.stderr)
        sys.exit(1)
    if hasattr(args, "_self_healed_patches"):
        args._self_healed_patches.append(advisor_fix)
    ret_tr, new_tree, _ = run_subprocess_tree_safe(["git", "write-tree"], cwd=cwd, env=exec_env)
    if ret_tr == 0 and new_tree.strip():
        candidate_tree = new_tree.strip()
    print("✓ Applied advisory patch to worktree. Restarting validation sequence...\n")
    return attempt, candidate_tree


def _affects_typescript(changed_files: List[str]) -> bool:
    ts_exts = frozenset({".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"})
    ts_configs = frozenset({"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock"})
    for f in changed_files:
        p = f.replace("\\", "/").lower()
        base = os.path.basename(p)
        if base in ts_configs or (base.startswith("tsconfig") and base.endswith(".json")):
            return True
        if base.endswith(".d.ts"):
            return True
        _, ext = os.path.splitext(base)
        if ext in ts_exts:
            return True
    return False


def _affects_code(changed_files: List[str]) -> bool:
    for f in changed_files:
        if not is_doc_or_asset_file(f):
            return True
    return False


CORE_MODULE_NAMES = {
    "triad_engine",
    "worktree",
    "paths",
    "server",
    "intent_engine",
    "competition",
    "circuit",
    "advisor_manager",
}


BUILD_MANIFEST_NAMES = {
    "pyproject.toml", "uv.lock", "setup.py", "setup.cfg", "tox.ini", "pytest.ini",
    "conftest.py", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "bun.lockb", "Pipfile", "Pipfile.lock",
}


SKIP_IMPORT_INDEX_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "site-packages", ".eggs",
}


_FILE_IMPORT_CACHE: Dict[str, Tuple[int, int, Set[str]]] = {}
_MAX_FILE_IMPORT_CACHE_ENTRIES = 5000


def _clear_import_index_caches() -> None:
    """Clear both the repository aggregate cache and file-level AST token cache."""
    _import_index.cache_clear()
    _FILE_IMPORT_CACHE.clear()


@lru_cache(maxsize=8)
def _import_index(cwd_resolved: Path) -> Optional[Dict[str, Set[str]]]:
    """
    Build index mapping imported module name to set of importing file relative paths across repository.
    Scans repository via AST parsing with per-file mtime invalidation (conservative fallback on parse or read error).
    """
    imported_to_callers: Dict[str, Set[str]] = {}
    for root, dirs, files in os.walk(str(cwd_resolved)):
        rel_root = os.path.relpath(root, str(cwd_resolved)).replace("\\", "/")
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_IMPORT_INDEX_DIRS
            and not (rel_root == "." and d in (".cursor", ".next", ".turbo"))
            and not ((rel_root == ".triad" or rel_root.startswith(".triad/")) and d == "worktrees")
            and not (Path(root) / d / "pyvenv.cfg").exists()
        ]
        for f in files:
            if not f.endswith(".py"):
                continue
            p = Path(root) / f
            try:
                rel = p.relative_to(cwd_resolved)
            except ValueError:
                rel = p
            rel_str = str(rel).replace("\\", "/")

            p_str = str(p)
            try:
                st = p.stat()
                mtime_ns = st.st_mtime_ns
                size = st.st_size
            except OSError:
                return None  # conservative fallback -> caller treats as "has importers"

            cached = _FILE_IMPORT_CACHE.get(p_str)
            if cached is not None and cached[0] == mtime_ns and cached[1] == size:
                file_tokens = cached[2]
            else:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    tree = ast.parse(content)
                    file_tokens = set()
                    for n in ast.walk(tree):
                        if isinstance(n, ast.Import):
                            for a in n.names:
                                for part in a.name.split("."):
                                    file_tokens.add(part)
                        elif isinstance(n, ast.ImportFrom):
                            if n.module:
                                for part in n.module.split("."):
                                    file_tokens.add(part)
                            for a in n.names:
                                file_tokens.add(a.name)
                        elif isinstance(n, ast.Call):
                            func_id = ""
                            if isinstance(n.func, ast.Name):
                                func_id = n.func.id
                            elif isinstance(n.func, ast.Attribute):
                                func_id = n.func.attr
                            if func_id in ("import_module", "__import__") and n.args:
                                for c in ast.walk(n.args[0]):
                                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                                        for part in re.findall(r"[A-Za-z_]\w*", c.value):
                                            file_tokens.add(part)
                        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and 0 < len(n.value) < 200:
                            v = n.value.replace("\\", "/")
                            file_tokens.add(v)
                            file_tokens.add(v.rsplit("/", 1)[-1])
                            for match in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b", n.value):
                                for part in match.split("."):
                                    file_tokens.add(part)
                    if len(_FILE_IMPORT_CACHE) >= _MAX_FILE_IMPORT_CACHE_ENTRIES:
                        _FILE_IMPORT_CACHE.clear()
                    _FILE_IMPORT_CACHE[p_str] = (mtime_ns, size, file_tokens)
                except (SyntaxError, ValueError, RecursionError):
                    file_tokens = set()
                    for tok in set(re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", content)):
                        for part in tok.split("."):
                            file_tokens.add(part)
                    if len(_FILE_IMPORT_CACHE) >= _MAX_FILE_IMPORT_CACHE_ENTRIES:
                        _FILE_IMPORT_CACHE.clear()
                    _FILE_IMPORT_CACHE[p_str] = (mtime_ns, size, file_tokens)
                except OSError:
                    return None

            for tok in file_tokens:
                imported_to_callers.setdefault(tok, set()).add(rel_str)

    return imported_to_callers


def _has_importers(name: str, cwd: Path) -> bool:
    """
    Check if any Python module other than the module itself and its dedicated unit test imports this module.
    """
    idx = _import_index(cwd.resolve())
    if idx is None:
        return True  # conservative fallback on unparseable/error repository
    callers = idx.get(name, set())
    own = {
        f"triad/{name}.py", f"{name}.py",
        f"triad/tests/test_{name}.py", f"tests/test_{name}.py",
    }
    for caller_rel in callers:
        norm_caller = caller_rel.replace("\\", "/")
        if norm_caller.startswith("./"):
            norm_caller = norm_caller[2:]
        if norm_caller not in own:
            return True

    # Check if entrypoints, manifests, or CI workflows reference this module name
    manifest_paths = [cwd / m for m in BUILD_MANIFEST_NAMES]
    wf_dir = cwd / ".github" / "workflows"
    if wf_dir.exists():
        manifest_paths.extend(wf_dir.glob("*.yml"))
        manifest_paths.extend(wf_dir.glob("*.yaml"))
    pat = re.compile(rf"\b{re.escape(name)}\b")
    for mp in manifest_paths:
        if mp.exists() and mp.is_file():
            try:
                txt = mp.read_text(encoding="utf-8", errors="ignore")
                if pat.search(txt):
                    return True
            except OSError:
                pass

    return False


def _resolve_targeted_test_pattern(changed_files: List[str], cwd: Path) -> str:
    """Resolve targeted test pattern from changed files, falling back to 'test_*.py' for core/imported files or ambiguity."""
    if not changed_files:
        return "test_*.py"
    matched_patterns = set()
    for f in changed_files:
        norm = f.replace("\\", "/")
        base = os.path.basename(norm)
        name, ext = os.path.splitext(base)

        # 1. Core infrastructure or build manifest files MUST trigger full test suite
        if name in CORE_MODULE_NAMES or base in BUILD_MANIFEST_NAMES or base.startswith("requirements"):
            return "test_*.py"

        # 2. Test file itself modified
        if base.startswith("test_") and ext == ".py":
            matched_patterns.add(base)
            continue

        # 3. Documentation or non-code assets
        if is_doc_or_asset_file(norm):
            if _has_importers(name, cwd) or _has_importers(base, cwd):
                return "test_*.py"
            # Pure documentation files can be safely skipped
            if ext.lower() in (".md", ".txt", ".rst"):
                continue
            # Any other non-pure-doc asset (e.g. .json, .yaml, .png, templates) triggers full suite
            return "test_*.py"

        # 4. Only Python source files can resolve to targeted Python tests
        if ext != ".py":
            return "test_*.py"

        # 5. If any other module or external test imports this module, partial testing is unsound
        if _has_importers(name, cwd):
            return "test_*.py"

        candidate_name = f"test_{name}.py"
        if (cwd / "triad" / "tests" / candidate_name).exists() or (cwd / "tests" / candidate_name).exists():
            matched_patterns.add(candidate_name)
        else:
            return "test_*.py"

    if matched_patterns:
        return ",".join(sorted(matched_patterns))
    return "test_*.py"


def _resolve_gate_python(cwd: Optional[Path] = None, extra_roots: Optional[List[Optional[Union[Path, str]]]] = None) -> str:
    """Prefer a repo-local .venv Python over sys.executable (e.g., Windows Store Python during git hooks)."""
    roots: List[Path] = []
    for candidate_root in [cwd, *(extra_roots or [])]:
        if candidate_root is None:
            continue
        p = Path(candidate_root)
        if p not in roots:
            roots.append(p)
    rel_bins = ("Scripts/python.exe", "bin/python") if os.name == "nt" else ("bin/python", "Scripts/python.exe")
    for root in roots:
        for rel in rel_bins:
            exe = root / ".venv" / rel
            if exe.is_file():
                try:
                    ret, _, _ = run_subprocess_tree_safe([str(exe), "-c", "0"], cwd=root, timeout=5)
                    if ret == 0:
                        return str(exe)
                except Exception:
                    continue
    return sys.executable


def _resolve_pytest_xdist_cmd(
    target: str,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    python_exe: Optional[str] = None,
) -> Optional[List[str]]:
    """Determine if pytest with xdist is available in current python environment or uv."""
    py = python_exe or _resolve_gate_python(cwd)
    try:
        ret, _, _ = run_subprocess_tree_safe([py, "-c", "import pytest, xdist"], cwd=cwd, env=env, timeout=5)
        if ret == 0:
            return [py, "-m", "pytest", "-n", "auto", "--dist=loadfile", "-p", "no:cacheprovider", target]
    except Exception:
        pass
    uv_bin = shutil.which("uv")
    if uv_bin:
        try:
            ret, _, _ = run_subprocess_tree_safe([uv_bin, "run", "--no-sync", "python", "-c", "import pytest, xdist"], cwd=cwd, env=env, timeout=10)
            if ret == 0:
                return [uv_bin, "run", "--no-sync", "pytest", "-n", "auto", "--dist=loadfile", "-p", "no:cacheprovider", target]
        except Exception:
            pass
    return None


def _run_gate(args, env: Optional[Dict[str, str]] = None, in_worktree: bool = False, review_base: Optional[str] = None, cwd: Optional[Path] = None):
    exec_env = dict(os.environ if env is None else env)
    gate_pycache_dir: Optional[Path] = None
    if "PYTHONDONTWRITEBYTECODE" not in exec_env:
        try:
            gate_pycache_dir = Path(tempfile.mkdtemp(prefix="triad_gate_pycache_"))
        except Exception:
            gate_pycache_dir = None

    try:
        return _run_gate_impl(args, env=env, in_worktree=in_worktree, review_base=review_base, cwd=cwd, gate_pycache_dir=gate_pycache_dir)
    finally:
        if gate_pycache_dir and gate_pycache_dir.exists():
            shutil.rmtree(str(gate_pycache_dir), ignore_errors=True)


def _run_gate_impl(args, env: Optional[Dict[str, str]] = None, in_worktree: bool = False, review_base: Optional[str] = None, cwd: Optional[Path] = None, gate_pycache_dir: Optional[Path] = None):
    _import_index.cache_clear()
    cwd = (cwd or Path.cwd()).resolve()
    exec_env = dict(os.environ if env is None else env)
    exec_env["TRIAD_GATE_ACTIVE"] = "1"
    in_worktree = getattr(args, "_in_worktree", False) or in_worktree
    review_base = getattr(args, "_review_base", None) or review_base

    # Reject combination of --apply-verified with targeted test execution up front
    _check_apply_verified_safety(args, exec_env)

    ret_head, initial_head_commit, _ = run_subprocess_tree_safe(["git", "rev-parse", "--verify", "HEAD"], cwd=cwd, env=exec_env)
    initial_head_commit = initial_head_commit.strip() if ret_head == 0 else "UNBORN"

    # Resolve target baseline tree for change detection and diff
    try:
        if review_base:
            ret_base, base_tree, _ = run_subprocess_tree_safe(["git", "rev-parse", "--verify", f"{review_base}^{{tree}}"], cwd=cwd, env=exec_env)
            if ret_base == 0 and base_tree.strip():
                target_base = base_tree.strip()
            else:
                ret_base2, base_tree2, _ = run_subprocess_tree_safe(["git", "rev-parse", "--verify", review_base], cwd=cwd, env=exec_env)
                target_base = base_tree2.strip() if ret_base2 == 0 and base_tree2.strip() else review_base
        else:
            ret_head_tree, head_tree, _ = run_subprocess_tree_safe(["git", "rev-parse", "--verify", "HEAD^{tree}"], cwd=cwd, env=exec_env)
            target_base = head_tree.strip() if ret_head_tree == 0 and head_tree.strip() else get_empty_tree_oid(cwd)
    except Exception as e:
        print(f"\n❌ [Triad Gate BLOCKED] Failed to resolve baseline tree: {e}", file=sys.stderr)
        sys.exit(1)

    def _verify_final_stability(cand_tree: Optional[str] = None, init_wt: Optional[str] = None, init_fp: Optional[dict] = None):
        c_tree = cand_tree if cand_tree is not None else candidate_tree
        i_wt = init_wt if init_wt is not None else initial_wt_tree
        i_fp = init_fp if init_fp is not None else initial_fingerprint
        ret_head, current_head_commit, _ = run_subprocess_tree_safe(["git", "rev-parse", "--verify", "HEAD"], cwd=cwd, env=exec_env)
        current_head_commit = current_head_commit.strip() if ret_head == 0 else "UNBORN"
        if current_head_commit != initial_head_commit:
            print(f"\n❌ [Triad Gate BLOCKED] Git HEAD was modified during validation (expected {initial_head_commit[:10]}, got {current_head_commit[:10]}).", file=sys.stderr)
            sys.exit(1)
        post_wt = snapshot_worktree_tree(cwd, head_tree=c_tree, env=exec_env)
        if post_wt != i_wt:
            ret, diff_summary, _ = run_subprocess_tree_safe(["git", "diff", "--no-color", "--name-status", i_wt, post_wt], cwd=cwd, env=exec_env)
            print(f"\n❌ [Triad Gate BLOCKED] Working tree was modified during evaluation:\n{diff_summary}", file=sys.stderr)
            sys.exit(1)
        post_fingerprint = compute_working_tree_fingerprint(cwd, env=exec_env)
        fp_match, mutated = fingerprints_match(i_fp, post_fingerprint)
        if not fp_match:
            diff_msg = "\n".join(mutated)
            print(f"\n❌ [Triad Gate BLOCKED] Working tree files mutated on disk during evaluation:\n{diff_msg}", file=sys.stderr)
            sys.exit(1)
        ret, post_idx, err = run_subprocess_tree_safe(["git", "write-tree"], cwd=cwd, env=exec_env)
        if ret != 0 or post_idx.strip() != c_tree:
            print("\n❌ [Triad Gate BLOCKED] Git index was modified during evaluation.", file=sys.stderr)
            sys.exit(1)
        _check_no_uncommitted_source_dependencies(cwd, exec_env, in_worktree=in_worktree, stage_name="post-validation")

    print(f"[Triad Gate] Running pre-commit verification in {cwd}...\n")
    max_retries = max(0, getattr(args, "max_retries", 1))

    tsconfig = cwd / "tsconfig.json"
    package_json = cwd / "package.json"
    test_timeout = int(os.environ.get("TRIAD_TEST_TIMEOUT", getattr(args, "test_timeout", 300)))

    attempt = 0
    candidate_tree = None
    while attempt <= max_retries:
        _import_index.cache_clear()
        if attempt > 0 and gate_pycache_dir and gate_pycache_dir.exists():
            shutil.rmtree(str(gate_pycache_dir), ignore_errors=True)
            gate_pycache_dir.mkdir(parents=True, exist_ok=True)
        # Capture candidate tree snapshot before running validation checks
        ret, candidate_tree, err = run_subprocess_tree_safe(["git", "write-tree"], cwd=cwd, env=exec_env)
        if ret != 0 or not candidate_tree.strip():
            print(f"\n❌ [Triad Gate Error] Failed to capture candidate tree snapshot: {err}", file=sys.stderr)
            sys.exit(1)
        candidate_tree = candidate_tree.strip()

        # Capture content-based baseline working-tree snapshot and filesystem fingerprint
        try:
            initial_wt_tree = snapshot_worktree_tree(cwd, head_tree=candidate_tree, env=exec_env)
            initial_fingerprint = compute_working_tree_fingerprint(cwd, env=exec_env)
        except Exception as e:
            print(f"\n❌ [Triad Gate Error] Failed to establish working tree baseline: {e}", file=sys.stderr)
            sys.exit(1)

        # Check for uncommitted source dependencies first
        _check_no_uncommitted_source_dependencies(cwd, exec_env, in_worktree=in_worktree, stage_name="pre-validation")

        # Verify working tree parity with candidate index
        if in_worktree:
            if initial_wt_tree != candidate_tree:
                print("\n❌ [Triad Gate Error] Isolated working tree differs from candidate index.", file=sys.stderr)
                sys.exit(1)
            # Certify checkout-byte representation in isolated worktree
            wt_mismatches = _eng("_verify_checkout_representation", _verify_checkout_representation)(cwd, candidate_tree, exec_env=exec_env)
            if wt_mismatches:
                diff_msg = ":\n" + "\n".join(wt_mismatches)
                print(f"\n❌ [Triad Gate Error] Isolated worktree bytes do not match expected checkout representation{diff_msg}", file=sys.stderr)
                sys.exit(1)
        else:
            # Direct gate execution: ensure actual working-tree bytes match the candidate index
            if initial_wt_tree != candidate_tree:
                _, unstaged_diff, _ = run_subprocess_tree_safe(["git", "diff", "--no-color", "--name-status", candidate_tree, initial_wt_tree], cwd=cwd, env=exec_env)
                diff_msg = ":\n" + unstaged_diff.strip() if unstaged_diff.strip() else ""
                print(f"\n❌ [Triad Gate BLOCKED] Working tree differs from candidate index{diff_msg}", file=sys.stderr)
                print("Direct gate validation requires tracked files to match the staged index to ensure what is tested is what is committed.", file=sys.stderr)
                print("Either stage all changes, discard unstaged edits, or use 'triad gate --worktree' for isolated index verification.", file=sys.stderr)
                sys.exit(1)

            run_subprocess_tree_safe(["git", "update-index", "-q", "--refresh"], cwd=cwd, env=exec_env)
            ret_df, diff_files, _ = run_subprocess_tree_safe(["git", "diff-files", "--no-color", "--name-status"], cwd=cwd, env=exec_env)
            if diff_files.strip():
                print(f"\n❌ [Triad Gate BLOCKED] Tracked files have unstaged modifications:\n{diff_files.strip()}", file=sys.stderr)
                print("Direct gate validation requires tracked files to match the staged index to ensure what is tested is what is committed.", file=sys.stderr)
                print("Either stage all changes, discard unstaged edits, or use 'triad gate --worktree' for isolated index verification.", file=sys.stderr)
                sys.exit(1)

            # Certify filesystem bytes against expected checkout representation for tracked files (detecting clean-filter bypasses)
            mismatched_files = _verify_checkout_representation(cwd, candidate_tree, exec_env=exec_env)
            if mismatched_files:
                diff_msg = ":\n" + "\n".join(mismatched_files)
                print(f"\n❌ [Triad Gate BLOCKED] Tracked files do not match expected checkout representation{diff_msg}", file=sys.stderr)
                print("Direct gate validation requires tracked files to match the staged index to ensure what is tested is what is committed.", file=sys.stderr)
                print("Either stage all changes, discard unstaged edits, or use 'triad gate --worktree' for isolated index verification.", file=sys.stderr)
                sys.exit(1)

        # Query which files changed between target_base and candidate_tree
        ret_df, changed_files_raw, _ = run_subprocess_tree_safe(
            ["git", "diff", "--no-color", "--no-ext-diff", "--no-renames", "--name-only", "-z", target_base, candidate_tree, "--"],
            cwd=cwd, env=exec_env
        )
        changed_files = [f.strip() for f in changed_files_raw.split("\0") if f.strip()]
        if changed_files:
            affects_code = _affects_code(changed_files)
            affects_ts = _affects_typescript(changed_files)
        else:
            affects_code = True
            affects_ts = True

        # Step 1: TypeScript Check
        if not affects_code:
            print("[Step 1/3] Only documentation / non-code assets changed. Skipping TypeScript check.")
        elif not affects_ts:
            print("[Step 1/3] No TypeScript or JavaScript files changed. Skipping tsc check.")
        elif tsconfig.exists():
            nm_dir = cwd / "node_modules"
            if not nm_dir.exists() and package_json.exists():
                print(f"\n❌ [Triad Gate Error] tsconfig.json found but node_modules does not exist in {cwd}.", file=sys.stderr)
                print("Cannot certify TypeScript compilation without installed dependencies.", file=sys.stderr)
                print("Run 'npm install' or ensure node_modules is present before running pre-commit verification.", file=sys.stderr)
                sys.exit(1)

            print("[Step 1/3] Verifying TypeScript type safety (npx tsc --noEmit)...")
            ret, out, err = run_subprocess_tree_safe([NPX_CMD, "tsc", "--noEmit"], cwd=cwd, timeout=test_timeout, env=exec_env)
            if ret != 0:
                attempt, candidate_tree = _handle_validation_failure(
                    stage_label="Step 1 FAILED] TypeScript errors detected",
                    exhausted_label="TypeScript errors persist after retry budget exhausted.",
                    diag_output=f"STDOUT:\n{out}\nSTDERR:\n{err}".strip(),
                    cwd=cwd, exec_env=exec_env, args=args, in_worktree=in_worktree,
                    candidate_tree=candidate_tree, attempt=attempt, max_retries=max_retries,
                )
                continue
            print("✓ TypeScript: 0 errors.")
        else:
            print("[Step 1/3] No tsconfig.json found. Skipping tsc check.")

        # Step 2: Test Suites (Supports polyglot projects: Node/Jest/Vitest AND Python/Unittest/Pytest)
        ran_any_tests = False
        step2_failed = False

        if not affects_code:
            print("[Step 2/3] Only documentation / non-code assets changed. Skipping test suite.")
        else:
            if package_json.exists():
                try:
                    with open(package_json, "r", encoding="utf-8") as f:
                        pkg_data = json.load(f)
                    scripts = pkg_data.get("scripts", {})
                    script = str(scripts.get("test") or "")
                    # Vitest's `--run` is appended below. A Python test script is already
                    # executed by the Python runner, and that extra flag breaks pytest.
                    if "test" in scripts and not re.search(r"\b(pytest|unittest)\b", script):
                        ran_any_tests = True
                        print("[Step 2/3] Running local test suite (npm test)...")
                        test_cmd = [NPM_CMD, "test", "--", "--run"]
                        ret, out, err = run_subprocess_tree_safe(test_cmd, cwd=cwd, timeout=test_timeout, env=exec_env)

                        if ret != 0:
                            step2_failed = True
                            attempt, candidate_tree = _handle_validation_failure(
                                stage_label="Step 2 FAILED] Node test suite failed",
                                exhausted_label="Test suite still failing after retry budget exhausted.",
                                diag_output=f"STDOUT:\n{out}\nSTDERR:\n{err}".strip(),
                                cwd=cwd, exec_env=exec_env, args=args, in_worktree=in_worktree,
                                candidate_tree=candidate_tree, attempt=attempt, max_retries=max_retries,
                            )
                            continue
                        print("✓ Node/npm tests passed successfully.")
                except SystemExit:
                    raise
                except Exception as e:
                    print(f"\n❌ [Triad Gate: Step 2 FAILED] Error executing Node test runner: {e}")
                    sys.exit(1)

            # Python test discovery: run all configured suites (supports targeted test patterns)
            py_test_targets = []
            if (cwd / "triad" / "tests").exists():
                py_test_targets.append("triad/tests")
            if (cwd / "tests").exists():
                py_test_targets.append("tests")

            raw_target_arg = getattr(args, "target", "") or exec_env.get("TRIAD_TEST_TARGET", "")
            norm_target = _normalize_target(raw_target_arg)
            explicit_target = norm_target != "test_*.py"
            target_source = ""
            if attempt > 0:
                # Post-heal retry verification: always execute full test suite to guarantee zero side regressions
                test_pattern = "test_*.py"
            elif _is_ci(exec_env):
                if explicit_target:
                    print("[Triad Gate Notice] CI environment detected; running full test suite 'test_*.py'.")
                test_pattern = "test_*.py"
            elif explicit_target:
                test_pattern = norm_target
            elif getattr(args, "targeted", False) or exec_env.get("TRIAD_TARGETED_TESTS") == "1":
                target_source = "--targeted" if getattr(args, "targeted", False) else "TRIAD_TARGETED_TESTS"
                test_pattern = _resolve_targeted_test_pattern(changed_files, cwd)
            else:
                test_pattern = "test_*.py"

            setattr(args, "_active_test_pattern", test_pattern)
            all_py_test_targets = list(py_test_targets)
            is_targeted = test_pattern != "test_*.py"
            explicit_target = explicit_target and is_targeted
            active_patterns = [p.strip() for p in test_pattern.split(",") if p.strip()]
            if is_targeted:
                banner_source = "explicit --target" if explicit_target else f"auto-resolved via {target_source}"
                print(f"[Step 2/3] [TARGETED GATE] Running test pattern(s) '{test_pattern}' ({banner_source})...")

                # Filter target directories to only those containing matching test files
                active_targets = []
                for target_dir in py_test_targets:
                    td_path = cwd / target_dir
                    if any(any(td_path.rglob(pat)) for pat in active_patterns):
                        active_targets.append(target_dir)

                if not active_targets and py_test_targets:
                    if explicit_target:
                        print(
                            f"\n[Triad Gate: Step 2 FAILED] Targeted test pattern '{test_pattern}' matched 0 test files in {py_test_targets}.",
                            file=sys.stderr,
                        )
                        sys.exit(5)
                    else:
                        print(f"[Step 2/3] Targeted test pattern '{test_pattern}' matched 0 test files in {py_test_targets}; falling back to full test suite.")
                        test_pattern = "test_*.py"
                        setattr(args, "_active_test_pattern", test_pattern)
                        is_targeted = False
                        active_patterns = [test_pattern]
                        active_targets = py_test_targets
                py_test_targets = active_targets

            target_idx = 0
            while target_idx < len(py_test_targets):
                py_test_target = py_test_targets[target_idx]
                target_idx += 1
                ran_any_tests = True
                pattern_desc = f", pattern: {test_pattern}" if is_targeted else ""
                print(f"[Step 2/3] Running Python unit test suite ({py_test_target}{pattern_desc})...")
                py_test_env = dict(exec_env if exec_env is not None else os.environ)
                if gate_pycache_dir and gate_pycache_dir.exists():
                    py_test_env["PYTHONPYCACHEPREFIX"] = str(gate_pycache_dir)
                    py_test_env.pop("PYTHONDONTWRITEBYTECODE", None)
                else:
                    py_test_env["PYTHONDONTWRITEBYTECODE"] = "1"
                py_test_env["TRIAD_GATE_ACTIVE"] = "1"
                if in_worktree:
                    py_test_env["TRIAD_ISOLATED_WORKTREE"] = "1"
                    orig_pp = py_test_env.get("PYTHONPATH", "")
                    sanitized_pp_parts = [str(cwd.resolve())]
                    originating_root_val = getattr(args, "_originating_root", None)
                    originating_root = Path(originating_root_val).resolve() if originating_root_val else None
                    if not originating_root:
                        try:
                            originating_root = get_repo_root(cwd, env=exec_env)
                        except Exception:
                            pass

                    parent_root = None
                    try:
                        ret_c, out_c, _ = run_subprocess_tree_safe(
                            ["git", "rev-parse", "--git-common-dir"],
                            cwd=cwd, env=exec_env
                        )
                        if ret_c == 0 and out_c.strip():
                            common_git = Path(out_c.strip())
                            if not common_git.is_absolute():
                                common_git = (cwd / common_git).resolve()
                            parent_root = common_git.parent.resolve()
                    except Exception:
                        pass
                    if not parent_root:
                        try:
                            parent_root = get_repo_root(cwd, env=exec_env)
                        except Exception:
                            pass

                    if not parent_root and not originating_root:
                        print("\n❌ [Triad Gate Error] Failed to establish parent repository exclusion boundary for Python import isolation.", file=sys.stderr)
                        sys.exit(1)

                    excluded_roots: List[Path] = []
                    for candidate_root in [parent_root, originating_root]:
                        if candidate_root and candidate_root not in excluded_roots and candidate_root != cwd.resolve():
                            excluded_roots.append(candidate_root)

                    if orig_pp:
                        for part in orig_pp.split(os.pathsep):
                            if not part:
                                continue
                            try:
                                resolved_part = Path(part).resolve()
                                is_venv_dep = any(seg.lower() in ("site-packages", "dist-packages") for seg in resolved_part.parts)
                                is_excluded = any(
                                    (resolved_part == ex or ex in resolved_part.parents)
                                    for ex in excluded_roots
                                )
                                if is_excluded and not is_venv_dep:
                                    if not (cwd.resolve() == resolved_part or cwd.resolve() in resolved_part.parents):
                                        continue
                                if str(resolved_part) not in sanitized_pp_parts:
                                    sanitized_pp_parts.append(str(resolved_part))
                            except Exception:
                                pass
                    py_test_env["PYTHONPATH"] = os.pathsep.join(sanitized_pp_parts)

                gate_python = _resolve_gate_python(cwd, excluded_roots if in_worktree else None)
                is_parallel_requested = bool(getattr(args, "parallel", False) or py_test_env.get("TRIAD_PARALLEL_TESTS") == "1")
                target_patterns = [pat for pat in active_patterns if any((cwd / py_test_target).rglob(pat))] if is_targeted else active_patterns
                if not target_patterns:
                    target_patterns = ["test_*.py"]
                if in_worktree:
                    if is_parallel_requested:
                        print("[Step 2/3] [Notice] --parallel is bypassed in isolated worktree mode (worktree runner manages process isolation).")
                    isolation_script = _build_python_isolation_script(cwd, py_test_target, excluded_roots, pattern=target_patterns)
                    test_cmd = [gate_python, "-c", isolation_script]
                else:
                    if is_targeted:
                        if is_parallel_requested:
                            print("[Step 2/3] [Notice] --parallel is bypassed for targeted test pattern(s).")
                        if len(target_patterns) > 1:
                            multi_script = _build_python_multi_pattern_script(cwd, py_test_target, target_patterns)
                            test_cmd = [gate_python, "-c", multi_script]
                        else:
                            test_cmd = [gate_python, "-m", "unittest", "discover", "-s", py_test_target, "-p", target_patterns[0]]
                    elif is_parallel_requested:
                        xdist_cmd = _resolve_pytest_xdist_cmd(py_test_target, cwd=cwd, env=py_test_env, python_exe=gate_python)
                        if xdist_cmd:
                            print("[Step 2/3] [PARALLEL] Executing test suite via pytest-xdist across CPU cores...")
                            test_cmd = xdist_cmd
                        else:
                            print("[Step 2/3] [Notice] pytest-xdist not detected; executing sequentially via unittest.")
                            test_cmd = [gate_python, "-m", "unittest", "discover", "-s", py_test_target, "-p", test_pattern]
                    else:
                        test_cmd = [gate_python, "-m", "unittest", "discover", "-s", py_test_target, "-p", test_pattern]
                ret, out, err = run_subprocess_tree_safe(test_cmd, cwd=cwd, timeout=test_timeout, env=py_test_env)

                diag_output = f"STDOUT:\n{out}\nSTDERR:\n{err}".strip()
                is_empty_suite = ("Ran 0 tests" in diag_output) or ("collected 0 items" in diag_output) or (ret == 5)
                if is_empty_suite:
                    if explicit_target:
                        print(
                            f"\n[Triad Gate: Step 2 FAILED] Explicit test target '{test_pattern}' matched 0 test cases.\n{diag_output}",
                            file=sys.stderr,
                        )
                        sys.exit(5)
                    elif is_targeted:
                        print(f"[Step 2/3] Targeted test pattern '{test_pattern}' matched 0 test cases; falling back to full test suite.")
                        test_pattern = "test_*.py"
                        setattr(args, "_active_test_pattern", test_pattern)
                        is_targeted = False
                        active_patterns = [test_pattern]
                        py_test_targets = list(all_py_test_targets)
                        target_idx = 0
                        continue

                if ret != 0 or is_empty_suite:
                    step2_failed = True
                    reason = "discovering 0 tests" if is_empty_suite else "failures"
                    attempt, candidate_tree = _handle_validation_failure(
                        stage_label=f"Step 2 FAILED] Python test suite failed ({reason})",
                        exhausted_label="Python test suite still failing after retry budget exhausted.",
                        diag_output=diag_output,
                        cwd=cwd, exec_env=exec_env, args=args, in_worktree=in_worktree,
                        candidate_tree=candidate_tree, attempt=attempt, max_retries=max_retries,
                    )
                    break  # breaks out of targets loop to restart validation
                print(f"✓ Python tests ({py_test_target}) passed successfully.")

            if step2_failed:
                continue

            if not ran_any_tests:
                print("[Step 2/3] No test runner found (package.json / Python tests). Skipping.")
                setattr(args, "_active_test_pattern", None)

        # Check for uncommitted source dependencies created during validation
        _check_no_uncommitted_source_dependencies(cwd, exec_env, in_worktree=in_worktree, stage_name="post-validation")

        # Content-based mutation verification: detect any content, addition, deletion, or revert
        final_wt_tree = snapshot_worktree_tree(cwd, head_tree=candidate_tree, env=exec_env)
        if final_wt_tree != initial_wt_tree:
            ret, diff_summary, _ = run_subprocess_tree_safe(["git", "diff", "--no-color", "--name-status", initial_wt_tree, final_wt_tree], cwd=cwd, env=exec_env)
            print(f"\n❌ [Triad Gate BLOCKED] Validation checks modified working-tree files during verification:\n{diff_summary}", file=sys.stderr)
            sys.exit(1)

        # Filesystem content fingerprint verification: detect any byte-level mutation masked by Git clean/smudge filters
        final_fingerprint = compute_working_tree_fingerprint(cwd, env=exec_env)
        fp_match, mutated = fingerprints_match(initial_fingerprint, final_fingerprint)
        if not fp_match:
            diff_msg = "\n".join(mutated)
            print(f"\n❌ [Triad Gate BLOCKED] Validation checks modified working-tree files during verification:\n{diff_msg}", file=sys.stderr)
            sys.exit(1)

        ret, check_tree, err = run_subprocess_tree_safe(["git", "write-tree"], cwd=cwd, env=exec_env)
        if ret != 0:
            print(f"\n❌ [Triad Gate BLOCKED] Failed to capture verification tree: {err}", file=sys.stderr)
            sys.exit(1)
        if check_tree.strip() != candidate_tree:
            print(f"\n❌ [Triad Gate BLOCKED] Candidate tree changed during validation (expected {candidate_tree}, got {check_tree.strip()}).", file=sys.stderr)
            sys.exit(1)

        # All steps verified clean
        break

    _verify_final_stability(candidate_tree, initial_wt_tree, initial_fingerprint)

    # Step 3: Advisory Council Diff Signoff
    print("\n[Step 3/3] Submitting diff to Advisory Council for pre-commit signoff...")
    try:
        # 1. Determine whether changes exist strictly from tree identity
        if candidate_tree == target_base:
            _verify_final_stability(candidate_tree, initial_wt_tree, initial_fingerprint)
            setattr(args, "_validated_tree", candidate_tree)
            print("✓ No changes detected in git working tree. Gate passed.")
            return

        # 2. Extract immutable unified diff bypassing any external diff drivers or textconv filters
        diff_cmd = ["git", "diff", "--no-color", "--no-ext-diff", "--no-textconv", target_base, candidate_tree, "--"]
        ret, diff, err = run_subprocess_tree_safe(diff_cmd, cwd=cwd, env=exec_env)
        if ret != 0 or not diff or not diff.strip():
            err_msg = err.strip() if err.strip() else "diff produced empty output despite different tree object IDs"
            raise RuntimeError(f"Failed to generate diff against baseline ({target_base[:10]} != {candidate_tree[:10]}): {err_msg}")
        raw_diff = diff
        diff = strip_diff_bloat(diff)
    except Exception as e:
        print(f"\n❌ [Triad Gate BLOCKED] Failed to retrieve git diff: {e}", file=sys.stderr)
        sys.exit(1)

    engine = getattr(args, "engine", "auto")
    if engine == "auto" and os.environ.get("TRIAD_GATE_ENGINE"):
        engine = os.environ["TRIAD_GATE_ENGINE"].strip() or "auto"
    competition = getattr(args, "competition", False)
    try:
        from triad.intent_engine import is_high_stakes
    except ImportError:
        from intent_engine import is_high_stakes
    try:
        gate_high_stakes = is_high_stakes(diff)
    except Exception:
        gate_high_stakes = True
    trivial_verdict, engine, competition = _resolve_triage_route(
        raw_diff, gate_high_stakes, engine, competition, allow_downgrade=False
    )
    if trivial_verdict is not None:
        resp = trivial_verdict
        competition = False
    elif competition:
        try:
            from triad.competition import query_competition_council
        except ImportError:
            from competition import query_competition_council
        adv_pair = ("mock", "mock") if engine == "mock" else ("claude", "codex")
        session = query_competition_council(
            _gate_signoff_prompt(diff, first_line=False)
            + "\nUnder Section 4 (Final Adjudicated Verdict & Action Plan), explicitly state either 'VERDICT: APPROVED' or 'VERDICT: REJECTED'.",
            diff=diff,
            mode="review_diff",
            timeout=getattr(args, "timeout", 240),
            advisor_names=adv_pair
        )
        resp = session.get("synthesis", "")
    else:
        resp = query_advisory_council(
            _gate_signoff_prompt(diff),
            diff=diff,
            mode="review_diff",
            engine=engine,
            timeout=getattr(args, "timeout", 240)
        )
    print("\n[Advisory Council Signoff]:")
    print(resp)

    # Parse verdict fail-closed: distinguish outages from explicit verdicts
    resp_clean = (resp or "").strip()
    council_errored = bool(competition and isinstance(session, dict) and session.get("status") == "error")
    if (
        not resp_clean
        or resp_clean.startswith("[Error")
        or resp_clean.startswith("[error")
        or council_errored
        or classify_advisor_response(resp_clean) in ("limit", "error", "timeout", "empty")
    ):
        print("\n❌ [Triad Gate BLOCKED] Advisory Council execution error or service outage.")
        if resp_clean:
            print(f"Details: {resp_clean[:200]}")
        sys.exit(1)

    # Fail closed: a competition council that ran degraded (one advisor failed) or without
    # quorum must never approve a pre-commit signoff.
    if competition and (
        not isinstance(session, dict)
        or session.get("status") == "degraded"
        or not session.get("quorum_met")
    ):
        print("\n❌ [Triad Gate BLOCKED] Competition council degraded or quorum not met; refusing to approve.")
        notify_event("Pre-Commit Gate Blocked", "Competition council degraded or quorum not met.", status="failed", timeout=1.5)
        sys.exit(1)

    # Rejection anywhere in the response takes precedence and immediately blocks
    is_rejected = bool(re.search(r"\bVERDICT:\s*REJECTED\b", resp_clean, re.IGNORECASE))
    if is_rejected:
        print("\n❌ [Triad Gate BLOCKED] Advisory Council explicitly rejected the diff.")
        print("Address the advisory council findings above before committing.")
        notify_event("Pre-Commit Gate Rejected", "Advisory Council explicitly rejected the diff.", status="failed", timeout=1.5)
        sys.exit(1)

    if competition:
        is_approved = bool(re.search(r"\bVERDICT:\s*APPROVED\b", resp_clean, re.IGNORECASE))
    else:
        # Approval must be explicitly declared on the opening non-empty line of the active advisor response
        non_empty_lines = [l.strip() for l in resp_clean.splitlines() if l.strip()]
        while non_empty_lines and non_empty_lines[0].startswith("[") and ("failover" in non_empty_lines[0].lower() or "auto-failover" in non_empty_lines[0].lower()):
            non_empty_lines.pop(0)
        first_line = non_empty_lines[0] if non_empty_lines else ""
        first_line_clean = re.sub(r"[\*#_`]", "", first_line).strip()
        is_approved = bool(re.match(r"^VERDICT:\s*APPROVED\b", first_line_clean, re.IGNORECASE))

    if is_approved:
        # Common final stability check: verify both working tree and index did not mutate
        _verify_final_stability()
        setattr(args, "_validated_tree", candidate_tree)
        print("\n✓ [Triad Gate COMPLETE] Advisory Council approved pre-commit signoff.")
    else:
        reason = "contain 'VERDICT: APPROVED'" if competition else "provide an explicit 'VERDICT: APPROVED' on line 1"
        print(f"\n❌ [Triad Gate BLOCKED] Advisory Council did not {reason}.")
        print("Address the advisory council findings above before committing.")
        notify_event("Pre-Commit Gate Blocked", f"Advisory Council did not approve diff: {reason}.", status="failed", timeout=1.5)
        sys.exit(1)

def _gate_signoff_prompt(diff: str, *, first_line: bool = True) -> str:
    """Stable pre-commit checklist. Truncation is named, and is not itself a rejection."""
    files = []
    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            files.append(line[len("diff --git "):])
    index = "\n".join(f"- {name}" for name in files[:100]) or "- (no file headers)"
    verdict_line = (
        "Start your response with exactly 'VERDICT: APPROVED' or 'VERDICT: REJECTED' on the first line.\n"
        if first_line else ""
    )
    return (
        "Evaluate this diff as the final pre-commit gate.\n"
        f"{verdict_line}"
        "Checklist: correctness of the changed lines; regressions in direct callers; "
        "data-loss or secret exposure; security of file and process handling.\n"
        "Do not reject for wording or for files that were not shown. "
        "If the diff was truncated, judge the files you can see and name what you could not review. "
        "Truncation alone is not a reason to reject.\n"
        f"Files in this diff:\n{index}\n"
    )


