# Tag: `tooling`

[← index](../REPO_TAGS.md) · 18 files

| File | Links | Queries |
| --- | --- | --- |
| `docs/2026-11-23_REPO_KNOWLEDGE_RESEARCH.md` | `docs/REPO_KNOWLEDGE.md`<br>`scripts/repo-tags.mjs` | `why did we choose this repository indexing stack` |
| `docs/HERMES_HANDOFF_2026-11-23_REPO_KNOWLEDGE.md` | `docs/REPO_KNOWLEDGE.md`<br>`docs/2026-11-23_REPO_KNOWLEDGE_RESEARCH.md`<br>`triad/repo_index.py` | `what is running for automatic repository indexing` |
| `docs/REPO_KNOWLEDGE.md` | `triad/repo_index.py`<br>`scripts/setup-repo-knowledge.ps1`<br>`docs/2026-11-23_REPO_KNOWLEDGE_RESEARCH.md` | `how do I search code by meaning`<br>`how are tags and embeddings updated automatically` |
| `docs/superpowers/specs/2026-11-23-repo-knowledge-design.md` | `triad/repo_index.py`<br>`scripts/setup-repo-knowledge.ps1`<br>`docs/REPO_KNOWLEDGE.md` | `how do repos stay tagged and embedded as I edit` |
| `scripts/download_swebench.py` | `triad/bench/swebench_instances.json`<br>`triad/bench/swebench_runner.py` | `how do I refresh the SWE-bench instance list`<br>`where does the benchmark data come from` |
| `scripts/generate_cases_v2.py` | `scripts/generate_cases.py`<br>`triad/bench/cases/` | `what makes a hardened case`<br>`which negative cases exist` |
| `scripts/generate_cases.py` | `scripts/generate_cases_v2.py`<br>`triad/bench/cases_v1/` | `how were the v1 bench cases generated`<br>`why are there two case generators` |
| `scripts/install.ps1` | `bin/triad.ps1`<br>`triad/sync_manager.py` | `how do I install triad on Windows`<br>`where does install put the launchers` |
| `scripts/prepare_bench_env.py` | `triad/bench/docker_harness.py`<br>`triad/bench/swebench_runner.py` | `how is the benchmark environment pinned`<br>`which instances are in the slice` |
| `scripts/repo-tags.mjs` | `docs/TAG_VOCABULARY.md`<br>`docs/REPO_TAGS.md`<br>`.github/workflows/ci.yml` | `how is the tag index generated`<br>`what does the audit reject`<br>`why is a link reported missing` |
| `scripts/setup-repo-knowledge.ps1` | `scripts/watch-repo-knowledge.ps1`<br>`docs/REPO_KNOWLEDGE.md` | `how do I install automatic local repository indexing` |
| `scripts/start-repo-embedding.ps1` | `scripts/watch-repo-knowledge.ps1`<br>`docs/REPO_KNOWLEDGE.md` | `how is the local embedding runtime started` |
| `scripts/triad_unify_audit.py` | `docs/TRIAD_V34_MERGE_MAP.md`<br>`triad/sync_manager.py` | `does the vendored copy match this tree`<br>`what drifts between triad and packages/triad` |
| `scripts/verify.ps1` | `scripts/install.ps1`<br>`triad/cli/doctor.py` | `how do I check the install is healthy`<br>`what does verify run` |
| `scripts/watch-repo-knowledge.ps1` | `triad/repo_index.py`<br>`scripts/start-repo-embedding.ps1` | `what runs automatic repository indexing at logon` |
| `triad/bench/__init__.py` | `triad/bench/run_bench.py` | `what is in the benchmark package` |
| `triad/repo_index.py` | `docs/REPO_KNOWLEDGE.md`<br>`scripts/setup-repo-knowledge.ps1` | `how do repository edits update local embeddings`<br>`how do I search one repo` |
| `triad/tests/test_repo_index.py` | `triad/repo_index.py` | `what verifies incremental repository indexing` |
