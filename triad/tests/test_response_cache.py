"""Tests for triad.response_cache and gate Python resolution."""

# Tags: cache, test-fixture
# Links: triad/response_cache.py
# Queries: "how is a cache key shaped", "how is python resolution handled"

from __future__ import annotations

import json
import os
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from triad.response_cache import (
    PROMPT_SCHEMA_VERSION,
    clear_cache,
    get_cached_response,
    make_cache_key,
    make_synthesis_cache_key,
    put_cached_response,
)
from triad.triad_engine import _resolve_gate_python


class TestResponseCache(unittest.TestCase):
    def test_hit_miss_and_normalization(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            k1 = make_cache_key("claude", "review_diff", "coding", "hello\r\nworld ", diff="a\r\nb", context="ctx")
            k2 = make_cache_key("claude", "review_diff", "coding", "hello\nworld", diff="a\nb", context="ctx")
            self.assertEqual(k1, k2)
            self.assertIsNone(get_cached_response(k1, base_dir=root))

            ok = put_cached_response(k1, "VERDICT: APPROVED", advisor="claude", base_dir=root)
            self.assertTrue(ok)
            self.assertEqual(get_cached_response(k1, base_dir=root), "VERDICT: APPROVED")

    def test_failures_and_mock_not_cached(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            k_fail = make_cache_key("claude", "general", None, "prompt")
            self.assertFalse(put_cached_response(k_fail, "[Error: timeout]", advisor="claude", base_dir=root))
            self.assertIsNone(get_cached_response(k_fail, base_dir=root))

            k_mock = make_cache_key("mock", "general", None, "prompt")
            self.assertFalse(put_cached_response(k_mock, "VERDICT: APPROVED", advisor="mock", base_dir=root))
            self.assertIsNone(get_cached_response(k_mock, base_dir=root))

    def test_ttl_expiry(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            k = make_cache_key("codex", "general", None, "ttl test")
            self.assertTrue(put_cached_response(k, "ok", advisor="codex", ttl=60, base_dir=root))

            entry_path = root / k[:2] / f"{k}.json"
            data = json.loads(entry_path.read_text(encoding="utf-8"))
            data["created"] = time.time() - 120
            entry_path.write_text(json.dumps(data), encoding="utf-8")

            self.assertIsNone(get_cached_response(k, ttl=60, base_dir=root))
            self.assertFalse(entry_path.exists())

    def test_schema_bump_invalidates(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            k_old = make_cache_key("claude", "general", None, "same", schema_version=PROMPT_SCHEMA_VERSION)
            k_new = make_cache_key("claude", "general", None, "same", schema_version="999")
            self.assertNotEqual(k_old, k_new)
            put_cached_response(k_old, "old-val", advisor="claude", base_dir=root)
            self.assertIsNone(get_cached_response(k_new, base_dir=root))

    def test_concurrent_writers_do_not_corrupt(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            k = make_cache_key("claude", "general", None, "concurrent")
            errors = []

            def writer(idx: int) -> None:
                try:
                    for j in range(10):
                        put_cached_response(k, f"resp-{idx}-{j}", advisor="claude", base_dir=root)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [])
            val = get_cached_response(k, base_dir=root)
            self.assertIsNotNone(val)
            self.assertTrue(val.startswith("resp-"))

    def test_kill_switch_and_clear_cache(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            k = make_cache_key("claude", "general", None, "clear-me")
            self.assertTrue(put_cached_response(k, "cached", advisor="claude", base_dir=root))
            with patch.dict(os.environ, {"TRIAD_CACHE": "0"}):
                self.assertIsNone(get_cached_response(k, base_dir=root))
                self.assertFalse(put_cached_response(k, "new", advisor="claude", base_dir=root))
            self.assertEqual(get_cached_response(k, base_dir=root), "cached")
            removed = clear_cache(base_dir=root)
            self.assertEqual(removed, 1)
            self.assertIsNone(get_cached_response(k, base_dir=root))

    def test_lru_pruning_enforces_max_bytes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            k1 = make_cache_key("claude", "general", None, "first")
            k2 = make_cache_key("claude", "general", None, "second")
            put_cached_response(k1, "A" * 200, advisor="claude", base_dir=root, max_bytes=10000)
            p1 = root / k1[:2] / f"{k1}.json"
            old_t = time.time() - 100
            os.utime(p1, (old_t, old_t))
            put_cached_response(k2, "B" * 200, advisor="claude", base_dir=root, max_bytes=350)
            self.assertFalse(p1.exists())
            self.assertIsNotNone(get_cached_response(k2, base_dir=root))

    def test_synthesis_cache_key_differs_on_response_change(self):
        k1 = make_synthesis_cache_key("claude", "codex", "r1", "r2")
        k2 = make_synthesis_cache_key("claude", "codex", "r1-changed", "r2")
        self.assertNotEqual(k1, k2)

    def test_execute_single_advisor_uses_cache_without_slot(self):
        from triad import advisor_manager as am

        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"TRIAD_STATE_DIR": tmp, "TRIAD_CACHE": "1"}):
                adv = {"name": "claude", "role": "production", "enabled": True}
                with patch.object(am, "_resolve_cache_repo_head", return_value="abc123"), \
                     patch.object(am, "_execute_single_advisor_raw", return_value="cached-ok") as raw_mock:
                    res1 = am._execute_single_advisor(
                        adv, "hello cache", diff="diff --git a/x b/x\n+1\n", mode="general", track_circuit=False
                    )
                    self.assertEqual(res1, "cached-ok")
                    self.assertEqual(raw_mock.call_count, 1)

                with patch.object(am, "_resolve_cache_repo_head", return_value="abc123"), \
                     patch.object(am, "_execute_single_advisor_raw", side_effect=AssertionError("should not run")), \
                     patch.object(am.GLOBAL_MODEL_SESSION_LIMITER, "acquire", side_effect=AssertionError("should not acquire")):
                    res2 = am._execute_single_advisor(
                        adv, "hello cache", diff="diff --git a/x b/x\n+1\n", mode="general", track_circuit=False
                    )
                    self.assertEqual(res2, "cached-ok")

                # use_cache=False bypasses cache read
                with patch.object(am, "_resolve_cache_repo_head", return_value="abc123"), \
                     patch.object(am, "_execute_single_advisor_raw", return_value="fresh") as raw_mock:
                    res3 = am._execute_single_advisor(
                        adv, "hello cache", diff="diff --git a/x b/x\n+1\n", mode="general", track_circuit=False, use_cache=False
                    )
                    self.assertEqual(res3, "fresh")
                    self.assertEqual(raw_mock.call_count, 1)

    def test_verdict_modes_do_not_cache_rejected_or_malformed(self):
        from triad import advisor_manager as am

        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"TRIAD_STATE_DIR": tmp, "TRIAD_CACHE": "1"}):
                adv = {"name": "claude", "role": "production", "enabled": True}
                with patch.object(am, "_resolve_cache_repo_head", return_value="head1"), \
                     patch.object(am, "_execute_single_advisor_raw", side_effect=[
                         "VERDICT: REJECTED\nBad",
                         "Malformed reply without verdict",
                         "VERDICT: APPROVED\nGood",
                     ]) as raw_mock:
                    r1 = am._execute_single_advisor(adv, "p", diff="d", mode="review_diff", track_circuit=False)
                    r2 = am._execute_single_advisor(adv, "p", diff="d", mode="review_diff", track_circuit=False)
                    r3 = am._execute_single_advisor(adv, "p", diff="d", mode="review_diff", track_circuit=False)
                    self.assertIn("REJECTED", r1)
                    self.assertIn("Malformed", r2)
                    self.assertIn("APPROVED", r3)
                    self.assertEqual(raw_mock.call_count, 3)

                # Now APPROVED is cached
                with patch.object(am, "_resolve_cache_repo_head", return_value="head1"), \
                     patch.object(am, "_execute_single_advisor_raw", side_effect=AssertionError("should be cached")):
                    r4 = am._execute_single_advisor(adv, "p", diff="d", mode="review_diff", track_circuit=False)
                    self.assertIn("APPROVED", r4)

    def test_repo_head_and_model_sig_affect_cache_key(self):
        k_base = make_cache_key("claude", "general", None, "p", repo_head="h1", model_sig="m1")
        k_head = make_cache_key("claude", "general", None, "p", repo_head="h2", model_sig="m1")
        k_model = make_cache_key("claude", "general", None, "p", repo_head="h1", model_sig="m2")
        self.assertNotEqual(k_base, k_head)
        self.assertNotEqual(k_base, k_model)


class TestGatePythonResolution(unittest.TestCase):
    def test_prefers_repo_venv_over_sys_executable(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = Path(".venv") / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            venv_py = root / rel
            venv_py.parent.mkdir(parents=True, exist_ok=True)
            venv_py.write_text("", encoding="utf-8")

            wt = root / "worktree"
            wt.mkdir()
            with patch("triad.triad_engine.run_subprocess_tree_safe", return_value=(0, "", "")):
                resolved = _resolve_gate_python(wt, [str(root)])
            self.assertEqual(Path(resolved).resolve(), venv_py.resolve())
