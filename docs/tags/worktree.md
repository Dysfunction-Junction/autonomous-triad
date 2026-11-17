# Tag: `worktree`

[← index](../REPO_TAGS.md) · 6 files

| File | Links | Queries |
| --- | --- | --- |
| `triad/agent/tools.py` | `triad/agent/runtime.py` | `which workspace tools can the agent call`<br>`what does the shell tool refuse to do` |
| `triad/cli/hook.py` | `triad/worktree.py`<br>`triad/cli/mesh.py` | `how do I install the pre-commit hook`<br>`what does the hook run`<br>`how does self-healing apply a fix` |
| `triad/patching.py` | `triad/worktree.py`<br>`triad/triad_engine.py` | `how is a patch applied and rolled back`<br>`what is a tree snapshot`<br>`how is the working tree fingerprinted` |
| `triad/tests/test_hook.py` | `triad/cli/hook.py`<br>`triad/worktree.py` | `how is the pre-commit hook tested`<br>`does the self-healing applicator close the loop` |
| `triad/tests/test_worktree.py` | `triad/worktree.py` | `how is isolation tested`<br>`is cleanup asserted` |
| `triad/worktree.py` | `triad/patching.py`<br>`triad/cli/hook.py` | `how is an ephemeral worktree created`<br>`who cleans it up`<br>`why isolate rather than edit in place` |
