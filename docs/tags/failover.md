# Tag: `failover`

[← index](../REPO_TAGS.md) · 9 files

| File | Links | Queries |
| --- | --- | --- |
| `docs/BLUEPRINT.md` | `docs/ARCHITECTURE.md`<br>`triad/competition.py`<br>`triad/circuit.py` | `what is the zero-token marginal cost design`<br>`how does dual-advisor consensus work`<br>`what is an ephemeral execution` |
| `HERMES_HANDOFF_2026-10-02.md` | `triad/circuit.py`<br>`docs/ARCHITECTURE.md` | `what shipped in the circuit breaker and bench env work`<br>`which branch landed it` |
| `skills/claude-advisor/advisor.py` | `triad/advisor_manager.py`<br>`triad/competition.py`<br>`skills/claude-advisor/SKILL.md` | `how does the bridge pick claude or codex`<br>`what happens at the claude session limit`<br>`how is the failover made free` |
| `triad/advisor_manager.py` | `triad/advisors.json`<br>`triad/circuit.py`<br>`triad/triad_engine.py` | `which advisor runs for this task`<br>`how does the cascade order work`<br>`what happens when an advisor is unhealthy`<br>`how is a free tier preferred` |
| `triad/agent/runtime.py` | `triad/agent/router.py`<br>`triad/agent/tools.py` | `how does the waterfall fall through`<br>`what happens when a tier is exhausted`<br>`how is a turn executed` |
| `triad/circuit.py` | `triad/advisor_manager.py` | `when is an advisor marked unhealthy`<br>`how long does the breaker stay open`<br>`what does auto-failover skip` |
| `triad/cli/doctor.py` | `triad/circuit.py`<br>`triad/nous_bridge.py`<br>`scripts/verify.ps1` | `what does triad doctor check`<br>`how do I see projected cost`<br>`which advisors are unhealthy` |
| `triad/tests/test_advisor_manager.py` | `triad/advisor_manager.py` | `what does the advisor manager guarantee`<br>`which failover paths are covered` |
| `triad/tests/test_circuit.py` | `triad/circuit.py` | `when does the breaker open and close`<br>`what is skipped while open` |
