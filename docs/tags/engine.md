# Tag: `engine`

[← index](../REPO_TAGS.md) · 11 files

| File | Links | Queries |
| --- | --- | --- |
| `bin/triad` | `triad/triad_engine.py`<br>`triad/paths.py` | `how does the sh launcher find python`<br>`where does it look for the repo root` |
| `bin/triad.cmd` | `bin/triad.ps1`<br>`bin/triad` | `how does the batch launcher find the engine`<br>`what happens if TRIAD_ROOT is unset` |
| `bin/triad.ps1` | `triad/triad_engine.py`<br>`triad/paths.py` | `how does the powershell launcher resolve the root`<br>`what is the search order` |
| `docs/ARCHITECTURE.md` | `triad/triad_engine.py`<br>`triad/server.py`<br>`docs/BLUEPRINT.md` | `how do the advisors talk to each other`<br>`what are the invariant rules`<br>`how is a prompt classified` |
| `docs/TRIAD_UPGRADE_SPEC.md` | `docs/TRIAD_V34_UNIFICATION_SPEC.md`<br>`triad/cli/review.py` | `what does v3.4 change about reviews`<br>`how much are tokens meant to drop`<br>`what is the phase order` |
| `docs/TRIAD_V34_UNIFICATION_SPEC.md` | `docs/TRIAD_UPGRADE_SPEC.md`<br>`scripts/triad_unify_audit.py`<br>`docs/TRIAD_V34_MERGE_MAP.md` | `which spec wins when the two disagree`<br>`what evidence backs the plan`<br>`how do the two trees get unified` |
| `README.md` | `triad/triad_engine.py`<br>`docs/ARCHITECTURE.md`<br>`bin/triad` | `what does the triad do`<br>`which commands does the CLI expose`<br>`how is zero incremental cost enforced` |
| `triad/__init__.py` | `triad/triad_engine.py`<br>`pyproject.toml` | `what version is the package`<br>`what does importing triad expose` |
| `triad/__main__.py` | `triad/triad_engine.py` | `what runs on python -m triad`<br>`where is main defined` |
| `triad/cli/__init__.py` | `triad/triad_engine.py` | `which command modules exist` |
| `triad/triad_engine.py` | `triad/advisor_manager.py`<br>`triad/intent_engine.py`<br>`bin/triad` | `where is the command surface defined`<br>`how does review dispatch to advisors`<br>`what does the engine do with a gate result` |
