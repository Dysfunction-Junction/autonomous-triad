"""Git pre-commit hook management (`triad hook`)."""

# Tags: cli, worktree, patching, verification
# Links: triad/worktree.py, triad/cli/mesh.py
# Queries: "how do I install the pre-commit hook", "what does the hook run", "how does self-healing apply a fix"

import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

try:
    from triad.worktree import get_repo_root
except ImportError:
    from worktree import get_repo_root


def _eng(name: str, fallback: Any = None) -> Any:
    mod = sys.modules.get("triad.triad_engine") or sys.modules.get("triad_engine")
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    return fallback


def _te():
    mod = sys.modules.get("triad.triad_engine") or sys.modules.get("triad_engine")
    if mod is None:
        try:
            from triad import triad_engine as mod
        except ImportError:
            import triad_engine as mod
    return mod


def _verify_destination_unmodified(
    hook_file: Path,
    initial_exists: bool,
    initial_is_symlink: bool,
    initial_target: Optional[str],
    initial_bytes: bytes
) -> None:
    """Verify that destination hook file was not modified concurrently during the operation."""
    current_exists = hook_file.is_symlink() or hook_file.exists()
    if current_exists != initial_exists:
        raise RuntimeError(f"Concurrent modification detected on {hook_file}: existence changed during operation.")
    if not initial_exists:
        return
    current_is_symlink = hook_file.is_symlink()
    if current_is_symlink != initial_is_symlink:
        raise RuntimeError(f"Concurrent modification detected on {hook_file}: symlink state changed during operation.")
    if initial_is_symlink:
        current_target = os.readlink(str(hook_file))
        if current_target != initial_target:
            raise RuntimeError(f"Concurrent modification detected on {hook_file}: symlink target changed during operation.")
    else:
        current_bytes = hook_file.read_bytes()
        if current_bytes != initial_bytes:
            raise RuntimeError(f"Concurrent modification detected on {hook_file}: content modified by concurrent process.")


def _allocate_exclusive_backup(
    hooks_dir: Path,
    is_symlink: bool,
    source_hook: Path,
    cleaned_content: Optional[str] = None,
    orig_mode: Optional[int] = None
) -> Path:
    """
    Exclusively allocate and create a backup artifact so concurrent operations never allocate the same backup name.
    """
    base_name = "pre-commit.legacy"
    idx = 0
    while True:
        candidate_name = base_name if idx == 0 else f"{base_name}.{idx}"
        candidate = hooks_dir / candidate_name
        idx += 1
        if is_symlink:
            try:
                link_target = os.readlink(str(source_hook))
                if candidate.parent != source_hook.parent and not os.path.isabs(link_target):
                    abs_target = (source_hook.parent / link_target).resolve()
                    try:
                        backup_target = os.path.relpath(str(abs_target), str(candidate.parent))
                    except Exception:
                        backup_target = str(abs_target)
                else:
                    backup_target = link_target
                os.symlink(backup_target, str(candidate))
                sidecar = candidate.parent / f"{candidate.name}.triad_link_target"
                try:
                    sidecar.write_text(link_target, encoding="utf-8")
                except Exception:
                    pass
                return candidate
            except FileExistsError:
                continue
            except OSError:
                pass
        try:
            fd = os.open(str(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "wb") as f:
                if cleaned_content is not None:
                    f.write(cleaned_content.encode("utf-8"))
                else:
                    with open(str(source_hook), "rb") as sf:
                        shutil.copyfileobj(sf, f)
            if orig_mode is not None:
                try:
                    candidate.chmod(orig_mode)
                except Exception:
                    pass
            return candidate
        except Exception:
            candidate.unlink(missing_ok=True)
            raise


def cmd_hook(args):
    """
    Manage Git hooks for autonomous pre-commit enforcement.
    Hook Contract & Bounded Execution Model:
    - User hook body in in-place integration runs in an isolated subshell preserving its exit code and traps.
    - Sourced hooks or hooks containing top-level 'return' statements cannot be wrapped inside subshells
      without altering return semantics; these are routed directly to .legacy chaining.
    - Each Triad installation owns exactly one backup artifact tagged via '# TRIAD_BACKUP_OWNED: <name>'.
    - On uninstall, Triad manages and restores ONLY its specifically tagged backup artifact, never touching
      unrelated historical backups.
    """
    te = _te()
    TRIAD_HOOK_SIGNATURE = te.TRIAD_HOOK_SIGNATURE
    TRIAD_USER_WRAPPER_START = te.TRIAD_USER_WRAPPER_START
    _HookLock = te._HookLock
    _has_top_level_return = te._has_top_level_return
    _integrate_triad_into_hook = te._integrate_triad_into_hook
    _is_hook_executable = te._is_hook_executable
    _is_integrated_triad_hook = te._is_integrated_triad_hook
    _is_standalone_triad_hook = te._is_standalone_triad_hook
    _render_hook_template = te._render_hook_template
    _render_triad_hook_block = te._render_triad_hook_block
    _unwrap_triad_user_body = te._unwrap_triad_user_body
    get_git_common_dir = te.get_git_common_dir
    is_posix_shell_shebang = te.is_posix_shell_shebang
    resolve_target_hook_file = te.resolve_target_hook_file
    action = getattr(args, "hook_action", None) or "status"
    try:
        repo_root = _eng("get_repo_root", get_repo_root)(".")
    except Exception as e:
        print(f"[Triad Hook Error] Not inside a git repository: {e}", file=sys.stderr)
        sys.exit(1)

    hook_file = resolve_target_hook_file(repo_root)
    hooks_dir = hook_file.parent

    common_git_dir = get_git_common_dir(repo_root)

    try:
        is_hooks_dir_in_git = bool(hooks_dir.resolve().relative_to(common_git_dir.resolve()))
    except (ValueError, RuntimeError):
        is_hooks_dir_in_git = (hooks_dir.resolve() == common_git_dir.resolve())

    admin_dir = hooks_dir if is_hooks_dir_in_git else (common_git_dir / "hooks")
    admin_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = hooks_dir if is_hooks_dir_in_git else admin_dir

    if action == "install":
        hooks_dir.mkdir(parents=True, exist_ok=True)
        with _HookLock(admin_dir):
            is_hook_existing = hook_file.is_symlink() or hook_file.exists()
            content = ""
            orig_mode = None
            orig_bytes = b""
            initial_target = None
            if is_hook_existing:
                try:
                    orig_mode = hook_file.stat().st_mode
                except Exception:
                    pass
                if hook_file.is_symlink():
                    try:
                        initial_target = os.readlink(str(hook_file))
                    except Exception:
                        pass
                try:
                    orig_bytes = hook_file.read_bytes()
                    content = orig_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    content = ""
                except Exception as e:
                    print(f"❌ [Triad Hook Error] Failed reading existing hook {hook_file}: {e}", file=sys.stderr)
                    sys.exit(1)

            initial_exists = is_hook_existing
            initial_is_symlink = hook_file.is_symlink()

            is_standalone = _is_standalone_triad_hook(content)
            is_integrated = _is_integrated_triad_hook(content)
            is_triad_hook = is_standalone or is_integrated or (TRIAD_HOOK_SIGNATURE in content)

            if not is_hook_existing:
                temp_hook = hooks_dir / f".pre-commit.tmp.{uuid.uuid4().hex[:8]}"
                try:
                    temp_hook.write_bytes(_render_hook_template("none").encode("utf-8"))
                    try:
                        temp_hook.chmod(0o755)
                    except Exception:
                        pass
                    if os.name != "nt" and not os.access(temp_hook, os.X_OK):
                        raise RuntimeError("Executable permission verification failed on hook file.")
                    _verify_destination_unmodified(hook_file, initial_exists, initial_is_symlink, initial_target, orig_bytes)
                    os.replace(str(temp_hook), str(hook_file))
                    print(f"✓ Triad pre-commit hook installed successfully at {hook_file}")
                    return
                except Exception as e:
                    if temp_hook.exists():
                        try:
                            temp_hook.unlink()
                        except Exception:
                            pass
                    print(f"❌ [Triad Hook Error] Failed to install pre-commit hook: {e}", file=sys.stderr)
                    sys.exit(1)

            if is_triad_hook and not getattr(args, "force", False):
                print(f"✓ Triad pre-commit hook is already installed at {hook_file}")
                return

            first_line = content.splitlines()[0] if content.splitlines() else ""
            has_shebang = first_line.startswith("#!")
            is_symlink = hook_file.is_symlink()
            is_husky = not is_symlink and ("husky" in content.lower() or ".husky" in str(hook_file))
            is_shebang_free_husky = is_husky and not has_shebang
            # Only strict POSIX sh is inlined. bash/zsh/ksh are chained so they
            # run as their own process under their shebang.
            inline_under_sh = is_shebang_free_husky or te._safe_to_inline_under_sh(first_line)
            is_pre_commit_framework = (
                "file generated by pre-commit" in content.lower()
                or "https://pre-commit.com" in content.lower()
                or "pre-commit.com" in content.lower()
            )

            # Standalone hook on --force: Re-install template directly without wrapping it
            if is_standalone and getattr(args, "force", False):
                m_own = re.search(r"# TRIAD_BACKUP_OWNED:\s*([^\s\r\n]+)", content)
                backup_name = m_own.group(1).strip() if m_own else "none"
                m_act = re.search(r"# TRIAD_BACKUP_ACTIVE:\s*([01])", content)
                backup_active = (m_act.group(1).strip() == "1") if m_act else True
                temp_hook = hooks_dir / f".pre-commit.tmp.{uuid.uuid4().hex[:8]}"
                try:
                    temp_hook.write_bytes(_render_hook_template(backup_name, should_execute_backup=backup_active).encode("utf-8"))
                    mode_to_set = (orig_mode | 0o755) if orig_mode is not None else 0o755
                    try:
                        temp_hook.chmod(mode_to_set)
                    except Exception as e:
                        if os.name != "nt":
                            raise RuntimeError(f"Failed to set executable permissions on hook: {e}")

                    if os.name != "nt" and not os.access(temp_hook, os.X_OK):
                        raise RuntimeError("Executable permission verification failed on hook file.")

                    _verify_destination_unmodified(hook_file, initial_exists, initial_is_symlink, initial_target, orig_bytes)
                    os.replace(str(temp_hook), str(hook_file))
                    print(f"✓ Triad pre-commit hook installed successfully at {hook_file}")
                    return
                except Exception as e:
                    if temp_hook.exists():
                        try:
                            temp_hook.unlink()
                        except Exception:
                            pass
                    print(f"❌ [Triad Hook Error] Failed to install pre-commit hook: {e}", file=sys.stderr)
                    sys.exit(1)

            is_executable = _is_hook_executable(orig_mode, is_husky=is_husky)

            # In-place integration strictly for compatible shell scripts without top-level return:
            # Sourced hooks or hooks containing top-level return statements cannot be wrapped inside
            # subshells without altering return semantics; these are routed directly to .legacy chaining.
            has_top_level_return = _has_top_level_return(content)
            can_execute = is_executable or is_husky
            if not is_symlink and not is_pre_commit_framework and inline_under_sh and can_execute and not has_top_level_return:
                backup_name = "none"
                if not is_triad_hook:
                    try:
                        backup_candidate = _allocate_exclusive_backup(
                            backup_dir,
                            is_symlink=hook_file.is_symlink(),
                            source_hook=hook_file,
                            orig_mode=orig_mode
                        )
                        backup_name = backup_candidate.name
                        print(f"[Triad Hook] Existing third-party pre-commit hook backed up to {backup_candidate} and chained.")
                    except Exception as e:
                        print(f"❌ [Triad Hook Error] Failed backing up hook before in-place modification: {e}", file=sys.stderr)
                        sys.exit(1)
                else:
                    m_own = re.search(r"# TRIAD_BACKUP_OWNED:\s*([^\s\r\n]+)", content)
                    backup_name = m_own.group(1).strip() if m_own else "none"

                temp_hook = hooks_dir / f".pre-commit.tmp.{uuid.uuid4().hex[:8]}"
                try:
                    new_content = _integrate_triad_into_hook(content, _render_triad_hook_block(backup_name))
                    temp_hook.write_bytes(new_content.encode("utf-8"))
                    try:
                        mode_to_set = (orig_mode | 0o755) if orig_mode is not None else 0o755
                        temp_hook.chmod(mode_to_set)
                    except Exception:
                        pass
                    _verify_destination_unmodified(hook_file, initial_exists, initial_is_symlink, initial_target, orig_bytes)
                    os.replace(str(temp_hook), str(hook_file))
                    desc = "integrated with Husky" if is_husky else "integrated in-place"
                    print(f"✓ Triad pre-commit hook installed successfully ({desc} at {hook_file})")
                    return
                except Exception as e:
                    if temp_hook.exists():
                        try:
                            temp_hook.unlink()
                        except Exception:
                            pass
                    print(f"❌ [Triad Hook Error] Failed to install pre-commit hook: {e}", file=sys.stderr)
                    sys.exit(1)

            # Backup existing third-party hook if present and not owned by Triad
            backup_name = "none"
            if is_hook_existing and not is_triad_hook:
                if getattr(args, "force", False):
                    print("[Triad Hook] Overwriting existing hook without backup (--force specified).")
                    backup_name = "none"
                else:
                    try:
                        cleaned_body = _unwrap_triad_user_body(content) if (content and TRIAD_USER_WRAPPER_START in content) else None
                        backup_candidate = _allocate_exclusive_backup(
                            backup_dir,
                            is_symlink=hook_file.is_symlink(),
                            source_hook=hook_file,
                            cleaned_content=cleaned_body if (cleaned_body is not None and cleaned_body != content) else None,
                            orig_mode=orig_mode
                        )
                        backup_name = backup_candidate.name
                        print(f"[Triad Hook] Existing third-party pre-commit hook backed up to {backup_candidate} and chained.")
                    except Exception as e:
                        print(f"❌ [Triad Hook Error] Failed backing up hook before replacement: {e}", file=sys.stderr)
                        sys.exit(1)
            else:
                m_own = re.search(r"# TRIAD_BACKUP_OWNED:\s*([^\s\r\n]+)", content)
                backup_name = m_own.group(1).strip() if m_own else "none"

            # Install TRIAD_HOOK_TEMPLATE. Always chain a third-party backup,
            # including one that was not executable at install time. The old
            # gate left BACKUP_ACTIVE=0 and the legacy hook was silently skipped.
            should_execute_backup = True
            if is_triad_hook:
                m_act = re.search(r"# TRIAD_BACKUP_ACTIVE:\s*([01])", content)
                if m_act:
                    should_execute_backup = (m_act.group(1).strip() == "1")

            temp_hook = hooks_dir / f".pre-commit.tmp.{uuid.uuid4().hex[:8]}"
            try:
                temp_hook.write_bytes(_render_hook_template(backup_name, should_execute_backup=should_execute_backup).encode("utf-8"))
                try:
                    mode_to_set = (orig_mode | 0o755) if orig_mode is not None else 0o755
                    temp_hook.chmod(mode_to_set)
                except Exception as e:
                    if os.name != "nt":
                        raise RuntimeError(f"Failed to set executable permissions on hook: {e}")

                if os.name != "nt" and not os.access(temp_hook, os.X_OK):
                    raise RuntimeError("Executable permission verification failed on hook file.")

                _verify_destination_unmodified(hook_file, initial_exists, initial_is_symlink, initial_target, orig_bytes)
                os.replace(str(temp_hook), str(hook_file))
                desc = "integrated with pre-commit framework" if is_pre_commit_framework else "installed successfully"
                print(f"✓ Triad pre-commit hook {desc} at {hook_file}")
            except Exception as e:
                if temp_hook.exists():
                    try:
                        temp_hook.unlink()
                    except Exception:
                        pass
                print(f"❌ [Triad Hook Error] Failed to install pre-commit hook: {e}", file=sys.stderr)
                sys.exit(1)

    elif action == "uninstall":
        with _HookLock(admin_dir):
            is_hook_existing = hook_file.is_symlink() or hook_file.exists()
            if not is_hook_existing:
                print(f"[Triad Hook] No pre-commit hook found at {hook_file}")
                return
            orig_mode = None
            try:
                orig_mode = hook_file.stat().st_mode
            except Exception:
                pass
            content = ""
            orig_bytes = b""
            initial_target = None
            if hook_file.is_symlink():
                try:
                    initial_target = os.readlink(str(hook_file))
                except Exception:
                    pass
            try:
                orig_bytes = hook_file.read_bytes()
                content = orig_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = orig_bytes.decode("utf-8", errors="replace")
            except Exception:
                pass

            initial_exists = is_hook_existing
            initial_is_symlink = hook_file.is_symlink()

            if TRIAD_HOOK_SIGNATURE not in content:
                if not getattr(args, "force", False):
                    print("[Triad Hook Warning] Existing pre-commit hook was not created by Triad. Use --force to remove.", file=sys.stderr)
                    sys.exit(1)
                # Force removal of an unsigned third-party hook without touching any historical backups
                try:
                    _verify_destination_unmodified(hook_file, initial_exists, initial_is_symlink, initial_target, orig_bytes)
                    hook_file.unlink(missing_ok=True)
                except Exception as e:
                    print(f"❌ [Triad Hook Error] Failed to remove pre-commit hook: {e}", file=sys.stderr)
                    sys.exit(1)
                print(f"✓ Removed third-party pre-commit hook from {hook_file}")
                return

            is_husky = ".husky" in str(hook_file) or (TRIAD_USER_WRAPPER_START in content and "husky" in content.lower())

            m_own = re.search(r"# TRIAD_BACKUP_OWNED:\s*([^\s\r\n]+)", content)
            owned_backup_name = m_own.group(1).strip() if m_own else None

            pattern = re.compile(
                r"\n?# --- # Triad Autonomous Pre-Commit Gate Hook \[START\] ---.*?# --- # Triad Autonomous Pre-Commit Gate Hook \[END\] ---\n?",
                re.DOTALL
            )
            cleaned = pattern.sub("", content)
            cleaned = _unwrap_triad_user_body(cleaned)

            def _legacy_sort_key(p: Path):
                suffix = p.name[len("pre-commit.legacy"):].lstrip(".")
                return int(suffix) if suffix.isdigit() else (0 if not suffix else 999999)
            legacy_backups = sorted([p for p in hooks_dir.glob("pre-commit.legacy*") if (p.is_symlink() or p.exists()) and not p.name.endswith(".triad_link_target")], key=_legacy_sort_key)
            if not is_hooks_dir_in_git:
                legacy_backups = sorted(
                    legacy_backups + [p for p in admin_dir.glob("pre-commit.legacy*") if (p.is_symlink() or p.exists()) and not p.name.endswith(".triad_link_target")],
                    key=_legacy_sort_key
                )
            valid_backups = list(legacy_backups)

            def _find_link_target_sidecar(target_b: Path) -> Optional[Path]:
                for sc in (target_b.parent / f"{target_b.name}.triad_link_target",
                           target_b.parent / f".{target_b.name}.triad_link_target"):
                    if sc.exists():
                        return sc
                return None

            def _restore_backup_file(target_b: Path, dest_hook: Path, is_b_symlink: bool, b_mode: Optional[int]) -> None:
                sidecar = _find_link_target_sidecar(target_b)
                if sidecar and (is_b_symlink or target_b.is_symlink()):
                    orig_link = sidecar.read_text(encoding="utf-8")
                    tmp_symlink = dest_hook.parent / f".tmp_hook_restore_{uuid.uuid4().hex[:8]}"
                    try:
                        os.symlink(orig_link, str(tmp_symlink))
                        os.replace(str(tmp_symlink), str(dest_hook))
                        target_b.unlink(missing_ok=True)
                        sidecar.unlink(missing_ok=True)
                    except Exception:
                        if tmp_symlink.is_symlink() or tmp_symlink.exists():
                            tmp_symlink.unlink(missing_ok=True)
                        raise
                elif is_b_symlink or target_b.is_symlink():
                    orig_link = os.readlink(str(target_b))
                    tmp_symlink = dest_hook.parent / f".tmp_hook_restore_{uuid.uuid4().hex[:8]}"
                    try:
                        os.symlink(orig_link, str(tmp_symlink))
                        os.replace(str(tmp_symlink), str(dest_hook))
                        target_b.unlink(missing_ok=True)
                    except Exception:
                        if tmp_symlink.is_symlink() or tmp_symlink.exists():
                            tmp_symlink.unlink(missing_ok=True)
                        raise
                else:
                    os.replace(str(target_b), str(dest_hook))
                    if not is_b_symlink and b_mode is not None:
                        try:
                            dest_hook.chmod(b_mode)
                        except Exception:
                            pass
                    if sidecar and sidecar.exists():
                        sidecar.unlink(missing_ok=True)

            target_backup = None
            if owned_backup_name is not None:
                if owned_backup_name != "none":
                    if not re.fullmatch(r"pre-commit\.legacy(?:\.[1-9][0-9]*)?", owned_backup_name):
                        raise RuntimeError(f"Invalid Triad backup ownership marker: {owned_backup_name}")
                    candidate = hooks_dir / owned_backup_name
                    if not (candidate.is_symlink() or candidate.exists()) and not is_hooks_dir_in_git:
                        candidate_admin = admin_dir / owned_backup_name
                        if candidate_admin.is_symlink() or candidate_admin.exists():
                            candidate = candidate_admin
                    try:
                        expected_parent = hooks_dir.resolve() if candidate.parent.resolve() == hooks_dir.resolve() else admin_dir.resolve()
                        if candidate.parent.resolve() != expected_parent:
                            raise RuntimeError("Triad backup marker escapes hooks directory")
                    except RuntimeError:
                        raise
                    except Exception:
                        pass
                    if candidate.is_symlink() or candidate.exists():
                        target_backup = candidate
            else:
                # Fallback ONLY for demonstrably older Triad installations (containing TRIAD_HOOK_SIGNATURE) without an ownership marker.
                # Third-party hooks uninstalled with --force must NEVER select or restore an untagged historical backup.
                if TRIAD_HOOK_SIGNATURE in content and valid_backups:
                    target_backup = valid_backups[-1]
                else:
                    target_backup = None

            # An integrated hook contains Triad's wrapper around user hook content
            is_integrated = (TRIAD_USER_WRAPPER_START in content) or (
                not _is_standalone_triad_hook(content)
                and cleaned.strip()
                and not cleaned.replace("\r\n", "\n").startswith("#!/bin/sh\n# Triad")
            )

            force_restore = getattr(args, "force", False)

            if is_integrated:
                # Check if extracted user body or cleaned content matches target backup
                backup_matches = False
                if target_backup:
                    try:
                        b_content = target_backup.read_text(encoding="utf-8", errors="replace")
                        triad_block = _render_triad_hook_block(owned_backup_name or "none")
                        expected_integrated = _integrate_triad_into_hook(b_content, triad_block)
                        norm_content = content.replace("\r\n", "\n").strip()
                        norm_exp = expected_integrated.replace("\r\n", "\n").strip()
                        norm_cleaned = cleaned.replace("\r\n", "\n").strip()
                        norm_b = b_content.replace("\r\n", "\n").strip()
                        if norm_content == norm_exp or norm_cleaned == norm_b:
                            backup_matches = True
                    except Exception:
                        pass

                if (backup_matches or force_restore) and target_backup:
                    try:
                        backup_mode = None
                        try:
                            backup_mode = target_backup.stat().st_mode
                        except Exception:
                            pass
                        is_backup_symlink = target_backup.is_symlink()
                        _verify_destination_unmodified(hook_file, initial_exists, initial_is_symlink, initial_target, orig_bytes)
                        _restore_backup_file(target_backup, hook_file, is_backup_symlink, backup_mode)
                        print(f"[Triad Hook] Restored previous hook from {target_backup}")
                    except Exception as e:
                        print(f"❌ [Triad Hook Error] Failed to restore pre-commit hook: {e}", file=sys.stderr)
                        sys.exit(1)
                else:
                    # Write back the cleaned user hook, preserving all user edits made after installation!
                    temp_hook = hooks_dir / f".pre-commit.tmp.{uuid.uuid4().hex[:8]}"
                    try:
                        cleaned_bytes = cleaned.encode("utf-8")
                        if not cleaned_bytes.endswith(b"\n"):
                            cleaned_bytes += b"\n"
                        temp_hook.write_bytes(cleaned_bytes)
                        mode_to_set = orig_mode if orig_mode is not None else 0o755
                        try:
                            temp_hook.chmod(mode_to_set)
                        except Exception:
                            pass
                        _verify_destination_unmodified(hook_file, initial_exists, initial_is_symlink, initial_target, orig_bytes)
                        os.replace(str(temp_hook), str(hook_file))
                        if target_backup:
                            try:
                                target_backup.unlink()
                            except Exception:
                                pass
                            sidecar = _find_link_target_sidecar(target_backup)
                            if sidecar and sidecar.exists():
                                sidecar.unlink(missing_ok=True)
                    except Exception as e:
                        if temp_hook.exists():
                            try:
                                temp_hook.unlink()
                            except Exception:
                                pass
                        print(f"❌ [Triad Hook Error] Failed to clean hook: {e}", file=sys.stderr)
                        sys.exit(1)

                if is_husky:
                    print(f"✓ Triad pre-commit hook uninstalled from Husky hook at {hook_file}")
                else:
                    print(f"✓ Triad pre-commit hook uninstalled from {hook_file}")
                return

            try:
                # Standalone hook edit protection: refuse to delete if user modified hook after install
                m_act = re.search(r"# TRIAD_BACKUP_ACTIVE:\s*([01])", content)
                backup_active = (m_act.group(1).strip() == "1") if m_act else True
                expected_template = _render_hook_template(owned_backup_name or "none", should_execute_backup=backup_active)
                if content.replace("\r\n", "\n").strip() != expected_template.replace("\r\n", "\n").strip():
                    if not force_restore:
                        print(
                            "[Triad Hook Warning] Standalone pre-commit hook contains user modifications made after installation.\n"
                            "Refusing to uninstall without --force to prevent data loss.",
                            file=sys.stderr
                        )
                        sys.exit(1)

                if target_backup:
                    backup_mode = None
                    try:
                        backup_mode = target_backup.stat().st_mode
                    except Exception:
                        pass
                    is_backup_symlink = target_backup.is_symlink()
                    _verify_destination_unmodified(hook_file, initial_exists, initial_is_symlink, initial_target, orig_bytes)
                    _restore_backup_file(target_backup, hook_file, is_backup_symlink, backup_mode)
                    print(f"[Triad Hook] Restored previous hook from {target_backup}")
                else:
                    _verify_destination_unmodified(hook_file, initial_exists, initial_is_symlink, initial_target, orig_bytes)
                    hook_file.unlink(missing_ok=True)
            except Exception as e:
                print(f"❌ [Triad Hook Error] Failed to restore pre-commit hook: {e}", file=sys.stderr)
                sys.exit(1)
            print(f"✓ Triad pre-commit hook uninstalled from {hook_file}")

    elif action == "status":
        is_hook_existing = hook_file.is_symlink() or hook_file.exists()
        if not is_hook_existing:
            print("Triad pre-commit hook: Not installed")
        else:
            content = ""
            try:
                content = hook_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
            if TRIAD_HOOK_SIGNATURE in content:
                legacy_hooks = [p for p in hook_file.parent.glob("pre-commit.legacy*") if (p.is_symlink() or p.exists()) and not p.name.endswith(".triad_link_target")]
                has_pre_commit_framework_backup = any(
                    ("pre-commit.com" in p.read_text(encoding="utf-8", errors="replace").lower()
                     or "file generated by pre-commit" in p.read_text(encoding="utf-8", errors="replace").lower())
                    for p in legacy_hooks if p.is_file()
                )
                if "husky" in content.lower() or ".husky" in str(hook_file):
                    print(f"Triad pre-commit hook: Installed (integrated with Husky at {hook_file})")
                elif "pre-commit.com" in content.lower() or "file generated by pre-commit" in content.lower() or has_pre_commit_framework_backup:
                    print(f"Triad pre-commit hook: Installed (integrated with pre-commit framework at {hook_file})")
                elif legacy_hooks:
                    print(f"Triad pre-commit hook: Installed (with legacy hook chained at {hook_file})")
                else:
                    print(f"Triad pre-commit hook: Installed ({hook_file})")
            else:
                hook_type = "Custom/Third-party"
                if "husky" in content.lower() or ".husky" in str(hook_file):
                    hook_type = "Husky"
                elif "pre-commit.com" in content.lower() or "file generated by pre-commit" in content.lower():
                    hook_type = "pre-commit framework"
                print(f"Triad pre-commit hook: {hook_type} hook installed ({hook_file})")


