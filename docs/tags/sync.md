# Tag: `sync`

[← index](../REPO_TAGS.md) · 9 files

| File | Links | Queries |
| --- | --- | --- |
| `AGENTS.md` | `README.md`<br>`docs/ARCHITECTURE.md`<br>`triad/advisors.json` | `which checkout is canonical for triad`<br>`how does packages/triad relate to this repo`<br>`which port does triad listen on` |
| `docs/TRIAD_V34_MERGE_MAP.md` | `scripts/triad_unify_audit.py`<br>`docs/TRIAD_V34_UNIFICATION_SPEC.md` | `which files diverge between triad and packages/triad`<br>`how is this file regenerated` |
| `docs/TRIAD_V34_UNIFICATION_SPEC.md` | `docs/TRIAD_UPGRADE_SPEC.md`<br>`scripts/triad_unify_audit.py`<br>`docs/TRIAD_V34_MERGE_MAP.md` | `which spec wins when the two disagree`<br>`what evidence backs the plan`<br>`how do the two trees get unified` |
| `HERMES_HANDOFF_2026-10-03.md` | `triad/paths.py`<br>`docs/ARCHITECTURE.md` | `what did the packaging and ctime merge change`<br>`was the suite green when it landed` |
| `scripts/triad_unify_audit.py` | `docs/TRIAD_V34_MERGE_MAP.md`<br>`triad/sync_manager.py` | `does the vendored copy match this tree`<br>`what drifts between triad and packages/triad` |
| `triad/cli/sync.py` | `triad/sync_manager.py` | `what does triad sync install`<br>`how do I keep the live install from drifting` |
| `triad/paths.py` | `triad/sync_manager.py`<br>`AGENTS.md` | `where does triad look for its install`<br>`how is the repo root resolved`<br>`where does ~/.agents come from` |
| `triad/sync_manager.py` | `triad/paths.py`<br>`triad/cli/sync.py` | `what does a full sync install`<br>`where do junctions point`<br>`how are hooks installed across repos` |
| `triad/tests/test_sync_manager.py` | `triad/sync_manager.py` | `what does a sync produce`<br>`how are custom advisors preserved` |
