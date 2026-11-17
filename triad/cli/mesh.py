"""Agent Mesh MCP coordination, status, and health supervision (`triad mesh`)."""

# Tags: cli, mcp, protocol-contract
# Links: triad/server.py, AGENTS.md
# Queries: "how do I check mesh health", "which MCP servers are coordinated"

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    from triad.paths import AGENT_MESH_DIR, AGENT_MESH_SERVER
except ImportError:
    from paths import AGENT_MESH_DIR, AGENT_MESH_SERVER


def _mesh_list_tools(node_bin: str, server_path: Path, origin: str = "antigravity", timeout: float = 8.0) -> List[Dict[str, Any]]:
    """Probe the Agent Mesh MCP server and retrieve registered tools with timeout and process cleanup."""
    env = dict(os.environ)
    if "AGENT_MESH_ALLOWED_ROOTS" not in env:
        default_roots = f"{Path.home() / 'projects'};{Path.home() / 'Desktop' / 'projects'}"
        env["AGENT_MESH_ALLOWED_ROOTS"] = default_roots

    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "triad", "version": "1.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    payload = "\n".join(json.dumps(m) for m in msgs) + "\n"
    proc = subprocess.Popen(
        [node_bin, str(server_path), "--origin", origin],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    try:
        out, _ = proc.communicate(payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise TimeoutError(f"Agent Mesh probe timed out after {timeout}s")
    except Exception:
        proc.kill()
        proc.communicate()
        raise

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            if r.get("id") == 2:
                return r.get("result", {}).get("tools", [])
        except ValueError:
            continue
    raise RuntimeError("No tools/list response received from Agent Mesh")


def cmd_mesh(args=None):
    """
    Agent Mesh MCP coordination, status, and health supervision.
    """
    if isinstance(args, str):
        mesh_action = "status"
        origin = "antigravity"
        as_json = False
    elif args is None:
        mesh_action = "status"
        origin = "antigravity"
        as_json = False
    else:
        mesh_action = getattr(args, "mesh_action", "status") or "status"
        origin = getattr(args, "origin", "antigravity") or "antigravity"
        as_json = bool(getattr(args, "json", False))

    node_bin = shutil.which("node")
    server_path = AGENT_MESH_SERVER
    server_exists = server_path.exists()

    report: Dict[str, Any] = {
        "node_available": bool(node_bin),
        "node_path": node_bin or "",
        "mesh_dir": str(AGENT_MESH_DIR),
        "server_path": str(server_path),
        "server_built": server_exists,
        "origin": origin,
        "status": "ready" if (node_bin and server_exists) else "unready",
    }

    if mesh_action in ("status", "doctor"):
        tools = []
        if node_bin and server_exists:
            try:
                tools = _mesh_list_tools(node_bin, server_path, origin=origin)
                report["tools_count"] = len(tools)
            except Exception as e:
                report["probe_error"] = str(e)
                report["status"] = "degraded"

        config_status = {}
        gemini_cfg = Path.home() / ".gemini" / "config" / "mcp_config.json"
        gemini_antigravity = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
        claude_cfg = Path.home() / ".claude.json"
        codex_cfg = Path.home() / ".codex" / "config.toml"

        for key, cfg_path in (
            ("gemini_cli", gemini_cfg),
            ("antigravity_ide", gemini_antigravity),
            ("claude_code", claude_cfg),
        ):
            try:
                if cfg_path.exists():
                    cfg_data = json.loads(cfg_path.read_text(encoding="utf-8", errors="replace"))
                    config_status[key] = "agent-mesh" in cfg_data.get("mcpServers", {})
                else:
                    config_status[key] = False
            except Exception:
                config_status[key] = False

        try:
            if codex_cfg.exists():
                codex_text = codex_cfg.read_text(encoding="utf-8", errors="replace")
                config_status["codex"] = "[mcp_servers.agent-mesh]" in codex_text
            else:
                config_status["codex"] = False
        except Exception:
            config_status["codex"] = False

        report["client_registrations"] = config_status

        if as_json:
            print(json.dumps(report, indent=2))
            if mesh_action == "doctor" and report["status"] != "ready":
                sys.exit(1)
            return

        print("\n=== Agent Mesh MCP Subsystem Status ===")
        print(f"  Directory:    {AGENT_MESH_DIR}")
        print(f"  Server:       {server_path} ({'✓ Built' if server_exists else '❌ Not Built'})")
        print(f"  Node.js:      {node_bin or '❌ Missing'}")
        print(f"  Active Tools: {report.get('tools_count', 'N/A')}")
        print("\n  Client Mounts:")
        for client, mounted in config_status.items():
            mark = "✓ Mounted" if mounted else "❌ Not mounted"
            print(f"    - {client:16s}: {mark}")
        print(f"\n  Subsystem Health: {'✅ OPTIMAL' if report['status'] == 'ready' else '❌ DEGRADED'}\n")

        if mesh_action == "doctor" and report["status"] != "ready":
            sys.exit(1)

    elif mesh_action == "tools":
        if not node_bin or not server_exists:
            print("❌ Agent Mesh server not built or Node.js missing.", file=sys.stderr)
            sys.exit(1)
        try:
            tools = _mesh_list_tools(node_bin, server_path, origin=origin)
            if as_json:
                print(json.dumps(tools, indent=2))
            else:
                print(f"\n=== Agent Mesh MCP Registered Tools ({len(tools)}) ===")
                for t in tools:
                    print(f"  - {t['name']:32s} : {t.get('description', '')[:70]}")
                print()
        except Exception as e:
            print(f"❌ Failed to list tools: {e}", file=sys.stderr)
            sys.exit(1)

    elif mesh_action == "serve":
        if not node_bin or not server_exists:
            print("❌ Agent Mesh server not built or Node.js missing.", file=sys.stderr)
            sys.exit(1)
        cmd = [node_bin, str(server_path), "--origin", origin]
        try:
            res = subprocess.run(cmd)
            sys.exit(res.returncode)
        except KeyboardInterrupt:
            sys.exit(0)
