# Repository knowledge handoff, 2026-11-23
**Tags:** tooling, local-llm, ops-runbook
**Links:** docs/REPO_KNOWLEDGE.md, docs/2026-11-23_REPO_KNOWLEDGE_RESEARCH.md, triad/repo_index.py
**Queries:** "what is running for automatic repository indexing"

## Delivered
Shared repo-knowledge CLI, per-checkout SQLite/FTS/vector lifecycle index, loopback
nomic embeddings, existing tag/links/query headers plus deterministic metadata,
and pinned Cartograph 1.3.0 for static dependency context. Agent start/end workflow
is installed in shared AGENTS.md and this repo's AGENTS.md.

Owner-selected scope: Foundry canonical checkout (origin foundry-work), Autonomous
Triad, Sovereign Exocortex, Bear House Classic. Four isolated caches; no raw code
is forwarded to Mem0, Hermes history, or the Exocortex world model.

## Runtime
RepoKnowledgeIndexer: hidden Python worker at logon, scans every 15 seconds after
a pass, prioritizes new edits, skips busy writers.
RepoKnowledgeBackfill: hidden round-robin historical vector drain, resumes at logon,
exits when all registered repos have zero pending. Both use the existing nomic
GGUF and localhost:8081; no model download or paid fallback.

Machine-specific config, SQLite databases, logs and verification receipts live
under ~/.local/share/repo-knowledge/. Wrapper commands live under ~/.local/bin/.
See the runbook for status/search/sync and stopping both tasks.

## Verification
- Initial unchanged Triad suite: 649 passed, 12 skipped, 90 subtests.
- Focused lifecycle/reliability tests: 28 passed before final backfill-controller coverage.
- Real automatic create/edit/rename/delete smoke test passed, including fresh=true
  and pending=0 after every phase; observed phase delays 12.6–60.24 seconds after
  initial registration under CPU/backfill contention.
- Cartograph static smoke: version1.3.0; 160 files / 161 dependency edges.
- New Python code passes ruff, medium/high Bandit and compilation.
- Full-repo ruff has 142 preexisting errors in unchanged files (including metrics.py);
  these were not silently repaired or claimed green.
- Required Triad review attempted; all configured routes failed. Native fresh reviewer
  found retry starvation and long write locks. Both were reproduced with failing
  regressions, fixed, and the reviewer confirmed no remaining defect in those fixes.
- Final full suite: 678 passed, 12 skipped, 90 subtests (256.02 seconds).
- 29 index/backfill regression cases included in that full suite.
- Triad tag index check and audit: current, 0 errors, 0 warnings (breadth notices informational).
- Scheduled workers use pythonw.exe directly so background operation creates no console.
- Final push receipts are recorded in the session completion message.

## Remaining background work
Historical embeddings are NOT complete. Source metadata/keyword retrieval is
already populated; use per-repo status pending counts to inspect vector progress.
The tasks continue automatically without keeping this chat open.

## Important boundaries
No Exocortex daemon restart. No Foundry/Bear House source edits. Existing untracked
CLAUDE.md files and mobile LivingBrain edits were left alone. Exocortex main has an
unrelated local commit and is behind origin; do not push that history for this task.


## Publication receipts
Implementation pushed to Triad master as 0db760a; formatting/final-plan follow-up
retains identical executable behavior (29 focused cases pass after normalization).
Exocortex docs pushed as a clean fast-forward to remote main, adefa2b, containing
only the six documentation/tag-index files. The existing push secret guard passed
the one-commit range; the failed new-branch attempt scanned old history and did not
publish it. Local canonical Exocortex main remains divergent with its preexisting
app work intact. Decision ledger: 5fae7e3d06e5.
