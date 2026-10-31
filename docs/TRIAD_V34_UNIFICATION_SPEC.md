# Autonomous Triad v3.4: Unification and Upgrade Spec

**Status:** Draft for Opus to finalize. Supersedes the consolidated brief of 2026-10-28. Amends [`TRIAD_UPGRADE_SPEC.md`](TRIAD_UPGRADE_SPEC.md); where the two disagree, this file wins.
**Evidence:** Three audit passes and a live verification pass on the owner's PC on 2026-10-28 (repositories, git history and branches, both CI workflows, running processes, the llama-server API).
**Generated appendix:** [`TRIAD_V34_MERGE_MAP.md`](TRIAD_V34_MERGE_MAP.md) lists every diverged file, every definition that differs, every test ID, and unmerged branch content. Both trees changed during the audit, so regenerate it before each step with `python scripts/triad_unify_audit.py` (§9).

Side names used throughout:

- **A** is `autonomous-triad`, the standalone repository: `master` at `762e2c3`.
- **B** is `sovereign-exocortex/packages/triad`, the copy inside the monorepo: `main` at `ea4a645`.

Line references read `A:123` or `B:123` at those commits.

---

## 1. Outcome

Triad code is authored in one place, A. B's `packages/triad` becomes a byte-identical copy of one pinned A commit, and B's CI checks that by comparing tree hashes. Every feature and security fix that exists in either tree today survives the merge. All 528 test IDs collected across both trees keep running in both CIs. The gateway (:8788), the Triad daemon (:8789), `triad`, and `tr` keep working at every step.

## 2. Decisions

Each decision has a recommended default; Opus confirms or changes it.

| ID | Decision | Recommended default |
|---|---|---|
| D1 | Where Triad is authored | A. B vendors A by pinned commit (§5). |
| D2 | Local advisor identity | Canonical name `llama`, with aliases `ollama` and `local`. Use B's in-process `openai_http` transport. Ollama stays available as a backend override. |
| D3 | Default route for the `tr` agent | Keep local-first for short, routine turns, which is the intent of commit `a978bf1`. Escalate by difficulty score and by context budget (F2). This amends Phase 2.1. |
| D4 | How `tr` is packaged | Versioned Windows launchers only, with no `tr` console script (F5). |
| D5 | Host execution of untrusted bench patches | Not carried over. B's rule stands: candidate tests run in Docker or not at all. |
| D6 | Who runs llama-server on :8080 | B's `apps/daemon/ops/ensure-llama-server.ps1`. Triad adds no launcher of its own. |
| D7 | `origin/base44/setup-b9ffc82c` in A | Archive it. Do not merge before auth step 3 (§7.4), because it adds a configurable bind address. |
| D8 | B commit `46b8a8c` (Docker test workspace permissions) | Carry it into A and verify it in B's informational Docker job. |
| D9 | `projects/sovereign-exocortex-broker` | Delete after the owner confirms. It is fully redundant (§3.4). |
| D10 | Runtime state location | Add `TRIAD_STATE_DIR` before building the Phase 3 cache (§6.3). |

## 3. Verified current state

### 3.1 Repositories and CI

| | A | B |
|---|---|---|
| Remote | `Dysfunction-Junction/autonomous-triad`, public. The local `origin` URL still says `Papa-Bear4216`, and GitHub redirects it. | `Dysfunction-Junction/sovereign-exocortex` |
| Head | `master` 762e2c3, clean, equal to origin | `main` ea4a645, clean |
| Tracked Triad files | 97 | 71 under `packages/triad` |
| CI test step | `uv sync --extra dev --locked`, then `ruff check triad/`, `bandit -r triad/ ... --severity-level medium`, `compileall`, and `pytest triad/tests -n auto --dist=loadfile` (`.github/workflows/ci.yml:30-43`) | `pnpm test` runs `python -m unittest discover -s triad/tests` (from `packages/triad/package.json`) with `TRIAD_SKIP_REAL_DOCKER=1`. A separate `docker-isolation` job runs the real-container class with `continue-on-error` (`ci.yml:33-58`). |
| How changes land | Direct pushes to `master` | Squash-merged PRs. For example, branch commit `7591a64` landed as `675f258 (#50)`. |

### 3.2 How the trees differ

- **Shared tracked paths:** 64. Of these, 44 are identical after line-ending normalization and 20 diverge (11 modules, 8 test files, and `pyproject.toml`).
- **Only in B:** `package.json`, `triad/morphogenetic.py`, `triad/docker_runner.py`, and four test files: `test_morphogenetic.py`, `test_morphogenetic_gates.py`, `test_docker_runner.py`, `test_local_llm_backend.py`.
- **Only in A (Triad code and packaging):** six files under `triad/agent/`, `triad/sync_manager.py`, `test_agent.py`, `test_sync_manager.py`, the `bin/triad*` launchers, and `uv.lock`, plus docs and scripts.
- **Collected tests (pytest):** A has 414 and B has 478. 364 are shared, 50 are A-only, and 114 are B-only, for a union of 528. Twelve same-named definitions in test files have different bodies (§6.3).
- **Tests B's runner can't see:** `test_agent.py` has 7 module-level pytest functions. B's `unittest discover` would not collect them.

### 3.3 Runtime wiring on the PC

- **A's checkout is the production install.** The daemon on :8789 is a child of a `node.exe` process, which fits the gateway launcher: the mesh launch table runs `triad.server` from the `autonomous-triad` checkout. `~/.agents/triad` is a junction to `A/triad`. `triad` and `tr` both execute A's working tree. Merging into A's checked-out `master` therefore deploys on the next process start.
- **B's copy is not used at runtime.** Nothing under `sovereign-exocortex/apps` references `packages/triad` or `morphogenetic`.
- **What `tr` actually is.** `tr` is `~/.local/bin/tr.cmd`, which runs `python <engine> agent %*`. That starts the `triad agent` REPL in `triad/agent/cli.py`.
  - It is not in A's `bin/`. `sync_launchers` only manages `triad.cmd`, `triad.ps1`, and `triad` (`sync_manager.py:455`).
  - The committed `pyproject.toml` does not declare it.
  - The venv's `tr.exe` comes from an entry point, `tr = triad.agent.cli:main`, that was installed on 2026-10-27. No commit on any branch ever declared it.
- **llama-server on :8080.** It serves `qwen3-1.7b.gguf` (alias `qwen3:1.7b`) with a **2048-token context**, on CPU only. Those settings match the triage role in B's sibling `apps/daemon/ops/ensure-llama-server.ps1:17-18` (`--ctx-size 2048 --threads 8`, `--gpu-layers 0`). Ollama on :11434 is not listening.
- **`TRIAD_SERVER_TOKEN` is unset** in the process, user, and machine environments.
  - The gateway sends `Authorization: Bearer` to Triad only when that variable is set (`apps/daemon/src/network.ts:149-150`, `mishmash-launch.ts:111-112`). It passes the variable only to the Triad child (`mishmash-launch.ts:176-177`).
  - Two other clients of :8789 send no token. One is the phone proxy: `pieces-android-shizuku-fix/apps/proxy/src/server.ts:269` and `:305`, both `POST /auto`. The other is Bear House: `api/chat.ts:462` (`POST /auto`) and `api/triad-telemetry.ts:33-34` (`GET /health`, `GET /telemetry`).
- **Advisor overlay files.** Neither `~/.agents/advisors.local.json` nor `~/.agents/triad/advisors.local.json` exists.

### 3.4 Copies and branches

| Location | Finding |
|---|---|
| `projects/autonomous-triad` | A |
| `projects/sovereign-exocortex/packages/triad` | B. It is the most complete copy in the Exocortex repo. |
| `sovereign-exocortex-brain`, `-scan`, `-seed` | Git worktrees of B's repo, on feature branches. They pick up the vendored tree when they next merge `main`. `seed` has two unrelated modified Capacitor gradle files; leave them alone. |
| `projects/sovereign-exocortex-broker` | Has no `.git`. The audit scanned its 282 files outside `node_modules` and caches, and every one already exists as a blob in A's or B's object database. Deleting it loses nothing that git does not already hold. |

Branch content that is not on a default branch. The check measures what share of each commit's added lines appear on the target branch; merge map §5 has the per-commit table.

- **A, `origin/base44/setup-b9ffc82c`** (`7d9cfc7`, a bot commit): 0 of 44 lines are on `master`, so it is unmerged. It adds a bind-address option to `triad/server.py`, `docker-compose.base44.yml`, `.base44/environment.json`, and an `AGENTS.md` section. Decision D7 covers it.
- **A, `origin/claude/dazzling-planck-291g3t`** (11 commits from 2026-09-28 and 09-29): five are fully present on `master`. The rest are partly present because later commits rewrote the same lines (Actions SHA pins, `uv.lock`, test fixes). Treat the branch as superseded after spot-checking `4b1d86e`, `78a6860`, and `50fefdf`.
- **A, `origin/fix/ci-rollback-inode-reuse`** (`ac42338`): the ctime check it adds is on `master` (A:1543-1547). It is merged in substance.
- **B, `origin/fix/docker-isolation-workspace-perms`** (`46b8a8c`): three lines in `test_docker_runner.py` that run `os.chmod(self.ws, 0o777)` in `TestDockerRunnerRealIsolation.setUp`. This change is on neither B `main` nor A. Every other B branch's Triad content is already on B `main`.

## 4. Corrections to earlier findings

These items in the consolidated brief were wrong or missing:

1. **File counts.** "181 identical files" counted untracked caches. The tracked numbers are 44 identical and 20 diverged.
2. **Worktree line numbers.** The brief's ranges (349-350, 422-495, 556-620, 432-548) were line numbers in a diff printout, not in the source. The real B locations:
   - `reject_option_like_ref`: B:165.
   - CRLF-normalized comparison: B:585-594, inside `_check_dependency_graph_compatibility`.
   - `deprovision_worktree_dependencies`: B:820. It raises at B:914 instead of swallowing the failure.
   - `_link_sig`: B:932.
   - `_is_volatile_dir`: B:950.
   - `capture_directory_snapshot`: B:978.
   - `_triad_worktree_root`: B:1045.
   - `_is_managed_worktree_path`: B:1050.
   - `remove_worktree`: B:1075.
   - The worktree-pool `rev-parse` call uses `--verify --end-of-options` (B:1284), not `--`.
3. **A's auth gap is narrower than claimed.**
   - `/action/approve` and `/action/reject` already require a configured token (A:972-974).
   - The gap is the delegate envelope. `/mishmash/delegate` accepts only loopback callers (A:955-958), and `ping` and `classify` need no token.
   - `approve` and `reject` check `if SERVER_TOKEN and not self._is_authorized()` (A:872, A:908). With no token configured, they run the same proposal flow that `/action/*` refuses.
4. **Porting B's delegate check as-is would break the live mesh.** B requires a configured token for every delegate action, including `ping` and `classify` (B test `test_mishmash_delegate_every_action_requires_token`). No token is configured on this PC, so every gateway call to Triad would return 401. §7.4 gives the order that avoids this.
5. **Intents.** MESH exists in both trees. The A-only intents are SYNC, BROWSE, SCRAPE, and REASONING.
6. **The bench recommendation contradicted the brief's own rule.** A configurable host-execution fallback for the bench breaks "zero security regression". B removed host execution of untrusted candidate patches on purpose.
7. **A copier in `sync_manager.py` is the wrong mirroring tool.** It reads a sibling working tree, so it can copy uncommitted or ignored files, and CI cannot reproduce it. §5.3 replaces it with a commit-pinned vendor.
8. **Missed by all three passes.**
   - The `tr` launcher (§3.3).
   - The 2048-token local context.
   - The agent's Tier-1 path, which bypasses MCP stripping, the two-session cap, the circuit breaker, and permission prompts (F1).
   - `test_agent.py` being invisible to B's unittest runner.
   - B landing PRs as squash merges, which rules out `git subtree`.

## 5. Target setup: one source of truth

### 5.1 Ownership

- **A is the only place where Triad is authored.** That covers code, tests, `advisors.json`, launchers, and `package.json`.
- **B's `packages/triad` is a vendored copy** of A's full root tree at one pinned commit. Nobody edits it in place; it changes only through the update script in §5.3.
- **Runtime does not change.** The gateway, the `~/.agents/triad` junction, `triad`, and `tr` keep running A's checkout.

### 5.2 Why vendor by commit

| Option | Verdict |
|---|---|
| NTFS junction in B | Rejected. Linux CI checks out B and needs real files at `packages/triad`. |
| Git submodule | Rejected. Every B worktree, including the ephemeral `triad-gate-*` worktrees that `worktree.py` creates, would need submodule init. CI would need submodule checkout, and pnpm would see an empty workspace package until init. |
| `git subtree --squash` | Rejected. B squash-merges PRs, which flattens the squash and merge commits whose trailers subtree uses to find the previous import. |
| File copier in `sync_manager.py` (from the brief) | Rejected. It copies from a working tree, and CI cannot reproduce the result. |
| pip dependency on A at a pinned SHA | Viable as a later end state. B has no runtime imports of `packages/triad`, but its CI, docs, and agent-queue rows still target that path. |
| **Commit-pinned vendor with a tree-hash check** | **Chosen.** `git read-tree` copies A's root tree object exactly. A lock file outside the vendored directory records the commit and tree, and CI compares one hash. This works with squash merges and needs no new tooling. |

### 5.3 Vendor procedure (B side)

The lock file is `tools/triad.lock.json`. It sits outside `packages/triad`, so it is not part of the compared tree:

```json
{
  "repo": "https://github.com/Dysfunction-Junction/autonomous-triad.git",
  "commit": "<A commit sha>",
  "tree": "<root tree sha of that commit>"
}
```

The update script is `scripts/update-triad.ps1`, with a POSIX twin. Run it on a B branch:

```powershell
param([Parameter(Mandatory)][string]$Commit)
$repo = 'https://github.com/Dysfunction-Junction/autonomous-triad.git'
git fetch $repo $Commit
git rm -r -q packages/triad
git read-tree --prefix=packages/triad/ -u FETCH_HEAD
$tree = git rev-parse 'FETCH_HEAD^{tree}'
@{ repo = $repo; commit = $Commit; tree = $tree } | ConvertTo-Json | Set-Content tools/triad.lock.json -Encoding utf8
git add tools/triad.lock.json packages/triad
git commit -m "chore(triad): vendor autonomous-triad@$Commit"
```

The CI guard is a new first step in B's `check` job. The default shallow checkout is enough:

```yaml
- name: packages/triad matches the pinned autonomous-triad commit
  run: |
    expected=$(python -c "import json;print(json.load(open('tools/triad.lock.json'))['tree'])")
    actual=$(git rev-parse HEAD:packages/triad)
    if [ "$expected" != "$actual" ]; then
      echo "packages/triad was edited in place. Make the change in autonomous-triad, then run scripts/update-triad."
      exit 1
    fi
```

An optional informational step checks that the lock's tree really belongs to the pinned commit, which catches a hand-edited lock:

```yaml
- name: lock tree belongs to the pinned commit
  continue-on-error: true
  run: |
    commit=$(python -c "import json;print(json.load(open('tools/triad.lock.json'))['commit'])")
    git fetch --depth=1 https://github.com/Dysfunction-Junction/autonomous-triad.git "$commit"
    test "$(git rev-parse 'FETCH_HEAD^{tree}')" = "$(git rev-parse HEAD:packages/triad)"
```

If someone edits `packages/triad` in a B PR anyway, CI fails, and nothing is lost. `git diff <lock tree> HEAD:packages/triad` produces a patch to apply in A.

Vendoring A's whole root tree also brings `README.md`, `docs/`, `scripts/`, `bin/`, `AGENTS.md`, `uv.lock`, and a nested `.github/`. GitHub ignores nested workflow folders. The vendored `README.md` also fills a gap: B's `pyproject.toml` already names a readme that `packages/triad` never had.

### 5.4 Governance text to change in the same PRs

- **A's `AGENTS.md`:** say that A is canonical and that `sovereign-exocortex/packages/triad` is a read-only vendor. Agents inside B will read this same file, because it is vendored.
- **B's `AGENTS.md:38-41`:** replace "different trees" with "vendored from autonomous-triad; edit upstream; update with `scripts/update-triad`".
- **B docs that send agents to edit `packages/triad`:** `docs/AGENT_QUEUE.md`, `docs/FINISH_LINE_PLAN_2026-10-28.md`, `docs/REMAINING_WORK.md`, `docs/AGY_HANDOFF.md`, `docs/CODEX_HANDOFF.md`, `docs/SETUP_GUIDE.md`. Point the Triad rows at A.
- **`projects/CLAUDE.md` and `~/AGENTS.md`:** record the vendoring rule in their repository maps.

### 5.5 Local machine

- Keep the `~/.agents/triad` junction.
- Version the `tr` launchers (F5), so `triad sync` maintains them.
- Delete `projects/sovereign-exocortex-broker` after the owner confirms (D9).
- Leave the `-brain`, `-scan`, and `-seed` worktrees alone.

## 6. Schemas

### 6.1 `advisors.json` version 2

| Field | Type | Default | Meaning |
|---|---|---|---|
| `schema_version` (top level) | int | 1 | Set to 2 for this layout. |
| `name` | string | required | Unique lowercase id. Circuit-breaker and telemetry key. |
| `aliases` | string[] | `[]` | Other names accepted by `--engine`, `get_active_advisor`, overlays, and ranking. |
| `display_name` | string | required | Model-agnostic label (Phase 2.3). |
| `role` | `production`, `interactive`, `test` | `production` | Auto failover never uses `test` advisors unless `TRIAD_ALLOW_MOCK=1`, and never dispatches `interactive` advisors. |
| `enabled` | bool | `true` | |
| `priority` | int | required | Lower runs first when no lane strength applies. |
| `transport` | `subprocess`, `openai_http` | `subprocess` | |
| `binary_path`, `fallback_binary`, `execution_flags`, `input_mode` (`stdin` or `arg`), `output_mode` (`stdout` or `file`), `env` | | | Used by `subprocess` advisors. Same meaning as today. |
| `model` | string | | Used by `openai_http` advisors. llama-server answers with whatever model it loaded. |
| `readiness_port` | int or token | none | Tokens: `{port_local_llm}` resolves from `llama_cpp_url()` or the active backend; `{port_ollama}` is kept for compatibility. |
| `timeout` | int seconds | caller's value | Per-advisor ceiling. |
| `context_tokens` | int or `"auto"` | `"auto"` for `openai_http` | Combined budget for prompt and completion. `auto` reads `n_ctx` from llama-server `/props` once per process (F2). |
| `strengths` | map of lane to a number from 0 to 1 | none | Lanes: `architecture`, `coding`, `reasoning`, `judge`, `red_team`, `long_context`, `micro`, `scraping`, `browsing`. A value of 0 excludes the advisor from that lane. If the map is missing, ranking falls back to `priority`. |
| `backend_overrides` | map of backend name to partial advisor | none | Applied when `local_backend()` returns that key. B's `ollama_override` is read as `backend_overrides.ollama`. |
| `dispatch_status`, `registration_date`, `registration_note`, `budget_policy` | strings | | Documentation only (Oz). |

Loader rules:

1. Build the alias map once. Resolve every external name through it: CLI `--engine`, overlay entries, and `TASK_ADVISOR_PRIORITY` until Phase 4 deletes it.
2. Merge overlay advisors by canonical name after alias resolution. An overlay entry named `ollama` then updates `llama` instead of adding a second local advisor.
3. `effective_advisor()` applies `backend_overrides[local_backend()]` before readiness checks, ranking, and execution.
4. An advisor can judge only if it has `role: production` and `strengths.judge > 0`. An advisor with no `strengths` map can judge only if its `transport` is `subprocess`. That keeps the local model out of the judge seat even before Phase 4 lands.
5. Ignore unknown keys. A file with no `schema_version` is version 1, and every rule above still applies to it.

The local advisor entry in full. `claude`, `codex`, `antigravity`, `nous`, `oz`, and `mock` keep their current entries in A, apart from the optional new fields and the Phase 2.3 display names.

```json
{
  "name": "llama",
  "aliases": ["ollama", "local"],
  "display_name": "Local llama.cpp (llama-server)",
  "priority": 5,
  "enabled": true,
  "transport": "openai_http",
  "model": "qwen3:1.7b",
  "readiness_port": "{port_local_llm}",
  "timeout": 90,
  "context_tokens": "auto",
  "strengths": {"architecture": 0.10, "coding": 0.15, "reasoning": 0.10, "judge": 0, "red_team": 0,
                "long_context": 0, "micro": 0.95, "scraping": 0.95, "browsing": 0.95},
  "backend_overrides": {
    "ollama": {
      "transport": "subprocess",
      "display_name": "Ollama Local Advisor (qwen3:1.7b)",
      "binary_path": "{localappdata}/Programs/Ollama/ollama.exe",
      "fallback_binary": "ollama",
      "execution_flags": ["run", "qwen3:1.7b", "--think=false"],
      "input_mode": "stdin",
      "output_mode": "stdout",
      "readiness_port": "{port_ollama}",
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

Strength values for the other advisors come from the Phase 4.1 table unchanged.

### 6.2 Environment variables

| Variable | Status | Meaning |
|---|---|---|
| `LLAMA_CPP_URL` | canonical; also used by the gateway | Base URL of the local llama-server. Must be plain `http` on loopback (`validate_loopback_url`). |
| `TRIAD_PORT_LLAMA_SERVER` | kept | Port for the default URL when `LLAMA_CPP_URL` is unset. Default 8080. `llama_cpp_url()` builds `http://127.0.0.1:<port>` from it. |
| `TRIAD_LOCAL_BACKEND` | new canonical | `llamacpp` (default) or `ollama`. |
| `EXOCORTEX_TRIAD_BACKEND` | compatibility | Read when `TRIAD_LOCAL_BACKEND` is unset. B's README documents it. |
| `TRIAD_PORT_OLLAMA` | compatibility | Port for the Ollama override. Default 11434. |
| `TRIAD_SERVER_TOKEN` | kept | Bearer token for the daemon. Rollout in §7.4. |
| `TRIAD_STATE_DIR` | new | Root for runtime state (§6.3). Default `~/.triad`. |
| `TRIAD_CIRCUIT_PATH` | kept | Overrides the circuit-state file. |
| `TRIAD_MORPHOGENETIC`, `TRIAD_MORPHOGENETIC_MAX_CHANGED_LINES`, `TRIAD_MORPHOGENETIC_SCAN_GATE`, `FORBIDDEN_MUTATION_TOKENS` | kept from B | The engine is off unless `TRIAD_MORPHOGENETIC` is `1`, `true`, `yes`, or `on`. The changed-lines cap defaults to 200, and the scan gate is on by default. |
| `TRIAD_SKIP_REAL_DOCKER` | kept from B | Tells CI to skip the real-container test class. |
| `TRIAD_LLAMA_MODEL`, `TRIAD_LLAMA_MAX_TOKENS`, `TRIAD_LLAMA_TIMEOUT` | dropped | They existed only for the `llama_bridge.py` design this spec removes. `model` and `timeout` live in `advisors.json`. |

All other existing `TRIAD_*` variables are unchanged.

### 6.3 Runtime state layout

Today runtime state is spread over several places:

- `~/.agents/triad/logs/` holds the circuit state (`circuit.py:113-117`), `advisor_calls.jsonl`, and `council_sessions.jsonl` (`competition.py:26-36`).
- `~/.agents/triad/patches/` holds server patches (`server.py:81`).
- `~/.triad/` holds the agent's sessions and usage ledger.
- `%TEMP%/triad_session_slots/` holds the session limiter's lock files.

The first two resolve inside A's working tree, through the junction. The cache proposed in Phase 3.1, `~/.agents/triad/cache/`, would also land there, and `.gitignore` does not cover it, so its JSON files would show up as untracked.

Target layout:

```
$TRIAD_STATE_DIR            (default ~/.triad)
  logs/advisor_calls.jsonl
  logs/council_sessions.jsonl
  circuit_state.json
  cache/<key[:2]>/<key>.json
  patches/
  sessions/
  usage_ledger.json
  advisors.local.json
%TEMP%/triad_session_slots/  (unchanged; machine-wide lock files)
```

Migration:

- Read the old location when the new file is absent, and write only the new location.
- `TRIAD_CIRCUIT_PATH` still wins over both.
- Overlay discovery checks `$TRIAD_STATE_DIR/advisors.local.json` first, then the two current paths.

## 7. Surgical fixes

### 7.1 Defects in A today

These are independent of v3.4. Ship them in Phase 0a.

- **F1. The agent's Tier 1 bypasses the council's guarantees.**
  - **Where:** `_call_tier_primary` in `triad/agent/runtime.py:132-163`.
  - **Problem:** It runs `claude -p` directly from a hardcoded path. That skips MCP stripping, the two-session cap (`ModelSessionLimiter`), the circuit breaker, telemetry, and Codex failover. With `-y` it also passes `--dangerously-skip-permissions`.
  - **Fix:**
    1. Add a pass-through mode to `build_advisor_prompt` that returns the prompt unchanged.
    2. Call `query_configured_advisor("claude", transcript, mode="passthrough")`, falling back to `"codex"` when the response is a failure.
    3. Drop `--dangerously-skip-permissions`. Tool execution stays in the local agent's permissioned `ToolRegistry`. `consult_architect` (`tools.py:298-331`) already uses this path.
- **F2. The local tier ignores the model's context window.**
  - **Where:** the local call at `runtime.py:197-206`.
  - **Problem:** It reserves `max_tokens=1024` against a 2048-token server. Any prompt over roughly 1,000 tokens overflows, and the agent's system prompt plus one `read_file` result is enough to get there.
  - **Fix:**
    1. Read `n_ctx` from `/props` once.
    2. Estimate prompt tokens; characters divided by 3.5 is close enough.
    3. Skip the local tier when prompt plus `max_tokens` would exceed 90% of `n_ctx`, and record the reason in the routing decision.
    4. Apply the same guard in `_execute_openai_http_advisor`, so council calls to `llama` fail fast with a classified error instead of a server 400.
- **F3. Agent calls to the local server honor system proxies.**
  - **Where:** `_call_http_openai_compatible` in `runtime.py:97-130`.
  - **Problem:** It uses the default URL opener, which routes through any configured system proxy.
  - **Fix:**
    1. For the local tier, use B's pattern: `validate_loopback_url` plus an opener built with `ProxyHandler({})`.
    2. Replace `LOCAL_LLAMA_URL` in `router.py:34` with `paths.llama_cpp_url()`.
- **F4. Delegate approve and reject run without a configured token.**
  - **Where:** A:872 and A:908 in `triad/server.py`.
  - **Fix:** change both to `if not SERVER_TOKEN or not self._is_authorized():`, which matches `/action/*`. Port B's test `test_mishmash_delegate_approve_reject_fail_closed_without_server_token`.
  - **Effect:** `ping` and `classify` are untouched, so the mesh keeps working with no token. Proposal approvals that arrive through the delegate envelope stop until §7.4 step 2 is done.
- **F5. `tr` is not versioned.**
  - **Fix:**
    1. Add `bin/tr.cmd` and `bin/tr.ps1`, copies of `bin/triad.cmd` and `bin/triad.ps1` that pass `agent` first.
    2. Add both names to `launcher_names` in `sync_manager.py:455`.
    3. Re-sync the venv from the committed `pyproject.toml`, so the stray `tr.exe` is removed.
  - **Do not add `tr` to `[project.scripts]`.** On Linux, on WSL, and in B's CI, which pip-installs this package onto `PATH`, a `tr` console script hides the POSIX `tr` utility that shell scripts depend on. `triad-agent` stays the cross-platform name.
- **F6. `resolve_binary` can't find Antigravity by name.**
  - **Where:** `canonical_map` in `advisor_manager.py:385-390`.
  - **Fix:** add `"antigravity": AGY_PATH` and `"llama-server": LLAMA_SERVER_PATH`, and accept `TRIAD_AGY_PATH` as the override for the `antigravity` advisor.
- **F7. A broken import is masked by its fallback.**
  - **Where:** `sync_manager.py:26` imports `TRIAD_DIR` from `paths`, which never defines it, so the fallback branch always runs.
  - **Fix:** define `TRIAD_DIR` in `paths.py`.
- **F8. B's test runner silently skips pytest-style tests.**
  - **Fix:** in A's new `package.json`, which B will vendor, set `"test": "python -m pytest triad/tests -q"`. The `[dev]` extra already installs pytest.
- **F9. Agent text still names Claude 3.7.**
  - **Where:** `cli.py:57`, `cli.py:118`, `cli.py:225`, `runtime.py:4`, and `router.py:14`, `router.py:158`, `router.py:161` (the hardcoded `claude-3-7-sonnet`).
  - **Fix:** fold these into Phase 2.3.

### 7.2 Phase 0 merge, file by file

"Base" is the side to start from. "Port" is what to bring in from the other side. Merge map §2 lists every definition by name and line.

| File | Base | Port |
|---|---|---|
| `triad/worktree.py` | B | Nothing. A has no A-only definitions. Take B's six changed definitions (`create_worktree`, `remove_worktree`, `deprovision_worktree_dependencies`, `capture_directory_snapshot`, `_check_dependency_graph_compatibility`, `WarmWorktreePool.__init__`) and B's seven new ones. |
| `triad/server.py` | B | In `_subsystem_status` and `_execute_remote_intent`, use the canonical local advisor name. Hold B's every-action check in `_handle_delegate` for step 3 of §7.4 and ship F4 in its place until then. Keep B's expanded `_DEVICE_ACTUATION` verb list and the `--` separators in `_handle_action_approve`. |
| `triad/bench/docker_harness.py` | B | Nothing. |
| `triad/bench/swebench_runner.py` | B | Nothing. A's host-execution fallback and its `docker_mode="off"` default are not carried over (D5). |
| `triad/advisor_manager.py` | A | From B: `effective_advisor` (B:80), `_execute_openai_http_advisor` (B:407), the `{port_local_llm}` token in `_resolve_readiness_port` (B:94), the `openai_http` branch in `advisor_is_ready` (B:122), transport dispatch in `_execute_single_advisor` and `_execute_single_advisor_raw`, and single-line failure notes in `query_configured_advisor` (B:832). Add alias resolution (§6.1). Keep A's `rank_advisors_for_task`, overlay-aware `load_config`, and the `include_overlay=False` writes in `add_advisor` and `remove_advisor`. |
| `triad/paths.py` | Union | No definition conflicts. Add B's `DEFAULT_LLAMA_CPP_URL`, `LOOPBACK_HOSTS`, `local_backend`, `validate_loopback_url`, `llama_cpp_url`, and `local_llm_port`. Make the default URL come from `PORT_LLAMA_SERVER`. List every port constant and helper in `__all__`. Add `TRIAD_DIR` (F7) and a state-dir helper. |
| `triad/triad_engine.py` | A | From B: `PROPOSED_FIX_PATCH_NAME` and `write_proposed_fix_patch` (B:2279-2315), plus their call site in `_handle_validation_failure`. Also the fail-closed council checks in `_run_gate_impl`, the `--` separators in `apply_patch_text` and `apply_verified_patch_to_workspace`, the leading-dash `--ref` rejection in `_run_in_isolated_worktree`, and `local_llm_port()` in the doctor. Keep A's `cmd_agent`, `cmd_sync`, the refreshable Codex status (`CODEX_MAX_REFRESH_AGE`), `--task` routing, the 8-subsystem parallel probe, and the wider `IGNORED_SOURCE_DEPENDENCY_DIR_NAMES`. |
| `triad/intent_engine.py` | A | From B: MICRO routing through `local_llm_port()` and the canonical local advisor. |
| `triad/nous_bridge.py` | A | Nothing. A's version is newer: per-model cooldowns, written after B's copy was made on 2026-10-09. |
| `triad/procutil.py` | A | Nothing. B's only unique definition, `_MARKER_RE`, is the old idempotency marker that A replaced. |
| `triad/advisors.json` | Rewrite | Version 2 per §6.1. |
| `pyproject.toml` | A | Keep `triad-agent` and the `triad.agent` package. Bump to 3.4.0 at the end of v3.4. |
| `package.json` | B | Move it to A's root and change the test script (F8). |
| New from B | | `triad/morphogenetic.py`, `triad/docker_runner.py`, and the four B-only test files. Then run A's ruff and bandit gates over them; B's CI does not run bandit. |
| `test_docker_runner.py` | B | Plus `46b8a8c` (D8). |

### 7.3 Test reconciliation

- **Target:** all 528 collected IDs. Drop an ID only with a written reason.
- **Twelve test-file definitions with different bodies.** Default to the side chosen as the module's base above, and keep assertions from both sides where both add coverage:
  - `test_docker_harness.py` (3: `test_checkout_argv_detaches_at_the_commit`, `test_docker_outcome_trusts_only_a_clean_pass`, `test_runner_executed_ignores_harness_failures`): take B's.
  - `test_server.py` (3: `test_evaluate_action_risk_unit`, `test_loopback_delegate_classifies_without_leaving_the_pc`, `test_mishmash_delegate_classify_and_risk_gating`): take B's, and re-check them against the staged delegate check in §7.4.
  - `test_worktree.py` (2: `test_cmd_auto_with_worktree_flag`, `test_warm_worktree_pool_recycling_and_concurrency_bound`): take B's.
  - `test_hook.py` (3): take B's for `test_direct_gate_persists_fix_without_mutating_working_tree` and `test_direct_healing_blocks_and_notifies_user`, because they follow the patch location from `write_proposed_fix_patch`. Diff `test_cmd_review_extracts_diff_from_review_base_in_worktree` by hand, because A changed `cmd_review` to pass `task`.
  - `test_nous_bridge.py` `setUp` (1): take A's; it resets the per-model cooldown state.
- **D3 changes the router test.** `test_router_default_local_orchestrator` in `test_agent.py` encodes today's always-local routing and needs updating.
- **The advisor rename.** `test_local_llm_backend.py` must pass with the advisor renamed to `llama`, through aliases and the `ollama_override` compatibility read.

### 7.4 Auth rollout without breaking the mesh

1. **Clients first.** Make the phone proxy (`apps/proxy/src/server.ts:269`, `:305`) and Bear House (`api/chat.ts:462`, `api/triad-telemetry.ts:33-34`) send `Authorization: Bearer $TRIAD_SERVER_TOKEN` when that variable is set. While no token is configured, the daemon ignores the header, so nothing changes yet.
2. **Provision one token value.** Set it for the gateway, which forwards it to the Triad child, and for the phone proxy and Bear House. Then restart the gateway.
   - A's existing `_require_auth()` starts enforcing it on `/auto`, `/review`, `/telemetry`, and `/doctor`, and `/action/*` starts accepting approvals.
3. **Close the envelope.** Land B's every-action delegate check together with `test_mishmash_delegate_every_action_requires_token`. Only then vendor A into B, so B never loses a check it has today.

## 8. Amendments to `TRIAD_UPGRADE_SPEC.md`

| Section | Amendment |
|---|---|
| §0 | **Baseline:** a full pytest run of the merged tree (at least 528 collected), in both CIs, recording pass, skip, and fail counts. **Where to work:** in a separate A worktree, because A's checkout is live (§3.3). |
| 1.1 and 1.2 | Replace `llama_bridge.py` with B's in-process `openai_http` transport, which Phase 0 already brings over, plus schema v2 aliases. No subprocess per call. |
| 1.3 | Keep `OLLAMA_PATH` and `PORT_OLLAMA`, because the backend override uses them. Add the B helpers (§7.2). |
| 1.4 | Resolve names through aliases instead of renaming in place. F6 covers `canonical_map`. |
| 1.5 to 1.7 | Use `local_llm_port()` and the canonical name everywhere. The doctor reports the model id and `n_ctx` from `/props`. |
| 1.9 | Allowed remaining `ollama` mentions: aliases, the backend override, compatibility environment variables, tests, and B's README note. |
| 2.1 | Use D3: score-based escalation plus the F2 context guard, with local still first for short turns. This depends on F1; otherwise escalations bypass the council's guarantees. |
| 2.2 | Apply the judge rule (§6.1 rule 4) to both standard synthesis (`competition.py:431`) and adversarial synthesis (`competition.py:423`). `_ready_production_names` (`competition.py:47-56`) currently returns any ready production advisor in priority order, local included. This does not need to wait for Phase 4. |
| 2.3 | Include the agent text listed in F9. |
| 2.4 | A already returns a classified error instead of crashing when argv exceeds the limit (`advisor_manager.py:492-545`). This phase's job is to make long prompts succeed through stdin or a temp file. It is a prerequisite for 4.2, which sends payloads over 30,000 characters to Antigravity, exactly where argv input fails today. |
| 2.5 and 5.2 | Merge them into one step: probe readiness for all candidates concurrently once per call, and reuse the results, including for `circuit_skipped` (`advisor_manager.py:900`). |
| 3.1 | Put the cache under `$TRIAD_STATE_DIR/cache` (§6.3). Include the resolved backend and model in the key, so switching between llama.cpp and Ollama never serves a stale answer. |
| 3.4 | The 800-line cap applies only to diffs in advisor prompts. `build_advisor_prompt` strips every diff before it looks at the mode, so `mode="brief"` and every `git apply` path need their own budget. |
| 3.6 | Reuse `procutil.is_doc_or_asset_file` (`procutil.py:234`) and `LOCKFILE_NAMES` for the pre-filter. Size the triage prompt by tokens, about 1,200, not by "200 lines"; the local context is 2048 tokens. |
| 4.1 | Use `strengths` per schema v2, with aliases resolved. |
| 4.2 | Depends on 2.4. |
| 5.1 | Drop `scripts/start-llama-server.ps1`. B's `ensure-llama-server.ps1` owns :8080 (D6). For a larger Triad context, add a `triad` role to that script on its own port and point `LLAMA_CPP_URL` at it. `--parallel N` splits `--ctx-size` across slots. |
| 5.3 | Keep the new `morphogenetic` and `docker_runner` imports lazy as well. |
| 6 | Split `triad_engine.py` (6,228 lines) after Phase 0, then re-vendor. |
| 7.4 | `scripts/generate_cases_v2.py` defines 12 cases (8 defects and 4 negatives). The checked-in `triad/bench/cases` has 16. Pick one set explicitly; "10" matches neither. |
| 7 | Add the B tree-hash check, and a live check that gateway delegate `ping` and `classify` succeed with the token and fail without it. |

## 9. Execution order and acceptance

1. **Freeze.**
   - Record the A and B SHAs.
   - Regenerate the merge map with `python scripts/triad_unify_audit.py`. It collects tests itself; override the checkout paths with `TRIAD_A` and `TRIAD_EXO`.
   - Run both suites with pytest to get the true baseline: A with `uv run pytest triad/tests -n auto --dist=loadfile`, and B from `packages/triad` with `python -m pytest triad/tests` and `TRIAD_SKIP_REAL_DOCKER=1`.
2. **Phase 0a,** on an A branch in a separate worktree.
   - Contents: §7.2, F1 to F9, schema v2, and optionally the state directory (D10).
   - Gate: at least 528 tests collected with 0 failures, A's ruff and bandit clean, and B's suite green when run against the merged tree.
3. **Auth steps 1 and 2** (§7.4). These change other repositories and the environment, not Triad code.
4. **Phase 0b:** the every-action delegate check (§7.4 step 3).
5. **Deploy.** Fast-forward A's `master`, restart the gateway, and run the smoke checks below.
6. **Vendor into B** (§5.3), add the CI guard, and update the docs (§5.4). Delete the broker directory after the owner confirms.
7. **v3.4 Phases 1 to 7,** as amended in §8. Each A release ends with a re-vendor PR in B.

Acceptance checks for the end state:

- **Vendoring.** In B, `git rev-parse HEAD:packages/triad` equals the lock's `tree`, and that equals the pinned A commit's root tree.
- **CI.** Both CIs are green, with at least 528 tests collected plus whatever v3.4 adds.
- **Live mesh and auth.** Gateway delegate `ping` and `classify` return 200 with the token and 401 without it, and `/action/*` approvals work with the token.
- **`tr`.**
  - `tr -p "hi"` answers on the local tier.
  - A prompt over the local budget routes to Nous, and the routing decision shows why.
  - `/status` shows llama-server online with its `n_ctx`.
  - `tr` still works after `triad sync --apply`.
- **Doctor.** `triad doctor` reports `llama`, with its model and context size.
- **No losses.** Re-running merge map §5 shows no Triad content on any A or B branch that is missing from A.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Both trees move while this runs. B's `main` moved during the audit. | Pin SHAs and regenerate the merge map before each step. |
| A's checkout is the live install. | Develop in a separate worktree and merge only after the gates pass. |
| The token rollout touches three other repositories. | Step 1 changes nothing until step 2. F4 closes the approval bypass in the meantime. |
| A's CI gates on bandit at medium severity, and B's new modules never ran it. | Run it in Phase 0a. Justify each `nosec` inline or fix the finding. |
| Renaming the local advisor changes its circuit and telemetry keys. | Old history stays under `ollama`. Harmless. |
| Vendoring the whole A tree puts docs and a nested `.github` under `packages/triad`. | GitHub ignores nested workflows. The vendored `AGENTS.md` text is written for both locations (§5.4). |
| The 2048-token local model limits what local triage and the agent can do. | Measure with F2 telemetry before investing in Phase 3.6. A larger Triad role is a D6 follow-up. |
