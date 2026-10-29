"""
Autonomous Multi-Agent Triad: Sync Manager (sync_manager.py).

Provides automated ecosystem synchronization across:
1. Runtime Engine: Repos -> ~/.agents/triad (validates/establishes NTFS junctions)
2. CLI Launchers: triad/bin -> ~/.local/bin (ensures system-wide PATH availability)
3. Advisory Skill Bridge: skills/claude-advisor -> ~/.agents/skills/claude-advisor
4. Multi-Repo Git Hooks: Installs/verifies Triad pre-commit gate in active repos
5. Configuration & Advisors: Aligns advisors.json preserving custom registrations
"""

from __future__ import annotations

import os
import time
import uuid
import json
import shutil
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

try:
    from triad.paths import TRIAD_DIR, HOME, LOCAL_APPDATA
except ImportError:
    TRIAD_DIR = Path(__file__).resolve().parent
    HOME = Path.home()
    LOCAL_APPDATA = Path(os.environ.get("LOCALAPPDATA", str(HOME / "AppData" / "Local")))

def get_default_repos() -> List[Path]:
    """Retrieve list of default ecosystem repositories dynamically, supporting TRIAD_SYNC_REPOS."""
    env_repos = os.environ.get("TRIAD_SYNC_REPOS")
    if env_repos:
        sep = os.pathsep if os.pathsep in env_repos else ","
        return [Path(p.strip()) for p in env_repos.split(sep) if p.strip()]
    projects_dir = HOME / "projects"
    candidates = [
        projects_dir / "autonomous-triad",
        projects_dir / "sovereign-exocortex",
        projects_dir / "agent-mesh-mcp",
        projects_dir / "bear-house-classic",
    ]
    return [p for p in candidates if (p / ".git").exists()]


DEFAULT_REPOS = get_default_repos()

HOOK_MARKER = "# AUTONOMOUS TRIAD PRE-COMMIT GATE HOOK"


def _file_hash(path: Path, normalize_newlines: bool = False) -> Optional[str]:
    """Compute sha256 of file for change detection. Returns None on error."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            content = f.read()
            if normalize_newlines:
                content = content.replace(b"\r\n", b"\n")
            h.update(content)
        return h.hexdigest()
    except Exception:
        return None


def _norm_path_str(p: Any) -> str:
    r"""Normalize path string across Windows and POSIX, stripping \\?\ and \??\ device prefixes."""
    s = str(p)
    if s.startswith(("\\\\?\\UNC\\", "//?/UNC/", "\\??\\UNC\\", "/??/UNC/")):
        s = "\\\\" + s[8:]
    elif s.startswith(("\\\\?\\", "//?/", "\\??\\", "/??/")):
        s = s[4:]
    s = s.replace("\\", "/")
    if len(s) > 3 or (len(s) == 3 and s[1] != ":"):
        s = s.rstrip("/")
    return s.lower() if os.name == "nt" else s


def _is_junction_or_link(path: Path) -> Tuple[bool, Optional[str]]:
    """Determine if directory is an NTFS junction or symlink and resolve target."""
    try:
        if os.name == "nt":
            if hasattr(os.path, "isjunction") and os.path.isjunction(str(path)):
                try:
                    target = os.readlink(str(path))
                    return True, _norm_path_str(target)
                except OSError:
                    return True, None
            if path.is_symlink():
                return True, _norm_path_str(path.resolve())
            import ctypes
            FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attrs != -1 and (attrs & FILE_ATTRIBUTE_REPARSE_POINT):
                try:
                    target = os.readlink(str(path))
                    return True, _norm_path_str(target)
                except OSError:
                    return False, None
        elif path.is_symlink():
            return True, _norm_path_str(path.resolve())
    except Exception:
        pass
    return False, None


def _rm_link(p: Path) -> bool:
    """Safely remove a symlink or NTFS junction without deleting target contents."""
    try:
        if os.name == "nt":
            os.rmdir(str(p))
        else:
            p.unlink()
    except OSError:
        pass
    if os.name == "nt" and os.path.lexists(str(p)):
        subprocess.run(["cmd", "/c", "rmdir", str(p)], capture_output=True)
    return not os.path.lexists(str(p))


def _prune_old_backups(parent_dir: Path, keep: int = 5, protect: Optional[Path] = None):
    """Keep only the newest N backup directories to prevent unbounded growth."""
    try:
        protect_resolved = protect.resolve() if protect and protect.exists() else None
        backups = sorted(
            [d for d in parent_dir.glob("triad_backup_*") if d.is_dir() and (protect_resolved is None or d.resolve() != protect_resolved)],
            key=lambda d: d.name
        )
        while len(backups) > keep:
            old = backups.pop(0)
            shutil.rmtree(str(old), ignore_errors=True)
    except Exception:
        pass


def _create_link_or_junction(link_path: Path, target_path: Path) -> bool:
    """Creates an NTFS junction on Windows or symlink on POSIX."""
    if os.name == "nt":
        target_str = str(target_path.resolve())
        link_str = str(link_path.resolve())
        try:
            import _winapi
            _winapi.CreateJunction(target_str, link_str)
            return True
        except Exception:
            pass
        res = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link_str, target_str],
            capture_output=True,
            text=True
        )
        return res.returncode == 0
    else:
        try:
            link_path.symlink_to(target_path.resolve())
            return True
        except Exception:
            return False


def _clear_target(p: Path):
    """Safely clear link or directory without following reparse points into real source content."""
    is_link, _ = _is_junction_or_link(p)
    if is_link:
        _rm_link(p)
    elif os.path.lexists(str(p)):
        shutil.rmtree(str(p), ignore_errors=True)


def _clean_link_target(raw: Optional[str]) -> Optional[str]:
    """Strip device prefixes from raw readlink string without lowercasing."""
    if not raw:
        return None
    s = raw
    if s.startswith(("\\\\?\\UNC\\", "//?/UNC/", "\\??\\UNC\\", "/??/UNC/")):
        return "\\\\" + s[8:]
    elif s.startswith(("\\\\?\\", "//?/", "\\??\\", "/??/")):
        return s[4:]
    return s


def _save_custom_advisors_overlay(backup_advisors_path: Path, overlay_path: Path, repo_advisors_path: Path) -> Optional[str]:
    """Preserves custom advisors in a local overlay file rather than mutating tracked git repo files."""
    try:
        if not backup_advisors_path.exists() or not repo_advisors_path.exists():
            return None
        with open(backup_advisors_path, "r", encoding="utf-8", errors="replace") as f:
            b_data = json.load(f)
        with open(repo_advisors_path, "r", encoding="utf-8", errors="replace") as f:
            r_data = json.load(f)

        def _nm(a):
            return str(a.get("name") or "").lower() if isinstance(a, dict) else ""

        repo_names = {_nm(a) for a in r_data.get("advisors", [])} - {""}

        existing_advisors = []
        if overlay_path.exists():
            try:
                with open(overlay_path, "r", encoding="utf-8", errors="replace") as f:
                    existing_advisors = json.load(f).get("advisors", [])
            except Exception:
                existing_advisors = []

        seen_names = {_nm(a) for a in existing_advisors} - {""}
        merged = list(existing_advisors)

        for adv in b_data.get("advisors", []):
            name = _nm(adv)
            if name and name not in repo_names and name not in seen_names:
                merged.append(adv)
                seen_names.add(name)

        if merged:
            overlay_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_overlay = overlay_path.parent / f".{overlay_path.name}.tmp"
            with open(tmp_overlay, "w", encoding="utf-8") as f:
                json.dump({"advisors": merged}, f, indent=2)
            os.replace(str(tmp_overlay), str(overlay_path))
        return None
    except Exception as e:
        return f"Failed saving custom advisors overlay: {e}"


def sync_engine(
    repo_triad: Path,
    target_triad: Path,
    dry_run: bool = False,
    lock_timeout: float = 5.0
) -> Dict[str, Any]:
    """
    Synchronizes the triad engine into target_triad (~/.agents/triad).
    Prefers creating an NTFS directory junction on Windows for zero-copy real-time drift prevention.
    """
    result: Dict[str, Any] = {
        "component": "engine",
        "source": str(repo_triad),
        "target": str(target_triad),
        "status": "up_to_date",
        "action_taken": "none",
        "detail": ""
    }

    if not repo_triad.exists():
        result["status"] = "error"
        result["detail"] = f"Source directory {repo_triad} does not exist"
        return result

    r = repo_triad.resolve()
    is_link, target = _is_junction_or_link(target_triad)

    # Containment & Self-Deletion Guards (test anchor without following leaf junction)
    anchor = target_triad.parent.resolve() / target_triad.name
    if anchor == r and not is_link:
        result["status"] = "error"
        result["detail"] = "Source and target resolve to the exact same physical directory; aborting to prevent self-deletion."
        return result
    if anchor in r.parents or (r in anchor.parents and not is_link):
        result["status"] = "error"
        result["detail"] = "Source and target cannot be parents/ancestors of each other; aborting to prevent circular containment."
        return result

    if os.path.lexists(str(target_triad)) and is_link and os.path.exists(str(target_triad)):
        try:
            if os.path.samefile(str(target_triad), str(repo_triad)):
                result["status"] = "junction_ok"
                result["detail"] = f"Live junction active: {target_triad} -> {repo_triad}"
                return result
        except OSError:
            pass

    if dry_run:
        result["status"] = "drift_detected"
        result["action_taken"] = "would_link"
        result["detail"] = f"Would establish junction: {target_triad} -> {repo_triad}"
        return result

    # Ensure parent directory exists
    target_triad.parent.mkdir(parents=True, exist_ok=True)

    # Acquire OS-level file lock with non-blocking retry to prevent races
    lock_file = target_triad.parent / ".triad_sync.lock"
    lock_fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR)
    deadline = time.monotonic() + lock_timeout
    while True:
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(lock_fd, 0, 0)
                msvcrt.locking(lock_fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() > deadline:
                os.close(lock_fd)
                result["status"] = "error"
                result["detail"] = "Sync lock held by another process; timeout waiting for lock."
                return result
            time.sleep(0.05)

    try:
        # Re-check state inside locked section to eliminate TOCTOU window
        r = repo_triad.resolve()
        is_link, target = _is_junction_or_link(target_triad)

        anchor = target_triad.parent.resolve() / target_triad.name
        if anchor == r and not is_link:
            result["status"] = "error"
            result["detail"] = "Source and target resolve to the exact same physical directory; aborting."
            return result
        if anchor in r.parents or (r in anchor.parents and not is_link):
            result["status"] = "error"
            result["detail"] = "Source and target cannot be parents/ancestors of each other; aborting."
            return result

        if os.path.lexists(str(target_triad)) and is_link and os.path.exists(str(target_triad)):
            try:
                if os.path.samefile(str(target_triad), str(repo_triad)):
                    result["status"] = "junction_ok"
                    result["detail"] = f"Live junction active: {target_triad} -> {repo_triad}"
                    return result
            except OSError:
                pass

        backup = target_triad.parent / f"triad_backup_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        backed_up = False
        raw_old_link_target = None
        if is_link:
            try:
                raw_old_link_target = os.readlink(str(target_triad))
            except OSError:
                raw_old_link_target = None

        if os.path.lexists(str(target_triad)) and not is_link:
            try:
                os.rename(str(target_triad), str(backup))
                backed_up = True
                overlay_err = _save_custom_advisors_overlay(backup / "advisors.json", target_triad.parent / "advisors.local.json", repo_triad / "advisors.json")
                if overlay_err:
                    result["detail"] = (result.get("detail", "") + f" ({overlay_err})").strip()
            except OSError as e:
                result["status"] = "error"
                result["detail"] = f"Failed to atomically back up existing directory before junctioning: {e}"
                return result
        elif os.path.lexists(str(target_triad)) and is_link:
            if not _rm_link(target_triad):
                result["status"] = "error"
                result["detail"] = f"Failed removing existing junction at {target_triad}; aborting to prevent overwrite."
                return result

        if os.name == "nt":
            junction_ok = _create_link_or_junction(target_triad, repo_triad)

            if junction_ok:
                result["status"] = "synchronized"
                result["action_taken"] = "junction_created"
                result["detail"] = f"Created live NTFS junction: {target_triad} -> {repo_triad}"
                _prune_old_backups(target_triad.parent, keep=5, protect=backup)
            else:
                # Fallback to copy if junction fails
                try:
                    shutil.copytree(str(repo_triad), str(target_triad), dirs_exist_ok=True)
                    result["status"] = "warning"
                    result["action_taken"] = "copied"
                    result["detail"] = "Degraded to copy (NTFS junction creation failed; verify privileges)"
                    _prune_old_backups(target_triad.parent, keep=5, protect=backup)
                except Exception as e:
                    # Rollback backup or previous link on failure safely without deleting target
                    _clear_target(target_triad)
                    if backed_up and backup.exists():
                        try:
                            os.rename(str(backup), str(target_triad))
                        except Exception:
                            pass
                    elif raw_old_link_target:
                        clean_old = _clean_link_target(raw_old_link_target)
                        if clean_old:
                            _create_link_or_junction(target_triad, Path(clean_old))
                    result["status"] = "error"
                    result["detail"] = f"Failed creating junction and copy fallback failed: {e}"
        else:
            try:
                target_triad.symlink_to(repo_triad.resolve())
                result["status"] = "synchronized"
                result["action_taken"] = "symlink_created"
                result["detail"] = f"Created symlink: {target_triad} -> {repo_triad}"
                _prune_old_backups(target_triad.parent, keep=5, protect=backup)
            except Exception as e:
                _clear_target(target_triad)
                if backed_up and backup.exists():
                    try:
                        os.rename(str(backup), str(target_triad))
                    except Exception:
                        pass
                elif raw_old_link_target:
                    clean_old = _clean_link_target(raw_old_link_target)
                    if clean_old:
                        _create_link_or_junction(target_triad, Path(clean_old))
                result["status"] = "error"
                result["detail"] = f"Failed creating symlink: {e}"
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(lock_fd, 0, 0)
                msvcrt.locking(lock_fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            os.close(lock_fd)
        except Exception:
            pass

    return result


def sync_launchers(
    bin_source: Path,
    target_bin: Path,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Synchronizes triad CLI launchers (triad.cmd, triad.ps1, triad) into ~/.local/bin.
    Uses atomic temporary-file replacement to avoid batch script offset corruption on Windows.
    """
    result: Dict[str, Any] = {
        "component": "launchers",
        "source": str(bin_source),
        "target": str(target_bin),
        "status": "up_to_date",
        "action_taken": "none",
        "updated_files": [],
        "errors": [],
        "detail": "",
        "path_ok": False
    }

    if not bin_source.exists():
        result["status"] = "error"
        result["detail"] = f"Source directory {bin_source} does not exist"
        return result

    if not dry_run:
        target_bin.mkdir(parents=True, exist_ok=True)

    env_paths = [_norm_path_str(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    result["path_ok"] = _norm_path_str(target_bin) in env_paths

    launcher_names = ["triad.cmd", "triad.ps1", "triad", "tr.cmd", "tr.ps1"]
    updated = []

    for name in launcher_names:
        src = bin_source / name
        dst = target_bin / name
        if not src.exists():
            continue

        needs_copy = False
        if not dst.exists():
            needs_copy = True
        else:
            is_sh = (name == "triad")
            h_src = _file_hash(src, normalize_newlines=is_sh)
            h_dst = _file_hash(dst, normalize_newlines=is_sh)
            if h_src is None or h_dst is None or h_src != h_dst:
                needs_copy = True

        if needs_copy:
            updated.append(name)
            if not dry_run:
                tmp_dst = target_bin / f".{name}.{os.getpid()}.tmp"
                try:
                    if name == "triad":
                        content = src.read_bytes().replace(b"\r\n", b"\n")
                        tmp_dst.write_bytes(content)
                    else:
                        shutil.copy2(str(src), str(tmp_dst))
                    try:
                        tmp_dst.chmod(0o755)
                    except Exception:
                        pass
                    os.replace(str(tmp_dst), str(dst))
                except Exception as e:
                    result["errors"].append(f"{name}: {e}")
                finally:
                    if tmp_dst.exists():
                        try:
                            tmp_dst.unlink()
                        except Exception:
                            pass

    if result["errors"]:
        result["status"] = "error"
        result["detail"] = f"Failed copying some launchers: {'; '.join(result['errors'])}"
    elif updated:
        result["status"] = "drift_detected" if dry_run else "synchronized"
        result["action_taken"] = "would_copy" if dry_run else "copied"
        result["updated_files"] = updated
        result["detail"] = f"{'Would update' if dry_run else 'Updated'} launchers: {', '.join(updated)}"
    else:
        result["detail"] = "All launchers up to date with repository versions."

    return result


def sync_skills(
    skill_source: Path,
    target_skill: Path,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Synchronizes the claude-advisor skill to ~/.agents/skills/claude-advisor.
    """
    result: Dict[str, Any] = {
        "component": "skills",
        "source": str(skill_source),
        "target": str(target_skill),
        "status": "up_to_date",
        "action_taken": "none",
        "updated_files": [],
        "errors": [],
        "detail": ""
    }

    if not skill_source.exists():
        result["status"] = "error"
        result["detail"] = f"Source directory {skill_source} does not exist"
        return result

    if not dry_run:
        target_skill.mkdir(parents=True, exist_ok=True)

    updated = []

    for src_file in skill_source.rglob("*"):
        if not src_file.is_file() or "__pycache__" in src_file.parts or src_file.suffix == ".pyc":
            continue
        rel = src_file.relative_to(skill_source)
        dst_file = target_skill / rel

        needs_copy = False
        if not dst_file.exists():
            needs_copy = True
        else:
            h_src = _file_hash(src_file)
            h_dst = _file_hash(dst_file)
            if h_src is None or h_dst is None or h_src != h_dst:
                needs_copy = True

        if needs_copy:
            updated.append(str(rel))
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                tmp_file = dst_file.parent / f".{dst_file.name}.{os.getpid()}.tmp"
                try:
                    shutil.copy2(str(src_file), str(tmp_file))
                    os.replace(str(tmp_file), str(dst_file))
                except Exception as e:
                    result["errors"].append(f"{rel}: {e}")
                finally:
                    if tmp_file.exists():
                        try:
                            tmp_file.unlink()
                        except Exception:
                            pass

    # Prune deletion drift: remove target files that no longer exist in skill_source
    # Only prune if source actually contains valid skill files (prevents wiping on partial checkout)
    has_source_files = (skill_source / "SKILL.md").exists() or any(skill_source.glob("*.py")) or any(skill_source.glob("*.md"))
    deleted = []
    if target_skill.exists() and has_source_files:
        for dst_file in target_skill.rglob("*"):
            if not dst_file.is_file() or dst_file.is_symlink() or "__pycache__" in dst_file.parts or dst_file.suffix == ".pyc":
                continue
            rel = dst_file.relative_to(target_skill)
            src_file = skill_source / rel
            if not src_file.exists():
                deleted.append(str(rel))
                if not dry_run:
                    try:
                        dst_file.unlink()
                    except Exception as e:
                        result["errors"].append(f"delete {rel}: {e}")

    if result["errors"]:
        result["status"] = "error"
        result["detail"] = f"Failed syncing skill files: {'; '.join(result['errors'])}"
    elif updated or deleted:
        result["status"] = "drift_detected" if dry_run else "synchronized"
        result["action_taken"] = "would_sync" if dry_run else "synced"
        result["updated_files"] = updated
        result["deleted_files"] = deleted
        detail_parts = []
        if updated:
            detail_parts.append(f"{'Would copy' if dry_run else 'Copied'}: {', '.join(updated)}")
        if deleted:
            detail_parts.append(f"{'Would delete' if dry_run else 'Deleted'}: {', '.join(deleted)}")
        result["detail"] = "; ".join(detail_parts)
    else:
        result["detail"] = "Skill files up to date with repository versions."

    return result


def _resolve_repo_hooks_dir(repo: Path) -> Optional[Path]:
    """Resolve the git hooks directory using git rev-parse if possible, with .git/hooks fallback."""
    if not repo.exists():
        return None
    try:
        res = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-path", "hooks"],
            capture_output=True,
            text=True,
            timeout=2.0
        )
        if res.returncode == 0 and res.stdout.strip():
            raw_path = res.stdout.strip()
            hooks_p = Path(raw_path)
            if not hooks_p.is_absolute():
                hooks_p = (repo / hooks_p).resolve()
            return hooks_p
    except Exception:
        pass

    fallback = repo / ".git" / "hooks"
    if (repo / ".git").exists():
        return fallback
    return None


def sync_hooks(
    repos: Optional[List[Path]] = None,
    install_missing: bool = False,
    dry_run: bool = False
) -> List[Dict[str, Any]]:
    """
    Audits and synchronizes the Triad pre-commit hook across active ecosystem repos.
    Ensures pure LF line endings to prevent Windows bash CRLF syntax failures.
    """
    target_repos = repos if repos is not None else get_default_repos()
    repo_results = []

    for repo in target_repos:
        entry: Dict[str, Any] = {
            "repo": repo.name,
            "path": str(repo),
            "exists": repo.exists(),
            "hook_status": "missing",
            "action_taken": "none",
            "detail": ""
        }

        hooks_dir = _resolve_repo_hooks_dir(repo)
        if not hooks_dir:
            entry["detail"] = "Repository or .git folder not found on disk"
            repo_results.append(entry)
            continue

        hook_file = hooks_dir / "pre-commit"
        has_hook = hook_file.exists()

        if has_hook:
            try:
                content = hook_file.read_text(encoding="utf-8", errors="replace")
                if HOOK_MARKER in content or "triad gate" in content:
                    entry["hook_status"] = "installed"
                    entry["detail"] = "Triad pre-commit gate hook active"
                else:
                    entry["hook_status"] = "third_party"
                    entry["detail"] = "Third-party pre-commit hook present"
            except Exception as e:
                entry["hook_status"] = "error"
                entry["detail"] = f"Error reading hook: {e}"
        else:
            entry["hook_status"] = "not_installed"
            entry["detail"] = "No pre-commit hook installed"

        if install_missing and entry["hook_status"] == "not_installed":
            if dry_run:
                entry["action_taken"] = "would_install"
                entry["detail"] = "Would install Triad pre-commit gate hook"
            else:
                try:
                    hooks_dir.mkdir(parents=True, exist_ok=True)
                    template = (
                        "#!/bin/sh\n"
                        f"{HOOK_MARKER}\n"
                        "# Automatically verifies type safety, test suites, and Advisory Council review in an isolated worktree.\n\n"
                        "if [ \"$TRIAD_GATE_ACTIVE\" = \"1\" ]; then\n"
                        "    exit 0\n"
                        "fi\n\n"
                        "echo \"[Triad Hook] Running pre-commit gate...\"\n"
                        "if command -v triad >/dev/null 2>&1; then\n"
                        "    triad gate --worktree --apply-verified\n"
                        "    exit $?\n"
                        "elif command -v python >/dev/null 2>&1 && python -c \"import triad\" >/dev/null 2>&1; then\n"
                        "    python -m triad gate --worktree --apply-verified\n"
                        "    exit $?\n"
                        "else\n"
                        "    echo \"[Triad Hook Warning] Triad CLI not found on PATH or via python module; skipping gate.\"\n"
                        "    exit 0\n"
                        "fi\n"
                    )
                    # Strictly write binary UTF-8 with LF only (\n) to prevent CRLF \r errors in sh
                    hook_file.write_bytes(template.encode("utf-8"))
                    try:
                        hook_file.chmod(0o755)
                    except Exception:
                        pass
                    entry["hook_status"] = "installed"
                    entry["action_taken"] = "installed"
                    entry["detail"] = "Installed Triad pre-commit gate hook"
                except Exception as e:
                    entry["hook_status"] = "error"
                    entry["detail"] = f"Failed installing hook: {e}"

        repo_results.append(entry)

    return repo_results


def _find_git_root(start_dir: Path) -> Path:
    """Find the git root of the repository containing start_dir."""
    try:
        res = subprocess.run(
            ["git", "-C", str(start_dir), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2.0
        )
        if res.returncode == 0 and res.stdout.strip():
            return Path(res.stdout.strip()).resolve()
    except Exception:
        pass
    return start_dir.parent


def run_full_sync(
    repo_root: Optional[Path] = None,
    dry_run: bool = False,
    sync_all: bool = False,
    include_engine: bool = True,
    include_launchers: bool = True,
    include_skills: bool = True,
    include_hooks: bool = False,
    repos: Optional[List[Path]] = None
) -> Dict[str, Any]:
    """
    Executes a comprehensive Triad synchronization pass with granular component selection.
    """
    root = repo_root or _find_git_root(TRIAD_DIR)
    home = Path.home()
    triad_dir = home / ".agents" / "triad"
    local_bin = home / ".local" / "bin"
    skill_dir = home / ".agents" / "skills" / "claude-advisor"
    target_repos = repos if repos is not None else get_default_repos()

    # Determine which components to execute
    do_all = sync_all or (include_engine and include_launchers and include_skills and not include_hooks)
    do_engine = do_all or include_engine
    do_launchers = do_all or include_launchers
    do_skills = do_all or include_skills
    do_hooks = sync_all or include_hooks

    engine_res = sync_engine(root / "triad", triad_dir, dry_run=dry_run) if do_engine else {"component": "engine", "status": "skipped", "detail": "Skipped per flags"}
    launchers_res = sync_launchers(root / "bin", local_bin, dry_run=dry_run) if do_launchers else {"component": "launchers", "status": "skipped", "detail": "Skipped per flags"}
    skills_res = sync_skills(root / "skills" / "claude-advisor", skill_dir, dry_run=dry_run) if do_skills else {"component": "skills", "status": "skipped", "detail": "Skipped per flags"}
    hooks_res = sync_hooks(target_repos, install_missing=(sync_all or include_hooks), dry_run=dry_run) if (do_hooks or do_all) else []

    has_error = (
        any(res.get("status") in ("error", "failed") for res in [engine_res, launchers_res, skills_res] if res.get("status") != "skipped")
        or any(h.get("hook_status") == "error" or "Failed" in h.get("detail", "") or "Error" in h.get("detail", "") for h in hooks_res)
    )

    return {
        "engine": engine_res,
        "launchers": launchers_res,
        "skills": skills_res,
        "hooks": hooks_res,
        "dry_run": dry_run,
        "has_error": has_error,
        "repo_root": str(root)
    }
