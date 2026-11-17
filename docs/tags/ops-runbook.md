# Tag: `ops-runbook`

[← index](../REPO_TAGS.md) · 23 files

| File | Links | Queries |
| --- | --- | --- |
| `.github/copilot-instructions.md` | `AGENTS.md`<br>`README.md` | `what should an agent read first`<br>`which execution protocol is the default` |
| `.github/workflows/ci.yml` | `pyproject.toml`<br>`scripts/repo-tags.mjs` | `what does CI run on a pull request`<br>`is the tag gate enforced in CI` |
| `AGENTS.md` | `README.md`<br>`docs/ARCHITECTURE.md`<br>`triad/advisors.json` | `which checkout is canonical for triad`<br>`how does packages/triad relate to this repo`<br>`which port does triad listen on` |
| `bin/tr.cmd` | `bin/tr.ps1`<br>`triad/agent/cli.py` | `how do I start the agent from cmd`<br>`what happens when the engine is missing` |
| `bin/tr.ps1` | `triad/agent/cli.py`<br>`bin/triad.ps1` | `how do I start the agent REPL on windows`<br>`how does it resolve the repo` |
| `bin/triad` | `triad/triad_engine.py`<br>`triad/paths.py` | `how does the sh launcher find python`<br>`where does it look for the repo root` |
| `bin/triad.cmd` | `bin/triad.ps1`<br>`bin/triad` | `how does the batch launcher find the engine`<br>`what happens if TRIAD_ROOT is unset` |
| `bin/triad.ps1` | `triad/triad_engine.py`<br>`triad/paths.py` | `how does the powershell launcher resolve the root`<br>`what is the search order` |
| `HERMES_HANDOFF_2026-10-02.md` | `triad/circuit.py`<br>`docs/ARCHITECTURE.md` | `what shipped in the circuit breaker and bench env work`<br>`which branch landed it` |
| `HERMES_HANDOFF_2026-10-03.md` | `triad/paths.py`<br>`docs/ARCHITECTURE.md` | `what did the packaging and ctime merge change`<br>`was the suite green when it landed` |
| `HERMES_HANDOFF_2026-10-27.md` | `triad/agent/router.py`<br>`triad/agent/runtime.py`<br>`docs/ARCHITECTURE.md` | `when did the agent stop using ollama`<br>`what does RouteLLM classify`<br>`which advisor signed off` |
| `pyproject.toml` | `triad/triad_engine.py`<br>`bin/triad` | `which console scripts does the package install`<br>`what are the runtime dependencies` |
| `README.md` | `triad/triad_engine.py`<br>`docs/ARCHITECTURE.md`<br>`bin/triad` | `what does the triad do`<br>`which commands does the CLI expose`<br>`how is zero incremental cost enforced` |
| `scripts/install.ps1` | `bin/triad.ps1`<br>`triad/sync_manager.py` | `how do I install triad on Windows`<br>`where does install put the launchers` |
| `scripts/verify.ps1` | `scripts/install.ps1`<br>`triad/cli/doctor.py` | `how do I check the install is healthy`<br>`what does verify run` |
| `skills/claude-advisor/SKILL.md` | `skills/claude-advisor/advisor.py` | `how does an agent load the advisor skill`<br>`when should an agent consult an advisor` |
| `triad/claims.py` | `triad/decision_log.py`<br>`AGENTS.md` | `who is touching which path right now`<br>`how do I claim paths before editing`<br>`how do I release a claim` |
| `triad/cli/doctor.py` | `triad/circuit.py`<br>`triad/nous_bridge.py`<br>`scripts/verify.ps1` | `what does triad doctor check`<br>`how do I see projected cost`<br>`which advisors are unhealthy` |
| `triad/cli/sync.py` | `triad/sync_manager.py` | `what does triad sync install`<br>`how do I keep the live install from drifting` |
| `triad/decision_log.py` | `AGENTS.md`<br>`triad/claims.py` | `what was decided for this project and when`<br>`how do I append a decision`<br>`how do I read the last ten decisions` |
| `triad/paths.py` | `triad/sync_manager.py`<br>`AGENTS.md` | `where does triad look for its install`<br>`how is the repo root resolved`<br>`where does ~/.agents come from` |
| `triad/procutil.py` | `triad/advisor_manager.py`<br>`triad/server.py` | `how is a subprocess timed out`<br>`how is a port probed`<br>`what happens when a binary is missing` |
| `triad/sync_manager.py` | `triad/paths.py`<br>`triad/cli/sync.py` | `what does a full sync install`<br>`where do junctions point`<br>`how are hooks installed across repos` |
