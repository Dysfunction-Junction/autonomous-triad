"""Triad Agent - Autonomous Zero-Cost Terminal AI Agent.

Inspired by LMSYS RouteLLM, Aider Architect/Editor pairing, and LiteLLM Circuit Breakers.
Provides an interactive and single-shot autonomous coding agent with a 3-tier model waterfall
(Claude/Codex -> Nous Research Free -> Local llama-server).
"""

try:
    from triad.agent.cli import main as agent_main
except ImportError:
    from agent.cli import main as agent_main

__all__ = ["agent_main"]
