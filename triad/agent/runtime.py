"""Autonomous Agent Execution Engine & Waterfall Dispatcher.

Orchestrates multi-turn autonomous tool execution loops across the 3-tier zero-cost waterfall:
  Tier 1: Claude 3.7 Sonnet / Codex (Primary Subscription Limit)
  Tier 2: Nous Research Free (stepfun/step-3.7-flash:free via auth.json)
  Tier 3: Local llama-server (:8080)
"""

import os
import re
import sys
import json
import time
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable

try:
    from triad.agent.router import ZeroCostRouter, ModelTier, RoutingDecision, NOUS_AUTH_PATH, LOCAL_LLAMA_URL
    from triad.agent.tools import ToolRegistry
    from triad.agent.tracker import RollingWindowTracker
except ImportError:
    from agent.router import ZeroCostRouter, ModelTier, RoutingDecision, NOUS_AUTH_PATH, LOCAL_LLAMA_URL
    from agent.tools import ToolRegistry
    from agent.tracker import RollingWindowTracker

DEFAULT_SESSION_DIR = Path.home() / ".triad" / "sessions"


class AgentRuntime:
    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        auto_approve: bool = False,
        router: Optional[ZeroCostRouter] = None,
        max_turns: int = 25
    ):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.auto_approve = auto_approve
        self.tools = ToolRegistry(workspace_root=self.workspace_root, auto_approve=self.auto_approve)
        self.tracker = RollingWindowTracker()
        self.router = router or ZeroCostRouter(tracker=self.tracker)
        self.max_turns = max_turns
        self.session_id = f"session_{int(time.time())}"
        self.history: List[Dict[str, str]] = []

    def _get_system_prompt(self) -> str:
        return f"""You are Triad Agent, an autonomous coding and systems agent working directly in {self.workspace_root}.
You execute tasks by thinking, inspecting the workspace, and taking concrete actions using workspace tools.

AVAILABLE TOOLS:
1. read_file(path: str, start_line: int = 1, end_line: int = 500)
2. write_file(path: str, content: str)
3. edit_file(path: str, target: str, replacement: str)
4. list_dir(path: str = ".", pattern: str = "*", recursive: bool = false)
5. search_code(pattern: str, path: str = ".")
6. run_command(command: str)

TO CALL A TOOL:
Output a single tool call block formatted exactly like this:
```tool_call
{{
  "name": "tool_name",
  "arguments": {{
    "arg1": "value1"
  }}
}}
```
After you output a tool call, wait for the tool output to be provided in the next turn.
When your task is complete or you have answered the user, output your final response without tool calls.
Always be concise, surgical, and fact-based. Never leave placeholders.
"""

    def _get_nous_api_key(self) -> Optional[str]:
        if NOUS_AUTH_PATH.exists():
            try:
                data = json.loads(NOUS_AUTH_PATH.read_text(encoding="utf-8"))
                return data.get("api_key") or data.get("access_token") or data.get("token")
            except Exception:
                pass
        return os.environ.get("NOUS_API_KEY")

    def _call_http_openai_compatible(
        self,
        base_url: str,
        model: str,
        messages: List[Dict[str, str]],
        api_key: Optional[str] = None,
        timeout: int = 120,
        max_tokens: int = 2048
    ) -> str:
        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

    def _call_tier_primary(self, messages: List[Dict[str, str]]) -> str:
        """Invokes primary subscription advisor (Claude Code / Codex) via local CLI wrapper."""
        # Check if claude CLI exists
        claude_bin = Path.home() / ".local" / "bin" / "claude.exe"
        if not claude_bin.exists():
            claude_bin = Path("claude")

        # Format conversation transcript into a prompt for claude -p
        conversation_text = ""
        for m in messages:
            role = m["role"].upper()
            content = m["content"]
            conversation_text += f"\n--- {role} ---\n{content}\n"
        conversation_text += "\nAssistant response:\n"

        cmd = [str(claude_bin), "-p"]
        if self.auto_approve:
            cmd.append("--dangerously-skip-permissions")
        res = subprocess.run(
            cmd,
            input=conversation_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180
        )
        if res.returncode != 0:
            err = res.stderr or res.stdout
            if "rate limit" in err.lower() or "usage limit" in err.lower() or "429" in err:
                raise RuntimeError(f"RATE_LIMIT: {err[:200]}")
            raise RuntimeError(f"CLI Error: {err[:200]}")
        return res.stdout.strip()

    def _dispatch_waterfall(
        self,
        decision: RoutingDecision,
        messages: List[Dict[str, str]],
        on_status: Optional[Callable[[str], None]] = None
    ) -> Tuple[str, ModelTier]:
        """Executes LLM completion across the 3-tier waterfall with automatic fallback."""
        tiers_to_try = [decision.selected_tier] + decision.fallback_chain
        last_error = None

        for tier in tiers_to_try:
            if on_status:
                on_status(f"Querying [{tier.value}] model...")

            try:
                if tier == ModelTier.TIER_1_PRIMARY:
                    text = self._call_tier_primary(messages)
                    self.tracker.record_request(provider="primary", model=decision.model_name)
                    return text, tier

                elif tier == ModelTier.TIER_2_CLOUD_FREE:
                    key = self._get_nous_api_key()
                    text = self._call_http_openai_compatible(
                        base_url="https://inference-api.nousresearch.com/v1",
                        model="stepfun/step-3.7-flash:free",
                        messages=messages,
                        api_key=key,
                        timeout=90
                    )
                    self.tracker.record_request(provider="nous_free", model="stepfun/step-3.7-flash:free")
                    return text, tier

                elif tier == ModelTier.TIER_3_LOCAL:
                    text = self._call_http_openai_compatible(
                        base_url=LOCAL_LLAMA_URL,
                        model="default",
                        messages=messages,
                        timeout=120,
                        max_tokens=1024
                    )
                    self.tracker.record_request(provider="llama_local", model="qwen3:1.7b")
                    return text, tier

            except Exception as exc:
                err_msg = str(exc)
                last_error = err_msg
                if on_status:
                    on_status(f"Tier [{tier.value}] failed ({err_msg[:80]}). Cascading down waterfall...")

                if tier == ModelTier.TIER_1_PRIMARY and "rate_limit" in err_msg.lower():
                    self.tracker.mark_circuit_break("primary", cooldown_seconds=600)
                elif tier == ModelTier.TIER_2_CLOUD_FREE and ("429" in err_msg or "rate limit" in err_msg.lower()):
                    self.tracker.mark_circuit_break("nous_free", cooldown_seconds=300)

        # If everything failed
        raise RuntimeError(f"All waterfall tiers exhausted. Last error: {last_error}")

    def _parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Extracts JSON tool call block from model response."""
        pattern = r"```(?:tool_call|json)?\s*(\{[\s\S]*?\})\s*```"
        match = re.search(pattern, text)
        if match:
            try:
                data = json.loads(match.group(1))
                if "name" in data:
                    return data
            except Exception:
                pass
        return None

    def _execute_tool(self, tool_call: Dict[str, Any]) -> str:
        """Routes tool call to ToolRegistry."""
        name = tool_call.get("name")
        args = tool_call.get("arguments", {})

        method = getattr(self.tools, name, None)
        if not method or not callable(method):
            return json.dumps({"error": f"Unknown tool: {name}"})

        try:
            res = method(**args)
            return json.dumps(res, indent=2)
        except Exception as exc:
            return json.dumps({"error": f"Tool execution failed: {exc}"})

    def run_turn(
        self,
        user_input: str,
        force_tier: Optional[str] = None,
        on_status: Optional[Callable[[str], None]] = None,
        on_text: Optional[Callable[[str], None]] = None
    ) -> str:
        """Runs an autonomous multi-turn loop until completion or max_turns."""
        # 1. Routing decision
        decision = self.router.select_route(
            prompt=user_input,
            context_length=sum(len(m.get("content", "")) for m in self.history),
            force_tier=force_tier
        )

        if on_status:
            on_status(f"\033[1;34m[Route Selected]\033[0m {decision.selected_tier.value} ({decision.reason})")

        # 2. Append user message
        if not self.history:
            self.history.append({"role": "system", "content": self._get_system_prompt()})

        self.history.append({"role": "user", "content": user_input})

        current_turn = 0
        final_response = ""

        while current_turn < self.max_turns:
            current_turn += 1

            # Dispatch to LLM via waterfall
            assistant_reply, active_tier = self._dispatch_waterfall(
                decision=decision,
                messages=self.history,
                on_status=on_status
            )

            # Check for tool call
            tool_call = self._parse_tool_call(assistant_reply)

            if tool_call:
                tool_name = tool_call.get("name")
                if on_status:
                    on_status(f"\033[1;36m[Tool Action]\033[0m {tool_name}({json.dumps(tool_call.get('arguments', {}))[:80]}...)")

                # Record assistant turn with tool call
                self.history.append({"role": "assistant", "content": assistant_reply})

                # Execute tool
                tool_output = self._execute_tool(tool_call)

                # Feed tool result back to agent
                self.history.append({
                    "role": "user",
                    "content": f"TOOL_OUTPUT for {tool_name}:\n{tool_output}"
                })
            else:
                # No tool call, this is the final answer
                self.history.append({"role": "assistant", "content": assistant_reply})
                final_response = assistant_reply
                if on_text:
                    on_text(assistant_reply)
                break

        if current_turn >= self.max_turns and not final_response:
            final_response = f"[Turn limit reached] The agent reached the maximum turn limit ({self.max_turns}) without completing the task."
            if on_text:
                on_text(final_response)

        # Save session transcript
        self._save_session()
        return final_response

    def _save_session(self) -> None:
        try:
            DEFAULT_SESSION_DIR.mkdir(parents=True, exist_ok=True)
            sess_file = DEFAULT_SESSION_DIR / f"{self.session_id}.json"
            sess_file.write_text(json.dumps({
                "session_id": self.session_id,
                "timestamp": time.time(),
                "workspace": str(self.workspace_root),
                "messages": self.history
            }, indent=2), encoding="utf-8")

            # Update latest symlink/file
            latest = DEFAULT_SESSION_DIR / "latest.json"
            latest.write_text(json.dumps({"latest_session": self.session_id}), encoding="utf-8")
        except Exception:
            pass

    def load_latest_session(self) -> bool:
        """Resumes the most recent session if available."""
        latest_file = DEFAULT_SESSION_DIR / "latest.json"
        if not latest_file.exists():
            return False
        try:
            info = json.loads(latest_file.read_text(encoding="utf-8"))
            sess_id = info.get("latest_session")
            target = DEFAULT_SESSION_DIR / f"{sess_id}.json"
            if target.exists():
                data = json.loads(target.read_text(encoding="utf-8"))
                self.session_id = sess_id
                self.history = data.get("messages", [])
                return True
        except Exception:
            pass
        return False
