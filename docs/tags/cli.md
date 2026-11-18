# Tag: `cli`

[← index](../REPO_TAGS.md) · 20 files

| File | Links | Queries |
| --- | --- | --- |
| `.github/copilot-instructions.md` | `AGENTS.md`<br>`README.md` | `what should an agent read first`<br>`which execution protocol is the default` |
| `bin/tr.cmd` | `bin/tr.ps1`<br>`triad/agent/cli.py` | `how do I start the agent from cmd`<br>`what happens when the engine is missing` |
| `bin/tr.ps1` | `triad/agent/cli.py`<br>`bin/triad.ps1` | `how do I start the agent REPL on windows`<br>`how does it resolve the repo` |
| `bin/triad` | `triad/triad_engine.py`<br>`triad/paths.py` | `how does the sh launcher find python`<br>`where does it look for the repo root` |
| `bin/triad.cmd` | `bin/triad.ps1`<br>`bin/triad` | `how does the batch launcher find the engine`<br>`what happens if TRIAD_ROOT is unset` |
| `bin/triad.ps1` | `triad/triad_engine.py`<br>`triad/paths.py` | `how does the powershell launcher resolve the root`<br>`what is the search order` |
| `pyproject.toml` | `triad/triad_engine.py`<br>`bin/triad` | `which console scripts does the package install`<br>`what are the runtime dependencies` |
| `README.md` | `triad/triad_engine.py`<br>`docs/ARCHITECTURE.md`<br>`bin/triad` | `what does the triad do`<br>`which commands does the CLI expose`<br>`how is zero incremental cost enforced` |
| `scripts/install.ps1` | `bin/triad.ps1`<br>`triad/sync_manager.py` | `how do I install triad on Windows`<br>`where does install put the launchers` |
| `triad/__main__.py` | `triad/triad_engine.py` | `what runs on python -m triad`<br>`where is main defined` |
| `triad/agent/cli.py` | `triad/agent/runtime.py`<br>`bin/tr.cmd` | `how do I start the agent REPL`<br>`what does a single-shot run do` |
| `triad/cli/__init__.py` | `triad/triad_engine.py` | `which command modules exist` |
| `triad/cli/doctor.py` | `triad/circuit.py`<br>`triad/nous_bridge.py`<br>`scripts/verify.ps1` | `what does triad doctor check`<br>`how do I see projected cost`<br>`which advisors are unhealthy` |
| `triad/cli/gate.py` | `triad/notifier.py`<br>`triad/competition.py` | `what does the ground-truth gate verify`<br>`when is a phone notified`<br>`what blocks a commit` |
| `triad/cli/hook.py` | `triad/worktree.py`<br>`triad/cli/mesh.py` | `how do I install the pre-commit hook`<br>`what does the hook run`<br>`how does self-healing apply a fix` |
| `triad/cli/mesh.py` | `triad/server.py`<br>`AGENTS.md` | `how do I check mesh health`<br>`which MCP servers are coordinated` |
| `triad/cli/review.py` | `triad/intent_engine.py`<br>`triad/competition.py` | `what review modes exist`<br>`how do I consult an advisor from the shell`<br>`what does triage decide` |
| `triad/cli/sync.py` | `triad/sync_manager.py` | `what does triad sync install`<br>`how do I keep the live install from drifting` |
| `triad/prw.py` | `triad/prompt_rewriter.py` | `what does prw do`<br>`how do I expand a rough prompt from the shell` |
| `triad/triad_engine.py` | `triad/advisor_manager.py`<br>`triad/intent_engine.py`<br>`bin/triad` | `where is the command surface defined`<br>`how does review dispatch to advisors`<br>`what does the engine do with a gate result` |
