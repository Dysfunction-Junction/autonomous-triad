# Tool inventory and Making Minds assessment, 2026-11-23
**Tags:** tooling, local-llm, ops-runbook
**Links:** docs/REPO_KNOWLEDGE.md, scripts/repo-tags.mjs
**Queries:** "why did we choose this repository indexing stack"

## Verified local inventory
- Node, Python 3.14, Git and SQLite 3.50.4/FTS5 available.
- Existing repo-tags.mjs plus TAG_VOCABULARY.md in Autonomous Triad and Sovereign Exocortex.
- Mem0 CLI query works; preserve it for curated preferences/decisions.
- Existing llama.cpp executable and 274,290,656-byte nomic-embed-text.gguf.
  Embedding endpoint initially offline; existing embedding-role launcher started
  it on 127.0.0.1:8081 and /health returned ok.
- Agent Mesh /health at 39401 returns ok. No repository index found in its source.
- Ollama 11434 and PiecesOS 39300 refuse connections. Miyo CLI exists but says
  its service is not running; cloud connector also reports disconnected.
- Hermes Mnemosyne is the Hermes history store per shared tool registry.
  Its MCP diagnosis did not complete here; no availability claim.
- Repomix is installed; useful for packing, not a verified lifecycle embedding index.
- Cartograph initially absent; installed 1.3.0 locally with npm install scripts disabled.
  CLI version and static Triad analysis verified: 160 files, 161 dependency edges.

## Reviewed primary sources
- Cartograph: https://making-minds.ai/products/cartograph/
  CLI/MCP/native Hermes integrations; static mode needs no model API key.
  Source: https://github.com/anthony-maio/cartograph (MIT).
- mnemos: https://making-minds.ai/products/mnemos/
  Parked development preview; source candidate not on PyPI because release benchmark
  fails. Automatic enrichment experimental; cited no-answer accuracy 22.73%.
  Do not confuse mnemos with the user's existing Hermes Mnemosyne store.
- Continuity Core: https://making-minds.ai/research/continuity-core/
  Preprint design inspiration for goal-based context selection, not a drop-in indexer.
- Older memory article: https://anthonymaio.substack.com/p/your-agent-has-amnesia
  Useful ideas: ingestion filtering, explicit scopes, current facts, provenance.
  Current product status takes precedence over older install/quality claims.
- Context engineering: https://anthonymaio.substack.com/p/context-is-the-only-lever
  Relevant direction: select task-specific context instead of dumping whole repos.
- Tool catalog: https://making-minds.ai/products/
  pulldown is useful for future web-document ingestion, not needed for a Git index;
  Slipstream handles agent messages, not repository embeddings.

## Decision
Reuse current tags and local nomic runtime; use disposable per-checkout SQLite
indexes for code retrieval. Add Cartograph as a static navigation companion.
No new paid service, heavyweight database daemon, or experimental memory replacement.

