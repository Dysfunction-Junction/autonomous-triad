"""Tests for Phase 3.2/3.3: cited-hunk extraction, synthesis evidence trimming, unanimous-approval shortcut."""

# Tags: review, advisor, test-fixture
# Links: triad/competition.py
# Queries: "how are cited hunks extracted", "what is trimmed from synthesis", "what counts as unanimous"

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from triad import competition as comp
from triad.procutil import extract_cited_hunks, is_approved_verdict, prepare_synthesis_evidence

SAMPLE_DIFF = (
    "diff --git a/triad/a.py b/triad/a.py\n"
    "--- a/triad/a.py\n"
    "+++ b/triad/a.py\n"
    "@@ -10,3 +10,4 @@ def foo():\n"
    "     x = 1\n"
    "+    y = 2\n"
    "     return x\n"
    "diff --git a/.github/ci.yml b/.github/ci.yml\n"
    "--- a/.github/ci.yml\n"
    "+++ b/.github/ci.yml\n"
    "@@ -50,2 +50,3 @@ jobs:\n"
    "+    z: 3\n"
    "     w: 0\n"
)


class TestExtractCitedHunks(unittest.TestCase):
    def test_keeps_only_cited_hunk(self):
        out = extract_cited_hunks(SAMPLE_DIFF, ["Bug at triad/a.py:11 [MAJOR]"])
        self.assertIn("- triad/a.py", out)
        self.assertIn("- .github/ci.yml", out)
        self.assertIn("+    y = 2", out)
        self.assertNotIn("+    z: 3", out)

    def test_empty_citations_returns_file_list_only(self):
        out = extract_cited_hunks(SAMPLE_DIFF, ["Looks clean overall."])
        self.assertIn("CHANGED FILES:", out)
        self.assertNotIn("+    y = 2", out)

    def test_line_slack_and_alternate_formats(self):
        # hunk 1 spans new lines 10-13; line 15 is within +/-3 slack
        self.assertIn("+    y = 2", extract_cited_hunks(SAMPLE_DIFF, ["see triad/a.py:15"]))
        self.assertIn("+    y = 2", extract_cited_hunks(SAMPLE_DIFF, ["see triad/a.py#L11"]))
        self.assertIn("+    y = 2", extract_cited_hunks(SAMPLE_DIFF, ["see triad/a.py line 11"]))
        self.assertNotIn("+    y = 2", extract_cited_hunks(SAMPLE_DIFF, ["see triad/a.py:40"]))

    def test_leading_dot_directory_is_not_stripped(self):
        out = extract_cited_hunks(SAMPLE_DIFF, ["problem in .github/ci.yml:51"])
        self.assertIn("+    z: 3", out)

    def test_plain_diff_without_git_headers_is_returned_whole_up_to_cap(self):
        plain = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"
        self.assertEqual(extract_cited_hunks(plain, ["x.py:1"]), plain)
        big = "+" + "x" * 50
        out = extract_cited_hunks(big, [], plain_cap=10)
        self.assertIn("truncated", out)


class TestPrepareSynthesisEvidence(unittest.TestCase):
    def test_small_diff_goes_in_whole(self):
        diff_text, ctx = prepare_synthesis_evidence(SAMPLE_DIFF, "short", ["no citations"])
        self.assertEqual(diff_text, SAMPLE_DIFF)
        self.assertEqual(ctx, "short")

    def test_large_diff_is_trimmed_to_cited_hunks(self):
        filler = "".join(f"+line {i}\n" for i in range(3000))
        big = SAMPLE_DIFF + (
            "diff --git a/big.txt b/big.txt\n--- a/big.txt\n+++ b/big.txt\n@@ -1,0 +1,3000 @@\n" + filler
        )
        diff_text, _ = prepare_synthesis_evidence(big, None, ["issue at triad/a.py:11"], diff_budget=1000)
        self.assertIn("+    y = 2", diff_text)
        self.assertNotIn("+line 2999", diff_text)

    def test_oversized_cited_hunk_is_capped_to_budget(self):
        filler = "".join(f"+line {i}\n" for i in range(500))
        big = (
            "diff --git a/big.txt b/big.txt\n--- a/big.txt\n+++ b/big.txt\n@@ -1,0 +1,500 @@\n" + filler
        )
        diff_text, _ = prepare_synthesis_evidence(big, None, ["issue at big.txt:10"], diff_budget=300)
        self.assertIn("diff truncated", diff_text)
        self.assertLess(len(diff_text), 400)

    def test_diff_passed_as_context_is_not_lost(self):
        long_ctx = SAMPLE_DIFF + ("# pad\n" * 600)
        diff_text, ctx = prepare_synthesis_evidence(None, long_ctx, [])
        self.assertIn("diff --git a/triad/a.py", diff_text)
        self.assertIsNone(ctx)

    def test_long_context_is_truncated_with_note_not_dropped(self):
        _, ctx = prepare_synthesis_evidence(None, "x" * 2500, [])
        self.assertTrue(ctx.startswith("x" * 2000))
        self.assertIn("context truncated, 500 chars omitted", ctx)


class TestApprovedVerdict(unittest.TestCase):
    def test_first_line_exact_and_light_markdown(self):
        self.assertTrue(is_approved_verdict("VERDICT: APPROVED\nok"))
        self.assertTrue(is_approved_verdict("**VERDICT: APPROVED**\nok"))
        self.assertTrue(is_approved_verdict("VERDICT: APPROVED."))

    def test_rejects_prefix_late_and_conflicting_verdicts(self):
        self.assertFalse(is_approved_verdict("VERDICT: APPROVED_WITH_CONDITIONS"))
        self.assertFalse(is_approved_verdict("VERDICT: REJECTED\nafter fixes -> VERDICT: APPROVED"))
        self.assertFalse(is_approved_verdict("Notes first\nVERDICT: APPROVED"))
        self.assertFalse(is_approved_verdict("VERDICT: APPROVED\nlater VERDICT: REJECTED"))
        self.assertFalse(is_approved_verdict(""))


class TestUnanimousShortcut(unittest.TestCase):
    OK1 = "VERDICT: APPROVED\nNIT: rename var"
    OK2 = "VERDICT: APPROVED\nClean."

    def setUp(self):
        patcher = patch.dict(os.environ, {"TRIAD_SKIP_UNANIMOUS_SYNTH": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_both_approve_produces_verdict_on_line_one(self):
        res = comp._try_unanimous_approved_synthesis(self.OK1, self.OK2)
        self.assertIsNotNone(res)
        self.assertEqual(res.splitlines()[0], "VERDICT: APPROVED")
        self.assertTrue(is_approved_verdict(res))
        self.assertIn("NIT: rename var", res)

    def test_tagged_blocker_or_major_blocks_shortcut(self):
        self.assertIsNone(comp._try_unanimous_approved_synthesis("VERDICT: APPROVED\n[BLOCKER] x", self.OK2))
        self.assertIsNone(comp._try_unanimous_approved_synthesis("VERDICT: APPROVED\nMAJOR: y", self.OK2))
        self.assertIsNone(comp._try_unanimous_approved_synthesis("VERDICT: APPROVED\n- MAJOR race in a.py", self.OK2))

    def test_prose_mentions_do_not_block_shortcut(self):
        prose = "VERDICT: APPROVED\nNo BLOCKER/MAJOR findings; no major or minor issues."
        res = comp._try_unanimous_approved_synthesis(prose, self.OK2)
        self.assertIsNotNone(res)
        self.assertIn("Minor notes: None", res)

    def test_late_or_conflicting_approval_does_not_count(self):
        late = "VERDICT: REJECTED\nafter fixes -> VERDICT: APPROVED"
        self.assertIsNone(comp._try_unanimous_approved_synthesis(late, self.OK2))

    def test_env_kill_switch(self):
        with patch.dict(os.environ, {"TRIAD_SKIP_UNANIMOUS_SYNTH": "0"}):
            self.assertIsNone(comp._try_unanimous_approved_synthesis(self.OK1, self.OK2))

    def test_council_skips_judge_call_when_both_approve(self):
        calls = []

        def fake_query(name, prompt, **kwargs):
            calls.append((name, kwargs.get("mode")))
            return "VERDICT: APPROVED\nLooks good."

        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "council_sessions.jsonl"
            with patch.object(comp, "query_configured_advisor", side_effect=fake_query), \
                 patch.object(comp, "write_state_file", return_value=log_path):
                res = comp.query_competition_council(
                    prompt="review", diff="+x", mode="review_diff", advisor_names=("mock", "mock")
                )
            self.assertTrue(log_path.exists())
        self.assertEqual(len(calls), 2, f"judge should be skipped, got calls: {calls}")
        self.assertEqual(res["synthesis"].splitlines()[0], "VERDICT: APPROVED")
        self.assertIn("Unanimous", res["synthesis"])
