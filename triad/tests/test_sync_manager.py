#!/usr/bin/env python3
"""
Unit tests for Triad Sync Manager (triad/sync_manager.py).
Verifies:
- Detection and synchronization of CLI launchers
- Detection and synchronization of claude-advisor skill files
- Audit and installation of pre-commit hooks in git repositories
- LF line-ending enforcement on Windows
- Same-directory safety guard against self-deletion
- Ancestor / parent containment safety guard against circular moves
- Granular component selection in run_full_sync
- Dry-run preview isolation (leaves disk untouched, no mkdirs)
- OS-level lock contention detection
- Repos=[] handling
"""

import os
import time
import tempfile
import unittest
from pathlib import Path

from triad.sync_manager import (
    sync_launchers,
    sync_skills,
    sync_hooks,
    sync_engine,
    run_full_sync,
    _file_hash,
    _norm_path_str,
)


class TestSyncManager(unittest.TestCase):

    def test_norm_path_str_strips_device_prefixes(self):
        self.assertEqual(
            _norm_path_str(r"\\?\C:\Users\micha\projects\autonomous-triad\triad"),
            "c:/users/micha/projects/autonomous-triad/triad" if os.name == "nt" else "C:/Users/micha/projects/autonomous-triad/triad"
        )
        self.assertEqual(
            _norm_path_str(r"\\?\UNC\server\share\repo"),
            "//server/share/repo"
        )

    def test_file_hash_handles_errors_gracefully(self):
        self.assertIsNone(_file_hash(Path("non_existent_path_xyz_123.bin")))

    def test_sync_engine_same_directory_guard(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            res = sync_engine(p, p, dry_run=False)
            self.assertEqual(res["status"], "error")
            self.assertIn("same physical directory", res["detail"])
            self.assertTrue(p.exists())

    def test_sync_engine_containment_guard(self):
        with tempfile.TemporaryDirectory() as d:
            parent = Path(d)
            child = parent / "child_triad"
            child.mkdir()

            # Target is ancestor of source
            res = sync_engine(child, parent, dry_run=False)
            self.assertEqual(res["status"], "error")
            self.assertIn("ancestors", res["detail"].lower())

            # Source is ancestor of target
            res2 = sync_engine(parent, child, dry_run=False)
            self.assertEqual(res2["status"], "error")
            self.assertIn("ancestors", res2["detail"].lower())

    def test_sync_engine_lock_contention(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            source = p / "source_triad"
            source.mkdir()
            target = p / "target_triad"
            target.parent.mkdir(parents=True, exist_ok=True)
            lock_file = target.parent / ".triad_sync.lock"

            fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                res = sync_engine(source, target, dry_run=False, lock_timeout=0.2)
                self.assertEqual(res["status"], "error")
                self.assertIn("lock held", res["detail"].lower())
            finally:
                try:
                    if os.name == "nt":
                        import msvcrt
                        os.lseek(fd, 0, 0)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_UN)
                except Exception:
                    pass
                os.close(fd)

    def test_sync_launchers_copies_and_detects(self):
        with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dst_dir:
            src_path = Path(src_dir)
            dst_path = Path(dst_dir)

            (src_path / "triad.cmd").write_text("@echo off\npython -m triad %*", encoding="utf-8")
            (src_path / "triad.ps1").write_text("python -m triad $args", encoding="utf-8")
            (src_path / "triad").write_text("#!/bin/sh\nexec python -m triad \"$@\"", encoding="utf-8")

            # First sync: files must be copied
            res = sync_launchers(src_path, dst_path, dry_run=False)
            self.assertEqual(res["status"], "synchronized")
            self.assertEqual(res["action_taken"], "copied")
            self.assertIn("triad.cmd", res["updated_files"])
            self.assertTrue((dst_path / "triad.cmd").exists())

            # Second sync: already up to date, 0 files copied
            res2 = sync_launchers(src_path, dst_path, dry_run=False)
            self.assertEqual(res2["status"], "up_to_date")
            self.assertEqual(res2["updated_files"], [])

    def test_sync_launchers_dry_run_leaves_disk_untouched(self):
        with tempfile.TemporaryDirectory() as src_dir:
            src_path = Path(src_dir)
            dst_path = src_path / "non_existent_dst_bin"

            (src_path / "triad.cmd").write_text("echo test", encoding="utf-8")

            res = sync_launchers(src_path, dst_path, dry_run=True)
            self.assertEqual(res["status"], "drift_detected")
            self.assertEqual(res["action_taken"], "would_copy")
            # Verify dry-run did NOT create dst_path
            self.assertFalse(dst_path.exists())

    def test_sync_skills_copies_and_detects(self):
        with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dst_dir:
            src_path = Path(src_dir)
            dst_path = Path(dst_dir)

            (src_path / "SKILL.md").write_text("# Skill", encoding="utf-8")
            (src_path / "advisor.py").write_text("# Python bridge", encoding="utf-8")

            res = sync_skills(src_path, dst_path, dry_run=False)
            self.assertEqual(res["status"], "synchronized")
            self.assertTrue((dst_path / "SKILL.md").exists())
            self.assertTrue((dst_path / "advisor.py").exists())

            # Sub-run: up to date
            res2 = sync_skills(src_path, dst_path, dry_run=False)
            self.assertEqual(res2["status"], "up_to_date")

    def test_sync_hooks_audits_and_installs_with_lf_line_endings(self):
        with tempfile.TemporaryDirectory() as repo_dir:
            repo_path = Path(repo_dir)
            (repo_path / ".git").mkdir()

            # Audit: missing
            res = sync_hooks([repo_path], install_missing=False, dry_run=False)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["hook_status"], "not_installed")

            # Install missing
            res_install = sync_hooks([repo_path], install_missing=True, dry_run=False)
            self.assertEqual(res_install[0]["action_taken"], "installed")
            self.assertEqual(res_install[0]["hook_status"], "installed")
            hook_file = repo_path / ".git" / "hooks" / "pre-commit"
            self.assertTrue(hook_file.exists())

            # Verify line endings are strictly LF (\n) and contain no CRLF (\r\n)
            hook_bytes = hook_file.read_bytes()
            self.assertNotIn(b"\r\n", hook_bytes)
            self.assertIn(b"\n", hook_bytes)

            # Re-audit: already installed
            res_audit = sync_hooks([repo_path], install_missing=False, dry_run=False)
            self.assertEqual(res_audit[0]["hook_status"], "installed")

    def test_sync_hooks_empty_repos_list_audits_nothing(self):
        res = sync_hooks(repos=[], install_missing=False, dry_run=False)
        self.assertEqual(res, [])

    def test_run_full_sync_component_flags(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            res = run_full_sync(
                repo_root=p,
                dry_run=True,
                include_engine=False,
                include_launchers=False,
                include_skills=False,
                include_hooks=False,
                repos=[]
            )
            self.assertEqual(res["engine"]["status"], "skipped")
            self.assertEqual(res["launchers"]["status"], "skipped")
            self.assertEqual(res["skills"]["status"], "skipped")
            self.assertEqual(res["hooks"], [])
            self.assertFalse(res["has_error"])


    def test_norm_path_str_handles_nt_unc(self):
        self.assertEqual(
            _norm_path_str(r"\??\UNC\server\share\path"),
            "//server/share/path"
        )
        self.assertEqual(
            _norm_path_str(r"\??\C:\Users\path"),
            "c:/users/path" if os.name == "nt" else "C:/Users/path"
        )

    def test_sync_skills_prunes_deletion_drift(self):
        with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dst_dir:
            src_path = Path(src_dir)
            dst_path = Path(dst_dir)

            (src_path / "SKILL.md").write_text("# Skill", encoding="utf-8")
            (dst_path / "SKILL.md").write_text("# Skill", encoding="utf-8")
            (dst_path / "stale_old_file.txt").write_text("old content", encoding="utf-8")

            res = sync_skills(src_path, dst_path, dry_run=False)
            self.assertEqual(res["status"], "synchronized")
            self.assertIn("stale_old_file.txt", res["deleted_files"])
            self.assertFalse((dst_path / "stale_old_file.txt").exists())
            self.assertTrue((dst_path / "SKILL.md").exists())

    def test_sync_engine_merges_custom_advisors(self):
        import json
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / "repo_triad"
            repo.mkdir()
            target = root / ".agents" / "triad"
            target.mkdir(parents=True)

            repo_adv = {"advisors": [{"name": "claude"}, {"name": "codex"}]}
            target_adv = {"advisors": [{"name": "claude"}, {"name": "my_custom_tool"}]}

            (repo / "advisors.json").write_text(json.dumps(repo_adv), encoding="utf-8")
            (target / "advisors.json").write_text(json.dumps(target_adv), encoding="utf-8")

            with patch.object(Path, "home", return_value=root):
                res = sync_engine(repo, target, dry_run=False)
                self.assertIn(res["status"], ("synchronized", "warning"))

                # Tracked repo advisors.json must remain clean and pristine
                repo_current = json.loads((repo / "advisors.json").read_text(encoding="utf-8"))
                self.assertEqual(len(repo_current["advisors"]), 2)

                # Local overlay file must capture custom advisor in ~/.agents/advisors.local.json
                overlay_file = root / ".agents" / "advisors.local.json"
                self.assertTrue(overlay_file.exists())
                overlay_data = json.loads(overlay_file.read_text(encoding="utf-8"))
                self.assertEqual(overlay_data["advisors"][0]["name"], "my_custom_tool")

                # load_config must merge local overlay
                from triad.advisor_manager import load_config
                merged = load_config(repo / "advisors.json")
                merged_names = [a["name"] for a in merged["advisors"]]
                self.assertIn("my_custom_tool", merged_names)
                self.assertIn("claude", merged_names)
                self.assertIn("codex", merged_names)


if __name__ == "__main__":
    unittest.main()
