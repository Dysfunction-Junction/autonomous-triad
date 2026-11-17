"""Patch application, rollback, tree-snapshot, and working-tree fingerprinting."""

# Tags: patching, worktree, verification
# Links: triad/worktree.py, triad/triad_engine.py
# Queries: "how is a patch applied and rolled back", "what is a tree snapshot", "how is the working tree fingerprinted"

import ast
import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


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


clean_git_env = _eng_call("clean_git_env")
get_provisioned_manifest_entries = _eng_call("get_provisioned_manifest_entries")
is_reparse_or_link = _eng_call("is_reparse_or_link")
kill_process_tree = _eng_call("kill_process_tree")
query_advisory_council = _eng_call("query_advisory_council")
query_competition_council = _eng_call("query_competition_council")


def apply_patch_text(patch_text: str, cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None, allow_3way: bool = False) -> bool:
    """Extracts unified diff from model response, validates with git apply --check, and applies it."""
    import re
    # Extract fenced code blocks or raw diff
    m = re.search(r"```(?:diff|patch)?\s*\n(.*?)```", patch_text, re.DOTALL)
    raw_diff = m.group(1).strip() if m else patch_text.strip()

    # Verify minimum diff headers
    has_diff_headers = (
        ("diff --git " in raw_diff or ("--- " in raw_diff and "+++" in raw_diff))
        and "@@ " in raw_diff
    )
    if not has_diff_headers:
        return False

    target_dir = cwd or Path.cwd()
    exec_env = env if env is not None else clean_git_env()

    # Create safe unique temp patch file
    fd, temp_patch_path = tempfile.mkstemp(suffix=".patch", prefix="triad_heal_")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(raw_diff + "\n")

        # 1. Check dry-run with whitespace tolerance for Windows
        check_cmd = ["git", "apply", "--check", "--whitespace=fix", "--ignore-whitespace", "--", temp_patch_path]
        check_res = subprocess.run(check_cmd, cwd=str(target_dir), env=exec_env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if check_res.returncode != 0:
            if not allow_3way:
                return False
            # Fallback retry with 3-way merge (strictly isolated to ephemeral worktrees)
            check_cmd = ["git", "apply", "--check", "--3way", "--", temp_patch_path]
            check_res = subprocess.run(check_cmd, cwd=str(target_dir), env=exec_env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if check_res.returncode != 0:
                return False
            apply_cmd = ["git", "apply", "--3way", "--", temp_patch_path]
        else:
            apply_cmd = ["git", "apply", "--whitespace=fix", "--ignore-whitespace", "--", temp_patch_path]

        # 2. Apply patch
        apply_res = subprocess.run(apply_cmd, cwd=str(target_dir), env=exec_env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return apply_res.returncode == 0
    except Exception:
        return False
    finally:
        if os.path.exists(temp_patch_path):
            try:
                os.remove(temp_patch_path)
            except Exception:
                pass

def _modes_match(mode1: Optional[int], mode2: Optional[int], is_git_comparison: bool = False) -> bool:
    """
    Compare file permission modes, normalizing for OS differences and Git executable bit semantics.
    On Unix:
    - If is_git_comparison is False (default): Compares exact 0o777 bits between filesystem states.
    - If is_git_comparison is True: Normalizes git tree modes (0o644 / 0o755) against filesystem modes
      (e.g. 0o664 / 0o775) by checking executable bit parity (0o111).
    On Windows (nt):
    - Windows does not track POSIX group/other or execute bits; stat() only reflects read-only flag.
      Checks read-only bit parity (0o200 / stat.S_IWRITE). If is_git_comparison is True and executable
      bits are present, also rejects executable status mismatch.
    """
    if mode1 is None or mode2 is None:
        return mode1 == mode2
    m1 = mode1 & 0o777
    m2 = mode2 & 0o777
    if m1 == m2:
        return True
    if is_git_comparison:
        if bool(m1 & 0o111) != bool(m2 & 0o111):
            return False
        if os.name == "nt":
            return bool(m1 & 0o200) == bool(m2 & 0o200)
        is_m1_git = (m1 in (0o644, 0o755))
        is_m2_git = (m2 in (0o644, 0o755))
        if is_m1_git or is_m2_git:
            return True
        return False
    if os.name == "nt":
        return bool(m1 & 0o200) == bool(m2 & 0o200)
    return False


@contextlib.contextmanager
def acquire_repo_mutation_lock(repo_root: Union[str, Path]):
    """
    Acquire an exclusive cooperative lock across patch application and rollback phases.
    Prevents concurrent writers from interleaving mutations in the same repository.
    Ensures lockfile always resides in git metadata or system temp, never in the working tree.
    """
    repo_path = Path(repo_root).resolve()
    lock_file = None
    try:
        ret, out, _ = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "rev-parse", "--git-path", "triad_mutation.lock"], cwd=repo_path)
        if ret == 0 and out.strip():
            p = Path(out.strip())
            lock_file = p if p.is_absolute() else (repo_path / p).resolve()
    except Exception:
        pass

    if lock_file is None:
        git_dir = repo_path / ".git"
        if git_dir.is_dir():
            lock_file = git_dir / "triad_mutation.lock"
        elif git_dir.is_file():
            try:
                content = git_dir.read_text(encoding="utf-8", errors="replace").strip()
                if content.startswith("gitdir:"):
                    gitdir = content[len("gitdir:"):].strip()
                    lock_file = (Path(gitdir).resolve()) / "triad_mutation.lock"
            except Exception:
                pass
        if lock_file is None:
            import hashlib
            h = hashlib.sha256(str(repo_path).encode("utf-8")).hexdigest()[:12]
            if not re.fullmatch(r"[0-9a-f]{12}", h):
                raise ValueError("Computed mutation-lock hash was not a well-formed hex digest")
            lock_file = Path(tempfile.gettempdir()) / f"triad_mutation_{h}.lock"

    lock_file.parent.mkdir(parents=True, exist_ok=True)

    # O_NOFOLLOW: this path can fall back to a name derived from a hash of the
    # repo path inside the shared system temp directory, so it must never
    # follow a pre-planted symlink there.
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(str(lock_file), flags, 0o600)
    except OSError as e:
        raise RuntimeError(f"Could not open repository mutation lockfile {lock_file}: {e}")

    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except (OSError, IOError) as e:
                raise RuntimeError(f"Could not acquire repository mutation lock on {lock_file}: {e}")
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, IOError) as e:
                raise RuntimeError(f"Could not acquire repository mutation lock on {lock_file}: {e}")
        yield lock_file
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except Exception:
                    pass
        finally:
            try:
                os.close(fd)
            except Exception:
                pass


def _is_symlink_or_reparse(p: Union[str, Path]) -> bool:
    """Check if path is a symlink or a Windows reparse point / junction."""
    try:
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            return True
        if hasattr(st, "st_file_attributes"):
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            if bool(st.st_file_attributes & reparse_flag):
                return True
    except (FileNotFoundError, OSError):
        pass
    return False


def _validate_and_resolve_contained_path(target_dir: Path, rel_p: str) -> Optional[Path]:
    """
    Validates that rel_p is strictly contained within target_dir without resolving
    symlinks at the leaf path. Rejects traversal through symlink or Windows reparse/junction
    parent components outright.
    Enforces component-aware relative_to(target_dir) containment rather than string prefix.
    Returns lexical Path(target_dir / norm_rel) or None if traversal/escape detected.
    """
    norm_rel = os.path.normpath(rel_p)
    if os.path.isabs(norm_rel) or norm_rel.startswith("..") or norm_rel == ".":
        return None

    target_dir_real = target_dir.resolve()
    file_p = target_dir / norm_rel
    try:
        file_p.relative_to(target_dir)
    except ValueError:
        return None

    # Reject symlink and Windows reparse/junction parent components outright
    curr = target_dir
    parent_parts = Path(norm_rel).parent.parts
    for part in parent_parts:
        curr = curr / part
        if _is_symlink_or_reparse(curr):
            return None

    # Ensure parent directory (if it exists) is strictly contained in target_dir_real
    parent_dir = target_dir / Path(norm_rel).parent
    try:
        if parent_dir.exists():
            parent_dir.resolve().relative_to(target_dir_real)
    except (ValueError, OSError):
        return None

    return file_p


def parse_diff_tree_records(raw_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parse git diff-tree -r -z output into structured change records.
    Uses os.fsdecode for lossless round-trip path decoding.
    Rejects malformed or truncated records (fail-closed).
    """
    records = []
    tokens = raw_bytes.split(b"\x00")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    i = 0
    while i < len(tokens):
        meta_bytes = tokens[i].strip()
        if not meta_bytes:
            i += 1
            continue
        if not meta_bytes.startswith(b":"):
            raise ValueError(f"Malformed diff-tree record: {meta_bytes!r}")
        parts = meta_bytes[1:].split()
        if len(parts) < 5:
            raise ValueError(f"Incomplete diff-tree metadata: {meta_bytes!r}")
        src_mode = parts[0].decode("ascii", errors="strict")
        dst_mode = parts[1].decode("ascii", errors="strict")
        src_sha = parts[2].decode("ascii", errors="strict")
        dst_sha = parts[3].decode("ascii", errors="strict")
        status = parts[4].decode("ascii", errors="strict")
        i += 1
        if i >= len(tokens):
            raise ValueError("Truncated diff-tree stream: missing path")
        path1 = os.fsdecode(tokens[i])
        i += 1
        path2 = None
        if status.startswith("R") or status.startswith("C"):
            if i >= len(tokens):
                raise ValueError("Truncated diff-tree stream: missing rename/copy destination path")
            path2 = os.fsdecode(tokens[i])
            i += 1
        records.append({
            "src_mode": src_mode,
            "dst_mode": dst_mode,
            "src_sha": src_sha,
            "dst_sha": dst_sha,
            "status": status,
            "src_path": path1,
            "dst_path": path2 or path1,
            "is_rename_or_copy": bool(path2)
        })
    return records


def get_tree_entries(tree_oid: str, repo_dir: Path, env: Optional[Dict[str, str]] = None) -> Dict[str, Tuple[str, str, str]]:
    """
    Returns a dict mapping rel_path -> (mode, type, sha) for all entries in tree_oid.
    Uses git ls-tree -r -z.
    Raises RuntimeError on command failure or malformed records so enumeration failures cannot masquerade as empty trees.
    """
    ret, out, err = _eng("run_subprocess_tree_safe_bytes", run_subprocess_tree_safe_bytes)(["git", "ls-tree", "-r", "-z", tree_oid], cwd=repo_dir, env=env)
    if ret != 0:
        err_msg = err.decode("utf-8", errors="replace") if isinstance(err, bytes) else str(err)
        raise RuntimeError(f"git ls-tree failed for tree {tree_oid}: {err_msg.strip()}")
    res = {}
    tokens = out.split(b"\x00")
    for tok in tokens:
        if not tok:
            continue
        parts = tok.split(b"\t", 1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed git ls-tree record in tree {tree_oid}: {repr(tok)}")
        meta, path_bytes = parts
        rel_p = os.fsdecode(path_bytes)
        meta_parts = meta.split()
        if len(meta_parts) < 3:
            raise RuntimeError(f"Malformed git ls-tree metadata in tree {tree_oid}: {repr(meta)}")
        mode = meta_parts[0].decode("ascii", errors="replace")
        obj_type = meta_parts[1].decode("ascii", errors="replace")
        sha = meta_parts[2].decode("ascii", errors="replace")
        res[rel_p] = (mode, obj_type, sha)
    return res


def _content_matches(cur: Optional[bytes], expected: Optional[bytes]) -> bool:
    """Compare byte contents with CRLF/LF normalization to account for Git smudge/clean filters."""
    if cur == expected:
        return True
    if cur is None or expected is None:
        return False
    return cur.replace(b"\r\n", b"\n") == expected.replace(b"\r\n", b"\n")


def _restore_entry(p: Path, info: Dict[str, Any], target_dir: Path) -> bool:
    """
    Restore a single path to its original baseline state, returning True on success.
    Strict non-destructive best-effort rollback: opens regular files with O_NOFOLLOW | O_RDWR (or O_CREAT | O_EXCL),
    re-verifies exact bytes and permissions directly from the open descriptor before any mutation to eliminate
    TOCTOU windows, refuses destructive deletion of directories, and aborts if concurrent edits or ownership
    mismatches are detected. Rollback is strictly cooperative single-writer; on any conflict, user workspace
    state is preserved intact and the unmerged recovery patch (get_recovery_patch_path) serves as the safety net.
    """
    try:
        try:
            rel_p = str(p.relative_to(target_dir))
        except ValueError:
            return False
        if _validate_and_resolve_contained_path(target_dir, rel_p) is None:
            return False

        if info["is_symlink"]:
            try:
                st = os.lstat(p)
                is_link = stat.S_ISLNK(st.st_mode)
                is_real_dir = stat.S_ISDIR(st.st_mode)
            except (FileNotFoundError, OSError):
                st = None
                is_link = False
                is_real_dir = False

            if is_real_dir:
                print(f"⚠️ [Triad Conflict] Path {p} is a real directory; refusing destructive removal during symlink rollback.", file=sys.stderr)
                return False

            if is_link:
                expected_link = info.get("expected_target_link")
                if expected_link is not None:
                    try:
                        cur_link = os.readlink(p)
                        if cur_link != expected_link:
                            print(f"⚠️ [Triad Conflict] Symlink target on {p} modified concurrently during rollback. Preserving symlink.", file=sys.stderr)
                            return False
                    except OSError:
                        return False
                else:
                    print(f"⚠️ [Triad Conflict] Symlink on {p} was not expected by mutation during rollback. Refusing destructive removal.", file=sys.stderr)
                    return False
                p.unlink()
            elif p.exists():
                expected_bytes = info.get("expected_target_bytes")
                if expected_bytes is not None:
                    try:
                        if p.read_bytes() != expected_bytes:
                            print(f"⚠️ [Triad Conflict] File content on {p} modified concurrently during rollback. Preserving user path.", file=sys.stderr)
                            return False
                    except OSError:
                        return False
                    p.unlink()
                else:
                    print(f"⚠️ [Triad Conflict] Path {p} was replaced with a non-symlink concurrently during rollback. Preserving user path.", file=sys.stderr)
                    return False
            os.symlink(info["link_target"], p)
            return True
        elif info["is_regular"]:
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                st = os.lstat(p)
                is_real_dir = stat.S_ISDIR(st.st_mode)
            except (FileNotFoundError, OSError):
                is_real_dir = False
            if is_real_dir:
                print(f"⚠️ [Triad Conflict] Path {p} is a real directory; refusing destructive removal during regular file rollback.", file=sys.stderr)
                return False

            # If operation had deleted this file (expected_target_exists is False),
            # any existing path or symlink means it was recreated concurrently. We must refuse to overwrite it!
            if info.get("expected_target_exists") is False:
                if p.is_symlink() or p.exists():
                    print(f"⚠️ [Triad Conflict] Path {p} was recreated concurrently during rollback. Preserving user path.", file=sys.stderr)
                    return False

            target_mode = info.get("mode")
            if p.is_symlink():
                expected_target_is_link = info.get("expected_target_is_link")
                expected_target_link = info.get("expected_target_link")
                if not expected_target_is_link or expected_target_link is None:
                    print(f"⚠️ [Triad Conflict] Path {p} has unexpected symlink during regular file rollback. Preserving user path.", file=sys.stderr)
                    return False
                try:
                    cur_link = os.readlink(p)
                    if cur_link != expected_target_link:
                        print(f"⚠️ [Triad Conflict] Symlink target on {p} modified concurrently during regular file rollback. Preserving symlink.", file=sys.stderr)
                        return False
                except OSError:
                    return False
                p.unlink()
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                file_mode = target_mode or 0o666
                try:
                    fd = os.open(str(p), flags, file_mode)
                except OSError:
                    return False
                try:
                    data = info["bytes"]
                    total_written = 0
                    while total_written < len(data):
                        n = os.write(fd, data[total_written:])
                        if n <= 0:
                            raise OSError("os.write made zero progress during restoration")
                        total_written += n
                    if target_mode is not None and os.name != "nt":
                        if hasattr(os, "fchmod"):
                            os.fchmod(fd, target_mode)
                        else:
                            os.chmod(str(p), target_mode)
                        if (os.fstat(fd).st_mode & 0o777) != (target_mode & 0o777):
                            return False
                finally:
                    os.close(fd)
            elif p.exists():
                flags = os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                try:
                    fd = os.open(str(p), flags)
                except OSError:
                    return False
                try:
                    if os.name == "nt":
                        import msvcrt
                        try:
                            os.lseek(fd, 0, os.SEEK_SET)
                            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                        except (OSError, IOError) as e:
                            print(f"⚠️ [Triad Conflict] Could not acquire lock on {p} during rollback: {e}. Preserving user path.", file=sys.stderr)
                            return False
                    else:
                        import fcntl
                        try:
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except (OSError, IOError) as e:
                            print(f"⚠️ [Triad Conflict] Could not acquire lock on {p} during rollback: {e}. Preserving user path.", file=sys.stderr)
                            return False

                    fd_st = os.fstat(fd)
                    if not stat.S_ISREG(fd_st.st_mode):
                        return False

                    # Read all descriptor bytes directly from open fd
                    cur_fd_bytes = b""
                    while True:
                        chunk = os.read(fd, 65536)
                        if not chunk:
                            break
                        cur_fd_bytes += chunk

                    needs_mode_restore = False
                    if target_mode is not None and os.name != "nt":
                        if (fd_st.st_mode & 0o777) != (target_mode & 0o777):
                            needs_mode_restore = True

                    # Exact byte equality check: if already matches baseline bytes:
                    if cur_fd_bytes == info["bytes"]:
                        if needs_mode_restore:
                            try:
                                if hasattr(os, "fchmod"):
                                    os.fchmod(fd, target_mode)
                                else:
                                    os.chmod(str(p), target_mode)
                                cur_mode = os.fstat(fd).st_mode & 0o777
                                if cur_mode != (target_mode & 0o777):
                                    return False
                            except Exception as e:
                                print(f"⚠️ [Triad Rollback Error] Failed restoring mode on {p}: {e}", file=sys.stderr)
                                return False
                        return True

                    # Verify descriptor content matches expected target bytes (exact byte equality)
                    expected_target = info.get("expected_target_bytes")
                    if expected_target is not None and cur_fd_bytes != expected_target:
                        # Descriptor content mutated concurrently!
                        return False

                    # Re-verify stat and re-read descriptor bytes immediately before truncate to guard against TOCTOU
                    pre_st = os.fstat(fd)
                    if pre_st.st_size != len(cur_fd_bytes):
                        return False

                    os.lseek(fd, 0, os.SEEK_SET)
                    pre_bytes = b""
                    while True:
                        chunk = os.read(fd, 65536)
                        if not chunk:
                            break
                        pre_bytes += chunk
                    if pre_bytes != cur_fd_bytes:
                        return False

                    os.ftruncate(fd, 0)
                    os.lseek(fd, 0, os.SEEK_SET)
                    data = info["bytes"]
                    total_written = 0
                    while total_written < len(data):
                        n = os.write(fd, data[total_written:])
                        if n <= 0:
                            raise OSError("os.write made zero progress during restoration")
                        total_written += n

                    if target_mode is not None and os.name != "nt":
                        try:
                            if hasattr(os, "fchmod"):
                                os.fchmod(fd, target_mode)
                            else:
                                os.chmod(str(p), target_mode)
                            cur_mode = os.fstat(fd).st_mode & 0o777
                            if cur_mode != (target_mode & 0o777):
                                return False
                        except Exception as e:
                            print(f"⚠️ [Triad Rollback Error] Failed restoring mode on {p}: {e}", file=sys.stderr)
                            return False
                finally:
                    if os.name == "nt":
                        import msvcrt
                        try:
                            os.lseek(fd, 0, os.SEEK_SET)
                            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                        except Exception:
                            pass
                    else:
                        import fcntl
                        try:
                            fcntl.flock(fd, fcntl.LOCK_UN)
                        except Exception:
                            pass
                    os.close(fd)
            else:
                # Newly created paths during restoration use O_CREAT | O_EXCL
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                file_mode = target_mode or 0o666
                try:
                    fd = os.open(str(p), flags, file_mode)
                except OSError:
                    return False
                try:
                    data = info["bytes"]
                    total_written = 0
                    while total_written < len(data):
                        n = os.write(fd, data[total_written:])
                        if n <= 0:
                            raise OSError("os.write made zero progress during restoration")
                        total_written += n
                    if target_mode is not None and os.name != "nt":
                        if hasattr(os, "fchmod"):
                            os.fchmod(fd, target_mode)
                        else:
                            os.chmod(str(p), target_mode)
                        if (os.fstat(fd).st_mode & 0o777) != (target_mode & 0o777):
                            return False
                finally:
                    os.close(fd)

            # Verify restored regular file bytes with exact byte equality
            if p.read_bytes() != info["bytes"]:
                return False

            if target_mode is not None and os.name != "nt":
                if (os.lstat(p).st_mode & 0o777) != (target_mode & 0o777):
                    return False
            return True
        elif not info["existed"]:
            if p.is_dir():
                print(f"⚠️ [Triad Conflict] Path {p} is a directory; refusing destructive removal during rollback.", file=sys.stderr)
                return False
            if p.is_symlink():
                try:
                    cur_link = os.readlink(p)
                    if info.get("expected_target_link") is not None and cur_link != info.get("expected_target_link"):
                        print(f"⚠️ [Triad Conflict] Symlink target on {p} modified concurrently during rollback. Preserving symlink.", file=sys.stderr)
                        return False
                except OSError:
                    return False
                p.unlink()
                return True
            if p.is_file():
                flags = os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                try:
                    fd = os.open(str(p), flags)
                except OSError:
                    return False
                try:
                    if os.name == "nt":
                        import msvcrt
                        try:
                            os.lseek(fd, 0, os.SEEK_SET)
                            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                        except (OSError, IOError) as e:
                            print(f"⚠️ [Triad Conflict] Could not acquire lock on {p} during rollback: {e}. Preserving file.", file=sys.stderr)
                            return False
                    else:
                        import fcntl
                        try:
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except (OSError, IOError) as e:
                            print(f"⚠️ [Triad Conflict] Could not acquire lock on {p} during rollback: {e}. Preserving file.", file=sys.stderr)
                            return False
                    cur_bytes = b""
                    while True:
                        chunk = os.read(fd, 65536)
                        if not chunk:
                            break
                        cur_bytes += chunk
                    if info.get("expected_target_bytes") is not None and cur_bytes != info.get("expected_target_bytes"):
                        print(f"⚠️ [Triad Conflict] Concurrent write detected on newly created file {p} before unlink. Preserving file.", file=sys.stderr)
                        return False
                finally:
                    if os.name == "nt":
                        import msvcrt
                        try:
                            os.lseek(fd, 0, os.SEEK_SET)
                            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                        except Exception:
                            pass
                    else:
                        import fcntl
                        try:
                            fcntl.flock(fd, fcntl.LOCK_UN)
                        except Exception:
                            pass
                    os.close(fd)
                p.unlink()
                return True
            return True
        return True
    except Exception as e:
        print(f"⚠️ [Triad Rollback Error] Failed restoring {p}: {e}", file=sys.stderr)
        return False


def _rollback(entries: Dict[Path, Dict[str, Any]], target_dir: Path) -> bool:
    """
    Safely roll back applied changes using descriptor-based no-follow writes and pre-mutation re-verification.
    Operating Contract:
    - Assumes a cooperative single-writer model within the repository workspace (coordinated via
      acquire_repo_mutation_lock and file-level advisory locks).
    - Uncoordinated external writers (such as background tools or editors that bypass locks) cannot be
      atomically excluded across multi-step OS primitives (e.g. readlink-unlink or fstat-ftruncate).
    - Under this contract, rollback is strictly non-destructive and fail-safe: any detected state
      divergence, unexpected inode, or concurrent mutation immediately aborts rollback mutations
      to avoid clobbering user files, preserving the complete unmerged recovery patch artifact on disk.
    - Re-validates parent containment against symlink/reparse point redirection.
    - Returns True if all paths were cleanly rolled back or confirmed untouched, False on conflicts.
    """
    # Phase 1: Concurrency and ownership validation.
    # If ANY path has concurrent modification, uncertain ownership, or parent containment violation,
    # abort all automatic rollback mutations.
    for p, info in entries.items():
        try:
            try:
                rel_p = str(p.relative_to(target_dir))
            except ValueError:
                print(f"⚠️ [Triad Rollback Error] Path {p} escapes target directory {target_dir}", file=sys.stderr)
                return False

            if _validate_and_resolve_contained_path(target_dir, rel_p) is None:
                print(f"⚠️ [Triad Rollback Error] Path {p} parent directory symlink/reparse traversal detected", file=sys.stderr)
                return False

            try:
                cur_st = os.lstat(p)
                cur_exists = True
                cur_is_link = stat.S_ISLNK(cur_st.st_mode)
                cur_is_dir = stat.S_ISDIR(cur_st.st_mode)
                cur_link = os.readlink(p) if cur_is_link else None
                cur_bytes = p.read_bytes() if stat.S_ISREG(cur_st.st_mode) else None
            except (FileNotFoundError, OSError):
                cur_exists = False
                cur_st = None
                cur_is_link = False
                cur_is_dir = False
                cur_link = None
                cur_bytes = None

            if cur_exists and cur_is_dir and not info.get("is_dir", False):
                print(f"⚠️ [Triad Conflict] Path {p} is a directory; refusing automatic rollback to prevent destructive removal.", file=sys.stderr)
                return False

            target_mode = info.get("target_mode")
            if target_mode is None and "record" in info and isinstance(info.get("record"), dict) and "dst_mode" in info["record"]:
                try:
                    target_mode = int(info["record"]["dst_mode"], 8)
                except Exception:
                    pass
            if target_mode is None and info.get("mode") is not None:
                target_mode = info.get("mode")

            # Path did not exist before this operation
            if not info["existed"]:
                if not cur_exists:
                    continue
                if info.get("expected_target_is_link"):
                    matches_written = cur_is_link and (cur_link == info.get("expected_target_link"))
                else:
                    matches_written = not cur_is_link and (cur_bytes == info.get("expected_target_bytes")) and (target_mode is None or _modes_match(cur_st.st_mode, target_mode, is_git_comparison=True))
                if not matches_written:
                    print(f"⚠️ [Triad Conflict] Concurrent modification detected on newly created path: {p}", file=sys.stderr)
                    return False
                continue

            # Path existed before this operation
            # Subcase: operation was deleting it
            if not info.get("expected_target_exists", True):
                if not cur_exists:
                    continue
                matches_baseline = False
                if info["is_symlink"]:
                    matches_baseline = cur_is_link and (cur_link == info["link_target"])
                elif info["is_regular"]:
                    matches_baseline = not cur_is_link and (cur_bytes == info["bytes"]) and (info.get("mode") is None or _modes_match(cur_st.st_mode, info["mode"], is_git_comparison=False))
                if not matches_baseline:
                    print(f"⚠️ [Triad Conflict] Concurrent modification detected on deletion candidate: {p}", file=sys.stderr)
                    return False
                continue

            # Subcase: operation was modifying it
            if not cur_exists:
                print(f"⚠️ [Triad Conflict] Path unexpectedly deleted concurrently: {p}", file=sys.stderr)
                return False

            matches_baseline = False
            if info["is_symlink"]:
                matches_baseline = cur_is_link and (cur_link == info["link_target"])
            elif info["is_regular"]:
                matches_baseline = not cur_is_link and (cur_bytes == info["bytes"]) and (info.get("mode") is None or _modes_match(cur_st.st_mode, info["mode"], is_git_comparison=False))

            if matches_baseline:
                continue

            matches_written = False
            if info.get("expected_target_is_link"):
                matches_written = cur_is_link and (cur_link == info.get("expected_target_link"))
            else:
                matches_written = not cur_is_link and (cur_bytes == info.get("expected_target_bytes")) and (target_mode is None or _modes_match(cur_st.st_mode, target_mode, is_git_comparison=True))

            if not matches_written:
                print(f"⚠️ [Triad Conflict] Concurrent user edits detected on {p}. Automatic rollback aborted to preserve concurrent edits.", file=sys.stderr)
                return False

        except Exception as e:
            print(f"⚠️ [Triad Conflict] Error checking concurrent state for {p}: {e}", file=sys.stderr)
            return False

    # Phase 2: Immediate pre-mutation re-verification per path before modifying or unlinking.
    # Never restore or unlink a path unless its current state STILL matches the expected written state.
    all_clean = True
    for p, info in entries.items():
        try:
            try:
                rel_p = str(p.relative_to(target_dir))
            except ValueError:
                all_clean = False
                continue

            if _validate_and_resolve_contained_path(target_dir, rel_p) is None:
                all_clean = False
                continue

            target_mode = info.get("target_mode")
            if target_mode is None and "record" in info and isinstance(info.get("record"), dict) and "dst_mode" in info["record"]:
                try:
                    target_mode = int(info["record"]["dst_mode"], 8)
                except Exception:
                    pass
            if target_mode is None and info.get("mode") is not None:
                target_mode = info.get("mode")

            # Subcase A: Path did not exist before this operation (we created it)
            if not info["existed"]:
                if p.is_symlink() or p.exists():
                    try:
                        cur_st = os.lstat(p)
                        cur_is_link = stat.S_ISLNK(cur_st.st_mode)
                        cur_link = os.readlink(p) if cur_is_link else None
                    except (FileNotFoundError, OSError):
                        continue

                    if cur_is_link:
                        expected_link = info.get("expected_target_link")
                        if not info.get("expected_target_is_link") or expected_link is None or cur_link != expected_link:
                            print(f"⚠️ [Triad Conflict] Concurrent modification detected on newly created symlink during rollback: {p}. Preserving path.", file=sys.stderr)
                            all_clean = False
                            continue
                        try:
                            post_st = os.lstat(p)
                            if not stat.S_ISLNK(post_st.st_mode) or os.readlink(p) != expected_link:
                                print(f"⚠️ [Triad Conflict] Symlink target on {p} modified concurrently immediately prior to unlink. Preserving path.", file=sys.stderr)
                                all_clean = False
                                continue
                        except Exception:
                            all_clean = False
                            continue
                        p.unlink()
                    elif stat.S_ISREG(cur_st.st_mode):
                        expected_bytes = info.get("expected_target_bytes")
                        if expected_bytes is None:
                            print(f"⚠️ [Triad Conflict] Path {p} was not expected to be a regular file during rollback. Preserving path.", file=sys.stderr)
                            all_clean = False
                            continue
                        flags = os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                        try:
                            fd = os.open(str(p), flags)
                        except OSError:
                            all_clean = False
                            continue
                        try:
                            if os.name == "nt":
                                import msvcrt
                                try:
                                    os.lseek(fd, 0, os.SEEK_SET)
                                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                                except (OSError, IOError):
                                    all_clean = False
                                    continue
                            else:
                                import fcntl
                                try:
                                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                except (OSError, IOError):
                                    all_clean = False
                                    continue
                            fd_st = os.fstat(fd)
                            if not stat.S_ISREG(fd_st.st_mode) or fd_st.st_size != len(expected_bytes):
                                all_clean = False
                                continue
                            os.lseek(fd, 0, os.SEEK_SET)
                            cur_fd_bytes = b""
                            while True:
                                chunk = os.read(fd, 65536)
                                if not chunk:
                                    break
                                cur_fd_bytes += chunk
                            if cur_fd_bytes != expected_bytes or (target_mode is not None and not _modes_match(fd_st.st_mode, target_mode, is_git_comparison=True)):
                                print(f"⚠️ [Triad Conflict] Concurrent modification detected on newly created file during rollback: {p}. Preserving path.", file=sys.stderr)
                                all_clean = False
                                continue
                        finally:
                            if os.name == "nt":
                                import msvcrt
                                try:
                                    os.lseek(fd, 0, os.SEEK_SET)
                                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                                except Exception:
                                    pass
                            else:
                                import fcntl
                                try:
                                    fcntl.flock(fd, fcntl.LOCK_UN)
                                except Exception:
                                    pass
                            os.close(fd)
                        try:
                            post_close_st = os.lstat(p)
                            if not stat.S_ISREG(post_close_st.st_mode) or post_close_st.st_size != len(expected_bytes):
                                print(f"⚠️ [Triad Conflict] File {p} modified concurrently immediately prior to unlink. Preserving file.", file=sys.stderr)
                                all_clean = False
                                continue
                            if hasattr(fd_st, "st_ino") and hasattr(post_close_st, "st_ino") and fd_st.st_ino and post_close_st.st_ino:
                                if post_close_st.st_ino != fd_st.st_ino or getattr(post_close_st, "st_dev", 0) != getattr(fd_st, "st_dev", 0):
                                    print(f"⚠️ [Triad Conflict] File {p} replaced by new inode prior to unlink. Preserving file.", file=sys.stderr)
                                    all_clean = False
                                    continue
                            # Best-effort guard (not atomic): a recreated file normally gets a fresh
                            # ctime, which catches an unlink+recreate with identical content on
                            # filesystems that reuse the freed inode number (tmpfs/overlayfs). Two
                            # limits: a recreate inside one coarse clock tick can go undetected, and
                            # on Windows st_ctime is creation time (NTFS tunneling can restore it),
                            # where the inode/file-ID check above is the effective protection.
                            fd_ctime = getattr(fd_st, "st_ctime_ns", None)
                            post_ctime = getattr(post_close_st, "st_ctime_ns", None)
                            if fd_ctime is not None and post_ctime is not None and post_ctime != fd_ctime:
                                print(f"⚠️ [Triad Conflict] File {p} recreated prior to unlink (ctime changed). Preserving file.", file=sys.stderr)
                                all_clean = False
                                continue
                            post_close_bytes = p.read_bytes()
                            if post_close_bytes != expected_bytes:
                                print(f"⚠️ [Triad Conflict] File {p} content mutated immediately prior to unlink. Preserving file.", file=sys.stderr)
                                all_clean = False
                                continue
                        except Exception:
                            all_clean = False
                            continue
                        p.unlink()
                    else:
                        print(f"⚠️ [Triad Conflict] Path {p} is a directory or special file; refusing destructive removal during rollback. Preserving path.", file=sys.stderr)
                        all_clean = False
                        continue
                continue

            # Subcase B: Path was being deleted by this operation
            if not info.get("expected_target_exists", True):
                if not (p.is_symlink() or p.exists()):
                    if not _restore_entry(p, info, target_dir):
                        all_clean = False
                else:
                    try:
                        cur_st = os.lstat(p)
                        cur_is_link = stat.S_ISLNK(cur_st.st_mode)
                        cur_link = os.readlink(p) if cur_is_link else None
                        cur_bytes = p.read_bytes() if stat.S_ISREG(cur_st.st_mode) else None
                    except (FileNotFoundError, OSError):
                        cur_is_link = False
                        cur_link = None
                        cur_bytes = None

                    matches_baseline = False
                    if info["is_symlink"]:
                        matches_baseline = cur_is_link and (cur_link == info["link_target"])
                    elif info["is_regular"]:
                        matches_baseline = not cur_is_link and (cur_bytes == info["bytes"]) and (info.get("mode") is None or _modes_match(cur_st.st_mode, info["mode"], is_git_comparison=False))
                    if not matches_baseline:
                        print(f"⚠️ [Triad Conflict] Concurrent modification detected on deletion candidate during rollback: {p}. Preserving path.", file=sys.stderr)
                        all_clean = False
                        continue
                continue

            # Subcase C: Path was being modified by this operation
            if not (p.is_symlink() or p.exists()):
                print(f"⚠️ [Triad Conflict] Path unexpectedly deleted concurrently during rollback: {p}.", file=sys.stderr)
                all_clean = False
                continue

            try:
                cur_st = os.lstat(p)
                cur_is_link = stat.S_ISLNK(cur_st.st_mode)
                cur_link = os.readlink(p) if cur_is_link else None
                cur_bytes = p.read_bytes() if stat.S_ISREG(cur_st.st_mode) else None
            except (FileNotFoundError, OSError):
                all_clean = False
                continue

            matches_baseline = False
            if info["is_symlink"]:
                matches_baseline = cur_is_link and (cur_link == info["link_target"])
            elif info["is_regular"]:
                matches_baseline = not cur_is_link and (cur_bytes == info["bytes"]) and (info.get("mode") is None or _modes_match(cur_st.st_mode, info["mode"], is_git_comparison=False))

            if matches_baseline:
                continue

            # Re-verify path matches expected written state right before restoring baseline
            matches_written = False
            if info.get("expected_target_is_link"):
                matches_written = cur_is_link and (cur_link == info.get("expected_target_link"))
            else:
                matches_written = not cur_is_link and (cur_bytes == info.get("expected_target_bytes")) and (target_mode is None or _modes_match(cur_st.st_mode, target_mode, is_git_comparison=True))

            if not matches_written:
                print(f"⚠️ [Triad Conflict] Concurrent user edits detected on {p} during rollback. Automatic rollback aborted for this path to preserve edits.", file=sys.stderr)
                all_clean = False
                continue

            if not _restore_entry(p, info, target_dir):
                all_clean = False

        except Exception as e:
            print(f"⚠️ [Triad Rollback Error] Failed restoring {p}: {e}", file=sys.stderr)
            all_clean = False

    return all_clean


def apply_verified_patch_to_workspace(
    patch_data: Union[str, bytes],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    expected_baseline_tree: Optional[str] = None,
    expected_target_tree: Optional[str] = None
) -> bool:
    """
    Applies a verified self-healing patch to the main working tree using a two-stage
    pre-verification (git apply --check) followed by application.
    Strict byte-preserving mode (--whitespace=nowarn, no --whitespace=fix, no --ignore-whitespace, no --3way).
    When expected_baseline_tree is provided:
    1. Verifies working tree parity immediately before applying (fail-closed concurrency check).
       Uses head_tree=expected_baseline_tree so tracked ignored files are properly preserved.
    2. Computes the exact expected post-application tree by applying the patch to an isolated
       temporary index seeded with expected_baseline_tree (and validates against expected_target_tree if provided).
    3. Enumerates all changes using git diff-tree -r -z -M to capture both rename endpoints and
       preserves filesystem type, link target, and mode via os.lstat(). Aborts before mutation if backup fails.
    4. Safe application protocol: operates under a cooperative single-writer model.
       Because uncoordinated external writers (such as IDE auto-savers) cannot be atomically
       excluded across multi-step Git OS invocations without kernel-level mandatory locking,
       application is strictly non-destructive fail-safe: when git apply fails, unexpected exceptions occur,
       or concurrent modification is detected, the verified recovery patch artifact is preserved on disk
       for manual inspection/application, leaving the workspace intact.
    5. Verifies post-application working tree exactly matches expected_target_tree.
    """
    target_dir = (cwd or Path.cwd()).resolve()
    exec_env = env if env is not None else clean_git_env()

    try:
        lock_ctx = acquire_repo_mutation_lock(target_dir)
        lock_ctx.__enter__()
    except Exception:
        return False

    fd, temp_patch_path = tempfile.mkstemp(suffix=".patch", prefix="triad_verified_")
    backup_entries: Dict[Path, Dict[str, Any]] = {}
    application_started = False

    try:
        raw_bytes = patch_data.encode("utf-8") if isinstance(patch_data, str) else patch_data
        with os.fdopen(fd, "wb") as f:
            f.write(raw_bytes)
            if not raw_bytes.endswith(b"\n"):
                f.write(b"\n")

        baseline_tree = expected_baseline_tree
        if baseline_tree:
            current_wt = _eng("snapshot_worktree_tree", snapshot_worktree_tree)(target_dir, head_tree=baseline_tree, env=exec_env)
            if current_wt != baseline_tree:
                return False
        else:
            baseline_tree = _eng("snapshot_worktree_tree", snapshot_worktree_tree)(target_dir, env=exec_env)
            if not baseline_tree:
                return False

        # Compute exact expected target tree using temporary index seeded from baseline_tree
        computed_target_tree = None
        temp_target_index = Path(tempfile.gettempdir()) / f"triad-target-{uuid.uuid4().hex[:8]}"
        temp_target_env = clean_git_env({"GIT_INDEX_FILE": str(temp_target_index)}, base_env=exec_env)
        try:
            r1, _, _ = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "read-tree", baseline_tree], cwd=target_dir, env=temp_target_env)
            if r1 != 0:
                return False
            r2, _, _ = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "apply", "--cached", "--whitespace=nowarn", "--", temp_patch_path], cwd=target_dir, env=temp_target_env)
            if r2 != 0:
                return False
            r3, out_tree, _ = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "write-tree"], cwd=target_dir, env=temp_target_env)
            if r3 != 0 or not out_tree.strip():
                return False
            computed_target_tree = out_tree.strip()
        finally:
            if temp_target_index.exists():
                try:
                    temp_target_index.unlink()
                except Exception:
                    pass

        if computed_target_tree == baseline_tree:
            return False

        if expected_target_tree and computed_target_tree != expected_target_tree:
            return False

        target_tree_to_verify = expected_target_tree or computed_target_tree

        # 1. Enumerate all changes using git diff-tree -r -z -M
        r_diff, diff_out, _ = _eng("run_subprocess_tree_safe_bytes", run_subprocess_tree_safe_bytes)(
            ["git", "diff-tree", "-r", "-z", "-M", baseline_tree, target_tree_to_verify],
            cwd=target_dir,
            env=exec_env
        )
        if r_diff != 0 or not diff_out:
            # Abort before mutation if backup discovery fails!
            return False

        records = parse_diff_tree_records(diff_out)
        if not records:
            return False

        # Collect union of all affected paths from diff-tree records
        affected_rel_paths = set()
        for rec in records:
            affected_rel_paths.add(rec["src_path"])
            affected_rel_paths.add(rec["dst_path"])

        # Directly obtain each path's baseline and final target state from the two trees
        try:
            baseline_tree_entries = get_tree_entries(baseline_tree, target_dir, exec_env)
            target_tree_entries = get_tree_entries(target_tree_to_verify, target_dir, exec_env)
        except RuntimeError as e:
            print(f"⚠️ [Triad Worktree Error] Tree entry enumeration failed: {e}", file=sys.stderr)
            return False

        # Explicitly detect unsupported file-to-directory or directory-to-file transitions
        # Build ancestor directory sets to perform O(N * depth) set-intersection checks instead of O(N^2) prefix scans
        baseline_paths = set(baseline_tree_entries.keys())
        target_paths = set(target_tree_entries.keys())

        def _get_ancestor_dirs(path_set: Set[str]) -> Set[str]:
            ancestors = set()
            for p in path_set:
                parts = p.split("/")
                for i in range(1, len(parts)):
                    ancestors.add("/".join(parts[:i]))
            return ancestors

        target_dir_ancestors = _get_ancestor_dirs(target_paths)
        file_to_dir_collisions = baseline_paths.intersection(target_dir_ancestors)
        if file_to_dir_collisions:
            first_col = sorted(file_to_dir_collisions)[0]
            print(f"⚠️ [Triad Notice] Unsupported file-to-directory transition detected ({first_col} -> {first_col}/...). Preserving recovery patch for manual merge.", file=sys.stderr)
            return False

        baseline_dir_ancestors = _get_ancestor_dirs(baseline_paths)
        dir_to_file_collisions = target_paths.intersection(baseline_dir_ancestors)
        if dir_to_file_collisions:
            first_col = sorted(dir_to_file_collisions)[0]
            print(f"⚠️ [Triad Notice] Unsupported directory-to-file transition detected ({first_col}/... -> {first_col}). Preserving recovery patch for manual merge.", file=sys.stderr)
            return False

        for rel_p in sorted(affected_rel_paths):
            file_p = _validate_and_resolve_contained_path(target_dir, rel_p)
            if file_p is None:
                # Traversal through symlinked parent directory or escape from repository: abort before mutation!
                return False

            existed_at_baseline = rel_p in baseline_tree_entries
            if existed_at_baseline:
                b_mode_str, _, b_sha = baseline_tree_entries[rel_p]
                try:
                    st = os.lstat(file_p)
                    is_link = stat.S_ISLNK(st.st_mode)
                    is_reg = stat.S_ISREG(st.st_mode)
                    is_dir = stat.S_ISDIR(st.st_mode)
                    link_target = os.readlink(file_p) if is_link else None
                    file_bytes = file_p.read_bytes() if is_reg else None
                    entry = {
                        "existed": True,
                        "is_symlink": is_link,
                        "is_regular": is_reg,
                        "is_dir": is_dir,
                        "link_target": link_target,
                        "mode": st.st_mode,
                        "size": st.st_size,
                        "mtime_ns": st.st_mtime_ns,
                        "bytes": file_bytes,
                        "baseline_sha": b_sha,
                        "baseline_mode": int(b_mode_str, 8),
                    }
                except Exception:
                    # File existed in baseline tree but cannot be statted/read from disk
                    return False
            else:
                # Did not exist in baseline tree
                if file_p.is_symlink() or file_p.exists():
                    # Untracked file occupying target path: abort before mutation!
                    return False
                entry = {
                    "existed": False,
                    "is_symlink": False,
                    "is_regular": False,
                    "is_dir": False,
                    "link_target": None,
                    "mode": None,
                    "size": None,
                    "mtime_ns": None,
                    "bytes": None,
                    "baseline_sha": None,
                    "baseline_mode": None,
                }

            # Final target state obtained directly from target_tree_to_verify
            if rel_p in target_tree_entries:
                t_mode_str, _, t_sha = target_tree_entries[rel_p]
                entry["expected_target_exists"] = True
                t_mode_int = int(t_mode_str, 8)
                if existed_at_baseline and entry.get("mode") is not None:
                    # Preserve baseline filesystem permissions (e.g. 0664 vs 0644), adjusting executable bits if git changed them
                    b_git_mode = entry.get("baseline_mode", 0o100644)
                    git_changed_exec = bool(t_mode_int & 0o111) != bool(b_git_mode & 0o111)
                    if not git_changed_exec:
                        entry["target_mode"] = entry["mode"]
                    else:
                        if bool(t_mode_int & 0o111):
                            entry["target_mode"] = entry["mode"] | 0o111
                        else:
                            entry["target_mode"] = entry["mode"] & ~0o111
                else:
                    entry["target_mode"] = t_mode_int

                is_target_link = (t_mode_str == "120000")
                entry["expected_target_is_link"] = is_target_link
                if is_target_link:
                    # Symlinks in git store raw target path strings; never apply checkout filters
                    r_cat, blob_bytes, _ = _eng("run_subprocess_tree_safe_bytes", run_subprocess_tree_safe_bytes)(
                        ["git", "cat-file", "blob", t_sha],
                        cwd=target_dir,
                        env=exec_env
                    )
                else:
                    # Apply checkout filters (CRLF, smudge) for rel_p if regular file
                    r_cat, blob_bytes, _ = _eng("run_subprocess_tree_safe_bytes", run_subprocess_tree_safe_bytes)(
                        ["git", "cat-file", "--filters", f"--path={rel_p}", t_sha],
                        cwd=target_dir,
                        env=exec_env
                    )
                    if r_cat != 0:
                        r_cat, blob_bytes, _ = _eng("run_subprocess_tree_safe_bytes", run_subprocess_tree_safe_bytes)(
                            ["git", "cat-file", "-p", t_sha],
                            cwd=target_dir,
                            env=exec_env
                        )
                if r_cat != 0:
                    return False
                if is_target_link:
                    entry["expected_target_link"] = os.fsdecode(blob_bytes)
                    entry["expected_target_bytes"] = None
                else:
                    entry["expected_target_bytes"] = blob_bytes
                    entry["expected_target_link"] = None
            else:
                entry["expected_target_exists"] = False
                entry["expected_target_bytes"] = None
                entry["expected_target_link"] = None
                entry["expected_target_is_link"] = False
                entry["target_mode"] = None

            backup_entries[file_p] = entry

        # 2. Dry run verify against working tree without modifying index (strictly byte-accurate)
        check_cmd = ["git", "apply", "--check", "--whitespace=nowarn", "--", temp_patch_path]
        check_res = subprocess.run(check_cmd, cwd=str(target_dir), env=exec_env, capture_output=True)
        if check_res.returncode != 0:
            return False

        # 3. Concurrency check: verify no touched file was modified between discovery and apply
        for file_p, info in backup_entries.items():
            if info["existed"]:
                try:
                    cur_st = os.lstat(file_p)
                    if cur_st.st_mtime_ns != info["mtime_ns"] or cur_st.st_size != info["size"]:
                        rec_path = _eng("get_recovery_patch_path", get_recovery_patch_path)(target_dir, unique=True)
                        try:
                            write_atomic_patch(rec_path, raw_bytes if raw_bytes.endswith(b"\n") else raw_bytes + b"\n")
                            print(f"[Triad Notice] Concurrent modification detected before apply; preserved recovery patch at {rec_path}", file=sys.stderr)
                        except Exception:
                            pass
                        return False
                except Exception:
                    return False

        # 4. Apply strictly to working tree (NO --index, NO --3way, NO --whitespace=fix)
        application_started = True
        apply_cmd = ["git", "apply", "--whitespace=nowarn", "--", temp_patch_path]
        apply_res = subprocess.run(apply_cmd, cwd=str(target_dir), env=exec_env, capture_output=True)
        if apply_res.returncode != 0:
            rec_path = _eng("get_recovery_patch_path", get_recovery_patch_path)(target_dir, unique=True)
            try:
                write_atomic_patch(rec_path, raw_bytes if raw_bytes.endswith(b"\n") else raw_bytes + b"\n")
                print(f"[Triad Notice] Preserved verified recovery patch at {rec_path}", file=sys.stderr)
            except Exception:
                pass
            return False

        # 5. Post-application verification: working tree must match target_tree_to_verify
        post_wt = _eng("snapshot_worktree_tree", snapshot_worktree_tree)(target_dir, head_tree=target_tree_to_verify, env=exec_env)
        if post_wt == baseline_tree or (target_tree_to_verify and post_wt != target_tree_to_verify):
            # To eliminate destructive races with external editors/writers, do not perform automatic in-place rollback.
            # Preserving the recovery patch artifact leaves workspace files intact without risking editor truncation/unlinking.
            rec_path = _eng("get_recovery_patch_path", get_recovery_patch_path)(target_dir, unique=True)
            try:
                write_atomic_patch(rec_path, raw_bytes if raw_bytes.endswith(b"\n") else raw_bytes + b"\n")
                print(f"[Triad Notice] Preserved verified recovery patch at {rec_path}", file=sys.stderr)
            except Exception:
                pass
            return False

        return True
    except Exception:
        if application_started:
            rec_path = _eng("get_recovery_patch_path", get_recovery_patch_path)(target_dir, unique=True)
            try:
                write_atomic_patch(rec_path, raw_bytes if raw_bytes.endswith(b"\n") else raw_bytes + b"\n")
                print(f"[Triad Notice] Preserved verified recovery patch at {rec_path}", file=sys.stderr)
            except Exception:
                pass
        return False
    finally:
        try:
            lock_ctx.__exit__(None, None, None)
        except Exception:
            pass
        if os.path.exists(temp_patch_path):
            try:
                os.remove(temp_patch_path)
            except Exception:
                pass

def _exec_subprocess_tree_safe(cmd: List[str], cwd: Path, env: Optional[Dict[str, str]] = None, timeout: int = 90, input_data: Optional[bytes] = None) -> Tuple[int, bytes, bytes]:
    """Execute command returning raw bytes, killing the entire process tree on timeout."""
    proc = None
    exec_env = env if env is not None else clean_git_env()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=exec_env,
            stdin=subprocess.PIPE if input_data is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(input=input_data, timeout=timeout)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        if proc:
            kill_process_tree(proc.pid)
        return 1, b"", f"Command timed out after {timeout}s (entire process tree killed)".encode("utf-8")
    except Exception as e:
        if proc:
            kill_process_tree(proc.pid)
        return 1, b"", f"Execution error: {e}".encode("utf-8")

def run_subprocess_tree_safe_bytes(cmd: List[str], cwd: Path, env: Optional[Dict[str, str]] = None, timeout: int = 90, input_data: Optional[bytes] = None) -> Tuple[int, bytes, bytes]:
    """Execute command returning raw bytes, killing the entire process tree on timeout."""
    return _exec_subprocess_tree_safe(cmd, cwd=cwd, env=env, timeout=timeout, input_data=input_data)

def run_subprocess_tree_safe(cmd: List[str], cwd: Path, env: Optional[Dict[str, str]] = None, timeout: int = 90, input_data: Optional[bytes] = None) -> Tuple[int, str, str]:
    """Execute command returning strings, killing the entire process tree on timeout."""
    ret, out_b, err_b = _exec_subprocess_tree_safe(cmd, cwd=cwd, env=env, timeout=timeout, input_data=input_data)
    out_str = out_b.decode("utf-8", errors="replace") if isinstance(out_b, bytes) else str(out_b)
    err_str = err_b.decode("utf-8", errors="replace") if isinstance(err_b, bytes) else str(err_b)
    return ret, out_str, err_str

def get_empty_tree_oid(repo_root: Path = Path(".")) -> str:
    """Dynamically determine the empty tree object ID for the repo's object format (SHA-1 or SHA-256)."""
    ret, out, _ = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "hash-object", "-t", "tree", "--stdin"], cwd=repo_root, input_data=b"")
    if ret == 0 and out.strip():
        return out.strip()
    return "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

def query_gate_fix(diag_output: str, args) -> str:
    """
    Query Advisory Council or Competition Council for a surgical fix to a test/build failure.
    """
    fix_prompt = (
        f"The test/build suite failed with this output:\n{diag_output}\n\n"
        "Diagnose the failure and provide the minimal unified diff to fix it."
    )
    competition = getattr(args, "competition", False)
    timeout = getattr(args, "timeout", 240)
    engine = getattr(args, "engine", "auto")
    if engine == "auto" and os.environ.get("TRIAD_GATE_ENGINE"):
        engine = os.environ["TRIAD_GATE_ENGINE"].strip() or "auto"

    if competition:
        try:
            from triad.competition import query_competition_council
        except ImportError:
            from competition import query_competition_council
        adv_pair = ("mock", "mock") if engine == "mock" else ("claude", "codex")
        session = query_competition_council(
            fix_prompt,
            mode="debug",
            timeout=timeout,
            advisor_names=adv_pair
        )
        return session.get("synthesis", "")

    return query_advisory_council(fix_prompt, mode="debug", engine=engine, timeout=timeout)

def snapshot_worktree_tree(repo_root: Path, head_tree: str = "", env: Optional[Dict[str, str]] = None) -> str:
    """
    Captures a full git tree snapshot of the working tree (including unstaged and untracked files).
    Uses an isolated temporary index file so the main git index is NEVER modified.
    Snapshots are strictly read-only with respect to checkout files (never invokes git checkout).
    Excludes only provisioned, untracked dependency paths (e.g. untracked node_modules or manifest links)
    while strictly preserving actual working-tree contents of any tracked paths.
    """
    temp_index = Path(tempfile.gettempdir()) / f"triad-wt-{uuid.uuid4().hex[:8]}"
    base_env = env if env is not None else clean_git_env()
    temp_env = clean_git_env({"GIT_INDEX_FILE": str(temp_index)}, base_env=base_env)
    try:
        # Seed temporary index from head_tree or caller's index tree
        seed_tree = head_tree
        if not seed_tree:
            ret_w, out_w, _ = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "write-tree"], cwd=repo_root, env=base_env)
            if ret_w == 0 and out_w.strip():
                seed_tree = out_w.strip()

        tracked_set: Set[str] = set()
        if seed_tree:
            ret, _, err = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "read-tree", seed_tree], cwd=repo_root, env=temp_env)
            if ret != 0:
                raise RuntimeError(f"Failed to initialize snapshot index from {seed_tree}: {err}")
            try:
                tree_entries = get_tree_entries(seed_tree, repo_root, temp_env)
                tracked_set = set(tree_entries.keys())
            except Exception:
                pass
        else:
            ret_ls, out_ls, err_ls = _eng("run_subprocess_tree_safe_bytes", run_subprocess_tree_safe_bytes)(["git", "ls-files", "-z"], cwd=repo_root, env=base_env)
            if ret_ls != 0:
                raise RuntimeError(f"Failed to query tracked files for snapshot: {err_ls}")
            tracked_set = set(os.fsdecode(p).replace("\\", "/") for p in out_ls.split(b"\0") if p)

        # Stage working tree to temporary index
        ret, _, err = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "add", "-A"], cwd=repo_root, env=temp_env)
        if ret != 0:
            raise RuntimeError(f"Failed to stage working tree to temporary index: {err}")

        prov_entries = get_provisioned_manifest_entries(repo_root)
        nm_path = Path(repo_root) / "node_modules"
        has_nm = nm_path.exists() or is_reparse_or_link(nm_path)

        paths_to_check: List[str] = list(prov_entries)
        if has_nm and "node_modules" not in paths_to_check:
            paths_to_check.append("node_modules")

        # Exclude ONLY untracked provisioned paths, without modifying any working tree files
        for entry in paths_to_check:
            norm_entry = entry.replace("\\", "/").rstrip("/")
            has_tracked = any(t == norm_entry or t.startswith(norm_entry + "/") for t in tracked_set)
            if not has_tracked:
                # No files under this provisioned entry are tracked: remove entire entry from temp index
                ret_rm, _, err_rm = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "rm", "--cached", "-r", "-f", "--ignore-unmatch", norm_entry], cwd=repo_root, env=temp_env)
                if ret_rm != 0:
                    raise RuntimeError(f"Failed to unstage untracked provisioned entry {norm_entry} from temporary index: {err_rm}")
            else:
                # Tracked files exist under this path; unstage only untracked entries
                ret_ls, out_ls, err_ls = _eng("run_subprocess_tree_safe_bytes", run_subprocess_tree_safe_bytes)(["git", "ls-files", "-z", "--stage", norm_entry], cwd=repo_root, env=temp_env)
                if ret_ls != 0:
                    raise RuntimeError(f"Failed to enumerate temporary index entries under {norm_entry}: {err_ls}")
                if out_ls:
                    for item in out_ls.split(b"\x00"):
                        if not item:
                            continue
                        try:
                            _, path_b = item.split(b"\t", 1)
                            p_str = os.fsdecode(path_b).replace("\\", "/")
                            if p_str not in tracked_set:
                                ret_rm, _, err_rm = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "rm", "--cached", "-f", p_str], cwd=repo_root, env=temp_env)
                                if ret_rm != 0:
                                    raise RuntimeError(f"Failed to unstage untracked entry {p_str} from temporary index: {err_rm}")
                        except Exception as e:
                            raise RuntimeError(f"Failed parsing temporary index entry for {norm_entry}: {e}")

        ret, wt_tree, err = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "write-tree"], cwd=repo_root, env=temp_env)
        if ret != 0 or not wt_tree.strip():
            raise RuntimeError(f"Failed to write working tree snapshot: {err}")
        return wt_tree.strip()
    finally:
        if temp_index.exists():
            try:
                temp_index.unlink()
            except Exception:
                pass


def _stage_candidate_worktree_changes(cwd: Path, exec_env: dict, head_tree: str = "") -> None:
    """
    Stage candidate changes in worktree while strictly excluding untracked provisioned
    dependencies (such as node_modules) when .gitignore is absent.
    Preserves tracked files and unstaged edits to tracked files.
    """
    ret, _, err = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "add", "-A"], cwd=cwd, env=exec_env)
    if ret != 0:
        raise RuntimeError(f"Failed to stage healed changes: {err.strip()}")

    tracked_set: Set[str] = set()
    if head_tree:
        try:
            tree_entries = get_tree_entries(head_tree, cwd, env=exec_env)
            tracked_set = set(tree_entries.keys())
        except Exception:
            pass

    prov_entries = get_provisioned_manifest_entries(cwd)
    nm_path = Path(cwd) / "node_modules"
    has_nm = nm_path.exists() or is_reparse_or_link(nm_path)

    paths_to_check: List[str] = list(prov_entries)
    if has_nm and "node_modules" not in paths_to_check:
        paths_to_check.append("node_modules")

    for entry in paths_to_check:
        norm_entry = entry.replace("\\", "/").rstrip("/")
        has_tracked = any(t == norm_entry or t.startswith(norm_entry + "/") for t in tracked_set)
        if not has_tracked:
            ret_rm, _, err_rm = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "rm", "--cached", "-r", "-f", "--ignore-unmatch", norm_entry], cwd=cwd, env=exec_env)
            if ret_rm != 0:
                raise RuntimeError(f"Failed to unstage untracked provisioned entry {norm_entry}: {err_rm.strip()}")
        else:
            ret_ls, out_ls, _ = _eng("run_subprocess_tree_safe_bytes", run_subprocess_tree_safe_bytes)(["git", "ls-files", "-z", "--stage", norm_entry], cwd=cwd, env=exec_env)
            if ret_ls == 0 and out_ls:
                for item in out_ls.split(b"\x00"):
                    if not item:
                        continue
                    try:
                        _, path_b = item.split(b"\t", 1)
                        p_str = os.fsdecode(path_b).replace("\\", "/")
                        if p_str not in tracked_set:
                            ret_rm, _, _ = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "rm", "--cached", "-f", p_str], cwd=cwd, env=exec_env)
                            if ret_rm != 0:
                                raise RuntimeError(f"Failed to unstage untracked file {p_str}")
                    except Exception:
                        pass


def compute_working_tree_fingerprint(cwd: Path, env: Optional[Dict[str, str]] = None) -> Dict[str, Tuple[int, int, str, str]]:
    """
    Capture byte-for-byte filesystem fingerprint (st_size, st_mtime_ns, sha256, mode) of all tracked
    and working tree files to detect raw mutations and mode changes that Git clean/smudge filters might normalize away.
    Returns rel_path -> (st_size, st_mtime_ns, content_hash, mode_str).
    Raises RuntimeError on git enumeration failure or unexpected file access/read errors (fail-closed).
    """
    exec_env = env if env is not None else clean_git_env()

    # Capture staged index modes to track executable bit changes on platforms with core.fileMode=false
    stage_modes: Dict[str, str] = {}
    ret_s, out_s, _ = _eng("run_subprocess_tree_safe_bytes", run_subprocess_tree_safe_bytes)(["git", "ls-files", "-z", "--stage"], cwd=cwd, env=exec_env)
    if ret_s == 0 and out_s:
        for entry in out_s.split(b"\x00"):
            if not entry:
                continue
            try:
                meta, path_b = entry.split(b"\t", 1)
                st_mode_str = meta.split(b" ")[0].decode("ascii", errors="replace")
                stage_modes[os.fsdecode(path_b)] = st_mode_str
            except Exception:
                pass

    prov_entries = get_provisioned_manifest_entries(cwd)
    prov_set = set(prov_entries)

    ret, out, err = _eng("run_subprocess_tree_safe_bytes", run_subprocess_tree_safe_bytes)(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=cwd, env=exec_env)
    if ret != 0:
        err_msg = err.decode("utf-8", errors="replace") if isinstance(err, bytes) else str(err)
        raise RuntimeError(f"git ls-files failed during fingerprint computation: {err_msg.strip()}")
    fingerprint: Dict[str, Tuple[int, int, str, str]] = {}
    for p_bytes in out.split(b"\x00"):
        if not p_bytes:
            continue
        rel_p = os.fsdecode(p_bytes).replace("\\", "/")
        is_tracked = rel_p in stage_modes
        if not is_tracked:
            if rel_p == "node_modules" or rel_p.startswith("node_modules/") or rel_p in prov_set:
                continue
        abs_p = cwd / rel_p
        try:
            st = os.lstat(abs_p)
            if stage_modes.get(rel_p) == "160000" or (stat.S_ISDIR(st.st_mode) and (abs_p / ".git").exists()):
                # Submodule certification in fingerprint
                ret_sub, sub_head, err_sub = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "-C", str(abs_p), "rev-parse", "HEAD"], cwd=cwd, env=exec_env)
                if ret_sub != 0 or not sub_head.strip():
                    raise RuntimeError(f"Submodule {rel_p} rev-parse failed: {err_sub.strip()}")
                ret_stat, sub_stat, err_stat = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "-C", str(abs_p), "status", "--porcelain"], cwd=cwd, env=exec_env)
                if ret_stat != 0:
                    raise RuntimeError(f"Submodule {rel_p} status inspection failed: {err_stat.strip()}")
                fingerprint[rel_p] = (0, st.st_mtime_ns, f"submodule:{sub_head.strip()}:{sub_stat.strip()}", "160000")
                continue

            if os.name != "nt":
                if stat.S_ISLNK(st.st_mode):
                    mode_str = "120000"
                elif (st.st_mode & 0o111) != 0:
                    mode_str = "100755"
                else:
                    mode_str = "100644"
            else:
                if stat.S_ISLNK(st.st_mode) or (hasattr(os.path, "isjunction") and os.path.isjunction(str(abs_p))):
                    mode_str = "120000"
                elif rel_p in stage_modes:
                    mode_str = stage_modes[rel_p]
                else:
                    mode_str = "100644"

            if stat.S_ISREG(st.st_mode):
                content = abs_p.read_bytes()
                h = hashlib.sha256(content).hexdigest()
                fingerprint[rel_p] = (st.st_size, st.st_mtime_ns, h, mode_str)
            elif stat.S_ISLNK(st.st_mode):
                link_target = os.readlink(abs_p)
                fingerprint[rel_p] = (0, st.st_mtime_ns, f"link:{link_target}", mode_str)
            else:
                fingerprint[rel_p] = (st.st_size, st.st_mtime_ns, "other", mode_str)
        except FileNotFoundError:
            fingerprint[rel_p] = (0, 0, "missing", "000000")
        except Exception as e:
            raise RuntimeError(f"Failed to inspect working-tree file {rel_p}: {e}")
    return fingerprint


def fingerprints_match(f1: Dict[str, Any], f2: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Compare two working tree fingerprints, returning (matches, list_of_differences)."""
    mutated = []
    for rel_p, v1 in f1.items():
        if rel_p not in f2:
            mutated.append(f"D\t{rel_p}")
        else:
            v2 = f2[rel_p]
            s1, _m1, h1 = v1[0], v1[1], v1[2]
            mode1 = v1[3] if len(v1) > 3 else None
            s2, _m2, h2 = v2[0], v2[1], v2[2]
            mode2 = v2[3] if len(v2) > 3 else None
            if s1 != s2 or h1 != h2 or (mode1 is not None and mode2 is not None and mode1 != mode2):
                desc = f"M\t{rel_p}"
                if mode1 is not None and mode2 is not None and mode1 != mode2:
                    desc += f" (mode changed: {mode1} -> {mode2})"
                mutated.append(desc)
    for rel_p in f2:
        if rel_p not in f1:
            mutated.append(f"A\t{rel_p}")
    return len(mutated) == 0, mutated


def capture_parent_state(repo_root: Path, env: Optional[Dict[str, str]] = None, require_index: bool = False) -> Dict[str, Any]:
    """
    Captures the complete state of parent repository:
    - candidate_tree: tree object representing the commit candidate
    - index_tree: current index tree (preserving GIT_INDEX_FILE if in env)
    - wt_tree: full working-tree snapshot (unstaged + untracked)
    - has_changes: bool
    - is_unborn: bool
    """
    exec_env = env if env is not None else os.environ

    # 1. Attempt writing current index tree (preserving alternate GIT_INDEX_FILE if provided)
    ret, index_tree, err = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "write-tree"], cwd=repo_root, env=exec_env)
    if ret != 0:
        raise RuntimeError(f"Failed to capture parent index tree: {err}")
    index_tree = index_tree.strip()

    # Get HEAD commit OID and tree sha
    ret_commit, head_commit, _ = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "rev-parse", "--verify", "HEAD"], cwd=repo_root, env=exec_env)
    head_commit = head_commit.strip() if ret_commit == 0 else "UNBORN"

    ret, head_tree, err = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "rev-parse", "HEAD^{tree}"], cwd=repo_root, env=exec_env)
    if ret != 0:
        head_tree = ""
    else:
        head_tree = head_tree.strip()

    empty_tree_oid = get_empty_tree_oid(repo_root)
    is_unborn = not bool(head_tree)

    # 2. Snapshot working tree contents seeded from index_tree so newly staged ignored files are tracked
    wt_tree = _eng("snapshot_worktree_tree", snapshot_worktree_tree)(repo_root, head_tree=index_tree, env=exec_env)

    # Staged changes exist if index differs from HEAD (or unborn index is non-empty)
    has_staged = (bool(head_tree) and index_tree != head_tree) or (is_unborn and index_tree != empty_tree_oid)
    has_unstaged = (wt_tree != index_tree)
    has_changes = has_staged or has_unstaged

    # Commit gating strictly commits index_tree when require_index is True.
    # Working-tree candidate selection is used for non-commit commands (e.g. triad auto intent execution).
    candidate_tree = index_tree if require_index else wt_tree

    return {
        "candidate_tree": candidate_tree,
        "index_tree": index_tree,
        "wt_tree": wt_tree,
        "head_tree": head_tree,
        "head_commit": head_commit,
        "has_changes": has_changes,
        "is_unborn": is_unborn,
        "has_staged": has_staged,
        "has_unstaged": has_unstaged
    }

def capture_candidate_tree(repo_root: Path, env: Optional[Dict[str, str]] = None, require_index: bool = False) -> Tuple[str, bool]:
    """
    Captures the exact candidate git tree object for verification.
    Preserves GIT_INDEX_FILE when present in env (e.g. from git pre-commit hook).
    Returns (candidate_tree, has_changes).
    Raises RuntimeError on git failures (fail-closed).
    """
    state = _eng("capture_parent_state", capture_parent_state)(repo_root, env=env, require_index=require_index)
    return state["candidate_tree"], state["has_changes"]

def get_recovery_patch_path(repo_root: Path, unique: bool = False) -> Path:
    """Resolve recovery patch path inside git directory so working directory is never polluted."""
    filename = f"triad_recovery_{int(time.time())}_{uuid.uuid4().hex[:8]}.patch" if unique else "triad_recovery.patch"
    ret, out, _ = _eng("run_subprocess_tree_safe", run_subprocess_tree_safe)(["git", "rev-parse", "--git-path", filename], cwd=repo_root)
    if ret == 0 and out.strip():
        p = Path(out.strip())
        if not p.is_absolute():
            p = (Path(repo_root) / p).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    git_dir = Path(repo_root) / ".git"
    if git_dir.is_dir():
        return git_dir / filename
    return Path(repo_root) / f".{filename}"

def write_atomic_patch(target_path: Path, data: bytes):
    """Write patch bytes atomically to target path; raises on error."""
    tmp_path = target_path.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
    tmp_path.write_bytes(data)
    os.replace(str(tmp_path), str(target_path))


def sanitize_worktree_env(
    env: Dict[str, str],
    repo_root: Union[str, Path],
    worktree_path: Optional[Union[str, Path]] = None,
) -> Dict[str, str]:
    """
    Establish strict worktree environment isolation:
    - Sets TRIAD_ISOLATED_WORKTREE="1"
    - Sets NODE_PRESERVE_SYMLINKS="1"
    - Strips parent repo_root (and uncontained descendants) from PYTHONPATH
    - Prepends worktree_path to PYTHONPATH if provided
    """
    iso_env = dict(env)
    iso_env["TRIAD_ISOLATED_WORKTREE"] = "1"
    iso_env["NODE_PRESERVE_SYMLINKS"] = "1"

    # Ensure Node resolves module dependencies in symlink-preserved mode without breaking CLI main relative imports
    orig_node_opts = iso_env.get("NODE_OPTIONS", "")
    if "--preserve-symlinks" not in orig_node_opts:
        iso_env["NODE_OPTIONS"] = (orig_node_opts + " --preserve-symlinks").strip()

    clean_repo = Path(repo_root).resolve()
    clean_wt = Path(worktree_path).resolve() if worktree_path is not None else None

    orig_pp = iso_env.get("PYTHONPATH", "")
    sanitized_parts: List[str] = []
    if clean_wt is not None:
        sanitized_parts.append(str(clean_wt))

    if orig_pp:
        for part in orig_pp.split(os.pathsep):
            if not part:
                continue
            try:
                p = Path(part).resolve()
                is_venv = any(seg.lower() in ("site-packages", "dist-packages") for seg in p.parts)
                is_parent = (p == clean_repo or clean_repo in p.parents)
                is_in_wt = clean_wt is not None and (p == clean_wt or clean_wt in p.parents)
                if is_parent and not is_in_wt and not is_venv:
                    continue
                if str(p) not in sanitized_parts:
                    sanitized_parts.append(str(p))
            except Exception:
                pass

    iso_env["PYTHONPATH"] = os.pathsep.join(sanitized_parts)
    return iso_env


def _notice_recovery_patch(recovery_path: Optional[Path]) -> None:
    if recovery_path and recovery_path.exists():
        print(f"[Triad Notice] Preserved verified self-healing patch at {recovery_path}")


