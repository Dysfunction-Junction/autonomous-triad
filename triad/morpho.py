#!/usr/bin/env python3
# Tags: morphogenetic, patching, verification
# Links: triad/morphogenetic.py, triad/docker_runner.py
# Queries: "how does SH-0 intake a failing check", "how is a morpho branch created"
"""morpho: SH-0 failing-check intake, gated branch, and gate report (decision D12).

SH-0 accepts only friction that already is a failing check: a test that is red
on ``main``, or a ``tsc --noEmit`` error on ``main``. That check is the
reproduction profile: it fails on the base by definition and must pass on the
candidate. No test is ever written by a model.

Wiring, in order::

    friction = friction_from_failing_check(check_kind="red-test", ...)
    engine = MorphogeneticEngine(repo, verification_runner=..., enabled=True)
    out = run_sh0_once(friction, candidates, engine, base_commit=<sha>)
    # out["branch"]   -> {"branch": "morpho/<event_id>", "sha": ...}
    # out["report"]   -> markdown gate report (the pull-request body)
    # out["mutation_row"] -> dict for the ledger ``mutations`` table

Scope guards (plan §SH-0): one file per candidate and the 200-line cap are
enforced by the engine; :func:`preflight` refuses to run without spare memory
or while the recap model is loaded. A merge never changes a running process:
the daemon picks a merged fix up at its next normal restart.

The ``mutations`` row needs the ledger ``seq`` of the logged friction event.
Log the red check first (``check.failed`` / decision-log), put its seq into
``friction.context["friction_seq"]`` (or pass ``friction_seq=``), then insert
with :func:`insert_mutation_row`. Inserting without a seq fails closed.
"""

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from triad.morphogenetic import (
    MorphogeneticEngine,
    MutationCandidate,
    RuntimeFrictionEvent,
)
from triad.worktree import clean_git_env, isolated_worktree

__all__ = [
    "CHECK_KINDS",
    "GATE_ORDER",
    "MORPHO_BRANCH_PREFIX",
    "RECAP_MODEL_ENV",
    "MIN_FREE_MB_ENV",
    "DEFAULT_MIN_FREE_MB",
    "MAX_CHECK_OUTPUT",
    "patch_class_for",
    "friction_from_failing_check",
    "preflight",
    "create_morpho_branch",
    "render_gate_report",
    "build_mutation_row",
    "insert_mutation_row",
    "run_sh0_once",
]

CHECK_KINDS = ("red-test", "tsc")
MORPHO_BRANCH_PREFIX = "morpho/"
RECAP_MODEL_ENV = "RECAP_MODEL_LOADED"
MIN_FREE_MB_ENV = "TRIAD_MORPHOGENETIC_MIN_FREE_MB"
DEFAULT_MIN_FREE_MB = 2048
MAX_CHECK_OUTPUT = 4000

_PKG_RE = re.compile(r"^(?:apps|packages)/[A-Za-z0-9][A-Za-z0-9_.-]*$")
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

# Canonical gate order for the report. Gates absent from a candidate's record
# never ran (early rejection, reproduction off, scan off) and render as not run.
GATE_ORDER = (
    "enabled",
    "runner",
    "target_input",
    "target_resolve",
    "protected",
    "symlink",
    "noop",
    "diff_cap",
    "reproduction",
    "reproduction_clean",
    "forbidden_tokens",
    "scan",
    "verification",
    "git_pointer",
    "target_stable",
    "tree_clean",
    "diff",
    "sandbox",
)


def patch_class_for(check_kind: str, failing_file: str) -> str:
    """SH-2 patch class, fixed pair ``<check kind>:<top-level package>``.

    Never a model's label: ``tsc:apps/daemon``, ``red-test:packages/memory``.
    """
    if check_kind not in CHECK_KINDS:
        raise ValueError(f"check_kind must be one of {CHECK_KINDS}: {check_kind!r}")
    rel = (failing_file or "").strip().replace("\\", "/").strip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    if len(parts) >= 2 and parts[0] in ("apps", "packages"):
        top = "/".join(parts[:2])
    elif parts:
        top = parts[0]
    else:
        top = "unknown"
    return f"{check_kind}:{top}"


def friction_from_failing_check(
    *,
    check_kind: str,
    package: str,
    failing_file: str,
    check_output: str,
    verification_profile: str,
    base_commit: str = "HEAD",
    event_id: Optional[str] = None,
    repo_path: Optional[str] = None,
    repo_root: Optional[Union[str, Path]] = None,
) -> RuntimeFrictionEvent:
    """Build SH-0 friction from a check that is red on the base commit.

    ``failing_file`` is the source file the repair will touch (never the test:
    tests are protected targets and the engine rejects them). ``check_output``
    is the red output already observed on ``base_commit``. The same trusted
    ``verification_profile`` serves as reproduction (must fail on base) and
    verification (must pass on the candidate).
    """
    if check_kind not in CHECK_KINDS:
        raise ValueError(f"check_kind must be one of {CHECK_KINDS}: {check_kind!r}")
    pkg = (package or "").strip().replace("\\", "/")
    if not _PKG_RE.match(pkg):
        raise ValueError(f"package must look like apps/<ws> or packages/<ws>: {package!r}")
    if not verification_profile or not verification_profile.strip():
        raise ValueError("verification_profile must be a non-empty trusted profile name")
    bad = MorphogeneticEngine._validate_rel_input(failing_file)
    if bad:
        raise ValueError(f"invalid failing_file ({bad}): {failing_file!r}")
    if repo_root is not None:
        # Fail fast: a protected or unresolvable target can never survive.
        probe = MorphogeneticEngine(Path(repo_root).resolve())
        target, err = probe._resolve_within(probe.repo_root, failing_file)
        if err or target is None:
            raise ValueError(f"failing_file unresolvable in {probe.repo_root}: {err}")
        if probe._is_protected_target(probe.repo_root, target):
            raise ValueError(f"failing_file is protected from mutation: {failing_file}")
    output = (check_output or "")[:MAX_CHECK_OUTPUT]
    first_line = output.strip().splitlines()[0][:160] if output.strip() else "(no output captured)"
    eid = event_id or f"friction_{os.urandom(4).hex()}"
    return RuntimeFrictionEvent(
        event_id=eid,
        error_type="failing_check",
        message=f"{check_kind} red on {base_commit} for {pkg}: {first_line}",
        stack_trace=output,
        failing_file=failing_file,
        repo_path=repo_path or (str(Path(repo_root).resolve()) if repo_root else None),
        context={
            "check_kind": check_kind,
            "package": pkg,
            "patch_class": patch_class_for(check_kind, failing_file),
            "verification_profile": verification_profile.strip(),
            "reproduction_profile": verification_profile.strip(),
            "base_commit": base_commit,
            "check_output": output,
        },
    )


def preflight(
    *,
    min_free_mb: Optional[int] = None,
    recap_env: str = RECAP_MODEL_ENV,
) -> Tuple[bool, str]:
    """SH-0 scope guards: spare memory, and never while the recap model is loaded."""
    if os.environ.get(recap_env, "").strip().lower() in ("1", "true", "yes", "on"):
        return False, f"refusing to run while the recap model is loaded ({recap_env} is set)"
    floor = min_free_mb
    if floor is None:
        try:
            floor = int(os.environ.get(MIN_FREE_MB_ENV, str(DEFAULT_MIN_FREE_MB)).strip())
        except ValueError:
            floor = DEFAULT_MIN_FREE_MB
        if floor <= 0:
            floor = DEFAULT_MIN_FREE_MB
    try:
        import psutil  # type: ignore
    except ImportError:
        return False, "refusing to run: psutil is unavailable, spare memory cannot be verified"
    free_mb = psutil.virtual_memory().available // (1024 * 1024)
    if free_mb < floor:
        return False, f"refusing to run: only {free_mb}MB free, need {floor}MB"
    return True, f"ok: {free_mb}MB free (floor {floor}MB), recap model not loaded"


def _git(repo: Union[str, Path], *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=timeout, env=clean_git_env(),
    )


def _diff_counts(unified_diff: str) -> Tuple[int, int]:
    added = deleted = 0
    for line in (unified_diff or "").splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return added, deleted


def create_morpho_branch(
    *,
    repo_root: Union[str, Path],
    base_commit: str,
    event: RuntimeFrictionEvent,
    survivor: MutationCandidate,
    strategy: str = "unknown",
    push: bool = False,
) -> Dict[str, Any]:
    """Commit the verified bytes of ``survivor`` onto ``morpho/<event_id>``.

    Works in an ephemeral worktree off ``base_commit``; the caller's checkout
    is never touched. The branch is created in the shared repo, so it survives
    the worktree cleanup. Push (``push=True``) and the pull request are the
    operator's explicit steps; :func:`render_gate_report` is the PR body.
    """
    if not survivor.survival_passed or not survivor.unified_diff:
        raise ValueError("create_morpho_branch needs a surviving candidate with a verified diff")
    eid = event.event_id or ""
    if not _EVENT_ID_RE.match(eid) or ".." in eid or eid.endswith("."):
        raise ValueError(f"event_id is not a safe branch component: {eid!r}")
    bad = MorphogeneticEngine._validate_rel_input(survivor.target_file)
    if bad:
        raise ValueError(f"invalid survivor target ({bad}): {survivor.target_file!r}")
    branch = MORPHO_BRANCH_PREFIX + eid
    root = Path(repo_root).resolve()

    exists = _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    if exists.returncode == 0:
        raise ValueError(f"branch {branch} already exists; refusing to overwrite it")
    resolved = _git(root, "rev-parse", "--verify", f"{base_commit}^{{commit}}")
    if resolved.returncode != 0 or not resolved.stdout.strip():
        raise ValueError(f"base_commit does not resolve: {base_commit!r}")
    base_sha = resolved.stdout.strip()

    ctx = event.context or {}
    check_kind = ctx.get("check_kind", "failing_check")
    package = ctx.get("package", "")
    patch_class = ctx.get("patch_class") or patch_class_for(
        check_kind if check_kind in CHECK_KINDS else "red-test", survivor.target_file
    )
    profile = ctx.get("verification_profile", "")
    added, deleted = _diff_counts(survivor.unified_diff)
    subject = f"morpho({eid}): gated {check_kind} repair in {package or 'repo'}"
    body = (
        f"{subject}\n"
        f"\n"
        f"Target: {survivor.target_file} (+{added} -{deleted})\n"
        f"Check: {profile} red on {base_sha[:12]}, green on this commit\n"
        f"Class: {patch_class}\n"
        f"Strategy: {strategy}\n"
    )

    with isolated_worktree(str(root), branch_or_commit=base_sha, prefix=f"morpho_branch_{eid}") as wt:
        wt_path = Path(wt)
        probe = MorphogeneticEngine(wt_path)
        target_path, err = probe._resolve_within(wt_path, survivor.target_file)
        if err or target_path is None:
            raise RuntimeError(f"survivor target unresolvable on {base_sha[:12]}: {err}")
        if probe._is_protected_target(wt_path, target_path):
            raise RuntimeError(f"survivor target is protected: {survivor.target_file}")
        if probe._has_link_component(wt_path, survivor.target_file):
            raise RuntimeError(f"survivor target has a link component: {survivor.target_file}")
        checkout = _git(wt_path, "checkout", "-b", branch)
        if checkout.returncode != 0:
            raise RuntimeError(f"could not create {branch}: {checkout.stderr.strip()[-300:]}")
        target_path.write_bytes(survivor.mutated_code.encode("utf-8"))
        rel = target_path.relative_to(wt_path).as_posix()
        status = _git(wt_path, "status", "--porcelain", "--untracked-files=all")
        lines = status.stdout.splitlines()
        if status.returncode != 0 or len(lines) != 1 or not (lines[0][:2] == " M" and lines[0][3:].strip('"') == rel):
            raise RuntimeError(f"unexpected tree before morpho commit: {lines[:5]}")
        add = _git(wt_path, "add", "--", f":(literal){rel}")
        if add.returncode != 0:
            raise RuntimeError(f"could not stage {rel}: {add.stderr.strip()[-300:]}")
        commit = _git(
            wt_path,
            "-c", "user.email=morpho@exocortex.local",
            "-c", "user.name=MorphogeneticEngine",
            "-c", "core.autocrlf=false",
            "commit", "-m", body,
        )
        if commit.returncode != 0:
            raise RuntimeError(f"could not commit {branch}: {(commit.stderr or commit.stdout).strip()[-300:]}")
        names = _git(wt_path, "diff", "--name-only", f"{base_sha}..HEAD")
        touched = [n for n in names.stdout.splitlines() if n.strip()]
        if touched != [rel]:
            raise RuntimeError(f"morpho commit touched {touched}, expected [{rel}]")
        sha = _git(wt_path, "rev-parse", "HEAD")
        if sha.returncode != 0 or not sha.stdout.strip():
            raise RuntimeError("could not read back the morpho commit sha")
        head_sha = sha.stdout.strip()
        pushed = False
        if push:
            res = _git(wt_path, "push", "origin", branch, timeout=300)
            if res.returncode != 0:
                raise RuntimeError(f"push of {branch} failed: {(res.stderr or res.stdout).strip()[-500:]}")
            pushed = True

    return {
        "branch": branch,
        "sha": head_sha,
        "base_sha": base_sha,
        "target": survivor.target_file,
        "added": added,
        "deleted": deleted,
        "patch_class": patch_class,
        "pushed": pushed,
    }


def render_gate_report(
    *,
    event: RuntimeFrictionEvent,
    survivor: MutationCandidate,
    trial_result: Dict[str, Any],
    branch_info: Dict[str, Any],
    image: Optional[str] = None,
    repo: Optional[str] = None,
    max_diff_lines: int = 40,
    max_output_lines: int = 20,
) -> str:
    """Markdown gate report for the ``morpho/<id>`` pull-request body. Every gate reported."""
    ctx = event.context or {}
    check_kind = ctx.get("check_kind", "failing_check")
    package = ctx.get("package", "")
    profile = ctx.get("verification_profile", "")
    patch_class = branch_info.get("patch_class") or ctx.get("patch_class", "")
    by_gate = {g.get("gate"): g for g in (survivor.gates or []) if isinstance(g, dict)}

    def row(name: str) -> str:
        rec = by_gate.get(name)
        if rec is None:
            return f"| {name} | not run | — |"
        mark = "PASS" if rec.get("passed") else "FAIL"
        detail = str(rec.get("detail", "")) or "—"
        return f"| {name} | {mark} | {detail} |"

    lines = [
        f"# SH-0 gated patch: {event.event_id}",
        "",
        f"- Friction: `{check_kind}` red on `{ctx.get('base_commit', '')}` for `{package}` (profile `{profile}`)",
        f"- Target: `{survivor.target_file}` (+{branch_info.get('added', 0)} -{branch_info.get('deleted', 0)}), one file",
        f"- Branch: `{branch_info.get('branch', '')}` @ `{branch_info.get('sha', '')}`",
        f"- Base: `{branch_info.get('base_sha', '')}`",
        f"- Patch class: `{patch_class}` (fixed `<check kind>:<top-level package>` pair)",
    ]
    if repo:
        lines.append(f"- Repo: `{repo}`")
    lines.append(f"- Verify image: `{image or 'python default (no TS image)'}` (verify images are never pulled)")
    lines.extend([
        "",
        "## Gates",
        "",
        "| Gate | Result | Detail |",
        "|---|---|---|",
    ])
    lines.extend(row(name) for name in GATE_ORDER)
    lines.extend([
        "",
        "## Candidates",
        "",
        f"{trial_result.get('candidates_evaluated', 0)} evaluated, "
        f"survivor `{trial_result.get('survivor') or 'none'}`.",
    ])
    for res in (trial_result.get("results") or [])[:10]:
        if res.get("survival_passed"):
            continue
        killer = "apoptosis"
        for g in reversed(res.get("gates") or []):
            if isinstance(g, dict) and not g.get("passed"):
                killer = f"{g.get('gate')}: {g.get('detail', '')}"[:160]
                break
        lines.append(f"- `{res.get('candidate_id')}` rejected at {killer}")
    output_head = "\n".join((survivor.verification_output or "").splitlines()[:max_output_lines])
    diff_head = "\n".join((survivor.unified_diff or "").splitlines()[:max_diff_lines])
    lines.extend([
        "",
        "## Verification output (head)",
        "",
        "```",
        output_head or "(empty)",
        "```",
        "",
        f"## Diff (first {max_diff_lines} lines)",
        "",
        "```diff",
        diff_head or "(empty)",
        "```",
    ])
    return "\n".join(lines) + "\n"


MUTATION_STATES = ("REJECTED", "PASSED", "MERGED", "DISCARDED")


def build_mutation_row(
    *,
    candidate: MutationCandidate,
    event: RuntimeFrictionEvent,
    friction_seq: Optional[int],
    base_commit: str,
    branch: str,
    strategy: str = "unknown",
    state: str = "PASSED",
    created_at: Optional[int] = None,
) -> Dict[str, Any]:
    """Dict for one ledger ``mutations`` row (see packages/core/schema.sql)."""
    if state not in MUTATION_STATES:
        raise ValueError(f"state must be one of {MUTATION_STATES}: {state!r}")
    return {
        "mutation_id": candidate.candidate_id,
        "friction_seq": friction_seq,
        "base_commit": base_commit,
        "branch": branch,
        "strategy": strategy,
        "diff_hash": hashlib.sha256((candidate.unified_diff or "").encode("utf-8")).digest(),
        "gates": json.dumps(candidate.gates or []),
        "state": state,
        "created_at": created_at if created_at is not None else int(time.time()),
    }


def insert_mutation_row(db_path: Union[str, Path], row: Dict[str, Any]) -> None:
    """Insert one row into the ledger ``mutations`` table. Fails closed.

    ``friction_seq`` must be the seq of the already-logged friction event;
    a missing seq raises instead of writing a dangling row.
    """
    if row.get("friction_seq") is None:
        raise ValueError("cannot insert a mutations row without friction_seq: log the friction event first")
    cols = ("mutation_id", "friction_seq", "base_commit", "branch", "strategy",
            "diff_hash", "gates", "state", "created_at")
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                f"INSERT INTO mutations ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [row[c] for c in cols],
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"could not insert mutations row into {db_path}: {e}")


def run_sh0_once(
    friction: RuntimeFrictionEvent,
    candidates: List[MutationCandidate],
    engine: MorphogeneticEngine,
    *,
    base_commit: str = "HEAD",
    strategy: str = "unknown",
    push: bool = False,
    preflight_check: bool = True,
    min_free_mb: Optional[int] = None,
    friction_seq: Optional[int] = None,
    image: Optional[str] = None,
    repo: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one SH-0 pass: preflight, Darwinian trial, and on a survivor the
    ``morpho/<id>`` branch, gate report, and mutations row (not inserted: the
    caller inserts it with :func:`insert_mutation_row` after logging friction).
    """
    out: Dict[str, Any] = {
        "event_id": friction.event_id,
        "preflight_passed": False,
        "preflight_reason": "",
        "trial": None,
        "survivor": None,
        "branch": None,
        "report": None,
        "mutation_row": None,
    }
    if preflight_check:
        ok, reason = preflight(min_free_mb=min_free_mb)
        out["preflight_reason"] = reason
        if not ok:
            return out
    out["preflight_passed"] = True
    verification_profile = (friction.context or {}).get("verification_profile", "")
    reproduction_profile = (friction.context or {}).get("reproduction_profile", verification_profile)
    if not verification_profile:
        raise ValueError("friction has no verification_profile in context")
    trial = engine.execute_darwinian_trial(
        friction, candidates, verification_profile,
        base_commit=base_commit, reproduction_profile=reproduction_profile,
    )
    out["trial"] = trial
    if not trial.get("survivor"):
        return out
    survivor = next(c for c in candidates if c.candidate_id == trial["survivor"])
    out["survivor"] = survivor.candidate_id
    branch_info = create_morpho_branch(
        repo_root=engine.repo_root, base_commit=base_commit,
        event=friction, survivor=survivor, strategy=strategy, push=push,
    )
    out["branch"] = branch_info
    out["report"] = render_gate_report(
        event=friction, survivor=survivor, trial_result=trial,
        branch_info=branch_info, image=image, repo=repo,
    )
    out["mutation_row"] = build_mutation_row(
        candidate=survivor, event=friction,
        friction_seq=friction.context.get("friction_seq", friction_seq),
        base_commit=branch_info["base_sha"], branch=branch_info["branch"],
        strategy=strategy, state="PASSED",
    )
    return out
