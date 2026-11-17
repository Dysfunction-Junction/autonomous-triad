# Tag: `docker`

[← index](../REPO_TAGS.md) · 7 files

| File | Links | Queries |
| --- | --- | --- |
| `scripts/prepare_bench_env.py` | `triad/bench/docker_harness.py`<br>`triad/bench/swebench_runner.py` | `how is the benchmark environment pinned`<br>`which instances are in the slice` |
| `triad/bench/docker_harness.py` | `triad/bench/swebench_runner.py`<br>`scripts/prepare_bench_env.py` | `how is a repo-native test run in docker`<br>`what is the cache key`<br>`which mounts are allowed` |
| `triad/bench/swebench_runner.py` | `triad/bench/docker_harness.py`<br>`triad/bench/swebench_instances.json` | `how is a SWE-bench instance checked out`<br>`which instances are verified` |
| `triad/docker_runner.py` | `triad/morphogenetic.py`<br>`triad/bench/docker_harness.py` | `how is a test run inside a container`<br>`what limits does the container get` |
| `triad/tests/test_docker_harness.py` | `triad/bench/docker_harness.py` | `how is the harness cache key built`<br>`does this test start docker` |
| `triad/tests/test_docker_runner.py` | `triad/docker_runner.py` | `how is the container-backed runner tested`<br>`what mounts are asserted` |
| `triad/tests/test_morphogenetic_gates.py` | `triad/morphogenetic.py`<br>`triad/docker_runner.py` | `is the engine flag default off`<br>`what is the diff-size cap`<br>`is a reproduction test required` |
