"""Interactive CLI Entrypoint for Triad Agent.

Provides an interactive REPL and non-interactive print mode matching 'agy' ergonomics:
  triad agent                 # Launch interactive session
  triad agent -p "prompt"     # Single-shot execution
  triad agent -c              # Resume most recent conversation
  triad agent -y              # Auto-approve tool modifications
"""

import os
import sys
import time
import argparse
import urllib.request
from pathlib import Path

try:
    from triad.agent.runtime import AgentRuntime
    from triad.agent.router import ZeroCostRouter, LOCAL_LLAMA_URL
except ImportError:
    from agent.runtime import AgentRuntime
    from agent.router import ZeroCostRouter, LOCAL_LLAMA_URL


def read_piped_stdin() -> str:
    """Non-blocking read of stdin on Windows and POSIX."""
    if sys.stdin.isatty():
        return ""
    try:
        if os.name == "nt":
            import msvcrt
            import ctypes
            from ctypes import wintypes
            try:
                handle = msvcrt.get_osfhandle(sys.stdin.fileno())
                avail = wintypes.DWORD()
                if ctypes.windll.kernel32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(avail), None):
                    if avail.value > 0:
                        return sys.stdin.read(avail.value).strip()
            except Exception:
                return ""
        else:
            import select
            if select.select([sys.stdin], [], [], 0.0)[0]:
                return sys.stdin.read().strip()
    except Exception:
        pass
    return ""


def print_banner():
    banner = r"""
  _____     _           _ 
 |_   _| __(_) __ _  __| |   Triad Terminal Agent
   | || '__| |/ _` |/ _` |   Local Orchestrator & Autonomous Engineer
   | || |  | | (_| | (_| |   Engine: Local llama-server (:8080)
   |_||_|  |_|\__,_|\__,_|   Chief Architect: Claude 3.7 / Codex (On-Demand)
"""
    print(f"\033[1;36m{banner}\033[0m")
    print("  Talk to \033[1;32mTriad\033[0m directly. Chief Architect is on standby for big decisions.")
    print("  Commands: \033[1m/architect <query>\033[0m, \033[1m/cancel\033[0m, \033[1m/status\033[0m, \033[1m/clear\033[0m, \033[1m/exit\033[0m (Ctrl+C cancels turn)\n")


def print_status(runtime: AgentRuntime):
    stats = runtime.tracker.get_window_stats(provider="primary")
    util = stats.get("utilization", 0.0) * 100
    turns = stats.get("total_turns", 0)
    tokens = stats.get("total_tokens", 0)
    cooling = stats.get("is_cooling_down", False)
    thresh, reason = runtime.router.get_effective_threshold()

    # Probe local llama server health
    local_health = "OFFLINE"
    try:
        req = urllib.request.Request(f"{LOCAL_LLAMA_URL.rstrip('/')}/health", headers={"User-Agent": "triad-agent"})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            if r.status == 200:
                local_health = "ONLINE / HEALTHY (Port 8080)"
    except Exception:
        pass

    print("\n\033[1;34m=== Triad Agent Status & Quota ===\033[0m")
    print(f"  Primary 5-Hour Utilization: {util:.1f}% ({turns} turns, {tokens} tokens)")
    print(f"  Primary Cooldown Status:    {'COOLING DOWN' if cooling else 'ACTIVE / READY'}")
    print(f"  RouteLLM Threshold (c):     {thresh:.2f} ({reason})")
    print(f"  Local Llama Server:         {LOCAL_LLAMA_URL} ({local_health})")
    print(f"  Active Session ID:          {runtime.session_id}")
    print(f"  Workspace:                  {runtime.workspace_root}\n")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="triad agent",
        description="Autonomous Zero-Cost Terminal AI Agent with RouteLLM Waterfall."
    )
    parser.add_argument(
        "-p", "--print", "--prompt",
        dest="prompt",
        type=str,
        help="Run a single prompt non-interactively and print the response."
    )
    parser.add_argument(
        "-c", "--continue",
        dest="resume",
        action="store_true",
        help="Resume the most recent conversation session."
    )
    parser.add_argument(
        "-y", "--auto", "--dangerously-skip-permissions",
        dest="auto_approve",
        action="store_true",
        help="Auto-approve file edits, writes, and shell commands without prompting."
    )
    parser.add_argument(
        "--heavy", "--pro", "--architect", "--council",
        dest="force_heavy",
        action="store_true",
        help="Delegate to Chief Architect (Claude 3.7 Sonnet / Codex)."
    )
    parser.add_argument(
        "--free", "--nous",
        dest="force_free",
        action="store_true",
        help="Force cloud free tier (stepfun/step-3.7-flash:free)."
    )
    parser.add_argument(
        "--local", "--fast",
        dest="force_local",
        action="store_true",
        help="Force local llama-server on port 8080 (Triad default)."
    )
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    runtime = AgentRuntime(auto_approve=args.auto_approve)

    if args.resume:
        resumed = runtime.load_latest_session()
        if resumed:
            sys.stderr.write(f"\033[1;32m[Resumed]\033[0m Session {runtime.session_id} ({len(runtime.history)} prior messages loaded)\n")
        else:
            sys.stderr.write("\033[1;33m[Notice]\033[0m No prior session found to resume. Starting fresh session.\n")

    force_tier = None
    if args.force_heavy:
        force_tier = "architect"
    elif args.force_free:
        force_tier = "free"
    elif args.force_local:
        force_tier = "local"

    # Check for piped input from stdin without blocking
    piped_stdin = read_piped_stdin()

    # 1. Non-interactive / Print mode
    if args.prompt or piped_stdin:
        combined_prompt = args.prompt or ""
        if piped_stdin:
            combined_prompt = f"{combined_prompt}\n\n[Piped Input]:\n{piped_stdin}" if combined_prompt else piped_stdin

        def on_status(msg):
            # Print status to stderr in print mode so stdout remains clean for piping
            sys.stderr.write(f"{msg}\n")
            sys.stderr.flush()

        try:
            res = runtime.run_turn(
                user_input=combined_prompt,
                force_tier=force_tier,
                on_status=on_status
            )
            print(res)
            return 0
        except KeyboardInterrupt:
            sys.stderr.write("\n[Interrupted / Canceled]\n")
            runtime.abort_current_turn()
            return 130

    # 2. Interactive REPL Mode
    print_banner()
    last_sigint = 0.0
    while True:
        try:
            user_input = input("\033[1;32mtriad\033[0m> ").strip()
        except KeyboardInterrupt:
            now = time.monotonic()
            if now - last_sigint < 2.0:
                print("\nExiting Triad Agent. Goodbye!")
                break
            last_sigint = now
            print("\n\033[1;30m(Press Ctrl+C again or type /exit to quit)\033[0m")
            continue
        except EOFError:
            print("\nExiting Triad Agent. Goodbye!")
            break

        if not user_input:
            continue

        turn_force_tier = force_tier
        lowered = user_input.lower()
        if lowered in ("/exit", "/quit", "exit", "quit"):
            print("Exiting Triad Agent. Goodbye!")
            break
        elif lowered in ("/cancel", "/abort"):
            canceled = runtime.abort_current_turn()
            if canceled:
                print("\033[1;33m[Canceled]\033[0m Active turn state cleared.")
            else:
                print("No active turn to cancel. (Press Ctrl+C during a running turn to cancel it)")
            continue
        elif lowered == "/status":
            print_status(runtime)
            continue
        elif lowered == "/clear":
            runtime.history = []
            print("\033[1;33m[Cleared]\033[0m Conversation history reset.")
            continue
        elif lowered == "/help":
            print("\nCommands:")
            print("  \033[1m/architect <query>\033[0m  Delegate a big decision directly to Claude 3.7 / Codex")
            print("  \033[1m/cancel\033[0m             Cancel or clear active turn state")
            print("  \033[1m/status\033[0m             Show 5-hour quota and local engine health")
            print("  \033[1m/clear\033[0m              Reset session conversation history")
            print("  \033[1m/exit\033[0m               Exit Triad CLI (or Ctrl+C twice)\n")
            continue
        elif lowered.startswith(("/architect", "/council", "/ask-claude")):
            parts = user_input.split(maxsplit=1)
            if len(parts) == 1:
                print("Usage: /architect <question or architectural decision>")
                continue
            turn_force_tier = "architect"
            user_input = parts[1]

        def on_status(msg):
            print(msg)

        try:
            print()
            reply = runtime.run_turn(
                user_input=user_input,
                force_tier=turn_force_tier,
                on_status=on_status
            )
            if reply:
                print(reply)
            print()
        except KeyboardInterrupt:
            print("\n\033[1;33m[Turn Canceled by user (Ctrl+C)]\033[0m\n")
            runtime.abort_current_turn()
        except Exception as exc:
            print(f"\n\033[1;31m[Error]\033[0m {exc}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
