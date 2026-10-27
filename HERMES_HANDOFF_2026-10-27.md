# Hermes Handoff: Autonomous Triad Agent & RouteLLM Integration (2026-10-27)

## Milestone Achieved
Implemented the autonomous zero-cost terminal agent (`triad agent` / `triad-agent`), migrated local inference completely from Ollama to `llama-server.exe` (:8080), integrated LMSYS RouteLLM difficulty classification with adaptive thresholding, and obtained full Advisory Council (Claude 3.7 Sonnet) pre-commit signoff.

---

## Deliverables & Architecture

1. **Local Inference Layer (`llama-server.exe` on port 8080):**
   - Dismantled Ollama: stopped running process, freed port 11434.
   - Preserved and hardlinked GGUF models into `C:\Users\micha\AppData\Local\llama.cpp\models\`:
     - `qwen2.5-coder-7b.gguf` (4.68 GB)
     - `qwen3-4b.gguf` (2.50 GB)
     - `qwen3-1.7b.gguf` (1.35 GB)
     - `nomic-embed-text.gguf` (274 MB)
   - Updated [config.yaml](file:///C:/Users/micha/AppData/Local/hermes/config.yaml) in Hermes Agent to point to `http://127.0.0.1:8080/v1`.
   - Updated [advisors.json](file:///C:/Users/micha/projects/autonomous-triad/triad/advisors.json) in Autonomous Triad to route local queries to `llama-server` on port 8080.

2. **RouteLLM Dynamic Routing Engine (`triad/agent/router.py`):**
   - Incorporates LMSYS RouteLLM (Ong et al., 2024) matrix factorization & syntactic complexity scoring.
   - Evaluates code density, stack traces, and multi-file refactoring patterns to score difficulty $P(\text{Strong Model}) \in [0.0, 1.0]$.
   - Dynamically shifts threshold $c$ when primary quota utilization $\ge 80\%$ or during circuit-break cooldowns to shed load to free/local compute.

3. **Autonomous Agent Runtime & Tools (`triad/agent/runtime.py`, `tools.py`):**
   - Interactive REPL and print mode (`-p`) with conversation resumption (`-c`).
   - Workspace tools: `read_file`, `write_file`, `edit_file`, `list_dir`, `search_code`, `run_command`.
   - Workspace containment enforced: blocks directory escapes and denies access to secret credentials (`.env`, `auth.json`, `*.pem`, `*.key`).
   - Strict editing: single occurrence matching, binary decode protection, and newline preservation.
   - Permission model: read-only tools auto-approved; destructive/shell tools prompt for user approval unless `--auto / -y`.

4. **Rolling Window Usage Tracker (`triad/agent/tracker.py`):**
   - Atomic disk persistence (`~/.triad/usage_ledger.json`) tracking requests in rolling 5-hour windows.
   - Soft-limit circuit breakers with automated cooling windows.

5. **CLI Launchers & Entrypoints:**
   - `triad agent [options]`
   - `triad-agent [options]`
   - Synchronized to `C:\Users\micha\.local\bin\`.

---

## Verification
- Unit test suite: `pytest triad/tests/test_agent.py` passed 4/4 in 1.19s.
- Live CLI verification: `triad agent -p "Reply in one word: operational" --local` succeeded.
- Council review: Claude 3.7 Sonnet pre-commit gate review completed; all blockers resolved.
- Remote synchronization: Master branch committed (`e1f2479`) and pushed to `origin/master`.
