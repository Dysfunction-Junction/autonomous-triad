# Tag: `test-fixture`

[← index](../REPO_TAGS.md) · 25 files

| File | Links | Queries |
| --- | --- | --- |
| `triad/tests/__init__.py` | `pyproject.toml` | `how is the test suite run` |
| `triad/tests/_isolated_repo.py` | `triad/tests/test_worktree.py`<br>`triad/worktree.py` | `which repository do worktree tests run against`<br>`why do the tests use a throwaway git repo`<br>`how are test worktrees kept off the developer checkout` |
| `triad/tests/test_advisor_manager.py` | `triad/advisor_manager.py` | `what does the advisor manager guarantee`<br>`which failover paths are covered` |
| `triad/tests/test_agent.py` | `triad/agent/router.py`<br>`triad/agent/runtime.py` | `how is routing tested`<br>`is quota tracking covered` |
| `triad/tests/test_circuit.py` | `triad/circuit.py` | `when does the breaker open and close`<br>`what is skipped while open` |
| `triad/tests/test_competition.py` | `triad/competition.py` | `how is concurrent dual-advisor output synthesised`<br>`what if one advisor fails` |
| `triad/tests/test_diff_bloat.py` | `triad/advisor_manager.py`<br>`triad/patching.py` | `how is diff bloat stripped`<br>`is stripping idempotent`<br>`how are docs classified` |
| `triad/tests/test_docker_harness.py` | `triad/bench/docker_harness.py` | `how is the harness cache key built`<br>`does this test start docker` |
| `triad/tests/test_docker_runner.py` | `triad/docker_runner.py` | `how is the container-backed runner tested`<br>`what mounts are asserted` |
| `triad/tests/test_egress.py` | `triad/egress.py` | `what is redacted before a send`<br>`does this test make live model calls` |
| `triad/tests/test_hook.py` | `triad/cli/hook.py`<br>`triad/worktree.py` | `how is the pre-commit hook tested`<br>`does the self-healing applicator close the loop` |
| `triad/tests/test_intent_engine.py` | `triad/intent_engine.py` | `which classifications are covered`<br>`how are high-stakes prompts detected` |
| `triad/tests/test_local_llm_backend.py` | `triad/advisor_manager.py`<br>`triad/nous_bridge.py` | `which endpoint is the local backend`<br>`is the local tier last in the cascade` |
| `triad/tests/test_morpho_sh0.py` | `triad/morpho.py`<br>`triad/morphogenetic.py`<br>`triad/ts_verify/__init__.py` | `how are SH-0 gates and TypeScript verification tested` |
| `triad/tests/test_morphogenetic_gates.py` | `triad/morphogenetic.py`<br>`triad/docker_runner.py` | `is the engine flag default off`<br>`what is the diff-size cap`<br>`is a reproduction test required` |
| `triad/tests/test_morphogenetic.py` | `triad/morphogenetic.py` | `what does the engine rewrite`<br>`which gates are exercised` |
| `triad/tests/test_notifier.py` | `triad/notifier.py` | `what payload is sent to the phone`<br>`how is a failed delivery handled` |
| `triad/tests/test_nous_bridge.py` | `triad/nous_bridge.py` | `which cascade order is asserted`<br>`what happens on timeout` |
| `triad/tests/test_prompt_rewriter.py` | `triad/prompt_rewriter.py` | `what does the rewriter add`<br>`are short prompts expanded` |
| `triad/tests/test_response_cache.py` | `triad/response_cache.py` | `how is a cache key shaped`<br>`how is python resolution handled` |
| `triad/tests/test_server.py` | `triad/server.py` | `which routes are covered`<br>`how is the daemon started in tests` |
| `triad/tests/test_sync_manager.py` | `triad/sync_manager.py` | `what does a sync produce`<br>`how are custom advisors preserved` |
| `triad/tests/test_synthesis_trim.py` | `triad/competition.py` | `how are cited hunks extracted`<br>`what is trimmed from synthesis`<br>`what counts as unanimous` |
| `triad/tests/test_triage.py` | `triad/cli/review.py` | `which docs are pre-filtered`<br>`how is local llama risk triage tested` |
| `triad/tests/test_worktree.py` | `triad/worktree.py` | `how is isolation tested`<br>`is cleanup asserted` |
