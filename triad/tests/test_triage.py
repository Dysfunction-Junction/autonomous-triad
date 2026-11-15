"""Tests for Phase 3.6: deterministic docs/format pre-filter and local llama risk triage."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from triad import triad_engine as te
from triad.procutil import extract_diff_file_paths, is_trivial_diff

DOCS_DIFF = (
    "diff --git a/README.md b/README.md\n"
    "--- a/README.md\n"
    "+++ b/README.md\n"
    "@@ -1 +1,2 @@\n"
    " # Triad\n"
    "+Updated docs.\n"
)

LOCK_DIFF = (
    "diff --git a/uv.lock b/uv.lock\n"
    "--- a/uv.lock\n"
    "+++ b/uv.lock\n"
    "@@ -1 +1,2 @@\n"
    "+pkg = 1\n"
)

CODE_DIFF = (
    "diff --git a/triad/app.py b/triad/app.py\n"
    "--- a/triad/app.py\n"
    "+++ b/triad/app.py\n"
    "@@ -1 +1,2 @@\n"
    " def run():\n"
    "+    return 1\n"
)

AUTH_DIFF = (
    "diff --git a/triad/auth_token.py b/triad/auth_token.py\n"
    "--- a/triad/auth_token.py\n"
    "+++ b/triad/auth_token.py\n"
    "@@ -1 +1,2 @@\n"
    "+def verify_jwt_secret(): pass\n"
)


class TestTrivialDiffPreFilter(unittest.TestCase):
    def test_docs_are_trivial_but_lockfiles_and_agent_instructions_are_not(self):
        self.assertTrue(is_trivial_diff(DOCS_DIFF))
        self.assertEqual(extract_diff_file_paths(DOCS_DIFF), ["README.md"])
        self.assertFalse(is_trivial_diff(LOCK_DIFF))
        for sensitive in (
            "CLAUDE.md",
            "AGENTS.md",
            "MEMORY.md",
            ".cursorrules",
            "llms.txt",
            ".claude/commands/x.md",
            ".agents/skills/a/notes.md",
            "pkg/.claude/x.md",
            ".github/workflows/ci.yml",
            "assets/diagram.svg",
            "requirements.txt",
            "CODEOWNERS",
            "AGENT.md",
            "CONVENTIONS.md",
            "deploy.prompt.md",
        ):
            self.assertFalse(is_trivial_diff(DOCS_DIFF.replace("README.md", sensitive)), f"should reject {sensitive}")

        secret_doc = DOCS_DIFF + "+OPENAI_API_KEY=sk-1234567890abcdef1234567890\n"
        self.assertFalse(is_trivial_diff(secret_doc))

        oversized_doc = DOCS_DIFF + ("+line\n" * 4000)
        self.assertFalse(is_trivial_diff(oversized_doc))

        symlink_mod = (
            "diff --git a/docs/guide.md b/docs/guide.md\n"
            "index 1111111..2222222 120000\n"
            "--- a/docs/guide.md\n"
            "+++ b/docs/guide.md\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+/etc/passwd\n"
        )
        self.assertFalse(is_trivial_diff(symlink_mod))

    def test_code_and_tests_are_not_trivial(self):
        self.assertFalse(is_trivial_diff(CODE_DIFF))
        test_diff = CODE_DIFF.replace("triad/app.py", "triad/tests/test_app.py")
        self.assertFalse(is_trivial_diff(test_diff))

    def test_source_whitespace_and_mixed_metadata_are_not_trivial(self):
        blank_in_py = (
            "diff --git a/triad/app.py b/triad/app.py\n"
            "--- a/triad/app.py\n"
            "+++ b/triad/app.py\n"
            "@@ -1,2 +1,3 @@\n"
            " x = '''\n"
            "+\n"
            " '''\n"
        )
        mode_change_doc = (
            "diff --git a/README.md b/README.md\n"
            "old mode 100644\n"
            "new mode 100755\n"
        )
        binary_doc = (
            "diff --git a/assets/logo.png b/assets/logo.png\n"
            "Binary files a/assets/logo.png and b/assets/logo.png differ\n"
        )
        self.assertFalse(is_trivial_diff(blank_in_py))
        self.assertFalse(is_trivial_diff(mode_change_doc))
        self.assertFalse(is_trivial_diff(binary_doc))


class TestTieredEscalation(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop("TRIAD_TRIAGE", None)
        self.addCleanup(patcher.stop)
    def _fake_advisors(self, llama_ready: bool = True, nous_ready: bool = True):
        def _get_advisors(enabled_only=True):
            return [{"name": "llama"}, {"name": "nous"}]

        def _ready(cfg):
            if cfg["name"] == "llama":
                return (llama_ready, "" if llama_ready else "port closed")
            if cfg["name"] == "nous":
                return (nous_ready, "" if nous_ready else "down")
            return (True, "")

        return _get_advisors, _ready

    def test_docs_only_cmd_review_makes_zero_advisor_calls(self):
        args = SimpleNamespace(
            diff_file=None, cached=True, head=False, prompt="review", engine="auto", task="auto",
            competition=False, adversarial=False,
        )
        with patch.object(te, "get_git_diff", return_value=DOCS_DIFF), \
             patch.object(te, "query_advisory_council") as mock_single, \
             patch.object(te, "query_competition_council") as mock_comp, \
             patch.object(te, "query_configured_advisor") as mock_raw:
            te.cmd_review(args)
        mock_single.assert_not_called()
        mock_comp.assert_not_called()
        mock_raw.assert_not_called()

    def test_high_stakes_diff_forces_competition_even_if_llama_says_trivial(self):
        get_adv, ready = self._fake_advisors(llama_ready=True)
        with patch.object(te, "get_advisors", side_effect=get_adv), \
             patch.object(te, "advisor_is_ready", side_effect=ready), \
             patch.object(te, "query_configured_advisor", return_value="TRIVIAL") as mock_llama:
            verdict, engine, competition = te._resolve_triage_route(AUTH_DIFF, True, "auto", False)
        self.assertIsNone(verdict)
        self.assertTrue(competition)
        self.assertEqual(engine, "auto")
        mock_llama.assert_not_called()

    def test_llama_trivial_routes_to_nous_and_high_to_competition(self):
        get_adv, ready = self._fake_advisors(llama_ready=True, nous_ready=True)
        with patch.object(te, "get_advisors", side_effect=get_adv), \
             patch.object(te, "advisor_is_ready", side_effect=ready), \
             patch.object(te, "query_configured_advisor", return_value="TRIVIAL"):
            verdict, engine, competition = te._resolve_triage_route(CODE_DIFF, False, "auto", False)
        self.assertIsNone(verdict)
        self.assertEqual(engine, "nous")
        self.assertFalse(competition)

        with patch.object(te, "get_advisors", side_effect=get_adv), \
             patch.object(te, "advisor_is_ready", side_effect=ready), \
             patch.object(te, "query_configured_advisor", return_value="HIGH"):
            verdict, engine, competition = te._resolve_triage_route(CODE_DIFF, False, "auto", False)
        self.assertIsNone(verdict)
        self.assertTrue(competition)

        # Ambiguous multi-word reply falls through to default auto (never downgraded)
        with patch.object(te, "get_advisors", side_effect=get_adv), \
             patch.object(te, "advisor_is_ready", side_effect=ready), \
             patch.object(te, "query_configured_advisor", return_value="Not TRIVIAL."):
            _, eng_ambig, comp_ambig = te._resolve_triage_route(CODE_DIFF, False, "auto", False)
        self.assertEqual(eng_ambig, "auto")
        self.assertFalse(comp_ambig)

        # Gate (allow_downgrade=False) and oversized diffs (>3600 chars) never downgrade to nous
        with patch.object(te, "get_advisors", side_effect=get_adv), \
             patch.object(te, "advisor_is_ready", side_effect=ready), \
             patch.object(te, "query_configured_advisor", return_value="TRIVIAL"):
            _, eng_gate, _ = te._resolve_triage_route(CODE_DIFF, False, "auto", False, allow_downgrade=False)
            _, eng_big, _ = te._resolve_triage_route(CODE_DIFF + ("#x\n" * 1500), False, "auto", False)
        self.assertEqual(eng_gate, "auto")
        self.assertEqual(eng_big, "auto")

    def test_llama_down_falls_through_to_default_auto(self):
        get_adv, ready = self._fake_advisors(llama_ready=False)
        with patch.object(te, "get_advisors", side_effect=get_adv), \
             patch.object(te, "advisor_is_ready", side_effect=ready), \
             patch.object(te, "query_configured_advisor") as mock_llama:
            verdict, engine, competition = te._resolve_triage_route(CODE_DIFF, False, "auto", False)
        self.assertIsNone(verdict)
        self.assertEqual(engine, "auto")
        self.assertFalse(competition)
        mock_llama.assert_not_called()

    def test_kill_switch_disables_triage_but_preserves_high_stakes(self):
        with patch.dict(os.environ, {"TRIAD_TRIAGE": "0"}):
            verdict, engine, competition = te._resolve_triage_route(DOCS_DIFF, False, "auto", False)
            self.assertIsNone(verdict)
            self.assertEqual(engine, "auto")
            self.assertFalse(competition)

            verdict_hs, engine_hs, competition_hs = te._resolve_triage_route(AUTH_DIFF, True, "auto", False)
            self.assertIsNone(verdict_hs)
            self.assertEqual(engine_hs, "auto")
            self.assertTrue(competition_hs)
