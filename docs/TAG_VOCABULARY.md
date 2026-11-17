# Tag vocabulary

The closed list of values allowed in a file's `Tags:` header. `scripts/repo-tags.mjs --audit` treats any
tag outside this table as an error, so adding a tag is a deliberate edit here, not an improvisation in
one file.

Frozen 2026-11-17. Derived from this tree, not copied from `sovereign-exocortex`: that repo's vocabulary
describes a TypeScript product with a mobile app, a desktop shell and a datastore. None of those exist
here. This repo is a Python advisor/agent engine, so its tags name advisors, routing, verification and
the zero-cost policy instead.

## Areas — where the code lives

| Tag | Covers |
| --- | --- |
| `agent` | `triad/agent`: REPL, model router, workspace tools, usage tracker |
| `advisor` | advisor roster, per-advisor invocation, cascade, circuit breaker, competition synthesis |
| `bench` | SWE-bench harness, curated cases, container verification, case generators |
| `cli` | `triad` command surface, `bin/` launchers, argument parsing |
| `engine` | the run loop that turns an intent into a routed, reviewed result |
| `server` | ambient HTTP daemon on :8789 |
| `skills` | the advisory skill shipped to other agents (`skills/claude-advisor`) |
| `sync` | ecosystem sync into `~/.agents`, launcher install, vendor drift audit |
| `tooling` | top-level install/verify scripts that are not part of the package |

`triad/tests` has no area tag on purpose: a test is filed under the area it tests plus `test-fixture`,
which is what makes "show me the routing tests" work.

## Concerns — what kind of question the file answers

| Tag | Covers |
| --- | --- |
| `cache` | content-addressed response cache, cache keys, invalidation |
| `claims` | live presence: who is touching which path right now |
| `cost` | zero-incremental-cost policy, quota windows, spending guards |
| `docker` | container execution, restricted harness, image and mount rules |
| `egress` | last-mile disclosure controls, redaction before a cloud call |
| `failover` | circuit breaker, advisor unhealthy marks, zero-downtime fallback |
| `intent` | natural-language classification, routing categories, stakes |
| `ledger` | append-only decision log, its schema and query surface |
| `local-llm` | llama.cpp backend, local model endpoints, offline advisor |
| `mcp` | Agent Mesh MCP coordination, tool exposure from the CLI |
| `morphogenetic` | self-modifying code engine, gates, reproduction tests |
| `notify` | phone notification bridge, delivery to a device |
| `nous` | Nous Research bridge and its model cascade |
| `ops-runbook` | install, doctor, health checks, env config, debugging procedure |
| `patching` | diff apply, rollback, tree snapshots, bloat stripping |
| `protocol-contract` | wire formats, JSON shapes, HTTP and MCP boundaries |
| `review` | review, consult and debug modes; what an advisor is asked |
| `routing` | model selection, waterfall order, tier cascade |
| `triage` | Phase 3.6 deterministic pre-filter and local risk triage |
| `verification` | ground-truth gate, repo-native tests, pass/fail adjudication |
| `worktree` | git worktree isolation, ephemeral checkouts, cleanup |
| `test-fixture` | tests, bench cases, mock data, harnesses |

## Rules

1. **A tag is a retrieval key.** If you would not type it into `grep`, it is not a tag.
2. **Canonical term only.** `routing`, never `router` or `route`. `verify` is `verification`. `nous`,
   never `nous-research`. `local-llm`, never `llama`.
3. **No IDs.** `2.4`, `phase-3.6`, `row-14` belong in `Links:` or `Queries:`, not in `Tags:`.
4. **No dates, versions, agents, or file extensions.**
5. **A tag on more than 15% of files is not discriminating.** `--audit` warns above that line. If a tag
   trips it, fold it into a narrower one rather than keeping both. At this repo's size the line is only 13
   files, so *every* area-level tag (`cli`, `advisor`, `verification`, `ops-runbook`, `test-fixture`,
   `review`) trips it. Those warnings are informational here and deliberately left alone: the alternative,
   splitting `cli` into `cli-review`/`cli-gate`/..., would invent vocabulary for a 91-file tree and make
   the tag list harder to read than the files it indexes. Treat the warning as a prompt to check, not a
   defect to clear.
6. **2 to 6 tags per file.** Six is the ceiling, not the target.
7. **A mirror is out of scope in the host repo.** `sovereign-exocortex/packages/triad/` is a subtree copy
   of this tree, replaced wholesale by `scripts/update-triad.ps1`. Headers are written **here** and flow
   downstream on the next sync; the host repo excludes `packages/triad/` from its index for that reason.

## Header format

```text
# Python / shell / YAML / TOML      **Markdown**                    @rem Windows batch
# Tags: advisor, failover           **Tags:** advisory council        @rem Tags: cli, ops-runbook
# Links: triad/advisors.json, docs/ **Links:** triad/advisor_manager  @rem Links: triad/paths.py
# Queries: "which advisor runs"     **Queries:** "who is called"      @rem Queries: "where am I"
```

Placement: after the shebang, and after a module docstring in Python. `Queries:` values are always
quoted — an unquoted comma silently splits a question in half.

## Adding a tag

Edit this table, then `npm run tags` to regenerate the index. A tag that only one file needs is a
`Links:` entry, not a tag.
