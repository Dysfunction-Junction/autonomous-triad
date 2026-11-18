#!/usr/bin/env python3
# Tags: morphogenetic, verification, test-fixture
# Links: triad/morpho.py, triad/morphogenetic.py, triad/ts_verify/__init__.py
# Queries: "how are SH-0 gates and TypeScript verification tested"
"""SH-0 tests: protected safety paths, TS verify image, failing-check intake.

Covers decision D12 (docs/superpowers/plans/2026-11-12-self-healing-ladder.md):
protected_paths.txt wiring, the exocortex-verify image contract and 2g tmpfs,
and the morpho branch / gate-report / mutations-row wiring. All hermetic: git
runs only in temp dirs, Docker is faked, no network.
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest
pytestmark = pytest.mark.xdist_group("triad-git-worktree")

from triad.docker_runner import DockerRunner, IsolationUnavailable
from triad.morphogenetic import MorphogeneticEngine, MutationCandidate, RuntimeFrictionEvent
from triad.morpho import (
    RECAP_MODEL_ENV,
    build_mutation_row,
    create_morpho_branch,
    friction_from_failing_check,
    insert_mutation_row,
    patch_class_for,
    preflight,
    render_gate_report,
    run_sh0_once,
)
from triad.tests.test_morphogenetic import FakeRunner, _Engine, _make_repo
import triad.ts_verify as ts_verify


def _make_repo_with(td, files):
    repo = Path(td).resolve()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    base = ["git", "-C", str(repo), "-c", "user.email=t@example.com",
            "-c", "user.name=t", "-c", "core.autocrlf=false"]
    for rel, data in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    subprocess.run(base + ["add", "-A"], check=True)
    subprocess.run(base + ["commit", "-qm", "init"], check=True)
    return repo


class _StatefulRunner:
    """Same check red on base, green on the candidate (SH-0 same-profile runs)."""

    def __init__(self, verify_rc=0):
        self.verify_rc = verify_rc
        self.calls = []

    def run(self, *, workspace, profile, timeout):
        self.calls.append(profile)
        rc = 1 if len(self.calls) == 1 else self.verify_rc
        return subprocess.CompletedProcess(args=[profile], returncode=rc,
                                           stdout=f"check {profile} rc={rc}", stderr="")


class _FakeDocker:
    """Fake docker CLI with a controllable `image inspect` result."""

    def __init__(self, inspect_rc=0):
        self.calls = []
        self.inspect_rc = inspect_rc

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        if cmd[1] == "info":
            return subprocess.CompletedProcess(cmd, 0, "27.0.1\n", "")
        if cmd[1] == "image":
            return subprocess.CompletedProcess(cmd, self.inspect_rc, "{}", "no such image")
        if cmd[1] == "run":
            return subprocess.CompletedProcess(cmd, 0, "ok", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def verbs(self):
        return [c[1] for c in self.calls]

    def run_cmd(self):
        return next(c for c in self.calls if c[1] == "run")


class TestProtectedPathsFile(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name).resolve()
        self.engine = MorphogeneticEngine(self.root)

    def _protected(self, rel):
        return self.engine._is_protected_target(self.root, (self.root / rel).resolve())

    def test_plan_safety_paths_are_protected(self):
        for rel in [
            "packages/triad/triad/morphogenetic.py",
            "packages/triad/triad/protected_paths.txt",
            "packages/triad/triad/ts_verify/__init__.py",
            "packages/allowlist/src/index.ts",
            "apps/daemon/src/approval-attestation.ts",
            "apps/daemon/src/key-attestation.ts",
            "apps/daemon/src/delegate-capabilities.ts",
            "apps/daemon/src/shadow-recorder.ts",
            "apps/daemon/src/scripted-executors.ts",
            "apps/daemon/src/pending-proposals.ts",
            "apps/daemon/src/attestation-roots/google-roots.ts",
            "apps/daemon/ops/supervisor.ts",
            "scripts/repo-tags.mjs",
        ]:
            with self.subTest(rel=rel):
                self.assertTrue(self._protected(rel), rel)

    def test_event_log_and_migrations_are_protected(self):
        for rel in [
            "packages/core/db.ts",
            "packages/core/canonical.ts",
            "packages/core/schema.sql",
            "packages/core/schema-types.ts",
            "packages/core/migrations/001.sql",
            "apps/daemon/migrations/002.sql",
            "migrations/003.sql",
        ]:
            with self.subTest(rel=rel):
                self.assertTrue(self._protected(rel), rel)

    def test_ordinary_source_is_not_protected(self):
        for rel in [
            "apps/daemon/src/server.ts",
            "packages/core/index.ts",
            "packages/memory/notes.ts",
            "scripts/other.mjs",
            "packages/core/migration-helper.ts",
            "apps/daemon/src/attestation-roots-backup/x.ts",
        ]:
            with self.subTest(rel=rel):
                self.assertFalse(self._protected(rel), rel)

    def test_matching_is_case_insensitive(self):
        self.assertTrue(self._protected("PACKAGES/TRIAD/TRIAD/MORPHOGENETIC.PY"))
        self.assertTrue(self._protected("APPS/DAEMON/SRC/SHADOW-RECORDER.TS"))
        self.assertTrue(self._protected("Packages/Core/DB.ts"))

    def test_dotdot_cannot_hide_a_safety_path(self):
        self.assertTrue(self._protected("src/../packages/triad/triad/x.py"))
        self.assertTrue(self._protected("apps/daemon/src/../src/shadow-recorder.ts"))

    def test_protected_target_rejected_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo_with(td, {
                "apps/daemon/src/shadow-recorder.ts": b"export const a = 1;\n",
                "src/app.py": b"a = 1\n",
            })
            engine = _Engine(repo, verification_runner=FakeRunner())
            cand = MutationCandidate("p", "d", "apps/daemon/src/shadow-recorder.ts",
                                     "", "export const a = 2;\n")
            self.assertFalse(engine.evaluate_mutation_in_sandbox(cand, "unit"))
            self.assertIn("protected", cand.verification_output)


class TestTsVerify(unittest.TestCase):
    def test_image_tag_is_first12_of_lockfile_sha(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "pnpm-lock.yaml").write_bytes(b"lockfileVersion: 9.0\n")
            tag = ts_verify.image_tag_for_lockfile(td)
            expect = "exocortex-verify:" + hashlib.sha256(b"lockfileVersion: 9.0\n").hexdigest()[:12]
            self.assertEqual(tag, expect)

    def test_image_tag_missing_lockfile(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                ts_verify.image_tag_for_lockfile(td)

    def test_is_ts_verify_image(self):
        self.assertTrue(ts_verify.is_ts_verify_image("exocortex-verify:abc123"))
        self.assertFalse(ts_verify.is_ts_verify_image("python:3.12-slim"))
        self.assertFalse(ts_verify.is_ts_verify_image("exocortex-verify"))

    def test_profile_argv_valid(self):
        self.assertEqual(
            ts_verify.ts_profile_argv("apps/daemon", run_tsc=True),
            ["/usr/local/bin/verify-ts", "apps/daemon", "--tsc"],
        )
        self.assertEqual(
            ts_verify.ts_profile_argv("packages/core", test_files=["packages/core/src/a.test.ts"]),
            ["/usr/local/bin/verify-ts", "packages/core", "packages/core/src/a.test.ts"],
        )

    def test_profile_argv_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            ts_verify.ts_profile_argv("../evil", run_tsc=True)
        with self.assertRaises(ValueError):
            ts_verify.ts_profile_argv("apps/a/b", run_tsc=True)
        with self.assertRaises(ValueError):
            ts_verify.ts_profile_argv("apps/daemon")  # nothing to do
        with self.assertRaises(ValueError):
            ts_verify.ts_profile_argv("apps/daemon", test_files=["packages/core/a.test.ts"])
        with self.assertRaises(ValueError):
            ts_verify.ts_profile_argv("apps/daemon", test_files=["apps/daemon/src/app.ts"])
        with self.assertRaises(ValueError):
            ts_verify.ts_profile_argv("apps/daemon",
                                      test_files=[f"apps/daemon/src/a{i}.test.ts" for i in range(21)])

    def test_profile_argv_checks_repo_when_given(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "apps" / "daemon" / "src").mkdir(parents=True)
            (root / "apps" / "daemon" / "package.json").write_text("{}", encoding="utf-8")
            (root / "apps" / "daemon" / "src" / "a.test.ts").write_text("x", encoding="utf-8")
            argv = ts_verify.ts_profile_argv("apps/daemon", run_tsc=True, repo_root=root)
            self.assertEqual(argv[1], "apps/daemon")
            with self.assertRaises(ValueError):
                ts_verify.ts_profile_argv("apps/daemon",
                                          test_files=["apps/daemon/src/missing.test.ts"],
                                          repo_root=root)
            with self.assertRaises(ValueError):
                ts_verify.ts_profile_argv("packages/nope", run_tsc=True, repo_root=root)

    def test_workspace_package_jsons(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "apps" / "a").mkdir(parents=True)
            (root / "packages" / "b").mkdir(parents=True)
            (root / "apps" / "a" / "package.json").write_text("{}", encoding="utf-8")
            (root / "packages" / "b" / "package.json").write_text("{}", encoding="utf-8")
            (root / "packages" / "b" / "notes.txt").write_text("x", encoding="utf-8")
            self.assertEqual(ts_verify.workspace_package_jsons(root),
                             ["apps/a/package.json", "packages/b/package.json"])

    def test_docker_tmpfs_is_2g_for_verify_image_only(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            docker = _FakeDocker()
            runner = DockerRunner({"u": ["true"]}, image="exocortex-verify:abc123",
                                  runner=docker, docker_bin="docker")
            runner.run(workspace=ws, profile="u", timeout=5)
            cmd = docker.run_cmd()
            self.assertEqual(cmd.count("--tmpfs"), 1)
            self.assertEqual(cmd[cmd.index("--tmpfs") + 1], "/tmp:rw,nosuid,size=2g")
            docker2 = _FakeDocker()
            runner2 = DockerRunner({"u": ["true"]}, runner=docker2, docker_bin="docker")
            runner2.run(workspace=ws, profile="u", timeout=5)
            self.assertEqual(docker2.run_cmd().count("--tmpfs"), 1)
            self.assertIn("/tmp:rw,nosuid,size=64m", docker2.run_cmd())

    def test_ensure_image_refuses_to_pull_verify_image(self):
        docker = _FakeDocker(inspect_rc=1)
        runner = DockerRunner({"u": ["true"]}, image="exocortex-verify:deadbeefcafe",
                              runner=docker, docker_bin="docker")
        with self.assertRaises(IsolationUnavailable) as cm:
            runner.ensure_image()
        self.assertIn("never pulled", str(cm.exception))
        self.assertNotIn("pull", docker.verbs())

    def test_ensure_image_still_pulls_ordinary_images(self):
        docker = _FakeDocker(inspect_rc=1)
        runner = DockerRunner({"u": ["true"]}, runner=docker, docker_bin="docker")
        runner.ensure_image()
        self.assertIn("pull", docker.verbs())

    def test_make_runner_pins_tag_and_tmpfs(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "pnpm-lock.yaml").write_bytes(b"lock\n")
            runner = ts_verify.make_ts_verify_runner(td, {"u": ["true"]})
            self.assertEqual(runner.image, ts_verify.image_tag_for_lockfile(td))
            self.assertEqual(runner.tmpfs_size, "2g")

    def test_verify_sources_shape(self):
        src = ts_verify.SOURCE_DIR
        self.assertTrue((src / "Dockerfile").is_file())
        raw = (src / "verify-ts").read_bytes()
        self.assertNotIn(b"\r", raw)
        text = raw.decode("utf-8")
        self.assertTrue(text.startswith("#!/bin/sh"))
        for needle in ("/work", "mktemp", "trap", "verify-ts: RESULT", "tsc", "--noEmit", "node_modules"):
            self.assertIn(needle, text)
        docker_text = (src / "Dockerfile").read_text(encoding="utf-8")
        for needle in ("node:24", "pnpm install --frozen-lockfile", "/usr/local/bin/verify-ts"):
            self.assertIn(needle, docker_text)

    def test_stage_build_context_is_minimal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            (root / "apps" / "a").mkdir(parents=True)
            (root / "packages" / "b").mkdir(parents=True)
            (root / "package.json").write_text("{}", encoding="utf-8")
            (root / "pnpm-workspace.yaml").write_text("packages:\n", encoding="utf-8")
            (root / "pnpm-lock.yaml").write_text("lock\n", encoding="utf-8")
            (root / "apps" / "a" / "package.json").write_text("{}", encoding="utf-8")
            (root / "packages" / "b" / "package.json").write_text("{}", encoding="utf-8")
            (root / "apps" / "a" / "src.ts").write_text("x", encoding="utf-8")
            dest = Path(td) / "ctx"
            dest.mkdir()
            ts_verify._stage_build_context(root, dest)
            self.assertTrue((dest / "pnpm-lock.yaml").is_file())
            self.assertTrue((dest / "apps" / "a" / "package.json").is_file())
            self.assertTrue((dest / "packages" / "b" / "package.json").is_file())
            self.assertFalse((dest / "apps" / "a" / "src.ts").exists())
            self.assertNotIn(b"\r", (dest / "verify-ts").read_bytes())


class TestPatchClass(unittest.TestCase):
    def test_fixed_pairs(self):
        self.assertEqual(patch_class_for("red-test", "apps/daemon/src/x.ts"), "red-test:apps/daemon")
        self.assertEqual(patch_class_for("tsc", "packages/memory/y.ts"), "tsc:packages/memory")

    def test_shallow_and_empty_paths(self):
        self.assertEqual(patch_class_for("tsc", "README.md"), "tsc:README.md")
        self.assertEqual(patch_class_for("tsc", ""), "tsc:unknown")

    def test_bad_kind_rejected(self):
        with self.assertRaises(ValueError):
            patch_class_for("model-says", "apps/daemon/x.ts")


class TestFrictionIntake(unittest.TestCase):
    def test_ok(self):
        ev = friction_from_failing_check(
            check_kind="red-test", package="packages/memory",
            failing_file="packages/memory/notes.ts",
            check_output="FAIL notes.test.ts\nAssertionError: nope",
            verification_profile="memory-tests", base_commit="abc123",
            event_id="friction_1",
        )
        self.assertEqual(ev.event_id, "friction_1")
        self.assertEqual(ev.error_type, "failing_check")
        self.assertIn("red-test", ev.message)
        self.assertIn("packages/memory", ev.message)
        self.assertEqual(ev.context["patch_class"], "red-test:packages/memory")
        self.assertEqual(ev.context["verification_profile"], "memory-tests")
        self.assertEqual(ev.context["reproduction_profile"], "memory-tests")
        self.assertEqual(ev.context["base_commit"], "abc123")
        self.assertIn("AssertionError", ev.context["check_output"])

    def test_event_id_defaults_to_friction_hex(self):
        ev = friction_from_failing_check(
            check_kind="tsc", package="apps/daemon", failing_file="apps/daemon/src/x.ts",
            check_output="error TS2322", verification_profile="tsc-daemon",
        )
        self.assertRegex(ev.event_id, r"^friction_[0-9a-f]{8}$")

    def test_check_output_truncated(self):
        ev = friction_from_failing_check(
            check_kind="tsc", package="apps/daemon", failing_file="apps/daemon/src/x.ts",
            check_output="y" * 9000, verification_profile="p",
        )
        self.assertEqual(len(ev.context["check_output"]), 4000)

    def test_bad_inputs_rejected(self):
        kw = dict(check_kind="red-test", package="packages/memory",
                  failing_file="packages/memory/notes.ts", check_output="x",
                  verification_profile="p")
        with self.assertRaises(ValueError):
            friction_from_failing_check(**{**kw, "check_kind": "vibes"})
        with self.assertRaises(ValueError):
            friction_from_failing_check(**{**kw, "package": "../evil"})
        with self.assertRaises(ValueError):
            friction_from_failing_check(**{**kw, "verification_profile": "  "})
        for bad_file in ("/etc/x", "a.py:stream", "src\\app.py", ""):
            with self.subTest(bad_file=bad_file):
                with self.assertRaises(ValueError):
                    friction_from_failing_check(**{**kw, "failing_file": bad_file})

    def test_protected_and_missing_targets_fail_fast_with_repo(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tests").mkdir()
            (root / "tests" / "x.py").write_text("x", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("y", encoding="utf-8")
            with self.assertRaises(ValueError) as cm:
                friction_from_failing_check(
                    check_kind="red-test", package="packages/memory",
                    failing_file="tests/x.py", check_output="x",
                    verification_profile="p", repo_root=root)
            self.assertIn("protected", str(cm.exception))
            with self.assertRaises(ValueError):
                friction_from_failing_check(
                    check_kind="red-test", package="packages/memory",
                    failing_file="src/missing.py", check_output="x",
                    verification_profile="p", repo_root=root)
            ok = friction_from_failing_check(
                check_kind="red-test", package="packages/memory",
                failing_file="src/app.py", check_output="x",
                verification_profile="p", repo_root=root)
            self.assertEqual(ok.failing_file, "src/app.py")


class TestPreflight(unittest.TestCase):
    def test_recap_model_loaded_blocks(self):
        with mock.patch.dict(os.environ, {RECAP_MODEL_ENV: "1"}):
            ok, reason = preflight()
        self.assertFalse(ok)
        self.assertIn("recap model", reason)

    def test_memory_floor(self):
        ok, _ = preflight(min_free_mb=1)
        self.assertTrue(ok)
        ok, reason = preflight(min_free_mb=2 ** 30)
        self.assertFalse(ok)
        self.assertIn("free", reason)

    def test_bad_env_floor_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"TRIAD_MORPHOGENETIC_MIN_FREE_MB": "junk"}):
            ok, reason = preflight(min_free_mb=None)
        self.assertIn(str(2048), reason)


class TestEngineGateRecords(unittest.TestCase):
    def test_gates_recorded_in_run_order(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo(td)
            engine = MorphogeneticEngine(repo, verification_runner=FakeRunner(returncode=0),
                                         enabled=True, require_reproduction=False,
                                         enable_scan_gate=False)
            cand = MutationCandidate("c1", "d", "src/app.py", "", "a = 1\nb = 99\n")
            self.assertTrue(engine.evaluate_mutation_in_sandbox(cand, "unit"))
            names = [g["gate"] for g in cand.gates]
            self.assertEqual(names, ["enabled", "runner", "target_input", "target_resolve",
                                     "protected", "symlink", "noop", "diff_cap",
                                     "forbidden_tokens", "verification", "git_pointer",
                                     "target_stable", "tree_clean", "diff"])
            self.assertTrue(all(g["passed"] for g in cand.gates))

    def test_gates_reset_and_show_the_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo(td)
            engine = MorphogeneticEngine(repo, verification_runner=FakeRunner(returncode=0),
                                         enabled=True, require_reproduction=False,
                                         enable_scan_gate=False)
            cand = MutationCandidate("c1", "d", "src/app.py", "", "a = 1\nb = 99\n")
            self.assertTrue(engine.evaluate_mutation_in_sandbox(cand, "unit"))
            engine.verification_runner = FakeRunner(returncode=1, stderr="boom")
            self.assertFalse(engine.evaluate_mutation_in_sandbox(cand, "unit"))
            names = [g["gate"] for g in cand.gates]
            self.assertEqual(names[0], "enabled")
            self.assertEqual(names[-1], "verification")
            self.assertFalse(cand.gates[-1]["passed"])
            self.assertEqual(len(names), 10)

    def test_trial_results_carry_gates(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo(td)
            engine = MorphogeneticEngine(repo, verification_runner=FakeRunner(returncode=0),
                                         enabled=True, require_reproduction=False,
                                         enable_scan_gate=False)
            cand = MutationCandidate("c1", "d", "src/app.py", "", "a = 1\nb = 99\n")
            ev = RuntimeFrictionEvent("e", "t", "m", "s", failing_file="src/app.py")
            trial = engine.execute_darwinian_trial(ev, [cand], "unit")
            self.assertEqual(trial["survivor"], "c1")
            self.assertTrue(trial["results"][0]["gates"])
            self.assertTrue(all(g["passed"] for g in trial["results"][0]["gates"]))


MUTATIONS_DDL = """CREATE TABLE mutations (
  mutation_id    TEXT PRIMARY KEY,
  friction_seq   INTEGER NOT NULL,
  base_commit    TEXT NOT NULL,
  branch         TEXT NOT NULL,
  strategy       TEXT NOT NULL,
  diff_hash      BLOB NOT NULL,
  gates          TEXT NOT NULL,
  state          TEXT NOT NULL,
  created_at     INTEGER NOT NULL
)"""


def _passed_candidate(target="packages/memory/notes.ts"):
    return MutationCandidate(
        "mut_sh0_1", "d", target, "export const a = 1;\n", "export const a = 2;\n",
        unified_diff=("diff --git a/packages/memory/notes.ts b/packages/memory/notes.ts\n"
                      "--- a/packages/memory/notes.ts\n+++ b/packages/memory/notes.ts\n"
                      "@@ -1 +1 @@\n-export const a = 1;\n+export const a = 2;\n"),
        survival_passed=True, verification_output="ok",
        gates=[{"gate": "verification", "passed": True, "detail": "exit 0"}],
    )


def _sh0_friction(event_id="friction_sh0test01", repo_root=None):
    return friction_from_failing_check(
        check_kind="red-test", package="packages/memory",
        failing_file="packages/memory/notes.ts",
        check_output="FAIL notes.test.ts\nAssertionError: expected 1 to be 2",
        verification_profile="memory-tests", base_commit="HEAD",
        event_id=event_id, repo_root=repo_root,
    )


class TestMorphoBranch(unittest.TestCase):
    def test_branch_created_with_only_the_target(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo_with(td, {"packages/memory/notes.ts": b"export const a = 1;\n"})
            info = create_morpho_branch(
                repo_root=repo, base_commit="HEAD", event=_sh0_friction(repo_root=repo),
                survivor=_passed_candidate(), strategy="test:manual")
            self.assertEqual(info["branch"], "morpho/friction_sh0test01")
            self.assertRegex(info["sha"], r"^[0-9a-f]{40}$")
            self.assertEqual((info["added"], info["deleted"]), (1, 1))
            self.assertEqual(info["patch_class"], "red-test:packages/memory")
            self.assertFalse(info["pushed"])
            verify = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify",
                                     "refs/heads/" + info["branch"]],
                                    capture_output=True, text=True)
            self.assertEqual(verify.returncode, 0)
            names = subprocess.run(["git", "-C", str(repo), "diff", "--name-only",
                                    f"{info['base_sha']}..{info['sha']}"],
                                   capture_output=True, text=True)
            self.assertEqual(names.stdout.split(), ["packages/memory/notes.ts"])
            status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                    capture_output=True, text=True)
            self.assertEqual(status.stdout.strip(), "")

    def test_existing_branch_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo_with(td, {"packages/memory/notes.ts": b"export const a = 1;\n"})
            kw = dict(repo_root=repo, base_commit="HEAD", event=_sh0_friction(repo_root=repo),
                      survivor=_passed_candidate())
            create_morpho_branch(**kw)
            with self.assertRaises(ValueError) as cm:
                create_morpho_branch(**kw)
            self.assertIn("already exists", str(cm.exception))

    def test_needs_a_survivor_and_a_safe_event_id(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo_with(td, {"packages/memory/notes.ts": b"export const a = 1;\n"})
            weak = _passed_candidate()
            weak.survival_passed = False
            with self.assertRaises(ValueError):
                create_morpho_branch(repo_root=repo, base_commit="HEAD",
                                     event=_sh0_friction(), survivor=weak)
            evil = RuntimeFrictionEvent("../evil", "failing_check", "m", "s",
                                        failing_file="packages/memory/notes.ts", context={})
            with self.assertRaises(ValueError):
                create_morpho_branch(repo_root=repo, base_commit="HEAD",
                                     event=evil, survivor=_passed_candidate())


class TestGateReport(unittest.TestCase):
    def test_every_gate_reported(self):
        ev = _sh0_friction()
        cand = _passed_candidate()
        cand.gates = [
            {"gate": "enabled", "passed": True, "detail": "TRIAD_MORPHOGENETIC set"},
            {"gate": "verification", "passed": True, "detail": "memory-tests exit 0"},
        ]
        trial = {"candidates_evaluated": 2, "survivor": cand.candidate_id, "results": [
            {"candidate_id": cand.candidate_id, "survival_passed": True, "gates": cand.gates},
            {"candidate_id": "mut_dead", "survival_passed": False, "gates": [
                {"gate": "enabled", "passed": True, "detail": ""},
                {"gate": "verification", "passed": False, "detail": "exit 1 (apoptosis)"},
            ]},
        ]}
        branch = {"branch": "morpho/friction_sh0test01", "sha": "a" * 40,
                  "base_sha": "b" * 40, "added": 1, "deleted": 1,
                  "patch_class": "red-test:packages/memory"}
        report = render_gate_report(event=ev, survivor=cand, trial_result=trial,
                                    branch_info=branch, image="exocortex-verify:abc",
                                    repo="sovereign-exocortex")
        for gate in ("enabled", "runner", "reproduction", "verification", "diff"):
            self.assertIn(f"| {gate} |", report)
        self.assertIn("| runner | not run |", report)
        self.assertIn("| verification | PASS |", report)
        self.assertIn("mut_dead", report)
        self.assertIn("apoptosis", report)
        self.assertIn("morpho/friction_sh0test01", report)
        self.assertIn("red-test:packages/memory", report)
        self.assertIn("```diff", report)


class TestMutationRow(unittest.TestCase):
    def test_build_row_shape(self):
        row = build_mutation_row(candidate=_passed_candidate(), event=_sh0_friction(),
                                 friction_seq=7, base_commit="b" * 40,
                                 branch="morpho/friction_sh0test01", strategy="test:manual")
        self.assertEqual(row["mutation_id"], "mut_sh0_1")
        self.assertEqual((row["friction_seq"], row["branch"], row["state"]), (7, "morpho/friction_sh0test01", "PASSED"))
        self.assertEqual(len(row["diff_hash"]), 32)
        self.assertTrue(json.loads(row["gates"]))
        with self.assertRaises(ValueError):
            build_mutation_row(candidate=_passed_candidate(), event=_sh0_friction(),
                               friction_seq=7, base_commit="x", branch="y", state="MAYBE")

    def test_insert_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "t.db"
            conn = sqlite3.connect(str(db))
            conn.execute(MUTATIONS_DDL)
            conn.commit()
            conn.close()
            row = build_mutation_row(candidate=_passed_candidate(), event=_sh0_friction(),
                                     friction_seq=3, base_commit="abc", branch="morpho/x")
            insert_mutation_row(db, row)
            conn = sqlite3.connect(str(db))
            got = conn.execute("SELECT mutation_id, friction_seq, state FROM mutations").fetchall()
            conn.close()
            self.assertEqual(got, [("mut_sh0_1", 3, "PASSED")])

    def test_insert_needs_a_seq(self):
        row = build_mutation_row(candidate=_passed_candidate(), event=_sh0_friction(),
                                 friction_seq=None, base_commit="abc", branch="morpho/x")
        with self.assertRaises(ValueError):
            insert_mutation_row(Path("nowhere.db"), row)


class TestRunSh0Once(unittest.TestCase):
    def test_produces_branch_report_and_row(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo_with(td, {"packages/memory/notes.ts": b"export const a = 1;\n"})
            friction = _sh0_friction(repo_root=repo)
            candidate = MutationCandidate("mut_sh0_1", "d", "packages/memory/notes.ts",
                                          "", "export const a = 2;\n")
            engine = MorphogeneticEngine(repo, verification_runner=_StatefulRunner(), enabled=True)
            out = run_sh0_once(friction, [candidate], engine, base_commit="HEAD",
                               strategy="test:manual", preflight_check=False, friction_seq=7,
                               image="exocortex-verify:abc123", repo="sovereign-exocortex")
            self.assertTrue(out["preflight_passed"])
            self.assertEqual(out["survivor"], "mut_sh0_1")
            self.assertEqual(out["branch"]["branch"], "morpho/friction_sh0test01")
            self.assertEqual(out["branch"]["patch_class"], "red-test:packages/memory")
            self.assertEqual(out["mutation_row"]["friction_seq"], 7)
            for needle in ("SH-0 gated patch", "friction_sh0test01",
                           "| verification | PASS |", "| reproduction | PASS |",
                           "morpho/friction_sh0test01", "red-test:packages/memory",
                           "exocortex-verify:abc123"):
                self.assertIn(needle, out["report"])
            status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                    capture_output=True, text=True)
            self.assertEqual(status.stdout.strip(), "")

    def test_no_survivor_means_no_branch(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo_with(td, {"packages/memory/notes.ts": b"export const a = 1;\n"})
            friction = _sh0_friction(repo_root=repo)
            candidate = MutationCandidate("mut_sh0_1", "d", "packages/memory/notes.ts",
                                          "", "export const a = 2;\n")
            engine = MorphogeneticEngine(repo, verification_runner=_StatefulRunner(verify_rc=1),
                                         enabled=True)
            out = run_sh0_once(friction, [candidate], engine, preflight_check=False)
            self.assertTrue(out["preflight_passed"])
            self.assertIsNone(out["survivor"])
            self.assertIsNone(out["branch"])
            self.assertIsNone(out["report"])
            self.assertIsNone(out["mutation_row"])
            branches = subprocess.run(["git", "-C", str(repo), "branch", "--list", "morpho/*"],
                                      capture_output=True, text=True)
            self.assertEqual(branches.stdout.strip(), "")

    def test_preflight_blocks_the_trial(self):
        with tempfile.TemporaryDirectory() as td:
            friction = _sh0_friction()
            runner = _StatefulRunner()
            engine = MorphogeneticEngine(Path(td), verification_runner=runner, enabled=True)
            with mock.patch.dict(os.environ, {RECAP_MODEL_ENV: "1"}):
                out = run_sh0_once(friction, [], engine, preflight_check=True)
            self.assertFalse(out["preflight_passed"])
            self.assertIn("recap model", out["preflight_reason"])
            self.assertIsNone(out["trial"])
            self.assertEqual(runner.calls, [])

    def test_unrun_gates_render_as_not_run(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo(td)
            friction = friction_from_failing_check(
                check_kind="red-test", package="packages/memory",
                failing_file="src/app.py", check_output="red",
                verification_profile="unit", event_id="friction_notrun")
            candidate = MutationCandidate("c1", "d", "src/app.py", "", "a = 1\nb = 99\n")
            engine = MorphogeneticEngine(repo, verification_runner=FakeRunner(returncode=0),
                                         enabled=True, require_reproduction=False,
                                         enable_scan_gate=False)
            out = run_sh0_once(friction, [candidate], engine, preflight_check=False)
            self.assertEqual(out["survivor"], "c1")
            self.assertIn("| reproduction | not run |", out["report"])
            self.assertIn("| scan | not run |", out["report"])


if __name__ == "__main__":
    unittest.main()
