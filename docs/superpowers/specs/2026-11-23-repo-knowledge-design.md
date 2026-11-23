# Repository knowledge, 2026-11-23
**Tags:** tooling, local-llm, ops-runbook
**Links:** triad/repo_index.py, scripts/setup-repo-knowledge.ps1, docs/REPO_KNOWLEDGE.md
**Queries:** "how do repos stay tagged and embedded as I edit"

Owner request: configure a complete create/update/delete indexing process, inspect existing tools, and evaluate Making Minds. Standing autonomous-execution instructions authorize implementation without another design approval round.

## Approach
Reuse this repository's Tags/Links/Queries convention, existing nomic-embed-text GGUF and llama.cpp localhost:8081. Python standard-library SQLite FTS5 plus stored vectors provides per-checkout hybrid retrieval; no API billing, new database daemon or model download. Install pinned Cartograph 1.3.0 separately for static dependency navigation. Mem0 remains curated decisions/preferences; Hermes Mnemosyne remains Hermes history. Neither receives raw repository dumps.

Alternatives: Miyo and Pieces are installed but offline and do not currently supply a verified code lifecycle index. Making Minds mnemos is a parked preview with failed release evaluation, so do not deploy its experimental enrichment. Cartograph complements embeddings; its static mode itself is not vector search.

## Lifecycle and boundaries
Explicitly register repos; each resolved checkout gets its own SQLite database outside git. Index eligible git-visible source/docs (including new unignored files), skip generated/dependency/credential files and symlinks, reject recognizable secrets before storage. Preserve header tags/links/queries, relative path, language, line spans, symbol hints and content hash. Use Python AST boundaries where possible and bounded line chunks elsewhere. Tags remain sidecar metadata; do not rewrite every source file.

Sync replaces changed file chunks transactionally, removes deleted/excluded entries, embeds only pending chunks in bounded batches, and reports pending on failure. A changed provider/model invalidates all stored vectors. Serialize writers using SQLite transaction locks. Queries combine FTS and cosine ranks, check live source hashes, and exclude stale/deleted content. An empty/unindexed repo is explicit, never proof of absence. Poll registered repos every 15 seconds and recover at logon with a hidden scheduled task. Agent completion requires an explicit successful sync/status check. Content and vectors stay on loopback/disk.

## Acceptance
Regression coverage: incremental no-op/edit/rename/delete; repo isolation; secret/symlink/ignore filters; embedding failure/retry; provider/model change; corrupt vectors; stale-read suppression. Live real-code queries and create/edit/delete smoke test must pass with actual nomic. Watcher must demonstrate fresh indexing without an explicit sync; scheduled task and status must be checked.
