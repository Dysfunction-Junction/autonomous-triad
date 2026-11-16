"""System health & cost audit CLI command (`triad doctor`)."""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

try:
    from triad.paths import (
        CLAUDE_PATH, CODEX_PATH, AGY_PATH, HERMES_PATH, CODEX_AUTH,
        PORT_HERMES_RELAY, PORT_PIECES_OS, PORT_TRIAD_SERVER, local_llm_port,
        PORT_EXOCORTEX_DAEMON, PORT_PIECES_PROXY, PORT_PIECES_FOR_ALL,
        PORT_AGENT_MESH_MCP, PORT_NEO4J_BOLT,
    )
    from triad.procutil import is_port_open, classify_advisor_response
    from triad.circuit import snapshot_circuits, is_circuit_open, reset_circuit
    from triad.advisor_manager import query_configured_advisor, get_advisors, advisor_is_ready
except ImportError:
    from paths import (
        CLAUDE_PATH, CODEX_PATH, AGY_PATH, HERMES_PATH, CODEX_AUTH,
        PORT_HERMES_RELAY, PORT_PIECES_OS, PORT_TRIAD_SERVER, local_llm_port,
        PORT_EXOCORTEX_DAEMON, PORT_PIECES_PROXY, PORT_PIECES_FOR_ALL,
        PORT_AGENT_MESH_MCP, PORT_NEO4J_BOLT,
    )
    from procutil import is_port_open, classify_advisor_response
    from circuit import snapshot_circuits, is_circuit_open, reset_circuit
    from advisor_manager import query_configured_advisor, get_advisors, advisor_is_ready

CODEX_MAX_REFRESH_AGE = timedelta(days=30)


def _decode_codex_auth(auth_path: Path) -> Dict[str, Any]:
    """
    Inspect the Codex OAuth cache without touching the network. Returns plan metadata
    and a computed ``status`` of ``active`` / ``refreshable`` / ``expired`` / ``unknown`` / ``missing``.
    """
    info: Dict[str, Any] = {"status": "missing", "plan": None, "active_until": None, "refreshable": False, "has_refresh_token": False}
    if not auth_path.exists():
        return info
    try:
        import base64
        with open(auth_path, "r", encoding="utf-8") as f:
            auth_data = json.load(f)
        raw_tokens = auth_data.get("tokens")
        tokens = raw_tokens if isinstance(raw_tokens, dict) else {}
        has_refresh = bool(tokens.get("refresh_token"))
        info["has_refresh_token"] = has_refresh

        is_refresh_valid = False
        last_refresh_raw = auth_data.get("last_refresh")
        if has_refresh and last_refresh_raw:
            try:
                lr_str = str(last_refresh_raw).replace("Z", "+00:00")
                lr_dt = datetime.fromisoformat(lr_str)
                if lr_dt.tzinfo is None:
                    lr_dt = lr_dt.replace(tzinfo=timezone.utc)
                delta = datetime.now(timezone.utc) - lr_dt
                if -timedelta(minutes=5) <= delta <= CODEX_MAX_REFRESH_AGE:
                    is_refresh_valid = True
            except Exception:
                is_refresh_valid = False
        info["refreshable"] = is_refresh_valid

        id_token = tokens.get("id_token", "")
        info["status"] = "unknown"
        parts = id_token.split(".") if isinstance(id_token, str) else []
        if len(parts) >= 2:
            padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace"))
            auth_meta = payload.get("https://api.openai.com/auth", {})
            info["plan"] = auth_meta.get("chatgpt_plan_type")
            until_raw = auth_meta.get("chatgpt_subscription_active_until")
            if until_raw:
                info["active_until"] = str(until_raw)[:10]
                try:
                    until_dt = datetime.fromisoformat(str(until_raw).replace("Z", "+00:00"))
                    if until_dt.tzinfo is None:
                        until_dt = until_dt.replace(tzinfo=timezone.utc)
                    if until_dt >= datetime.now(timezone.utc):
                        info["status"] = "active"
                    elif is_refresh_valid:
                        info["status"] = "refreshable"
                    else:
                        info["status"] = "expired"
                except ValueError:
                    info["status"] = "refreshable" if is_refresh_valid else "unknown"
            elif is_refresh_valid:
                info["status"] = "refreshable"
        elif is_refresh_valid:
            info["status"] = "refreshable"
    except Exception as e:
        info["status"] = "unknown"
        info["error"] = str(e)
    return info


def collect_doctor_report(probe_advisors: bool = True, claude_probe_timeout: int = 15) -> Dict[str, Any]:
    """
    Gather the health of every Triad layer as structured data (no printing).

    ``probe_advisors=False`` skips the live Claude round-trip, which otherwise spends a
    Claude Pro turn on every ``triad doctor`` run.
    """
    advisors = get_advisors()
    by_name = {a.get("name"): a for a in advisors}

    # 1. Antigravity
    agy = {"binary": str(AGY_PATH), "present": AGY_PATH.exists()}

    # 2. Claude Code
    claude_cfg = by_name.get("claude", {})
    claude_ready, _ = advisor_is_ready(claude_cfg) if claude_cfg else (False, "")
    claude_bin = str(claude_cfg.get("binary_path") or CLAUDE_PATH)
    claude = {
        "binary": claude_bin,
        "present": claude_ready or CLAUDE_PATH.exists(),
        "enabled": bool(claude_cfg.get("enabled", False)),
        "probe": "skipped",
        "probe_detail": "",
    }
    if probe_advisors and claude["present"] and claude["enabled"]:
        resp = query_configured_advisor("claude", "Respond with OK", mode="general", timeout=claude_probe_timeout, track_circuit=False)
        kind = classify_advisor_response(resp)
        if kind == "limit":
            claude["probe"] = "limit"
        elif kind == "ok" and "OK" in resp:
            claude["probe"] = "online"
        else:
            claude["probe"] = "error"
        claude["probe_detail"] = resp.strip()[:160]
    elif not claude["present"]:
        claude["probe"] = "missing"

    # 3. Codex
    codex_cfg = by_name.get("codex", {})
    codex_ready, _ = advisor_is_ready(codex_cfg) if codex_cfg else (False, "")
    codex_bin = str(codex_cfg.get("binary_path") or CODEX_PATH)
    codex = {
        "binary": codex_bin,
        "present": codex_ready or CODEX_PATH.exists(),
        "enabled": bool(codex_cfg.get("enabled", False)),
        "auth_file": str(CODEX_AUTH),
    }
    codex.update(_decode_codex_auth(CODEX_AUTH))
    codex_has_key = bool(
        os.environ.get("OPENAI_API_KEY", "").strip()
        or os.environ.get("CODEX_API_KEY", "").strip()
        or (codex_cfg.get("env") or {}).get("OPENAI_API_KEY")
        or (codex_cfg.get("env") or {}).get("CODEX_API_KEY")
    )
    codex["has_api_key"] = codex_has_key

    # 4. Hermes / Nous
    nous_authed = False
    general_cascade: List[str] = []
    nous_error = ""
    try:
        try:
            from triad.nous_bridge import get_nous_token, TASK_MODEL_CASCADES
        except ImportError:
            from nous_bridge import get_nous_token, TASK_MODEL_CASCADES
        nous_authed = bool(get_nous_token())
        general_cascade = list(TASK_MODEL_CASCADES.get("general", []))
    except Exception as e:
        nous_error = str(e)
    nous_cfg = by_name.get("nous", {})
    hermes = {
        "binary": str(HERMES_PATH),
        "present": HERMES_PATH.exists(),
        "nous_authed": nous_authed,
        "nous_enabled": bool(nous_cfg.get("enabled", False)),
        "nous_priority": nous_cfg.get("priority"),
        "nous_lead_model": general_cascade[0] if general_cascade else None,
        "nous_error": nous_error,
        "relay_port": PORT_HERMES_RELAY,
        "relay_listening": is_port_open("127.0.0.1", PORT_HERMES_RELAY),
    }

    # 5. Local subsystems (parallel loopback probe for zero latency)
    from concurrent.futures import ThreadPoolExecutor

    subsystem_targets = {
        "pieces_os": PORT_PIECES_OS,
        "exocortex_daemon": PORT_EXOCORTEX_DAEMON,
        "pieces_proxy": PORT_PIECES_PROXY,
        "pieces_for_all": PORT_PIECES_FOR_ALL,
        "agent_mesh": PORT_AGENT_MESH_MCP,
        "neo4j": PORT_NEO4J_BOLT,
        "llama": local_llm_port(),
        "triad_server": PORT_TRIAD_SERVER,
    }
    with ThreadPoolExecutor(max_workers=len(subsystem_targets)) as executor:
        futures = {k: executor.submit(is_port_open, "127.0.0.1", port) for k, port in subsystem_targets.items()}
        local = {k: {"port": subsystem_targets[k], "online": futures[k].result()} for k in subsystem_targets}

    circuits = snapshot_circuits()
    open_circuits = {
        name for name, entry in (circuits.get("advisors") or {}).items()
        if isinstance(entry, dict) and entry.get("state") == "open"
    }

    usable: List[str] = []
    prod_advisors = get_advisors(enabled_only=True, production_only=True)
    for adv in prod_advisors:
        name = str(adv.get("name") or "")
        if not name or name in open_circuits or is_circuit_open(name):
            continue
        ready, _ = advisor_is_ready(adv)
        if not ready:
            continue
        if name == "claude" and claude["probe"] in ("error", "limit", "missing"):
            continue
        if name == "codex":
            if codex["status"] == "expired" and not codex["has_api_key"]:
                continue
            if codex["status"] == "missing" and not codex["has_api_key"]:
                continue
        if name == "nous" and not hermes["nous_authed"]:
            continue
        usable.append(name)

    warnings: List[str] = []
    if claude["probe"] == "limit" or is_circuit_open("claude"):
        warnings.append("Claude Code is at its session limit; failover to the next advisor is armed.")
    if claude["probe"] == "error":
        warnings.append(f"Claude Code probe failed: {claude['probe_detail']}")
    if codex["enabled"] and codex["status"] == "expired" and not codex["has_api_key"]:
        warnings.append(f"Codex ChatGPT subscription appears expired (active until {codex['active_until']}).")
    if codex["enabled"] and codex["status"] == "missing" and not codex["has_api_key"]:
        warnings.append(f"Codex auth cache not found at {CODEX_AUTH}; run 'codex login' or set OPENAI_API_KEY.")
    if codex["enabled"] and codex["status"] == "unknown" and not codex["has_api_key"]:
        warnings.append("Codex authentication is unverified; operating with session cache.")
    if hermes["nous_enabled"] and not hermes["nous_authed"]:
        warnings.append("Nous advisor is enabled but no NOUS_API_KEY / Hermes auth.json token was found.")
    for name, entry in (circuits.get("advisors") or {}).items():
        if isinstance(entry, dict) and entry.get("state") == "open":
            rem = entry.get("remaining_seconds", 0)
            warnings.append(f"Advisor '{name}' circuit is open ({entry.get('reason')}, {rem}s remaining).")

    return {
        "healthy": bool(usable),
        "usable_advisors": usable,
        "warnings": warnings,
        "antigravity": agy,
        "claude": claude,
        "codex": codex,
        "hermes": hermes,
        "local": local,
        "circuits": circuits,
    }


def _render_doctor_report(report: Dict[str, Any]) -> None:
    def flag(ok: bool, yes: str = "OK", no: str = "MISSING") -> str:
        return yes if ok else no

    print("================================================================================")
    print("           AUTONOMOUS MULTI-AGENT TRIAD: SYSTEM HEALTH & COST AUDIT              ")
    print("================================================================================")
    print("Policy: STRICT ZERO INCREMENTAL COST (Flat-rate subscriptions & local execution)\n")

    agy = report["antigravity"]
    print("[1] Antigravity (Executive Engine & Context Shield)")
    print(f"    - Binary:       {agy['binary']} ({flag(agy['present'])})")
    print("    - Context:      Up to 2,000,000 tokens")
    print("    - Billing:      $0 extra (Included in Antigravity IDE access)")

    c = report["claude"]
    print("\n[2] Claude Code (Chief Architect & Diff Verifier)")
    print(f"    - Binary:       {c['binary']} ({flag(c['present'])})")
    print(f"    - Subscription: Claude Pro (Flat-rate, $0 extra API cost) | advisors.json enabled={c['enabled']}")
    probe_text = {
        "online": "ONLINE & READY",
        "limit": "PAUSED [Session Limit Hit] -> Auto-Failover armed",
        "error": f"ERROR ({c['probe_detail']})",
        "skipped": "NOT PROBED (--quick)",
        "missing": "BINARY NOT FOUND",
    }.get(c["probe"], c["probe"])
    print(f"    - Status:       {probe_text}")

    x = report["codex"]
    print("\n[3] OpenAI Codex (High-Availability Failover Advisor)")
    print(f"    - Binary:       {x['binary']} ({flag(x['present'])})")
    if x["status"] == "missing":
        print(f"    - Status:       Auth config not found at {x['auth_file']}")
    else:
        plan = (x.get("plan") or "plus").capitalize()
        until = x.get("active_until") or "unknown"
        if x["status"] == "refreshable":
            print(f"    - Plan:         ChatGPT {plan} (subscription claim lapsed {until})")
        else:
            print(f"    - Plan:         ChatGPT {plan} (active until {until})")
        print("    - Mode:         chatgpt OAuth via WebSockets")
        print("    - Billing:      $0 extra (Included in ChatGPT subscription)")
        status_label = "REFRESH TOKEN PRESENT (unverified session)" if x["status"] == "refreshable" else x["status"].upper()
        print(f"    - Status:       {status_label} | advisors.json enabled={x['enabled']}")

    h = report["hermes"]
    print("\n[4] Hermes Agent & Nous Research (Device Specialist & Advisory Member)")
    print(f"    - Binary:       {h['binary']} ({flag(h['present'])})")
    if h["nous_lead_model"]:
        print(f"    - Advisory Lead: {h['nous_lead_model']} (general cascade default, $0 cost)")
    if h["nous_error"]:
        print(f"    - Nous Auth:    ERROR ({h['nous_error']})")
    else:
        print(f"    - Nous Auth:    {'OK (token found)' if h['nous_authed'] else 'MISSING (no NOUS_API_KEY / Hermes auth.json entry)'}")
    advisory_status = "ONLINE" if (h["nous_enabled"] and h["nous_authed"]) else "OFFLINE"
    print(f"    - Advisory:     {advisory_status} (advisors.json enabled={h['nous_enabled']}, priority {h['nous_priority'] if h['nous_priority'] is not None else 'n/a'})")
    relay = f"Port {h['relay_port']} LISTENING (Phone bridge connected)" if h["relay_listening"] else f"Port {h['relay_port']} STANDBY (Will accept connection from com.hermesandroid.bridge)"
    print(f"    - Android Relay: {relay}")

    loc = report["local"]
    print("\n[5] Local Subsystems (On-Device Local Memory & Execution)")
    subsystem_labels = [
        ("pieces_os", "PiecesOS"),
        ("exocortex_daemon", "Exocortex Daemon"),
        ("pieces_proxy", "Pieces Proxy"),
        ("pieces_for_all", "Pieces Gateway"),
        ("agent_mesh", "Agent Mesh MCP"),
        ("neo4j", "Neo4j Graph"),
        ("llama", "llama.cpp"),
        ("triad_server", "Triad HTTP"),
    ]
    for key, label in subsystem_labels:
        sub = loc.get(key)
        if sub:
            st = "ONLINE" if sub["online"] else "OFFLINE"
            if key == "triad_server":
                st = "LISTENING" if sub["online"] else "NOT RUNNING"
            print(f"    - {label:<17} {st:<11} (port {sub['port']})")

    circ = report.get("circuits") or {}
    print("\n[6] Advisor Circuits (skip open advisors instead of waiting out their timeout)")
    if not circ.get("enabled", True):
        print("    - Disabled (TRIAD_CIRCUIT=0)")
    else:
        advisors_circ = circ.get("advisors") or {}
        if not advisors_circ:
            print("    - All closed (no recent failures)")
        else:
            for name, entry in advisors_circ.items():
                if not isinstance(entry, dict):
                    continue
                state = str(entry.get("state") or "closed").upper()
                if state == "OPEN":
                    print(f"    - {name}: OPEN ({entry.get('reason')}, {entry.get('remaining_seconds', 0)}s remaining)")
                else:
                    print(f"    - {name}: closed")
        if circ.get("path"):
            print(f"    - State:        {circ['path']}")

    print("\n================================================================================")
    if report["healthy"]:
        print(f"TRIAD AUDIT SUMMARY: HEALTHY. Usable advisors: {', '.join(report['usable_advisors'])}.")
    else:
        print("TRIAD AUDIT SUMMARY: DEGRADED. No enabled advisor is currently usable.")
    for w in report["warnings"]:
        print(f"  ! {w}")
    print("================================================================================\n")


def cmd_doctor(args):
    """
    Run the diagnostic audit across all platform layers.

    Exit code is 0 when at least one enabled advisor is usable, otherwise 1 - so the
    command is meaningful in scripts (``scripts/verify.ps1`` previously always succeeded).
    ``--quick`` skips the live Claude probe; ``--json`` emits the structured report.
    """
    if getattr(args, "reset_circuits", False):
        reset_circuit(None)
        print("[Triad] Cleared advisor circuit-breaker cooldowns.")
    if getattr(args, "clear_cache", False):
        try:
            from triad.response_cache import clear_cache
        except ImportError:
            from response_cache import clear_cache
        removed = clear_cache()
        print(f"[Triad] Cleared {removed} cached advisor response(s).")
    quick = bool(getattr(args, "quick", False))
    report = collect_doctor_report(probe_advisors=not quick)
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2, default=str))
    else:
        _render_doctor_report(report)
    if not report["healthy"]:
        sys.exit(1)
