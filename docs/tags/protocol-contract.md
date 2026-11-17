# Tag: `protocol-contract`

[← index](../REPO_TAGS.md) · 11 files

| File | Links | Queries |
| --- | --- | --- |
| `AGENTS.md` | `README.md`<br>`docs/ARCHITECTURE.md`<br>`triad/advisors.json` | `which checkout is canonical for triad`<br>`how does packages/triad relate to this repo`<br>`which port does triad listen on` |
| `docs/ARCHITECTURE.md` | `triad/triad_engine.py`<br>`triad/server.py`<br>`docs/BLUEPRINT.md` | `how do the advisors talk to each other`<br>`what are the invariant rules`<br>`how is a prompt classified` |
| `docs/TRIAD_V34_MERGE_MAP.md` | `scripts/triad_unify_audit.py`<br>`docs/TRIAD_V34_UNIFICATION_SPEC.md` | `which files diverge between triad and packages/triad`<br>`how is this file regenerated` |
| `scripts/repo-tags.mjs` | `docs/TAG_VOCABULARY.md`<br>`docs/REPO_TAGS.md`<br>`.github/workflows/ci.yml` | `how is the tag index generated`<br>`what does the audit reject`<br>`why is a link reported missing` |
| `triad/__init__.py` | `triad/triad_engine.py`<br>`pyproject.toml` | `what version is the package`<br>`what does importing triad expose` |
| `triad/cli/mesh.py` | `triad/server.py`<br>`AGENTS.md` | `how do I check mesh health`<br>`which MCP servers are coordinated` |
| `triad/egress.py` | `triad/advisor_manager.py`<br>`triad/nous_bridge.py` | `what is stripped before a cloud call`<br>`which secrets never leave the machine`<br>`what does the redaction cover` |
| `triad/notifier.py` | `triad/cli/gate.py`<br>`triad/triad_engine.py` | `how does a phone get notified`<br>`what payload does the device receive` |
| `triad/procutil.py` | `triad/advisor_manager.py`<br>`triad/server.py` | `how is a subprocess timed out`<br>`how is a port probed`<br>`what happens when a binary is missing` |
| `triad/server.py` | `triad/triad_engine.py`<br>`triad/intent_engine.py`<br>`AGENTS.md` | `which port does the daemon listen on`<br>`which routes does it expose`<br>`how does a phone or mesh call it` |
| `triad/tests/test_server.py` | `triad/server.py` | `which routes are covered`<br>`how is the daemon started in tests` |
