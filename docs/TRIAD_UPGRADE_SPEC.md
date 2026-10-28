# autonomous-triad: Upgrade Spec (v3.4)

**Repo:** `Dysfunction-Junction/autonomous-triad` @ `a978bf1`
**Goal:** more speed and accuracy, a large cut in tokens per review, every agent participating in the lane it does best, and $0 incremental cost.
**Rule:** this is a spec only. Each phase is one commit, with tests green before moving to the next phase.

---

## 0. Ground rules

- **Branch:** `feat/v3.4-lean-council`
- **Baseline first:** `uv run pytest -q`. Record the pass/skip count; the README says 292 pass and 1 is skipped. Every phase must end with the same count or higher and zero new failures.
- **No metered APIs.** Claude Pro, ChatGPT Plus, Antigravity, the Nous free tier and llama.cpp only.
- **Keep these invariants:** the 2-session cap (`ModelSessionLimiter`), circuit breaker semantics, MCP stripping, mock isolation, worktree gate safety, and Windows path handling.
- **Each phase can be reverted on its own.** New behaviour sits behind an env flag that defaults to on, so an emergency off-switch exists.

---

## Phase 1: Replace Ollama with llama.cpp (llama-server :8080)

### 1.1 New `triad/llama_bridge.py`
This is a stdin→stdout advisor shim modelled on `nous_bridge.py`, using the stdlib only (`urllib`).
- Reads the prompt from stdin.
- POSTs to `http://127.0.0.1:{PORT_LLAMA_SERVER}/v1/chat/completions` with `{"model": env TRIAD_LLAMA_MODEL or "local", "messages":[{"role":"user","content":prompt}], "temperature":0.2, "max_tokens": env TRIAD_LLAMA_MAX_TOKENS or 1024, "stream":false}`.
- Timeout comes from `TRIAD_LLAMA_TIMEOUT` (default 90s).
- Strips any `<think>...</think>` block from the output, since qwen3 can emit one.
- On connection refused it prints `[Error: llama-server unreachable on :PORT]` and exits 1. On an HTTP error or an empty reply it prints `[Error: llama-server HTTP <code>]` and exits 1. Both strings must match `is_failed_advisor_response()` (`procutil.py:146`); add a test for that.
- `--health` flag: GET `/health`, exit 0 when healthy.

### 1.2 `triad/advisors.json`
Delete the `ollama` entry and add:
```json
{
  "name": "llama",
  "display_name": "llama.cpp Local (llama-server :8080)",
  "binary_path": "python", "fallback_binary": "python3",
  "priority": 5,
  "execution_flags": ["{triad_dir}/llama_bridge.py"],
  "input_mode": "stdin", "output_mode": "stdout",
  "readiness_port": "{port_llama}",
  "timeout": 90,
  "env": {"PYTHONIOENCODING": "utf-8"},
  "enabled": true
}
```

### 1.3 `triad/paths.py`
- Remove `OLLAMA_PATH` (lines 101–104) and `PORT_OLLAMA` (line 130), plus their entries in the `__all__` list (138, 141).
- Keep `LLAMA_SERVER_PATH` and `PORT_LLAMA_SERVER`.
- Add a compatibility alias for one release: `PORT_OLLAMA = PORT_LLAMA_SERVER  # deprecated, remove v3.5`. This keeps third-party imports from breaking.

### 1.4 `triad/advisor_manager.py`
- Imports (lines 28 and 38): `PORT_OLLAMA`/`OLLAMA_PATH` become `PORT_LLAMA_SERVER`/`LLAMA_SERVER_PATH`.
- `_resolve_readiness_port` (line 124): accept `{port_llama}` and `llama`, returning `PORT_LLAMA_SERVER`. Keep `{port_ollama}` mapped to the same port so old overlays still resolve.
- Binary map (line 388): `"ollama": OLLAMA_PATH` becomes `"llama-server": LLAMA_SERVER_PATH`.
- Line 359: drop `OLLAMA_MODELS`.
- `TASK_ADVISOR_PRIORITY`: superseded in Phase 4. Until then, a straight rename from `ollama` to `llama`.
- Line 7 docstring: rename.
- **Alias shim:** `get_active_advisor("ollama")` resolves to `llama` and logs a one-time deprecation warning. This protects scripts and hooks that pass `--engine ollama`.

### 1.5 `triad/server.py`
- Imports (43, 50) and the port map (235): `ollama` becomes `llama` with `PORT_LLAMA_SERVER`.
- Line 1306: `if (intent == "MICRO" or engine in ("llama","ollama")) and is_port_open("127.0.0.1", PORT_LLAMA_SERVER, timeout=0.3): resp = query_configured_advisor("llama", ...)`

### 1.6 `triad/intent_engine.py`
- Imports (20, 22): `PORT_LLAMA_SERVER`.
- Line 36 comment: `ollama` becomes `llama`.
- Line 287 rationale: "llama.cpp local / Nous Flash".
- Lines 553–555: reason `"...local SLM (llama-server :8080)"`, `suggested_engine="llama"`.
- Lines 701–703: `== "llama"`, port `PORT_LLAMA_SERVER`, `engine="llama"`.

### 1.7 `triad/triad_engine.py`
- Imports (43, 60): `PORT_LLAMA_SERVER`.
- Doctor port map (300): `"llama": PORT_LLAMA_SERVER`.
- Doctor label (435): `("llama", "llama.cpp")`. The doctor also runs `llama_bridge.py --health` and reports the model id from `GET /v1/models`.
- `--engine` help strings (6064, 6074, 6084, 6090): replace `ollama` with `llama`.

### 1.8 Docs and skills
- `skills/claude-advisor/advisor.py` (305, 335) and `SKILL.md`: rename.
- `README.md`: update the mermaid node `O["llama.cpp qwen3 :8080"]`, the zero-cost list, the role table and the Ollama text in §3.5.
- `docs/BLUEPRINT.md`: same rename.
- `HERMES_HANDOFF_2026-10-27.md` is a historical record. Leave it unchanged and add a note pointing to this spec.

### 1.9 Tests
- `test_advisor_manager.py` (5 hits) and `test_intent_engine.py` (1 hit): rename the expectations.
- **New** `tests/test_llama_bridge.py`:
  - Stub HTTP server (stdlib `http.server` on an ephemeral port) for: success, `<think>` stripping, HTTP 500, connection refused, empty choices. Every failure path must satisfy `is_failed_advisor_response`.
  - Readiness: closed port means `advisor_is_ready("llama")` is False and gets skipped in under 5ms.
  - Alias: `--engine ollama` resolves to `llama`.
- **Done when:** `grep -rni ollama triad skills README.md docs` returns only the alias shim, the deprecation note and the tests for the alias.

---

## Phase 2: Fix the accuracy bugs

### 2.1 Router ignores its own score (`triad/agent/router.py` ~L185–196)
Currently every call returns `TIER_3_LOCAL`. Replace the default branch with:
```python
if difficulty >= threshold_c:
    return RoutingDecision(TIER_1_PRIMARY, primary_model, difficulty, threshold_c,
        f"Complexity {difficulty:.2f} >= c {threshold_c:.2f}: escalate to council",
        [TIER_2_CLOUD_FREE, TIER_3_LOCAL])
if difficulty >= threshold_c - 0.15:
    return RoutingDecision(TIER_2_CLOUD_FREE, nous_model, ..., [TIER_3_LOCAL])
return RoutingDecision(TIER_3_LOCAL, local_model, ..., [TIER_2_CLOUD_FREE])
```
- Read model names from `advisors.json` display names or env (`TRIAD_LLAMA_MODEL`). Remove the hard-coded `"claude-3-7-sonnet"`.
- The quota-aware threshold (`get_effective_threshold`) then starts to matter: when the primary is rate-limited, `c` becomes 1.0 and everything sheds to free or local tiers.
- Escape hatch: `TRIAD_AGENT_LOCAL_DEFAULT=1` restores the old always-local behaviour.
- **Tests:** high-difficulty prompt → primary; low → local; cooling down → never primary; force flags unchanged.

### 2.2 The judge never grades itself (`competition.py` ~L428)
For non-adversarial synthesis, use the same rule adversarial mode already uses:
```python
third = next((n for n in _ready_production_names() if n not in (adv1_name, adv2_name)), None)
synth_engine = third or (adv2_name if failed1 and not failed2 else adv1_name)
```
- Rank the "third" candidates by the `judge` strength (Phase 4), so Claude judges when it didn't compete, and Codex or Nous judge otherwise. Never pick `llama` as judge: a 1.7B model must not rule on Claude or Codex. Set `"judge": 0` for llama in `strengths`.
- Fallback stays as it is (try the other advisor if the judge fails).
- **Tests:** pair (claude, codex) plus nous ready → judge is nous. Only two ready → falls back as today. llama is never the judge.

### 2.3 Out-of-date model labels
- `advisors.json` display names become model-agnostic: `"Claude Code (Claude Pro)"`, `"OpenAI Codex (ChatGPT Plus)"`, `"Google Antigravity"`. The model version comes from `triad doctor` at runtime instead of being hard-coded.
- Remove `Claude 3.7` and `Gemini 2.5` strings from `router.py`, `intent_engine.py` (rationales at L275 and L280) and the README.
- Why: the judge prompt includes these labels, and stale names skew how it weighs each advisor.

### 2.4 Antigravity input over the command-line limit
- Check whether `agy -p` accepts stdin (`echo hi | agy -p -` or no-arg `-p`).
  - **If yes:** `input_mode: "stdin"` and drop `{prompt}`.
  - **If no:** in `_execute_single_advisor_raw`, when `input_mode == "arg"` and the encoded length is over 24,000 characters, write the prompt to a temp file and pass `"Read and follow the instructions in: <path>"`. Delete the file in `finally`.
- **Test:** a 40k-character prompt doesn't raise `OSError`/`WinError 206`.

### 2.5 Leftover readiness checks after the loop (`advisor_manager.py` ~L893)
`circuit_skipped` calls `advisor_is_ready()` again for every advisor, which means a second port probe. Cache `(name → ready)` from the first loop in a local dict and reuse it.

---

## Phase 3: Token reduction (largest savings first)

### 3.1 Response cache by content hash (biggest single win)
**New** `triad/response_cache.py`:
- Key: `sha256(advisor_name | mode | task | PROMPT_SCHEMA_VERSION | normalized_prompt | stripped_diff | context)`.
- Store: `~/.agents/triad/cache/<key[:2]>/<key>.json` holding `{response, advisor, created, ttl}`, written atomically (temp file + `os.replace`).
- TTL: `TRIAD_CACHE_TTL` (default 7 days). Size cap of 50 MB, with LRU pruning on write.
- **Never cache** a failed response (`is_failed_advisor_response`) or a mock response.
- Hook it into `_execute_single_advisor` before `ModelSessionLimiter.acquire()`. A cache hit costs 0 tokens, takes no session slot and leaves the circuit untouched.
- The competition session caches its synthesis under `hash(pair + both response hashes)`.
- Kill switches: `TRIAD_CACHE=0` and `triad doctor --clear-cache`.
- `PROMPT_SCHEMA_VERSION` constant: bump it whenever a prompt template changes, which invalidates old entries automatically.
- **Effect:** re-running the pre-commit hook on an unchanged diff, retrying `triad gate` after a non-code fix, or repeating `consult` calls costs 0 tokens.
- **Tests:** hit/miss, failures not cached, TTL expiry, concurrent writers (two threads, same key) don't corrupt, schema bump invalidates.

### 3.2 The judge gets findings, not the diff (`competition.py` `build_synthesis_prompt` and the adversarial version)
- Advisors already get the diff. Add to the review prompt (`build_advisor_prompt` `review_diff`): *"Cite every finding as `path:line` with severity [BLOCKER|MAJOR|MINOR|NIT]."*
- In the synthesis prompt, replace the full `DIFF:` block with **only the hunks referenced by any `path:line` citation** (new helper `extract_cited_hunks(diff, responses)` in `procutil.py`) and a file list. If nothing is cited, send only the file list.
- Drop `CONTEXT` from synthesis unless it's under 2k characters.
- **Effect:** about 3× diff tokens per competition becomes about 1.3×.
- **Tests:** a cited hunk is kept, an uncited one is dropped, fences stay intact, an empty citation set produces only the file list.

### 3.3 Skip the judge when both approve
Before synthesis: if both responses parse to APPROVED (reuse the verdict regex used by the hook) **and** neither contains BLOCKER or MAJOR, return a deterministic merged synthesis:
```
### Unanimous: APPROVED
Both advisors approved. Minor notes: <deduped MINOR/NIT lines>
VERDICT: APPROVED
```
- Not applied in adversarial mode, where the referee is the point.
- Kill switch: `TRIAD_SKIP_UNANIMOUS_SYNTH=0`.
- **Tests:** approve+approve skips the call (assert the advisor mock isn't invoked), approve+blocker still synthesizes.

### 3.4 Smaller diffs (`get_git_diff` and `strip_diff_bloat`)
- `get_git_diff`: add `-U1 -w --no-color --find-renames` (env `TRIAD_DIFF_CONTEXT`, default 1).
- `strip_diff_bloat`:
  - Pure renames and mode-only changes become a header only.
  - Pure-deletion files become a header plus `[N lines deleted]`.
  - Default budget: `max_total_lines` 2500 → 800 and `max_lines_per_file` 500 → 250, configurable through env. The omission marker lists the dropped files so an advisor can ask for them.
  - It must stay idempotent; the existing tests in `test_diff_bloat.py` guard this.
- **Gate safety:** `apply_verified_patch` and the worktree code use their own full-context diffs. Only the diffs **sent to advisors** change. Grep every `get_git_diff(` caller and confirm none of them feed `git apply`.

### 3.5 Remove the duplicate role preamble
- Claude's `--system-prompt` and `build_advisor_prompt`'s `system_preamble` both set the role. Trim the preamble to one line: `"Advisory reviewer for Antigravity. Dense, specific, cite path:line."`. Leave Claude's flag as it is.
- Bump `PROMPT_SCHEMA_VERSION`.

### 3.6 Tiered escalation with local triage
In `cmd_review` and the hook path, before calling the council:
1. **Deterministic pre-filter** (0 tokens): if every changed file matches `*.md|*.txt|docs/**|*.lock|LICENSE` or the diff is whitespace-only, return `VERDICT: APPROVED (trivial: docs/format)`.
2. **llama triage** (local, $0): when llama is ready, ask it to `Classify risk: TRIVIAL|NORMAL|HIGH. One word.` using the file list plus the first 200 diff lines.
   - TRIVIAL and not `is_high_stakes()` → one cheapest-capable advisor (Nous).
   - NORMAL → single council advisor (current behaviour).
   - HIGH, or `is_high_stakes()` → competition.
   - `is_high_stakes()` always wins over llama, so a small model can't de-escalate security-sensitive work.
3. If llama is down, skip step 2 and use the current behaviour.
- Kill switch: `TRIAD_TRIAGE=0`.
- **Tests:** a docs-only diff makes no advisor call, an auth diff goes to competition even when llama says TRIVIAL, llama down falls through.

---

## Phase 4: Every agent participates, by lane

### 4.1 Strengths in `advisors.json` instead of the hard-coded ranking
Add to each advisor:
```json
"strengths": {"architecture":0.95,"coding":0.95,"reasoning":0.85,"judge":0.95,
              "red_team":0.8,"long_context":0.6,"micro":0.2,"scraping":0.2}
```
Starting values:

| Lane | claude | codex | antigravity | nous | llama |
|---|---|---|---|---|---|
| architecture | .95 | .85 | .80 | .50 | .10 |
| coding (review) | .95 | .90 | .75 | .50 | .15 |
| reasoning | .85 | .95 | .75 | .45 | .10 |
| judge | .95 | .85 | .70 | .55 | **0** |
| red_team | .80 | .95 | .70 | .50 | 0 |
| long_context | .60 | .55 | **1.0** | .30 | 0 |
| scraping / browsing | .20 | .20 | .50 | .80 | **.95** |
| micro / triage | .15 | .15 | .30 | .80 | **.95** |

`rank_advisors_for_task`: sort by `(-strengths.get(task, 0.5), priority)`, and exclude advisors with a strength of 0 for that task. Delete the `TASK_ADVISOR_PRIORITY` dict. Overlay files can tune the numbers without code changes.
- **Tests:** each task's top pick matches the table, a strength of 0 is excluded, a missing `strengths` falls back to priority (backward compatible).

### 4.2 Lane roles in the flows
- **Antigravity becomes the context condenser** (new `mode="brief"`). When the context or diff is over `TRIAD_BRIEF_THRESHOLD` (default 30k characters), Antigravity first produces a brief of at most 2k tokens: touched symbols, invariants, call sites and risks. Claude and Codex receive **the brief plus cited hunks** instead of the raw blob. This is its executive "context shield" role as actually built.
  - Cache the brief under the content hash (3.1).
  - If Antigravity fails, fall back to `strip_diff_bloat` truncation.
- **Codex is Red Team by default** in adversarial mode (`red_team` lane), and writes tests in `gate` when the fix needs new tests.
- **Claude is Blue Team, primary reviewer, and judge when it isn't competing.**
- **Nous is the tiebreaker.** Competition invokes it only when the judge marks section 3 (Direct Contradictions) as non-empty on a BLOCKER, and it receives only the contradicting claims plus their hunks.
- **llama handles triage (3.6), commit messages and small tasks**, and is never the judge.
- **Hermes:** device lane, already routed by intent. No change.
- **Oz:** stays `enabled:false`. The doctor reports why (`dispatch_status`).

### 4.3 Competition pair by lane
`select_competition_pair` takes `task` and picks the top 2 by strength for that lane, skipping circuit-open or not-ready advisors. That gives Claude+Codex for coding and Codex+Claude for reasoning; Blue/Red order follows `coding`/`red_team`.

---

## Phase 5: Speed

1. **Keep llama warm:** the doctor reports whether llama-server is running. Add `scripts/start-llama-server.ps1` with `--port 8080 -c 8192 --cont-batching --parallel 2`. Choosing the model is up to the user.
2. **Probe readiness in parallel:** in auto mode, probe every advisor's readiness port concurrently (ThreadPool, 0.3s timeout) before the loop, then iterate the ranked ready list.
3. **Lazy imports:** `triad_engine.py` imports competition, worktree and bench at top level. Move them into the command functions so `triad hook`, `doctor` and `consult` start faster. Measure `python -X importtime -m triad --help` before and after; the target is at least 30% less.
4. **Competition wall clock:** non-adversarial mode already runs in parallel. Confirm both calls use the remaining deadline, not the full `timeout` each.

---

## Phase 6: Hygiene (makes agents working on the repo cheaper)

- Split `triad_engine.py` (6.2k lines) mechanically. **Moves only, no logic changes:**
  - `triad/cli/doctor.py`, `review.py`, `gate.py`, `hook.py`, `mesh.py`, `sync.py`
  - `triad/patching.py` (apply/rollback/fingerprint, about lines 664–2000)
  - `triad_engine.py` keeps `build_parser`, `main` and re-exports every moved symbol so `from triad.triad_engine import X` keeps working. This matters for the 6k-line `test_hook.py`, which patches `triad.triad_engine.*`.
  - **Mock paths:** tests that `mock.patch("triad.triad_engine.foo")` keep working only if callers look `foo` up through `triad_engine`. Where a moved function calls a sibling, patch tests must target the new module. Run the full suite after each file move.
- Update the paths in `AGENTS.md`.
- README: bump the status to v3.4 with the new test count.

---

## Phase 7: Verify end to end

1. `uv run pytest -q`: all green, count ≥ baseline plus new tests.
2. `uv run python -m triad doctor`: llama shown as ONLINE or skipped cleanly, no Ollama references.
3. Smoke tests on the user's Windows machine; these can't be run in CI:
   - `triad consult "explain X" --engine llama`
   - `triad review --cached` twice. The second run shows `[cache hit]` and 0 advisor calls.
   - A docs-only commit through the hook: trivial approve, no advisor call.
   - An auth-touching diff: competition, with the judge ≠ either competitor.
   - `triad-agent "hard multi-file refactor plan"`: routes to primary (router fix).
   - A 40k-character prompt to antigravity: no command-line overflow.
4. **Token audit:** advisor telemetry (`record_advisor_call`) already logs `prompt_chars`. Run the same 10-diff set from `scripts/generate_cases_v2.py` before and after. Targets:
   - At least 60% fewer total prompt characters per review.
   - 100% cache hits on the repeat run.
   - Zero accuracy regressions on bench cases (`triad bench`).
5. **Independent check:** have a reviewer that didn't write the code (Codex via `triad review --engine codex`) review the whole branch diff before merge.

---

## Expected impact

| Change | Token effect | Accuracy effect |
|---|---|---|
| Cache | Repeat runs drop to 0 | Neutral |
| Judge gets findings only | ~-55% per competition | Neutral to slightly better (less noise) |
| Skip unanimous judge | -1 call on clean diffs | Neutral |
| Smaller diffs | ~-30–50% per review | Neutral (gate unchanged) |
| Triage and pre-filter | Docs/format changes → 0 | Neutral; high-stakes can't be downgraded |
| Antigravity brief | Large contexts ~-80% to premium models | Better focus |
| Router fix | Neutral | **Hard prompts stop landing on the 1.7B model** |
| Independent judge | +0 | **Removes self-grading bias** |

## Risk register

- **Cache serves a stale verdict after the policy changes:** mitigated by bumping `PROMPT_SCHEMA_VERSION` and the TTL.
- **The small triage model under-rates risk:** `is_high_stakes()` override; triage can only route down when the deterministic check agrees.
- **Hunk extraction misses context:** the judge sees the file list and can flag "insufficient context". Fall back to the full stripped diff with `TRIAD_SYNTH_FULL_DIFF=1`.
- **The split breaks mock paths:** re-exports, file-by-file moves and the full suite after each.
- **llama-server isn't running:** readiness-skipped in under 5ms; every lane has a non-local fallback.
