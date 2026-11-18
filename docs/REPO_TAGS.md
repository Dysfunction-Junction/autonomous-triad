# Repository tag index

> Generated view — do not edit. Regenerate with `node scripts/repo-tags.mjs`.
> Source: `git ls-files` · branch `test/isolated-repo-fixture` · commit `43f4cfd` · 98 tracked files.
>
> `Tags/Links/Queries` is the header written at the top of each file. This file is the map;
> the headers are the body. Both move together in the same commit.

**Coverage:** 97 / 98 files carry a tag header (99.0%). 1 untagged.

## How to read this

| Field | Meaning |
| --- | --- |
| Tags | coarse filter — `grep` this file for a tag to find its files |
| Links | where to look next: the file that calls this one, a doc, a config |
| Queries | the questions the file answers, in the words you would ask them |

Per-tag pages live under [`tags/`](tags/). They are generated too.

The vocabulary is frozen in [`TAG_VOCABULARY.md`](TAG_VOCABULARY.md). A tag outside it fails
`--audit`. `sovereign-exocortex` vendors this tree at `packages/triad/`; headers written here
flow downstream on the next `scripts/update-triad.ps1` sync, so tag here and never there.

## Tagged files

| File | Tags | Links |
| --- | --- | --- |
| `.github/copilot-instructions.md` | `ops-runbook`<br>`cli` | `AGENTS.md`<br>`README.md` |
| `.github/workflows/ci.yml` | `ops-runbook`<br>`verification` | `pyproject.toml`<br>`scripts/repo-tags.mjs` |
| `AGENTS.md` | `ops-runbook`<br>`protocol-contract`<br>`sync`<br>`advisor` | `README.md`<br>`docs/ARCHITECTURE.md`<br>`triad/advisors.json` |
| `bin/tr.cmd` | `agent`<br>`cli`<br>`ops-runbook` | `bin/tr.ps1`<br>`triad/agent/cli.py` |
| `bin/tr.ps1` | `agent`<br>`cli`<br>`ops-runbook` | `triad/agent/cli.py`<br>`bin/triad.ps1` |
| `bin/triad` | `cli`<br>`engine`<br>`ops-runbook` | `triad/triad_engine.py`<br>`triad/paths.py` |
| `bin/triad.cmd` | `cli`<br>`engine`<br>`ops-runbook` | `bin/triad.ps1`<br>`bin/triad` |
| `bin/triad.ps1` | `cli`<br>`engine`<br>`ops-runbook` | `triad/triad_engine.py`<br>`triad/paths.py` |
| `docs/ARCHITECTURE.md` | `engine`<br>`advisor`<br>`protocol-contract`<br>`review` | `triad/triad_engine.py`<br>`triad/server.py`<br>`docs/BLUEPRINT.md` |
| `docs/BLUEPRINT.md` | `advisor`<br>`review`<br>`failover`<br>`cost` | `docs/ARCHITECTURE.md`<br>`triad/competition.py`<br>`triad/circuit.py` |
| `docs/TRIAD_UPGRADE_SPEC.md` | `engine`<br>`review`<br>`triage`<br>`cost`<br>`verification` | `docs/TRIAD_V34_UNIFICATION_SPEC.md`<br>`triad/cli/review.py` |
| `docs/TRIAD_V34_MERGE_MAP.md` | `sync`<br>`verification`<br>`protocol-contract` | `scripts/triad_unify_audit.py`<br>`docs/TRIAD_V34_UNIFICATION_SPEC.md` |
| `docs/TRIAD_V34_UNIFICATION_SPEC.md` | `sync`<br>`engine`<br>`verification`<br>`review` | `docs/TRIAD_UPGRADE_SPEC.md`<br>`scripts/triad_unify_audit.py`<br>`docs/TRIAD_V34_MERGE_MAP.md` |
| `HERMES_HANDOFF_2026-10-02.md` | `ops-runbook`<br>`failover`<br>`bench` | `triad/circuit.py`<br>`docs/ARCHITECTURE.md` |
| `HERMES_HANDOFF_2026-10-03.md` | `ops-runbook`<br>`sync` | `triad/paths.py`<br>`docs/ARCHITECTURE.md` |
| `HERMES_HANDOFF_2026-10-27.md` | `ops-runbook`<br>`agent`<br>`routing`<br>`local-llm` | `triad/agent/router.py`<br>`triad/agent/runtime.py`<br>`docs/ARCHITECTURE.md` |
| `pyproject.toml` | `cli`<br>`ops-runbook` | `triad/triad_engine.py`<br>`bin/triad` |
| `README.md` | `engine`<br>`advisor`<br>`cli`<br>`routing`<br>`ops-runbook` | `triad/triad_engine.py`<br>`docs/ARCHITECTURE.md`<br>`bin/triad` |
| `scripts/download_swebench.py` | `bench`<br>`tooling` | `triad/bench/swebench_instances.json`<br>`triad/bench/swebench_runner.py` |
| `scripts/generate_cases_v2.py` | `bench`<br>`tooling` | `scripts/generate_cases.py`<br>`triad/bench/cases/` |
| `scripts/generate_cases.py` | `bench`<br>`tooling` | `scripts/generate_cases_v2.py`<br>`triad/bench/cases_v1/` |
| `scripts/install.ps1` | `cli`<br>`tooling`<br>`ops-runbook` | `bin/triad.ps1`<br>`triad/sync_manager.py` |
| `scripts/prepare_bench_env.py` | `bench`<br>`docker`<br>`tooling` | `triad/bench/docker_harness.py`<br>`triad/bench/swebench_runner.py` |
| `scripts/repo-tags.mjs` | `tooling`<br>`verification`<br>`protocol-contract` | `docs/TAG_VOCABULARY.md`<br>`docs/REPO_TAGS.md`<br>`.github/workflows/ci.yml` |
| `scripts/triad_unify_audit.py` | `sync`<br>`verification`<br>`tooling` | `docs/TRIAD_V34_MERGE_MAP.md`<br>`triad/sync_manager.py` |
| `scripts/verify.ps1` | `verification`<br>`tooling`<br>`ops-runbook` | `scripts/install.ps1`<br>`triad/cli/doctor.py` |
| `skills/claude-advisor/advisor.py` | `skills`<br>`advisor`<br>`failover`<br>`cost` | `triad/advisor_manager.py`<br>`triad/competition.py`<br>`skills/claude-advisor/SKILL.md` |
| `skills/claude-advisor/SKILL.md` | `skills`<br>`advisor`<br>`ops-runbook` | `skills/claude-advisor/advisor.py` |
| `triad/__init__.py` | `engine`<br>`protocol-contract` | `triad/triad_engine.py`<br>`pyproject.toml` |
| `triad/__main__.py` | `cli`<br>`engine` | `triad/triad_engine.py` |
| `triad/advisor_manager.py` | `advisor`<br>`routing`<br>`failover`<br>`cost` | `triad/advisors.json`<br>`triad/circuit.py`<br>`triad/triad_engine.py` |
| `triad/agent/__init__.py` | `agent`<br>`routing`<br>`cost` | `triad/agent/cli.py`<br>`triad/agent/router.py` |
| `triad/agent/cli.py` | `agent`<br>`cli` | `triad/agent/runtime.py`<br>`bin/tr.cmd` |
| `triad/agent/router.py` | `agent`<br>`routing`<br>`cost` | `triad/agent/tracker.py`<br>`triad/agent/runtime.py` |
| `triad/agent/runtime.py` | `agent`<br>`routing`<br>`failover` | `triad/agent/router.py`<br>`triad/agent/tools.py` |
| `triad/agent/tools.py` | `agent`<br>`worktree` | `triad/agent/runtime.py` |
| `triad/agent/tracker.py` | `agent`<br>`cost` | `triad/agent/router.py` |
| `triad/bench/__init__.py` | `bench`<br>`tooling` | `triad/bench/run_bench.py` |
| `triad/bench/docker_harness.py` | `bench`<br>`docker`<br>`verification` | `triad/bench/swebench_runner.py`<br>`scripts/prepare_bench_env.py` |
| `triad/bench/run_bench.py` | `bench`<br>`verification`<br>`cost` | `triad/bench/swebench_runner.py`<br>`triad/triad_engine.py` |
| `triad/bench/swebench_runner.py` | `bench`<br>`docker`<br>`verification` | `triad/bench/docker_harness.py`<br>`triad/bench/swebench_instances.json` |
| `triad/circuit.py` | `advisor`<br>`failover` | `triad/advisor_manager.py` |
| `triad/claims.py` | `claims`<br>`ops-runbook` | `triad/decision_log.py`<br>`AGENTS.md` |
| `triad/cli/__init__.py` | `cli`<br>`engine` | `triad/triad_engine.py` |
| `triad/cli/doctor.py` | `cli`<br>`ops-runbook`<br>`cost`<br>`failover` | `triad/circuit.py`<br>`triad/nous_bridge.py`<br>`scripts/verify.ps1` |
| `triad/cli/gate.py` | `cli`<br>`verification`<br>`notify`<br>`review` | `triad/notifier.py`<br>`triad/competition.py` |
| `triad/cli/hook.py` | `cli`<br>`worktree`<br>`patching`<br>`verification` | `triad/worktree.py`<br>`triad/cli/mesh.py` |
| `triad/cli/mesh.py` | `cli`<br>`mcp`<br>`protocol-contract` | `triad/server.py`<br>`AGENTS.md` |
| `triad/cli/review.py` | `cli`<br>`review`<br>`triage`<br>`advisor` | `triad/intent_engine.py`<br>`triad/competition.py` |
| `triad/cli/sync.py` | `cli`<br>`sync`<br>`ops-runbook` | `triad/sync_manager.py` |
| `triad/competition.py` | `advisor`<br>`review`<br>`cost` | `triad/advisor_manager.py`<br>`triad/triad_engine.py` |
| `triad/decision_log.py` | `ledger`<br>`ops-runbook` | `AGENTS.md`<br>`triad/claims.py` |
| `triad/docker_runner.py` | `docker`<br>`verification` | `triad/morphogenetic.py`<br>`triad/bench/docker_harness.py` |
| `triad/egress.py` | `egress`<br>`protocol-contract` | `triad/advisor_manager.py`<br>`triad/nous_bridge.py` |
| `triad/intent_engine.py` | `intent`<br>`routing`<br>`review` | `triad/cli/review.py`<br>`triad/triad_engine.py`<br>`docs/ARCHITECTURE.md` |
| `triad/morpho.py` | `morphogenetic`<br>`patching`<br>`verification` | `triad/morphogenetic.py`<br>`triad/docker_runner.py` |
| `triad/morphogenetic.py` | `morphogenetic`<br>`patching`<br>`verification` | `triad/docker_runner.py`<br>`triad/worktree.py` |
| `triad/notifier.py` | `notify`<br>`protocol-contract` | `triad/cli/gate.py`<br>`triad/triad_engine.py` |
| `triad/nous_bridge.py` | `nous`<br>`routing`<br>`cost` | `triad/advisor_manager.py`<br>`triad/cli/doctor.py` |
| `triad/patching.py` | `patching`<br>`worktree`<br>`verification` | `triad/worktree.py`<br>`triad/triad_engine.py` |
| `triad/paths.py` | `ops-runbook`<br>`sync` | `triad/sync_manager.py`<br>`AGENTS.md` |
| `triad/procutil.py` | `ops-runbook`<br>`protocol-contract` | `triad/advisor_manager.py`<br>`triad/server.py` |
| `triad/prompt_rewriter.py` | `intent`<br>`review` | `triad/intent_engine.py`<br>`triad/prw.py` |
| `triad/prw.py` | `intent`<br>`cli` | `triad/prompt_rewriter.py` |
| `triad/response_cache.py` | `cache`<br>`cost` | `triad/advisor_manager.py`<br>`triad/cli/doctor.py` |
| `triad/server.py` | `server`<br>`protocol-contract`<br>`advisor` | `triad/triad_engine.py`<br>`triad/intent_engine.py`<br>`AGENTS.md` |
| `triad/sync_manager.py` | `sync`<br>`ops-runbook` | `triad/paths.py`<br>`triad/cli/sync.py` |
| `triad/tests/__init__.py` | `test-fixture`<br>`verification` | `pyproject.toml` |
| `triad/tests/_isolated_repo.py` | `test-fixture`<br>`worktree` | `triad/tests/test_worktree.py`<br>`triad/worktree.py` |
| `triad/tests/test_advisor_manager.py` | `advisor`<br>`failover`<br>`test-fixture` | `triad/advisor_manager.py` |
| `triad/tests/test_agent.py` | `agent`<br>`routing`<br>`cost`<br>`test-fixture` | `triad/agent/router.py`<br>`triad/agent/runtime.py` |
| `triad/tests/test_circuit.py` | `advisor`<br>`failover`<br>`test-fixture` | `triad/circuit.py` |
| `triad/tests/test_competition.py` | `advisor`<br>`review`<br>`test-fixture` | `triad/competition.py` |
| `triad/tests/test_diff_bloat.py` | `patching`<br>`review`<br>`test-fixture` | `triad/advisor_manager.py`<br>`triad/patching.py` |
| `triad/tests/test_docker_harness.py` | `bench`<br>`docker`<br>`verification`<br>`test-fixture` | `triad/bench/docker_harness.py` |
| `triad/tests/test_docker_runner.py` | `docker`<br>`verification`<br>`test-fixture` | `triad/docker_runner.py` |
| `triad/tests/test_egress.py` | `egress`<br>`test-fixture` | `triad/egress.py` |
| `triad/tests/test_hook.py` | `cli`<br>`worktree`<br>`verification`<br>`test-fixture` | `triad/cli/hook.py`<br>`triad/worktree.py` |
| `triad/tests/test_intent_engine.py` | `intent`<br>`routing`<br>`test-fixture` | `triad/intent_engine.py` |
| `triad/tests/test_local_llm_backend.py` | `local-llm`<br>`advisor`<br>`test-fixture` | `triad/advisor_manager.py`<br>`triad/nous_bridge.py` |
| `triad/tests/test_morpho_sh0.py` | `morphogenetic`<br>`verification`<br>`test-fixture` | `triad/morpho.py`<br>`triad/morphogenetic.py`<br>`triad/ts_verify/__init__.py` |
| `triad/tests/test_morphogenetic_gates.py` | `morphogenetic`<br>`docker`<br>`verification`<br>`test-fixture` | `triad/morphogenetic.py`<br>`triad/docker_runner.py` |
| `triad/tests/test_morphogenetic.py` | `morphogenetic`<br>`test-fixture` | `triad/morphogenetic.py` |
| `triad/tests/test_notifier.py` | `notify`<br>`test-fixture` | `triad/notifier.py` |
| `triad/tests/test_nous_bridge.py` | `nous`<br>`test-fixture` | `triad/nous_bridge.py` |
| `triad/tests/test_prompt_rewriter.py` | `intent`<br>`review`<br>`test-fixture` | `triad/prompt_rewriter.py` |
| `triad/tests/test_response_cache.py` | `cache`<br>`test-fixture` | `triad/response_cache.py` |
| `triad/tests/test_server.py` | `server`<br>`protocol-contract`<br>`test-fixture` | `triad/server.py` |
| `triad/tests/test_sync_manager.py` | `sync`<br>`test-fixture` | `triad/sync_manager.py` |
| `triad/tests/test_synthesis_trim.py` | `review`<br>`advisor`<br>`test-fixture` | `triad/competition.py` |
| `triad/tests/test_triage.py` | `triage`<br>`local-llm`<br>`test-fixture` | `triad/cli/review.py` |
| `triad/tests/test_worktree.py` | `worktree`<br>`test-fixture` | `triad/worktree.py` |
| `triad/triad_engine.py` | `engine`<br>`cli`<br>`review`<br>`verification` | `triad/advisor_manager.py`<br>`triad/intent_engine.py`<br>`bin/triad` |
| `triad/ts_verify/__init__.py` | `docker`<br>`morphogenetic`<br>`verification` | `triad/docker_runner.py`<br>`triad/ts_verify/Dockerfile`<br>`triad/ts_verify/verify-ts` |
| `triad/ts_verify/Dockerfile` | `docker`<br>`verification` | `triad/ts_verify/__init__.py`<br>`triad/ts_verify/verify-ts` |
| `triad/ts_verify/verify-ts` | `docker`<br>`verification` | `triad/ts_verify/__init__.py`<br>`triad/ts_verify/Dockerfile` |
| `triad/worktree.py` | `worktree`<br>`patching`<br>`verification` | `triad/patching.py`<br>`triad/cli/hook.py` |

## Tags

| Tag | Files | Page |
| --- | --- | --- |
| `advisor` | 16 | [tags/advisor.md](tags/advisor.md) |
| `agent` | 10 | [tags/agent.md](tags/agent.md) |
| `bench` | 10 | [tags/bench.md](tags/bench.md) |
| `cache` | 2 | [tags/cache.md](tags/cache.md) |
| `claims` | 1 | [tags/claims.md](tags/claims.md) |
| `cli` | 21 | [tags/cli.md](tags/cli.md) |
| `cost` | 13 | [tags/cost.md](tags/cost.md) |
| `docker` | 10 | [tags/docker.md](tags/docker.md) |
| `egress` | 2 | [tags/egress.md](tags/egress.md) |
| `engine` | 11 | [tags/engine.md](tags/engine.md) |
| `failover` | 9 | [tags/failover.md](tags/failover.md) |
| `intent` | 5 | [tags/intent.md](tags/intent.md) |
| `ledger` | 1 | [tags/ledger.md](tags/ledger.md) |
| `local-llm` | 3 | [tags/local-llm.md](tags/local-llm.md) |
| `mcp` | 1 | [tags/mcp.md](tags/mcp.md) |
| `morphogenetic` | 6 | [tags/morphogenetic.md](tags/morphogenetic.md) |
| `notify` | 3 | [tags/notify.md](tags/notify.md) |
| `nous` | 2 | [tags/nous.md](tags/nous.md) |
| `ops-runbook` | 23 | [tags/ops-runbook.md](tags/ops-runbook.md) |
| `patching` | 6 | [tags/patching.md](tags/patching.md) |
| `protocol-contract` | 11 | [tags/protocol-contract.md](tags/protocol-contract.md) |
| `review` | 14 | [tags/review.md](tags/review.md) |
| `routing` | 10 | [tags/routing.md](tags/routing.md) |
| `server` | 2 | [tags/server.md](tags/server.md) |
| `skills` | 2 | [tags/skills.md](tags/skills.md) |
| `sync` | 9 | [tags/sync.md](tags/sync.md) |
| `test-fixture` | 25 | [tags/test-fixture.md](tags/test-fixture.md) |
| `tooling` | 9 | [tags/tooling.md](tags/tooling.md) |
| `triage` | 3 | [tags/triage.md](tags/triage.md) |
| `verification` | 27 | [tags/verification.md](tags/verification.md) |
| `worktree` | 7 | [tags/worktree.md](tags/worktree.md) |

## Backfill backlog

Untagged files per area, largest first. Tag the areas you actually query.

| Area | Untagged files |
| --- | --- |
| `triad/protected_paths.txt` | 1 |
