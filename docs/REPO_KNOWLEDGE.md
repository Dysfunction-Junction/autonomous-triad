# Repository knowledge
**Tags:** tooling, local-llm, ops-runbook
**Links:** triad/repo_index.py, scripts/setup-repo-knowledge.ps1, docs/2026-11-23_REPO_KNOWLEDGE_RESEARCH.md
**Queries:** "how do I search code by meaning", "how are tags and embeddings updated automatically"

This pipeline indexes eligible source and documentation on creation/edit/deletion.
Each checkout has a separate SQLite database outside Git. No raw repo content enters
Mem0, Hermes history, the Exocortex world model, or a paid API.

## Agent workflow

Run from the repository being changed. Use the full command path when PATH is stale:

```powershell
& "$env:USERPROFILE\.local\bin\repo-knowledge.cmd" register --repo .
& "$env:USERPROFILE\.local\bin\repo-knowledge.cmd" sync --repo .
& "$env:USERPROFILE\.local\bin\repo-knowledge.cmd" search --repo . --query "how are advisor failures routed"
# After changes:
& "$env:USERPROFILE\.local\bin\repo-knowledge.cmd" sync --repo .
& "$env:USERPROFILE\.local\bin\repo-knowledge.cmd" status --repo .
```

Read the cited current source before editing. Search output contains path, line span,
hash, tags, symbol hints and retrieval mode. Search is an aid, never proof all
references were found; retain rg and language tools for exhaustive changes.

Sync commits progress in batches of 64 chunks and exits 0 only with no pending embeddings. Status exits 0 only when the eligible
Git-visible tree is fresh and no embeddings are pending. Exit 2 means work remains;
exit 1 means the operation failed. An initial empty index has last_sync=null.
A query can fall back to keyword mode when embeddings are unavailable; it does not
pretend that fallback is semantic retrieval.

## Setup and automatic updates

```powershell
# Existing Python 3.10+, Git and SQLite FTS5 are required.
# Uses existing %LOCALAPPDATA%\llama.cpp\models\nomic-embed-text.gguf.
.\scripts\setup-repo-knowledge.ps1 -Repos @("C:\path\to\repo")
```

Setup installs wrappers in ~/.local/bin, registers explicit repos in
~/.local/share/repo-knowledge/config.json, and creates hidden, limited-permission
RepoKnowledgeIndexer and RepoKnowledgeBackfill logon tasks. The watcher starts immediately and scans registered repos
sequentially every 15 seconds after each pass. Large initial backfills take longer:
each pass embeds up to 4 chunks per repo, prioritizing new edits over historical backlog. The separate backfill worker drains historical content in round-robin batches
and exits when all registered repos have zero pending embeddings; it resumes at
logon if interrupted. Explicit sync drains the chosen repo immediately;
--max-chunks 128 allows bounded batches.

The watcher task starts the already-installed embedding role on 127.0.0.1:8081; it neither
downloads models nor restarts the Exocortex daemon. Recognizable secret assignments,
private keys, credentials, ignored untracked files, generated output, symlinks,
junctions, evidence/fixture directories, files over 1 MB and non-UTF-8 data are
excluded. This is conservative filtering, not a guarantee of recognizing every secret.
Do not register repos that contain sensitive material outside these protections.

Content tags come from existing Tags/Links/Queries headers plus deterministic language
and directory metadata. Original source is not rewritten. Python top-level symbols
use AST boundaries; other languages use bounded line chunks with symbol hints.
Embeddings use nomic search_document/search_query prefixes. Small chunks fit the
existing 2048-token local runtime; unusually token-dense files may remain pending.

Changed/deleted chunks are replaced/removed. Queries recheck current source hashes
and suppress stale/secret/deleted content before returning results. Model or endpoint
changes invalidate vectors at the next sync; do not replace model weights behind the
same model alias without changing --model or rebuilding the disposable index.
Indexes are derived caches, not the source of truth or backups.

## Inspection and recovery

- Task: Get-ScheduledTask -TaskName RepoKnowledgeIndexer
- Logs: ~/.local/share/repo-knowledge/watch.log and backfill.log (2 MB each, two backups)
- Per-repo watcher receipt: <database-stem>.watch.json next to its SQLite database
- Config: ~/.local/share/repo-knowledge/config.json
- Offline embeddings: index keeps pending work, retries next pass; search falls back
  to keywords. Restore the runtime with scripts/start-repo-embedding.ps1.
- Stop automatic work: Stop-ScheduledTask -TaskName RepoKnowledgeIndexer, then
  Disable-ScheduledTask -TaskName RepoKnowledgeIndexer. Also stop/disable RepoKnowledgeBackfill to pause historical work. No content is deleted.

## Cartograph companion

Pinned package: @anthony-maio/cartograph@1.3.0, isolated under
~/.local/share/repo-knowledge/cartograph. Use only static mode for this workflow:

```powershell
& "$env:USERPROFILE\.local\bin\repo-map.cmd" analyze . --static
& "$env:USERPROFILE\.local\bin\repo-map.cmd" context . --task "trace advisor failover" --static --json
```

Cartograph supplies dependency maps and focused source selection. Its static
workflow does not generate vector embeddings. Installing a package alone does not
register its MCP server with every host; these verified CLI wrappers are the shared
integration here.



## Initial watch scope (owner-selected, 2026-11-23)

- Foundry: canonical Foundry checkout, origin Papa-Bear4216/foundry-work.
- Autonomous Triad.
- Sovereign Exocortex.
- Bear House Classic (isolated index; no world-model integration).

Machine-specific absolute paths live only in the local config. Foundry worktrees
are separate checkouts and are not implicitly indexed with the canonical root.

The watcher skips busy repos promptly rather than waiting behind another writer.
Embedding HTTP calls hold no SQLite write lock. Short chunk leases prevent duplicate
workers from publishing stale vectors; failed chunks rotate behind unattempted work.
Initial backfills can take hours on this CPU-only host; current source and metadata
are searchable before vector coverage is complete. Pending counts are authoritative.
