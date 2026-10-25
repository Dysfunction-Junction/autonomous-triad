# Agent index

This file is a map. It names checkouts, ports, and the file to open. It does not describe behavior. If a line here and the code disagree, the code wins; then correct this file's path or port.

The launch table is copied from `sovereign-exocortex/apps/daemon/src/mishmash-nodes.ts`. That file is the routing contract. Checkouts sit next to each other. The launcher treats a directory as the repos root when it contains `hermes-api`, `autonomous-triad`, and `pieces-for-all`.

## Family

| Launch id | Directory | Port | Role in the launch table | Mesh entry |
|---|---|---|---|---|
| `exocortexd` | `sovereign-exocortex` | 8788 | gateway | `apps/daemon/src/server.ts` |
| `hermes-api` | `hermes-api` | 3000 | device and phone tasks | `mishmash/delegate.ts` |
| `autonomous-triad` | `autonomous-triad` | 8789 | intent and review | `triad.server` |
| `pieces-for-all` | `pieces-for-all` | 39400 | local memory gateway | `src/server.ts` |
| `agent-mesh-mcp` | `agent-mesh-mcp` | 39401 | local MCP switchboard | `src/mishmash-delegate.ts` |
| `pattern-analyzer` | `pattern-analyzer` | 39402 | pattern lifecycle ranking | `src/mishmash-delegate.ts` |
| `registry-app` | `registry-app` | 39403 | SecondGuess staging | `mishmash/delegate.ts` |
| `gut-instinct` | `Gut-Instinct` | 39404 | on-device coach contract | `mishmash/delegate.mjs` |
| `tool-registry-heartbeat` | `tool-registry-heartbeat` | 39405 | scheduled tool-inventory tasks | `mishmash/delegate.mjs` |

The home proxy (often `:8787`) and PiecesOS (`:39300`) are separate local processes. They are not checkouts in this table.

## This checkout

Mesh launch id `autonomous-triad`, port 8789, runner `python`, script `triad.server`.

| Path | Open when the question is about |
|---|---|
| [`README.md`](README.md) | overview and CLI. Confirm advisor names and flags in code before repeating them. |
| [`triad/advisors.json`](triad/advisors.json) | which advisors exist, their display names, binaries, and priority |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | topology writeup. Treat it as a spec, then check `triad/` |
| [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md) | longer design notes |
| [`pyproject.toml`](pyproject.toml) | package metadata and tool entry points |

This checkout is the sibling advisor service. `sovereign-exocortex/packages/triad` is a different tree inside the gateway repo. Device tasks live in the `hermes-api` checkout, not here.
