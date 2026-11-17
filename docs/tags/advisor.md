# Tag: `advisor`

[← index](../REPO_TAGS.md) · 16 files

| File | Links | Queries |
| --- | --- | --- |
| `AGENTS.md` | `README.md`<br>`docs/ARCHITECTURE.md`<br>`triad/advisors.json` | `which checkout is canonical for triad`<br>`how does packages/triad relate to this repo`<br>`which port does triad listen on` |
| `docs/ARCHITECTURE.md` | `triad/triad_engine.py`<br>`triad/server.py`<br>`docs/BLUEPRINT.md` | `how do the advisors talk to each other`<br>`what are the invariant rules`<br>`how is a prompt classified` |
| `docs/BLUEPRINT.md` | `docs/ARCHITECTURE.md`<br>`triad/competition.py`<br>`triad/circuit.py` | `what is the zero-token marginal cost design`<br>`how does dual-advisor consensus work`<br>`what is an ephemeral execution` |
| `README.md` | `triad/triad_engine.py`<br>`docs/ARCHITECTURE.md`<br>`bin/triad` | `what does the triad do`<br>`which commands does the CLI expose`<br>`how is zero incremental cost enforced` |
| `skills/claude-advisor/advisor.py` | `triad/advisor_manager.py`<br>`triad/competition.py`<br>`skills/claude-advisor/SKILL.md` | `how does the bridge pick claude or codex`<br>`what happens at the claude session limit`<br>`how is the failover made free` |
| `skills/claude-advisor/SKILL.md` | `skills/claude-advisor/advisor.py` | `how does an agent load the advisor skill`<br>`when should an agent consult an advisor` |
| `triad/advisor_manager.py` | `triad/advisors.json`<br>`triad/circuit.py`<br>`triad/triad_engine.py` | `which advisor runs for this task`<br>`how does the cascade order work`<br>`what happens when an advisor is unhealthy`<br>`how is a free tier preferred` |
| `triad/circuit.py` | `triad/advisor_manager.py` | `when is an advisor marked unhealthy`<br>`how long does the breaker stay open`<br>`what does auto-failover skip` |
| `triad/cli/review.py` | `triad/intent_engine.py`<br>`triad/competition.py` | `what review modes exist`<br>`how do I consult an advisor from the shell`<br>`what does triage decide` |
| `triad/competition.py` | `triad/advisor_manager.py`<br>`triad/triad_engine.py` | `how do two advisors run at once`<br>`how is a structured synthesis built`<br>`what happens when both agree` |
| `triad/server.py` | `triad/triad_engine.py`<br>`triad/intent_engine.py`<br>`AGENTS.md` | `which port does the daemon listen on`<br>`which routes does it expose`<br>`how does a phone or mesh call it` |
| `triad/tests/test_advisor_manager.py` | `triad/advisor_manager.py` | `what does the advisor manager guarantee`<br>`which failover paths are covered` |
| `triad/tests/test_circuit.py` | `triad/circuit.py` | `when does the breaker open and close`<br>`what is skipped while open` |
| `triad/tests/test_competition.py` | `triad/competition.py` | `how is concurrent dual-advisor output synthesised`<br>`what if one advisor fails` |
| `triad/tests/test_local_llm_backend.py` | `triad/advisor_manager.py`<br>`triad/nous_bridge.py` | `which endpoint is the local backend`<br>`is the local tier last in the cascade` |
| `triad/tests/test_synthesis_trim.py` | `triad/competition.py` | `how are cited hunks extracted`<br>`what is trimmed from synthesis`<br>`what counts as unanimous` |
