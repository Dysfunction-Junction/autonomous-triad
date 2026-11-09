#!/usr/bin/env python3
"""
Unit tests for Triad Advisor Manager (triad/advisor_manager.py).
Verifies:
- Loading of declarative advisors.json configuration
- Runtime inspection (get_advisors, get_active_advisor)
- Execution of configured advisors (mock, claude)
- Dynamic registration of third advisors via configuration edits without modifying code
- Auto-failover logic across configured advisor priorities
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from triad.advisor_manager import (
    get_advisors,
    get_active_advisor,
    query_configured_advisor,
    add_advisor,
    save_config,
    expand_env_value,
    rank_advisors_for_task,
)


class TestAdvisorManager(unittest.TestCase):
    def setUp(self):
        # Keep live advisor probes from writing into the user's real circuit file.
        self._circuit_tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._circuit_tmp.close()
        self._circuit_env = patch.dict(os.environ, {
            "TRIAD_CIRCUIT_PATH": self._circuit_tmp.name,
            "TRIAD_CIRCUIT": "1",
        })
        self._circuit_env.start()

    def tearDown(self):
        self._circuit_env.stop()
        try:
            os.unlink(self._circuit_tmp.name)
        except OSError:
            pass

    def test_expand_env_value_leaves_tokens_alone(self):
        self.assertEqual(expand_env_value("API_KEY", "sk-$HOME-%USERPROFILE%"), "sk-$HOME-%USERPROFILE%")
        self.assertEqual(expand_env_value("PYTHONIOENCODING", "utf-8"), "utf-8")
        self.assertEqual(expand_env_value("SERVICE_URL", "https://api.anthropic.com/v1"), "https://api.anthropic.com/v1")

    def test_expand_env_value_expands_path_keys(self):
        expanded = expand_env_value("TRIAD_CLAUDE_PATH", "{home}/.local/bin/claude.exe")
        self.assertNotIn("{home}", expanded)
        self.assertTrue(expanded.endswith(".local\\bin\\claude.exe") or expanded.endswith(".local/bin/claude.exe"))

        path_expanded = expand_env_value("PATH", "{home}/bin")
        self.assertNotIn("{home}", path_expanded)

        models_expanded = expand_env_value("OLLAMA_MODELS", "{home}/.ollama/models")
        self.assertNotIn("{home}", models_expanded)

    def test_get_advisors_loading_and_sorting(self):
        """Verify advisors are loaded from advisors.json in priority order."""
        advisors = get_advisors()
        self.assertGreaterEqual(len(advisors), 3)

        names = [a.get("name") for a in advisors]
        self.assertIn("claude", names)
        self.assertIn("codex", names)
        self.assertIn("mock", names)

        # Check sorting by priority
        priorities = [a.get("priority", 999) for a in advisors]
        self.assertEqual(priorities, sorted(priorities))

    def test_get_active_advisor(self):
        """Verify lookup by name and default active resolution."""
        claude = get_active_advisor("claude")
        self.assertIsNotNone(claude)
        self.assertEqual(claude.get("name"), "claude")

        mock = get_active_advisor("MOCK")  # Case-insensitive
        self.assertIsNotNone(mock)
        self.assertEqual(mock.get("name"), "mock")

        # Non-existent advisor
        unknown = get_active_advisor("non_existent_engine_xyz")
        self.assertIsNone(unknown)

        # Auto resolution
        auto_adv = get_active_advisor("auto")
        self.assertIsNotNone(auto_adv)
        self.assertEqual(auto_adv.get("name"), "claude")

    def test_query_configured_advisor_mock(self):
        """Verify querying mock advisor via query_configured_advisor."""
        prompt = "Hello from automated triad test"
        resp = query_configured_advisor("mock", prompt)
        self.assertIn("[Mock Advisor]", resp)
        self.assertIn("characters", resp)

    @unittest.skipUnless(
        shutil.which("claude"),
        "requires a local, authenticated Claude Code CLI on PATH -- not available in CI",
    )
    def test_query_configured_advisor_claude(self):
        """Verify live querying of Claude Code advisor."""
        resp = query_configured_advisor("claude", "Respond with OK", timeout=30)
        self.assertTrue(
            "OK" in resp or "session limit" in resp.lower() or "rate limit" in resp.lower(),
            f"Unexpected response from Claude Code: {resp}"
        )

    def test_dynamic_advisor_addition_without_code_change(self):
        """
        Verify that adding a new advisor dynamically via configuration edit
        enables immediate querying without any changes to the engine codebase.
        """
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False, encoding="utf-8") as tf:
            temp_config_path = Path(tf.name)

        try:
            # Create a isolated config with mock and a new dynamic advisor
            dynamic_advisor = {
                "name": "custom_agent_v3",
                "display_name": "Dynamic Custom Agent V3",
                "binary_path": "python",
                "priority": 1,
                "execution_flags": [
                    "-c",
                    "import sys; sys.stdout.write('DYNAMIC_ADVISOR_RESPONSE_SUCCESS')"
                ],
                "input_mode": "stdin",
                "output_mode": "stdout",
                "enabled": True
            }

            initial_data = {
                "advisors": [
                    {
                        "name": "base_mock",
                        "display_name": "Base Mock",
                        "binary_path": "python",
                        "priority": 10,
                        "execution_flags": ["-c", "print('base')"],
                        "enabled": True
                    }
                ]
            }
            save_config(initial_data, temp_config_path)

            # Query before adding: should fail
            res_before = query_configured_advisor("custom_agent_v3", "test", config_path=temp_config_path)
            self.assertIn("not found in configuration", res_before)

            # Dynamically register the new advisor via config edit
            add_advisor(dynamic_advisor, config_path=temp_config_path)

            # Verify it's now in get_advisors()
            advisors = get_advisors(config_path=temp_config_path)
            self.assertEqual(len(advisors), 2)
            self.assertEqual(advisors[0]["name"], "custom_agent_v3")

            # Query the dynamically added advisor: must work without modifying engine code!
            res_after = query_configured_advisor("custom_agent_v3", "test", config_path=temp_config_path)
            self.assertEqual(res_after.strip(), "DYNAMIC_ADVISOR_RESPONSE_SUCCESS")

        finally:
            if temp_config_path.exists():
                try:
                    temp_config_path.unlink()
                except Exception:
                    pass

    def test_auto_failover_across_configured_advisors(self):
        """Verify automatic failover when the primary advisor encounters an error."""
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False, encoding="utf-8") as tf:
            temp_config_path = Path(tf.name)

        try:
            config_data = {
                "advisors": [
                    {
                        "name": "failing_primary",
                        "display_name": "Failing Primary",
                        "binary_path": "python",
                        "priority": 1,
                        "execution_flags": ["-c", "import sys; sys.stderr.write('Rate limit exceeded'); sys.exit(1)"],
                        "enabled": True
                    },
                    {
                        "name": "backup_secondary",
                        "display_name": "Backup Secondary",
                        "binary_path": "python",
                        "priority": 2,
                        "execution_flags": ["-c", "import sys; sys.stdout.write('BACKUP_REACHED')"],
                        "enabled": True
                    }
                ]
            }
            save_config(config_data, temp_config_path)

            resp = query_configured_advisor("auto", "Failover test prompt", config_path=temp_config_path)
            self.assertIn("Advisor Auto-Failover", resp)
            self.assertIn("Backup Secondary", resp)
            self.assertIn("BACKUP_REACHED", resp)

        finally:
            if temp_config_path.exists():
                try:
                    temp_config_path.unlink()
                except Exception:
                    pass


    def test_resolve_binary_precedence(self):
        from triad.advisor_manager import resolve_binary
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".exe", delete=False) as f_cfg:
            f_cfg.write("")
            cfg_path = f_cfg.name
        with tempfile.NamedTemporaryFile("w", suffix=".exe", delete=False) as f_env:
            f_env.write("")
            env_path = f_env.name

        try:
            # 1. Configured binary takes precedence over canonical binary
            resolved = resolve_binary(binary_path=cfg_path, advisor_name="claude")
            self.assertEqual(resolved, cfg_path)

            # 2. Environment override takes precedence over configured binary
            with patch.dict(os.environ, {"TRIAD_CLAUDE_PATH": env_path}):
                resolved_env = resolve_binary(binary_path=cfg_path, advisor_name="claude")
                self.assertEqual(resolved_env, env_path)
        finally:
            for p in (cfg_path, env_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass


class TestCodexAuthDecode(unittest.TestCase):
    def test_missing_file_returns_missing(self):
        from triad.triad_engine import _decode_codex_auth
        info = _decode_codex_auth(Path("non_existent_auth_file_12345.json"))
        self.assertEqual(info["status"], "missing")
        self.assertFalse(info["refreshable"])

    def test_active_unexpired_token(self):
        from triad.triad_engine import _decode_codex_auth
        import base64
        from datetime import datetime, timezone, timedelta

        future_iso = (datetime.now(timezone.utc) + timedelta(days=15)).isoformat()
        payload = {
            "https://api.openai.com/auth": {
                "chatgpt_plan_type": "plus",
                "chatgpt_subscription_active_until": future_iso,
            }
        }
        b64_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
        fake_jwt = f"header.{b64_payload}.sig"

        data = {
            "tokens": {"id_token": fake_jwt, "refresh_token": "valid_refresh"},
            "last_refresh": datetime.now(timezone.utc).isoformat(),
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            t_path = Path(f.name)
        try:
            info = _decode_codex_auth(t_path)
            self.assertEqual(info["status"], "active")
            self.assertEqual(info["plan"], "plus")
            self.assertTrue(info["refreshable"])
        finally:
            t_path.unlink(missing_ok=True)

    def test_expired_token_with_valid_refresh_is_refreshable(self):
        from triad.triad_engine import _decode_codex_auth
        import base64
        from datetime import datetime, timezone, timedelta

        past_iso = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        payload = {
            "https://api.openai.com/auth": {
                "chatgpt_plan_type": "pro",
                "chatgpt_subscription_active_until": past_iso,
            }
        }
        b64_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
        fake_jwt = f"header.{b64_payload}.sig"

        data = {
            "tokens": {"id_token": fake_jwt, "refresh_token": "valid_refresh"},
            "last_refresh": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            t_path = Path(f.name)
        try:
            info = _decode_codex_auth(t_path)
            self.assertEqual(info["status"], "refreshable")
            self.assertEqual(info["plan"], "pro")
            self.assertTrue(info["refreshable"])
        finally:
            t_path.unlink(missing_ok=True)

    def test_stale_refresh_token_older_than_30_days_is_expired(self):
        from triad.triad_engine import _decode_codex_auth
        import base64
        from datetime import datetime, timezone, timedelta

        past_iso = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        payload = {
            "https://api.openai.com/auth": {
                "chatgpt_plan_type": "plus",
                "chatgpt_subscription_active_until": past_iso,
            }
        }
        b64_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
        fake_jwt = f"header.{b64_payload}.sig"

        data = {
            "tokens": {"id_token": fake_jwt, "refresh_token": "stale_refresh"},
            "last_refresh": (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(),
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            t_path = Path(f.name)
        try:
            info = _decode_codex_auth(t_path)
            self.assertEqual(info["status"], "expired")
            self.assertFalse(info["refreshable"])
            self.assertTrue(info["has_refresh_token"])
        finally:
            t_path.unlink(missing_ok=True)

    def test_refresh_token_at_boundary_edges_and_future_timestamp(self):
        from triad.triad_engine import _decode_codex_auth
        import base64
        from datetime import datetime, timezone, timedelta

        past_iso = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        payload = {
            "https://api.openai.com/auth": {
                "chatgpt_plan_type": "plus",
                "chatgpt_subscription_active_until": past_iso,
            }
        }
        b64_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
        fake_jwt = f"header.{b64_payload}.sig"

        # Edge A: 29 days old -> valid refreshable
        data_29d = {
            "tokens": {"id_token": fake_jwt, "refresh_token": "valid_refresh"},
            "last_refresh": (datetime.now(timezone.utc) - timedelta(days=29)).isoformat(),
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data_29d, f)
            t_path = Path(f.name)
        try:
            info = _decode_codex_auth(t_path)
            self.assertEqual(info["status"], "refreshable")
            self.assertTrue(info["refreshable"])
            self.assertTrue(info["has_refresh_token"])
        finally:
            t_path.unlink(missing_ok=True)

        # Edge B: 31 days old -> expired
        data_31d = {
            "tokens": {"id_token": fake_jwt, "refresh_token": "valid_refresh"},
            "last_refresh": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data_31d, f)
            t_path = Path(f.name)
        try:
            info = _decode_codex_auth(t_path)
            self.assertEqual(info["status"], "expired")
            self.assertFalse(info["refreshable"])
            self.assertTrue(info["has_refresh_token"])
        finally:
            t_path.unlink(missing_ok=True)

        # Edge C: Future timestamp (> 5 minutes in future) -> rejected as invalid / expired
        data_future = {
            "tokens": {"id_token": fake_jwt, "refresh_token": "valid_refresh"},
            "last_refresh": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data_future, f)
            t_path = Path(f.name)
        try:
            info = _decode_codex_auth(t_path)
            self.assertEqual(info["status"], "expired")
            self.assertFalse(info["refreshable"])
            self.assertTrue(info["has_refresh_token"])
        finally:
            t_path.unlink(missing_ok=True)

    def test_corrupt_json_returns_unknown(self):
        from triad.triad_engine import _decode_codex_auth

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{not valid json: true")
            t_path = Path(f.name)
        try:
            info = _decode_codex_auth(t_path)
            self.assertEqual(info["status"], "unknown")
            self.assertFalse(info["refreshable"])
        finally:
            t_path.unlink(missing_ok=True)

    def test_rank_advisors_for_task(self):
        sample_advisors = [
            {"name": "claude", "priority": 1, "strengths": {
                "architecture": 0.95, "coding": 0.95, "reasoning": 0.85,
                "scraping": 0.20, "browsing": 0.20, "micro": 0.15, "judge": 0.95,
            }},
            {"name": "codex", "priority": 2, "strengths": {
                "architecture": 0.85, "coding": 0.90, "reasoning": 0.95,
                "scraping": 0.20, "browsing": 0.20, "micro": 0.15, "judge": 0.85,
            }},
            {"name": "antigravity", "priority": 3, "strengths": {
                "architecture": 0.80, "coding": 0.75, "reasoning": 0.75,
                "scraping": 0.50, "browsing": 0.50, "micro": 0.30, "judge": 0.70,
            }},
            {"name": "nous", "priority": 4, "strengths": {
                "architecture": 0.50, "coding": 0.50, "reasoning": 0.45,
                "scraping": 0.80, "browsing": 0.80, "micro": 0.80, "judge": 0.55,
            }},
            {"name": "ollama", "priority": 5, "strengths": {
                "architecture": 0.10, "coding": 0.15, "reasoning": 0.10,
                "scraping": 0.95, "browsing": 0.95, "micro": 0.95, "judge": 0,
            }},
            {"name": "custom_agent", "priority": 15},  # missing map -> 0.5
        ]

        scraping_ranked = [a["name"] for a in rank_advisors_for_task(sample_advisors, "scraping")]
        self.assertEqual(scraping_ranked[:3], ["ollama", "nous", "antigravity"])

        arch_ranked = [a["name"] for a in rank_advisors_for_task(sample_advisors, "architecture")]
        self.assertEqual(arch_ranked[:3], ["claude", "codex", "antigravity"])

        reasoning_ranked = [a["name"] for a in rank_advisors_for_task(sample_advisors, "reasoning")]
        self.assertEqual(reasoning_ranked[:3], ["codex", "claude", "antigravity"])

        browsing_ranked = [a["name"] for a in rank_advisors_for_task(sample_advisors, "browsing")]
        self.assertEqual(browsing_ranked[:3], ["ollama", "nous", "antigravity"])

        coding_ranked = [a["name"] for a in rank_advisors_for_task(sample_advisors, "coding")]
        self.assertEqual(coding_ranked[:3], ["claude", "codex", "antigravity"])

        # judge 0 excludes ollama
        judge_ranked = [a["name"] for a in rank_advisors_for_task(sample_advisors, "judge")]
        self.assertNotIn("ollama", judge_ranked)
        self.assertEqual(judge_ranked[0], "claude")

        general_ranked = [a["name"] for a in rank_advisors_for_task(sample_advisors, "general")]
        self.assertEqual(general_ranked, ["claude", "codex", "antigravity", "nous", "ollama", "custom_agent"])

        none_task_ranked = [a["name"] for a in rank_advisors_for_task(sample_advisors, None)]
        self.assertEqual(none_task_ranked, general_ranked)

    def test_execute_advisor_blocks_cmd_batch_scripts(self):
        from triad.advisor_manager import _execute_single_advisor_raw
        fake_advisor = {
            "name": "batch_tool",
            "binary_path": "my_tool.cmd",
            "input_mode": "arg",
            "execution_flags": ["-p", "{prompt}"]
        }
        res = _execute_single_advisor_raw(fake_advisor, "test & inject %VAR%")
        if os.name == "nt":
            self.assertIn("batch script", res.lower())
            self.assertIn("unsafe", res.lower())

    def test_execute_advisor_argv_limit_fails_on_diff(self):
        from triad.advisor_manager import _execute_single_advisor_raw
        fake_advisor = {
            "name": "native_tool",
            "binary_path": sys.executable,
            "input_mode": "arg",
            "execution_flags": ["-p", "{prompt}"]
        }
        # A massive diff that exceeds 30k
        huge_diff = "diff --git a/foo.py b/foo.py\n" + ("+line of code\n" * 3000)
        res = _execute_single_advisor_raw(fake_advisor, "review diff", diff=huge_diff, mode="review_diff")
        if os.name == "nt":
            self.assertIn("exceeds windows argv limit", res.lower())

    def test_execute_advisor_prompt_file_keeps_diff_off_argv(self):
        from triad.advisor_manager import _execute_single_advisor_raw
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            captured["stdin"] = kwargs.get("stdin")
            prompt_path = None
            for arg in cmd:
                if isinstance(arg, str) and arg.endswith(".txt") and "triad_prompt_" in arg:
                    prompt_path = arg
                    break
            captured["prompt_path"] = prompt_path
            if prompt_path and os.path.exists(prompt_path):
                with open(prompt_path, encoding="utf-8") as fh:
                    captured["file_body"] = fh.read()

            class FakeProc:
                returncode = 0

                def communicate(self, input=None, timeout=None):
                    captured["stdin_input"] = input
                    return ("VERDICT: APPROVED\n", "")

                @property
                def pid(self):
                    return 0

            return FakeProc()

        fake_advisor = {
            "name": "file_tool",
            "binary_path": sys.executable,
            "input_mode": "file",
            "output_mode": "stdout",
            "execution_flags": ["--prompt-file", "{prompt_file}"],
        }
        huge_diff = "diff --git a/foo.py b/foo.py\n" + ("+line of code UNIQUE_DIFF_BODY\n" * 3000)
        with patch("triad.advisor_manager.subprocess.Popen", side_effect=fake_popen):
            with patch("triad.advisor_manager.kill_process_tree"):
                res = _execute_single_advisor_raw(
                    fake_advisor, "review diff", diff=huge_diff, mode="review_diff"
                )
        self.assertIn("VERDICT: APPROVED", res)
        joined = " ".join(str(a) for a in captured.get("cmd", []))
        self.assertIn("--prompt-file", joined)
        self.assertNotIn("UNIQUE_DIFF_BODY", joined)
        self.assertIsNotNone(captured.get("prompt_path"))
        self.assertIn("UNIQUE_DIFF_BODY", captured.get("file_body", ""))
        self.assertIsNone(captured.get("stdin_input"))
        self.assertFalse(os.path.exists(captured["prompt_path"]))

    def test_execute_advisor_unknown_input_mode_does_not_spawn(self):
        from triad.advisor_manager import _execute_single_advisor_raw
        fake_advisor = {
            "name": "bad_mode",
            "binary_path": sys.executable,
            "input_mode": "telepathy",
            "execution_flags": [],
        }
        with patch("triad.advisor_manager.subprocess.Popen") as popen:
            res = _execute_single_advisor_raw(fake_advisor, "hello")
        self.assertIn("unrecognized input_mode", res.lower())
        popen.assert_not_called()

    def test_grok_argv_and_xai_key_stripped(self):
        from triad.advisor_manager import _execute_single_advisor_raw, get_active_advisor
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            captured["env"] = dict(kwargs.get("env") or {})

            class FakeProc:
                returncode = 0

                def communicate(self, input=None, timeout=None):
                    return ("VERDICT: APPROVED\n", "")

                @property
                def pid(self):
                    return 0

            return FakeProc()

        grok = dict(get_active_advisor("grok") or {})
        self.assertTrue(grok, "grok advisor must be configured")
        grok["binary_path"] = sys.executable
        grok["fallback_binary"] = None
        with patch.dict(os.environ, {"XAI_API_KEY": "should-not-leak", "TRIAD_GROK": "1"}, clear=False):
            with patch("triad.advisor_manager.subprocess.Popen", side_effect=fake_popen):
                with patch("triad.advisor_manager.kill_process_tree"):
                    with patch("triad.advisor_manager.resolve_binary", return_value=sys.executable):
                        res = _execute_single_advisor_raw(grok, "say approved", mode="general")
        self.assertIn("VERDICT: APPROVED", res)
        joined = " ".join(str(a) for a in captured["cmd"])
        self.assertIn("--prompt-file", joined)
        self.assertIn("--permission-mode", joined)
        self.assertIn("plan", joined)
        self.assertIn("--max-turns", joined)
        self.assertIn("1", joined)
        self.assertIn("--no-subagents", joined)
        self.assertIn("--disable-web-search", joined)
        self.assertNotIn(" -p ", f" {joined} ")
        self.assertNotIn("XAI_API_KEY", captured["env"])

    def test_grok_kill_switch_skips_spawn(self):
        from triad.advisor_manager import query_configured_advisor
        with patch.dict(os.environ, {"TRIAD_GROK": "0"}, clear=False):
            with patch("triad.advisor_manager.subprocess.Popen") as popen:
                res = query_configured_advisor("grok", "hello")
        self.assertIn("dispatch disabled", res.lower())
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
