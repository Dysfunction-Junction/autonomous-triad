"""Unit tests for Triad Agent, RouteLLM Router, Quota Tracker, and Tools."""

import tempfile
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

        # Test consult_architect tool exists and is callable
        assert hasattr(tools, "consult_architect")
        assert callable(tools.consult_architect)


def test_router_default_local_orchestrator(monkeypatch):
    router = ZeroCostRouter()
    # Short turns stay on the local tier. Score-based escalation is Phase 2.1.
    dec = router.select_route("Write a python script to parse CSV")
    assert dec.selected_tier == ModelTier.TIER_3_LOCAL

    # High complexity still starts local unless the caller delegates or the context budget is exceeded.
    dec_complex = router.select_route("Refactor distributed state machine and fix race conditions")
    assert dec_complex.selected_tier == ModelTier.TIER_3_LOCAL

    # Explicit delegation to Chief Architect
    dec_architect = router.select_route("Major migration plan", force_tier="architect")
    assert dec_architect.selected_tier == ModelTier.TIER_1_PRIMARY

    # F2: a prompt that cannot fit 90% of n_ctx skips the local tier.
    monkeypatch.setattr("triad.paths.llama_n_ctx", lambda: 2048)
    # Reset the process cache so the monkeypatch is visible through exceeds_context_budget.
    import triad.paths as paths_mod
    paths_mod._N_CTX_TRIED = False
    paths_mod._N_CTX_CACHE = None
    monkeypatch.setattr(paths_mod, "llama_n_ctx", lambda: 2048)
    dec_budget = router.select_route("x" * 20000)
    assert dec_budget.selected_tier == ModelTier.TIER_2_CLOUD_FREE
    assert "context budget" in dec_budget.reason
    assert dec_budget.fallback_chain == []


def test_exceeds_context_budget_none_when_n_ctx_unknown(monkeypatch):
    import triad.paths as paths_mod
    paths_mod._N_CTX_TRIED = False
    paths_mod._N_CTX_CACHE = None
    monkeypatch.setattr(paths_mod, "llama_n_ctx", lambda: None)
    assert paths_mod.exceeds_context_budget("hello world") is None


def test_runtime_abort_current_turn(monkeypatch):
    import pytest
    import triad.agent.runtime as rt
    from triad.agent.runtime import AgentRuntime
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_sess_dir = Path(tmpdir) / "sessions"
        monkeypatch.setattr(rt, "DEFAULT_SESSION_DIR", fake_sess_dir)

        runtime = AgentRuntime(workspace_root=Path(tmpdir))
        runtime.history = [{"role": "system", "content": "prompt"}]

        # Idle REPL (no active turn)
        assert not runtime.abort_current_turn()

        # Simulate KeyboardInterrupt inside run_turn
        def mock_dispatch(*args, **kwargs):
            raise KeyboardInterrupt("Simulated user Ctrl+C")

        monkeypatch.setattr(runtime, "_dispatch_waterfall", mock_dispatch)

        with pytest.raises(KeyboardInterrupt):
            runtime.run_turn("test interrupt")

        # History should be cleanly rolled back to exactly the system prompt
        assert len(runtime.history) == 1
        assert runtime.history[0]["role"] == "system"
        assert not runtime._turn_active


def test_consult_architect_secret_filter():
    with tempfile.TemporaryDirectory() as tmpdir:
        tools = ToolRegistry(workspace_root=Path(tmpdir), auto_approve=True)
        res = tools.consult_architect("Review this key: sk-ant-api03-12345678901234567890")
        assert "error" in res
        assert "Security restriction" in res["error"]


def test_nous_auth_nested_providers_schema(monkeypatch):
    import json
    import triad.agent.runtime as rt
    from triad.agent.router import DEFAULT_NOUS_MODEL

    with tempfile.TemporaryDirectory() as tmpdir:
        auth_file = Path(tmpdir) / "auth.json"
        auth_file.write_text(
            json.dumps({
                "version": 2,
                "active_provider": "nous",
                "providers": {
                    "nous": {
                        "agent_key": "sk-nous-agent-test",
                        "access_token": "tok-fallback",
                    }
                },
            }),
            encoding="utf-8",
        )
        monkeypatch.delenv("NOUS_API_KEY", raising=False)
        monkeypatch.setattr(rt, "NOUS_AUTH_PATH", auth_file)
        monkeypatch.setattr(rt, "DEFAULT_SESSION_DIR", Path(tmpdir) / "sessions")

        runtime = rt.AgentRuntime(workspace_root=Path(tmpdir))
        assert runtime._get_nous_api_key() == "sk-nous-agent-test"

        dec = runtime.router.select_route("hello", force_tier="nous")
        assert dec.selected_tier == ModelTier.TIER_2_CLOUD_FREE
        assert dec.model_name == DEFAULT_NOUS_MODEL


def test_router_skips_cooling_down_local_tier():
    from triad.agent.router import DEFAULT_NOUS_MODEL

    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = RollingWindowTracker(ledger_path=Path(tmpdir) / "ledger.json")
        router = ZeroCostRouter(tracker=tracker)

        tracker.mark_circuit_break("llama_local", cooldown_seconds=120)
        dec = router.select_route("Write a python script to parse CSV")
        assert dec.selected_tier == ModelTier.TIER_2_CLOUD_FREE
        assert dec.model_name == DEFAULT_NOUS_MODEL
        assert dec.fallback_chain == []


def test_parse_nested_tool_call_and_null_args():
    from triad.agent.runtime import AgentRuntime

    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = AgentRuntime(workspace_root=Path(tmpdir))
        reply = (
            "Let me read that file.\n"
            "```tool_call\n"
            "{\n"
            '  "name": "read_file",\n'
            '  "arguments": {\n'
            '    "path": "nested/file.py",\n'
            '    "start_line": 1\n'
            "  }\n"
            "}\n"
            "```\n"
            "Extra trailing text with } brace."
        )
        parsed = runtime._parse_tool_call(reply)
        assert parsed is not None
        assert parsed["name"] == "read_file"
        assert parsed["arguments"]["path"] == "nested/file.py"

        # Null arguments should not crash _execute_tool with TypeError
        out = runtime._execute_tool({"name": "list_dir", "arguments": None})
        assert "error" not in out.lower() or "count" in out.lower()


def test_runtime_model_override_and_usage_recording(monkeypatch):
    import triad.agent.runtime as rt

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(rt, "DEFAULT_SESSION_DIR", Path(tmpdir) / "sessions")
        tracker = RollingWindowTracker(ledger_path=Path(tmpdir) / "ledger.json")
        runtime = rt.AgentRuntime(
            workspace_root=Path(tmpdir),
            router=ZeroCostRouter(tracker=tracker),
            model_override="deepseek/deepseek-v4-pro",
        )
        monkeypatch.setattr(runtime, "_get_nous_api_key", lambda: "sk-test")

        seen = {}

        def fake_http(base_url, model, messages, api_key=None, timeout=120, max_tokens=2048, loopback=False):
            seen["model"] = model
            runtime._last_usage = (120, 30)
            return "OK"

        monkeypatch.setattr(runtime, "_call_http_openai_compatible", fake_http)
        reply = runtime.run_turn("ping", force_tier="nous")
        assert reply == "OK"
        assert seen["model"] == "deepseek/deepseek-v4-pro"
        stats = tracker.get_window_stats(provider="nous_free")
        assert stats["total_turns"] == 1
        assert stats["total_tokens"] == 150


def test_nous_cascade_on_429_and_concise_prompt(monkeypatch):
    import triad.agent.runtime as rt
    from triad.agent.router import NOUS_MODEL_CASCADE

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(rt, "DEFAULT_SESSION_DIR", Path(tmpdir) / "sessions")
        tracker = RollingWindowTracker(ledger_path=Path(tmpdir) / "ledger.json")
        runtime = rt.AgentRuntime(
            workspace_root=Path(tmpdir),
            router=ZeroCostRouter(tracker=tracker),
            concise=True,
        )
        assert "CONCISE MODE:" in runtime._get_system_prompt()
        monkeypatch.setattr(runtime, "_get_nous_api_key", lambda: "sk-test")

        tried = []

        def fake_http(base_url, model, messages, api_key=None, timeout=120, max_tokens=2048, loopback=False):
            tried.append(model)
            if len(tried) == 1:
                raise RuntimeError("HTTP Error 429: Too Many Requests")
            runtime._last_usage = (50, 10)
            return "FALLBACK_OK"

        monkeypatch.setattr(runtime, "_call_http_openai_compatible", fake_http)
        reply = runtime.run_turn("hello", force_tier="nous")
        assert reply == "FALLBACK_OK"
        assert len(tried) == 2
        assert tried[0] == NOUS_MODEL_CASCADE[0]
        assert tried[1] == NOUS_MODEL_CASCADE[1]


def test_compact_history_reduces_size():
    from triad.agent.runtime import AgentRuntime

    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = AgentRuntime(workspace_root=Path(tmpdir))
        runtime.history = [{"role": "system", "content": "sys"}]
        for i in range(10):
            runtime.history.append({"role": "user", "content": f"turn {i} " + ("x" * 500)})
            runtime.history.append({"role": "assistant", "content": f"reply {i} " + ("y" * 500)})

        res = runtime.compact_history(keep_recent=4)
        assert res["removed"] == 16
        assert res["chars_after"] < res["chars_before"]
        assert runtime.history[0]["role"] == "system"
        assert runtime.history[1]["role"] == "user"
        assert "[Compacted Earlier Turns" in runtime.history[1]["content"]
        assert len(runtime.history) == 6


def test_recall_memory_and_mesh_delegate_graceful_offline():
    with tempfile.TemporaryDirectory() as tmpdir:
        tools = ToolRegistry(workspace_root=Path(tmpdir), auto_approve=True)
        bad_mem = tools.recall_memory("")
        assert "error" in bad_mem

        bad_mesh = tools.mesh_delegate(action="invalid_action")
        assert "error" in bad_mesh

        # Offline mesh returns clean error dict rather than raising
        mesh_res = tools.mesh_delegate(action="ping")
        assert isinstance(mesh_res, dict)


def test_savings_telemetry_and_architect_handoff(monkeypatch):
    import triad.agent.runtime as rt

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(rt, "DEFAULT_SESSION_DIR", Path(tmpdir) / "sessions")
        tracker = RollingWindowTracker(ledger_path=Path(tmpdir) / "ledger.json")
        runtime = rt.AgentRuntime(
            workspace_root=Path(tmpdir),
            router=ZeroCostRouter(tracker=tracker),
            auto_approve=True,
        )
        runtime.history = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Investigate bug in auth.py"},
            {"role": "assistant", "content": "Checked auth.py, found token issue"},
        ]

        captured = {}

        def fake_consult(query, context=None):
            captured["query"] = query
            captured["context"] = context
            return {"advice": "ok"}

        monkeypatch.setattr(runtime.tools, "consult_architect", fake_consult)
        runtime._execute_tool({"name": "consult_architect", "arguments": {"query": "How should we fix?"}})
        assert "Investigate bug in auth.py" in (captured["context"] or "")

        bad_ctx = runtime._execute_tool({"name": "consult_architect", "arguments": {"query": "Fix", "context": {"file": "auth.py"}}})
        assert "must be a string" in bad_ctx

        # Exercise actual tool-output truncation and history compaction telemetry
        big_file = Path(tmpdir) / "big.txt"
        big_file.write_text("A" * 20000, encoding="utf-8")
        calls = {"n": 0}

        def fake_dispatch(decision, messages, on_status=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return '```tool_call\n{"name": "read_file", "arguments": {"path": "big.txt", "end_line": 100}}\n```', ModelTier.TIER_2_CLOUD_FREE
            return "DONE", ModelTier.TIER_2_CLOUD_FREE

        monkeypatch.setattr(runtime, "_dispatch_waterfall", fake_dispatch)
        assert runtime.run_turn("read big file", force_tier="nous") == "DONE"
        s1 = tracker.get_savings_stats()
        assert s1["events"] == 1
        assert s1["chars_saved"] > 5000

        for i in range(6):
            runtime.history.append({"role": "user", "content": f"extra {i} " + ("z" * 400)})
        comp = runtime.compact_history(keep_recent=4)
        assert comp["chars_before"] > comp["chars_after"]
        s2 = tracker.get_savings_stats()
        assert s2["events"] == 2
        assert s2["chars_saved"] == s1["chars_saved"] + (comp["chars_before"] - comp["chars_after"])

        # Telemetry failures (OSError / TimeoutError) must not abort tool turns or compaction
        def fail_os(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(tracker, "record_savings", fail_os)
        calls["n"] = 0
        assert runtime.run_turn("read big file again", force_tier="nous") == "DONE"

        def fail_timeout(*args, **kwargs):
            raise TimeoutError("lock busy")

        monkeypatch.setattr(tracker, "record_savings", fail_timeout)
        for i in range(6):
            runtime.history.append({"role": "user", "content": f"extra2 {i} " + ("w" * 400)})
        comp2 = runtime.compact_history(keep_recent=4)
        assert comp2["chars_before"] > comp2["chars_after"]
