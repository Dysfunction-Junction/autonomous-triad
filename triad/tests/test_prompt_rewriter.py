"""Unit tests for Triad Prompt Rewriter (prompt_rewriter.py)."""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from triad.prompt_rewriter import rewrite_prompt, format_output


class TestPromptRewriter(unittest.TestCase):
    def test_expands_sparse_fix_prompt(self):
        brief = rewrite_prompt("fix the login bug in src/auth.ts")
        self.assertIn("Agent Task Brief", brief.rewritten)
        self.assertIn("src/auth.ts", brief.paths)
        self.assertTrue(brief.high_stakes)  # auth
        self.assertIn("Goal", brief.rewritten)
        self.assertIn("Acceptance criteria", brief.rewritten)
        self.assertIn("fix the login bug", brief.rewritten)

    def test_question_stays_read_only(self):
        brief = rewrite_prompt("what does classify_intent do?")
        self.assertIn("do not change code", brief.action.lower())
        self.assertTrue(
            any("mutations" in o.lower() for o in brief.out_of_scope)
            or any(a.code == "question_vs_action" for a in brief.ambiguities)
        )

    def test_compact_style(self):
        brief = rewrite_prompt("refactor prompt_rewriter.py", style="compact")
        self.assertTrue(brief.rewritten.startswith("GOAL:"))
        self.assertIn("ACTION:", brief.rewritten)
        self.assertIn("prompt_rewriter.py", brief.rewritten)

    def test_json_output_roundtrip(self):
        brief = rewrite_prompt("debug TypeError in server.py")
        payload = json.loads(format_output(brief, as_json=True))
        self.assertEqual(payload["original"], "debug TypeError in server.py")
        self.assertIn("server.py", payload["paths"])
        self.assertEqual(payload["intent"], "DEBUG")

    def test_extra_constraints(self):
        brief = rewrite_prompt(
            "add caching",
            extra_constraints=["No new dependencies", "Keep public API stable"],
        )
        self.assertTrue(any("No new dependencies" in c for c in brief.constraints))
        self.assertTrue(any("public API" in c for c in brief.constraints))

    def test_underspecified_flags_ambiguity(self):
        brief = rewrite_prompt("fix it")
        codes = {a.code for a in brief.ambiguities}
        self.assertTrue(codes & {"too_short", "underspecified", "missing_paths"})

    def test_high_stakes_without_user_constraints(self):
        brief = rewrite_prompt("change jwt auth token validation")
        self.assertTrue(brief.high_stakes)
        codes = {a.code for a in brief.ambiguities}
        self.assertIn("high_stakes_no_constraints", codes)

    def test_emdash_constraint_clause(self):
        brief = rewrite_prompt("fix the login bug in src/auth.ts — don't touch billing")
        userish = [c for c in brief.constraints if "touch billing" in c.lower()]
        self.assertTrue(userish, brief.constraints)
        self.assertTrue(all("auth.ts" not in c.lower() for c in userish))
        self.assertFalse(any(c.lower().startswith("ts") for c in userish))
        self.assertIn("src/auth.ts", brief.paths)


if __name__ == "__main__":
    unittest.main()
