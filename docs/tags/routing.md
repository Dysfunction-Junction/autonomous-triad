# Tag: `routing`

[← index](../REPO_TAGS.md) · 10 files

| File | Links | Queries |
| --- | --- | --- |
| `HERMES_HANDOFF_2026-10-27.md` | `triad/agent/router.py`<br>`triad/agent/runtime.py`<br>`docs/ARCHITECTURE.md` | `when did the agent stop using ollama`<br>`what does RouteLLM classify`<br>`which advisor signed off` |
| `README.md` | `triad/triad_engine.py`<br>`docs/ARCHITECTURE.md`<br>`bin/triad` | `what does the triad do`<br>`which commands does the CLI expose`<br>`how is zero incremental cost enforced` |
| `triad/advisor_manager.py` | `triad/advisors.json`<br>`triad/circuit.py`<br>`triad/triad_engine.py` | `which advisor runs for this task`<br>`how does the cascade order work`<br>`what happens when an advisor is unhealthy`<br>`how is a free tier preferred` |
| `triad/agent/__init__.py` | `triad/agent/cli.py`<br>`triad/agent/router.py` | `what is the agent waterfall`<br>`which tiers are available with no spend` |
| `triad/agent/router.py` | `triad/agent/tracker.py`<br>`triad/agent/runtime.py` | `how is a model chosen for this turn`<br>`what is the adaptive threshold`<br>`how is difficulty classified` |
| `triad/agent/runtime.py` | `triad/agent/router.py`<br>`triad/agent/tools.py` | `how does the waterfall fall through`<br>`what happens when a tier is exhausted`<br>`how is a turn executed` |
| `triad/intent_engine.py` | `triad/cli/review.py`<br>`triad/triad_engine.py`<br>`docs/ARCHITECTURE.md` | `how is a prompt classified`<br>`what makes a task high stakes`<br>`when is it auto-adjudicated` |
| `triad/nous_bridge.py` | `triad/advisor_manager.py`<br>`triad/cli/doctor.py` | `which nous models are tried and in what order`<br>`what is the per-model timeout`<br>`when does the free cascade fall through` |
| `triad/tests/test_agent.py` | `triad/agent/router.py`<br>`triad/agent/runtime.py` | `how is routing tested`<br>`is quota tracking covered` |
| `triad/tests/test_intent_engine.py` | `triad/intent_engine.py` | `which classifications are covered`<br>`how are high-stakes prompts detected` |
