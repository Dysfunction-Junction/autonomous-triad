"""Unit tests for Triad Agent, RouteLLM Router, Quota Tracker, and Tools."""

import os
import tempfile
import time
from pathlib import Path

from triad.agent.tracker import RollingWindowTracker, DEFAULT_SOFT_LIMIT
from triad.agent.router import RouteLLMClassifier, ZeroCostRouter, ModelTier
from triad.agent.tools import ToolRegistry


def test_tracker_sliding_window():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = Path(tmpdir) / "test_ledger.json"
        tracker = RollingWindowTracker(ledger_path=ledger)

        # Initially empty
        stats = tracker.get_window_stats(provider="primary")
        assert stats["total_turns"] == 0
        assert stats["total_tokens"] == 0
        assert stats["utilization"] == 0.0
        assert not tracker.is_soft_limit_reached("primary")

        # Record 10 turns
        for _ in range(10):
            tracker.record_request("primary", "claude-3-7-sonnet", prompt_tokens=1000, completion_tokens=500)

        stats = tracker.get_window_stats(provider="primary")
        assert stats["total_turns"] == 10
        assert stats["total_tokens"] == 15000

        # Mark circuit break
        tracker.mark_circuit_break("primary", cooldown_seconds=60)
        assert tracker.is_cooling_down("primary")
        assert tracker.is_soft_limit_reached("primary")


def test_routellm_classifier():
    classifier = RouteLLMClassifier()

    # Complex coding / architectural task
    complex_prompt = "Refactor the state machine to prevent race conditions and memory leak in the distributed event loop."
    complex_score = classifier.score_prompt(complex_prompt)
    assert complex_score > 0.50

    # Routine formatting / boilerplate task
    routine_prompt = "Format this JSON schema and fix typo in comment."
    routine_score = classifier.score_prompt(routine_prompt)
    assert routine_score < 0.50


def test_router_adaptive_threshold():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = Path(tmpdir) / "test_ledger.json"
        tracker = RollingWindowTracker(ledger_path=ledger)
        router = ZeroCostRouter(tracker=tracker, base_threshold_c=0.50)

        # Baseline: low usage
        thresh, _ = router.get_effective_threshold()
        assert thresh == 0.50

        # Force high utilization (>80%)
        for _ in range(40):
            tracker.record_request("primary", "claude-3-7-sonnet", prompt_tokens=2500, completion_tokens=500)

        stats = tracker.get_window_stats("primary")
        assert stats["utilization"] >= DEFAULT_SOFT_LIMIT

        adaptive_thresh, reason = router.get_effective_threshold()
        assert adaptive_thresh > 0.50
        assert "soft-limit reached" in reason.lower()


def test_tool_registry():
    with tempfile.TemporaryDirectory() as tmpdir:
        tools = ToolRegistry(workspace_root=Path(tmpdir), auto_approve=True)

        # Write file
        res = tools.write_file("hello.txt", "line1\nline2\nline3\n")
        assert res["status"] == "success"

        # Read file
        read_res = tools.read_file("hello.txt", start_line=1, end_line=2)
        assert "line1" in read_res["content"]
        assert "line2" in read_res["content"]
        assert read_res["total_lines"] == 3

        # Edit file
        edit_res = tools.edit_file("hello.txt", "line2", "LINE_TWO_REPLACED")
        assert edit_res["status"] == "success"

        verify_read = tools.read_file("hello.txt")
        assert "LINE_TWO_REPLACED" in verify_read["content"]

        # List dir
        list_res = tools.list_dir(".")
        assert list_res["count"] == 1

        # Test workspace containment escape attempt
        escape_res = tools.read_file("../../outside.txt")
        assert "error" in escape_res
        assert "escapes workspace boundary" in escape_res["error"]

        # Test secret file deny-list
        secret_res = tools.write_file(".env", "SECRET=123")
        assert "error" in secret_res
        assert "Security restriction" in secret_res["error"]
