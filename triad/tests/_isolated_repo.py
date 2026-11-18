# Tags: test-fixture, worktree
# Links: triad/tests/test_worktree.py, triad/worktree.py
# Queries: "which repository do worktree tests run against", "why do the tests use a throwaway git repo", "how are test worktrees kept off the developer checkout"

"""A throwaway git repository for tests that create real worktrees.

These tests used to create worktrees against the developer's checkout, via
`get_repo_root(__file__)`. That borrowed the checkout's identity, and git worktrees
inherit their parent's hooks, so a test that committed inside a worktree fired the
developer's installed pre-commit hook — which runs `triad gate --worktree`, i.e. the
whole test suite plus an advisor call. On a machine with the hook installed, one test
took 675s instead of a few seconds; on CI, where nothing is installed, it was fast.
The suite was measuring the machine, not the code.

This module builds a repository that owns nothing but itself: a fresh `git init`, one
commit, an explicit identity, and a hooks path pointed at an empty directory so that a
global `core.hooksPath` cannot reintroduce the problem. `atexit` removes it, so the
leftovers that previously accumulated in %TEMP% do not get created at all.
"""

import atexit
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

_ROOT: Optional[Path] = None


def _git(repo: Path, *args: str, env: Optional[dict] = None) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def _build() -> Path:
    root = Path(tempfile.mkdtemp(prefix="triad-isolated-repo-")).resolve()
    hooks = root / ".no-hooks"
    hooks.mkdir()

    # Keep the user's global/system config out of the fixture: a stray core.hooksPath,
    # templateDir or init.defaultBranch would otherwise leak into every assertion.
    empty_global = root / ".empty-gitconfig"
    empty_global.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = str(empty_global)
    env["GIT_CONFIG_SYSTEM"] = str(empty_global)
    env["GIT_TERMINAL_PROMPT"] = "0"

    _git(root, "init", "-q", env=env)
    _git(root, "config", "user.name", "Triad Test", env=env)
    _git(root, "config", "user.email", "triad-test@example.invalid", env=env)
    _git(root, "config", "core.hooksPath", str(hooks), env=env)
    _git(root, "config", "commit.gpgsign", "false", env=env)

    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "seed.txt", env=env)
    _git(root, "commit", "-qm", "seed", env=env)
    _git(root, "branch", "-M", "master", env=env)
    return root


def isolated_repo_root() -> Path:
    """The shared throwaway repository for this process, created on first use."""
    global _ROOT
    if _ROOT is None:
        _ROOT = _build()
        atexit.register(shutil.rmtree, _ROOT, True)
    return _ROOT
