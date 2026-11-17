# Tag: `cost`

[← index](../REPO_TAGS.md) · 13 files

| File | Links | Queries |
| --- | --- | --- |
| `docs/BLUEPRINT.md` | `docs/ARCHITECTURE.md`<br>`triad/competition.py`<br>`triad/circuit.py` | `what is the zero-token marginal cost design`<br>`how does dual-advisor consensus work`<br>`what is an ephemeral execution` |
| `docs/TRIAD_UPGRADE_SPEC.md` | `docs/TRIAD_V34_UNIFICATION_SPEC.md`<br>`triad/cli/review.py` | `what does v3.4 change about reviews`<br>`how much are tokens meant to drop`<br>`what is the phase order` |
| `skills/claude-advisor/advisor.py` | `triad/advisor_manager.py`<br>`triad/competition.py`<br>`skills/claude-advisor/SKILL.md` | `how does the bridge pick claude or codex`<br>`what happens at the claude session limit`<br>`how is the failover made free` |
| `triad/advisor_manager.py` | `triad/advisors.json`<br>`triad/circuit.py`<br>`triad/triad_engine.py` | `which advisor runs for this task`<br>`how does the cascade order work`<br>`what happens when an advisor is unhealthy`<br>`how is a free tier preferred` |
| `triad/agent/__init__.py` | `triad/agent/cli.py`<br>`triad/agent/router.py` | `what is the agent waterfall`<br>`which tiers are available with no spend` |
| `triad/agent/router.py` | `triad/agent/tracker.py`<br>`triad/agent/runtime.py` | `how is a model chosen for this turn`<br>`what is the adaptive threshold`<br>`how is difficulty classified` |
| `triad/agent/tracker.py` | `triad/agent/router.py` | `how is the quota window tracked`<br>`when does a tier count as used up` |
| `triad/bench/run_bench.py` | `triad/bench/swebench_runner.py`<br>`triad/triad_engine.py` | `how do I run the benchmark`<br>`what counts as a pass`<br>`how is cost reported` |
| `triad/cli/doctor.py` | `triad/circuit.py`<br>`triad/nous_bridge.py`<br>`scripts/verify.ps1` | `what does triad doctor check`<br>`how do I see projected cost`<br>`which advisors are unhealthy` |
| `triad/competition.py` | `triad/advisor_manager.py`<br>`triad/triad_engine.py` | `how do two advisors run at once`<br>`how is a structured synthesis built`<br>`what happens when both agree` |
| `triad/nous_bridge.py` | `triad/advisor_manager.py`<br>`triad/cli/doctor.py` | `which nous models are tried and in what order`<br>`what is the per-model timeout`<br>`when does the free cascade fall through` |
| `triad/response_cache.py` | `triad/advisor_manager.py`<br>`triad/cli/doctor.py` | `how is a model response cached`<br>`what makes a cache key`<br>`what does a cache hit save` |
| `triad/tests/test_agent.py` | `triad/agent/router.py`<br>`triad/agent/runtime.py` | `how is routing tested`<br>`is quota tracking covered` |
