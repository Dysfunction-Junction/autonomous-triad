# Tag: `bench`

[← index](../REPO_TAGS.md) · 10 files

| File | Links | Queries |
| --- | --- | --- |
| `HERMES_HANDOFF_2026-10-02.md` | `triad/circuit.py`<br>`docs/ARCHITECTURE.md` | `what shipped in the circuit breaker and bench env work`<br>`which branch landed it` |
| `scripts/download_swebench.py` | `triad/bench/swebench_instances.json`<br>`triad/bench/swebench_runner.py` | `how do I refresh the SWE-bench instance list`<br>`where does the benchmark data come from` |
| `scripts/generate_cases_v2.py` | `scripts/generate_cases.py`<br>`triad/bench/cases/` | `what makes a hardened case`<br>`which negative cases exist` |
| `scripts/generate_cases.py` | `scripts/generate_cases_v2.py`<br>`triad/bench/cases_v1/` | `how were the v1 bench cases generated`<br>`why are there two case generators` |
| `scripts/prepare_bench_env.py` | `triad/bench/docker_harness.py`<br>`triad/bench/swebench_runner.py` | `how is the benchmark environment pinned`<br>`which instances are in the slice` |
| `triad/bench/__init__.py` | `triad/bench/run_bench.py` | `what is in the benchmark package` |
| `triad/bench/docker_harness.py` | `triad/bench/swebench_runner.py`<br>`scripts/prepare_bench_env.py` | `how is a repo-native test run in docker`<br>`what is the cache key`<br>`which mounts are allowed` |
| `triad/bench/run_bench.py` | `triad/bench/swebench_runner.py`<br>`triad/triad_engine.py` | `how do I run the benchmark`<br>`what counts as a pass`<br>`how is cost reported` |
| `triad/bench/swebench_runner.py` | `triad/bench/docker_harness.py`<br>`triad/bench/swebench_instances.json` | `how is a SWE-bench instance checked out`<br>`which instances are verified` |
| `triad/tests/test_docker_harness.py` | `triad/bench/docker_harness.py` | `how is the harness cache key built`<br>`does this test start docker` |
