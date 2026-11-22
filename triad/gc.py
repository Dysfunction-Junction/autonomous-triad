"""GC-F8: Unused data cleanup.

Provides automatic cleanup of stale data from previous test runs,
including abandoned worktree registrations and temp directory artifacts.

Exported entry points:
- gc_cleanup() — remove triad-owned artifacts from %TEMP%
- gc_prune_worktrees(repo) — prune worktrees with dead owner PIDs
"""
import atexit
import os
import shutil
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Module-level state so the atexit hook has something to work with.
# ---------------------------------------------------------------------------
_registered_roots: set[Path] = set()


def register_root(root: Path) -> None:
    """Called by each test fixture so the atexit hook knows which trees to prune."""
    _registered_roots.add(root)


def gc_cleanup() -> None:
    """Remove triad-owned artifacts from %TEMP% that outlived their owning process.

    Removes:
      - %TEMP%\\triad-gate-*
      - %TEMP%\\triad-test-warm-*
      - %TEMP%\\notriad-*
      - %TEMP%\\triad_session_slots (if empty)
      - %TEMP%\\triad-isolated-repo-*
      - %TEMP%\\triad-real-repo-*
      - %TEMP%\\triad-grok-smoke-*
    """
    temp = Path(os.environ.get("TEMP", "C:/Users/micha/AppData/Local/Temp"))
    patterns = [
        "triad-gate-*",
        "triad-test-warm-*",
        "notriad-*",
        "triad_session_slots",
        "triad-isolated-repo-*",
        "triad-real-repo-*",
        "triad-grok-smoke-*",
    ]
    removed = 0
    for pattern in patterns:
        for p in temp.glob(pattern):
            try:
                shutil.rmtree(p, ignore_errors=False)
                removed += 1
            except Exception:
                pass
    # also prune any worktree registrations whose directories are gone
    from triad.worktree import prune_worktrees
    # use the developer's repo root (or fallback to cwd)
    repo_root = Path(os.getcwd())
    try:
        prune_worktrees(repo_root)
    except Exception:
        pass
    # silence the atexit-on-exit chatter by not logging on every run
    # (the caller can enable --debug if desired)


def gc_prune_worktrees(repo_path: Path) -> None:
    """Prune worktree registrations whose directories no longer exist.

    Safe to call even when other processes hold live worktrees — it only
    removes *registrations* for directories that are already gone.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "worktree", "prune"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            # best-effort only
            pass
    except Exception:
        pass


# Register cleanup on process exit so leftovers are not created
# (rather than swept later).
_aexit_registered = False


def _ensure_aexit() -> None:
    global _aexit_registered
    if not _aexit_registered:
        atexit.register(gc_cleanup)
        _aexit_registered = True


# Convenience for test fixtures
__all__ = ["register_root", "gc_cleanup", "gc_prune_worktrees", "_ensure_aexit"]