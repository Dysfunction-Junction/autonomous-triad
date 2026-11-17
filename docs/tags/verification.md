# Tag: `verification`

[← index](../REPO_TAGS.md) · 24 files

| File | Links | Queries |
| --- | --- | --- |
| `.github/workflows/ci.yml` | `pyproject.toml`<br>`scripts/repo-tags.mjs` | `what does CI run on a pull request`<br>`is the tag gate enforced in CI` |
| `docs/TRIAD_UPGRADE_SPEC.md` | `docs/TRIAD_V34_UNIFICATION_SPEC.md`<br>`triad/cli/review.py` | `what does v3.4 change about reviews`<br>`how much are tokens meant to drop`<br>`what is the phase order` |
| `docs/TRIAD_V34_MERGE_MAP.md` | `scripts/triad_unify_audit.py`<br>`docs/TRIAD_V34_UNIFICATION_SPEC.md` | `which files diverge between triad and packages/triad`<br>`how is this file regenerated` |
| `docs/TRIAD_V34_UNIFICATION_SPEC.md` | `docs/TRIAD_UPGRADE_SPEC.md`<br>`scripts/triad_unify_audit.py`<br>`docs/TRIAD_V34_MERGE_MAP.md` | `which spec wins when the two disagree`<br>`what evidence backs the plan`<br>`how do the two trees get unified` |
| `scripts/repo-tags.mjs` | `docs/TAG_VOCABULARY.md`<br>`docs/REPO_TAGS.md`<br>`.github/workflows/ci.yml` | `how is the tag index generated`<br>`what does the audit reject`<br>`why is a link reported missing` |
| `scripts/triad_unify_audit.py` | `docs/TRIAD_V34_MERGE_MAP.md`<br>`triad/sync_manager.py` | `does the vendored copy match this tree`<br>`what drifts between triad and packages/triad` |
| `scripts/verify.ps1` | `scripts/install.ps1`<br>`triad/cli/doctor.py` | `how do I check the install is healthy`<br>`what does verify run` |
| `triad/bench/docker_harness.py` | `triad/bench/swebench_runner.py`<br>`scripts/prepare_bench_env.py` | `how is a repo-native test run in docker`<br>`what is the cache key`<br>`which mounts are allowed` |
| `triad/bench/run_bench.py` | `triad/bench/swebench_runner.py`<br>`triad/triad_engine.py` | `how do I run the benchmark`<br>`what counts as a pass`<br>`how is cost reported` |
| `triad/bench/swebench_runner.py` | `triad/bench/docker_harness.py`<br>`triad/bench/swebench_instances.json` | `how is a SWE-bench instance checked out`<br>`which instances are verified` |
| `triad/cli/gate.py` | `triad/notifier.py`<br>`triad/competition.py` | `what does the ground-truth gate verify`<br>`when is a phone notified`<br>`what blocks a commit` |
| `triad/cli/hook.py` | `triad/worktree.py`<br>`triad/cli/mesh.py` | `how do I install the pre-commit hook`<br>`what does the hook run`<br>`how does self-healing apply a fix` |
| `triad/docker_runner.py` | `triad/morphogenetic.py`<br>`triad/bench/docker_harness.py` | `how is a test run inside a container`<br>`what limits does the container get` |
| `triad/morphogenetic.py` | `triad/docker_runner.py`<br>`triad/worktree.py` | `what does the morphogenetic engine rewrite`<br>`what gates guard a self-edit`<br>`how is a reproduction test required` |
| `triad/patching.py` | `triad/worktree.py`<br>`triad/triad_engine.py` | `how is a patch applied and rolled back`<br>`what is a tree snapshot`<br>`how is the working tree fingerprinted` |
| `triad/patching.py` | `triad/worktree.py`<br>`triad/triad_engine.py` | `how is a patch applied and rolled back`<br>`what is a tree snapshot`<br>`how is the working tree fingerprinted` |
| `triad/patching.py` | `triad/worktree.py`<br>`triad/triad_engine.py` | `how is a patch applied and rolled back`<br>`what is a tree snapshot`<br>`how is the working tree fingerprinted` |
| `triad/tests/__init__.py` | `pyproject.toml` | `how is the test suite run` |
| `triad/tests/test_docker_harness.py` | `triad/bench/docker_harness.py` | `how is the harness cache key built`<br>`does this test start docker` |
| `triad/tests/test_docker_runner.py` | `triad/docker_runner.py` | `how is the container-backed runner tested`<br>`what mounts are asserted` |
| `triad/tests/test_hook.py` | `triad/cli/hook.py`<br>`triad/worktree.py` | `how is the pre-commit hook tested`<br>`does the self-healing applicator close the loop` |
| `triad/tests/test_morphogenetic_gates.py` | `triad/morphogenetic.py`<br>`triad/docker_runner.py` | `is the engine flag default off`<br>`what is the diff-size cap`<br>`is a reproduction test required` |
| `triad/triad_engine.py` | `triad/advisor_manager.py`<br>`triad/intent_engine.py`<br>`bin/triad` | `where is the command surface defined`<br>`how does review dispatch to advisors`<br>`what does the engine do with a gate result` |
| `triad/worktree.py` | `triad/patching.py`<br>`triad/cli/hook.py` | `how is an ephemeral worktree created`<br>`who cleans it up`<br>`why isolate rather than edit in place` |
