"""Dynamic Zero-Cost Model Router.

References & Prior Art:
- RouteLLM (LMSYS Org / UC Berkeley, 2024 - Ong et al.):
  Dynamic routing between strong (frontier) and weak/free models using preference scoring
  and thresholding 'c' to achieve 95%+ frontier capability at 50-85% lower usage/token drain.
- Aider (Paul Gauthier, 2023):
  Architect / Editor pattern — routing high-level planning and code synthesis to strong
  reasoners while offloading routine formatting, edits, and tool runs.
- LiteLLM Router:
  Cooldown-aware fallback cascades with circuit breaking.

3-Tier Waterfall:
  Tier 1: Primary Frontier (Claude 3.7 Sonnet / Codex via Triad Bridge) [Paid Subscription Limit]
  Tier 2: Cloud Free-Tier (Nous Research stepfun/step-3.7-flash:free) [Zero Cost Cloud]
  Tier 3: Local Hardware (llama-server :8080 qwen3 / qwen2.5-coder) [Zero Cost Local]
"""

import os
import re
import urllib.request
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

try:
    from triad.agent.tracker import RollingWindowTracker
except ImportError:
    from agent.tracker import RollingWindowTracker

NOUS_AUTH_PATH = Path.home() / "AppData" / "Local" / "hermes" / "auth.json"
LOCAL_LLAMA_URL = "http://127.0.0.1:8080/v1"


class ModelTier(str, Enum):
    TIER_1_PRIMARY = "primary"        # Claude Pro / Codex via Triad Bridge
    TIER_2_CLOUD_FREE = "nous_free"   # stepfun/step-3.7-flash:free via Nous Portal
    TIER_3_LOCAL = "llama_local"      # llama-server.exe on port 8080


@dataclass
class RoutingDecision:
    selected_tier: ModelTier
    model_name: str
    difficulty_score: float
    threshold_c: float
    reason: str
    fallback_chain: list


class RouteLLMClassifier:
    """Lightweight heuristic & matrix-factorization-inspired difficulty scorer.
    
    Evaluates prompt complexity to estimate P(Strong Model Needed) in [0.0, 1.0].
    Prioritizes getting complex, multi-file code right the first time while
    offloading routine syntax fixes, documentation, single-file edits, and batch queries.
    """

    # High complexity indicators (bias towards Tier 1 Strong Model)
    COMPLEXITY_PATTERNS = [
        r"\b(refactor|architect|redesign|migrate|migration|concurrency|race condition)\b",
        r"\b(type\s*error|generic|trait|interface\s+segregation|polymorphism)\b",
        r"\b(state\s*machine|event\s*loop|distributed|deadlock|memory\s*leak)\b",
        r"\b(traceback|stack\s*trace|segfault|undefined\s+is\s+not\s+a\s+function)\b",
        r"\b(security|cryptograph|vulnerability|audit|sanitize)\b",
        r"(diff\s+--git|@@\s+-\d+,\d+\s+\+\d+,\d+\s+@@)",
    ]

    # Low complexity indicators (bias towards Tier 2/3 Free/Local Models)
    ROUTINE_PATTERNS = [
        r"\b(format|lint|prettier|beautify|indent|typo|spelling)\b",
        r"\b(docstring|readme|document|comment|explain\s+this\s+function)\b",
        r"\b(rename\s+variable|extract\s+constant|add\s+logging|print)\b",
        r"\b(regex|generate\s+dummy|json\s+schema|boilerplate)\b",
        r"\b(batch|summarize|list\s+files|find\s+all)\b",
    ]

    def score_prompt(self, prompt: str, context_length: int = 0) -> float:
        """Returns difficulty score in [0.0, 1.0]. Higher = requires stronger model."""
        p_lower = prompt.lower()
        score = 0.40  # Neutral baseline

        # 1. Pattern matching heuristics
        for pattern in self.COMPLEXITY_PATTERNS:
            if re.search(pattern, p_lower):
                score += 0.12

        for pattern in self.ROUTINE_PATTERNS:
            if re.search(pattern, p_lower):
                score -= 0.12

        # 2. Size / Context weight
        # Very short prompts or huge multi-file contexts
        prompt_len = len(prompt)
        if prompt_len > 2500 or context_length > 8000:
            score += 0.15
        elif prompt_len < 80:
            score -= 0.08

        # 3. Code density: ratio of special syntax chars
        code_chars = sum(1 for c in prompt if c in "{}[]()<>=:;/*&$|^~")
        code_ratio = code_chars / max(1, prompt_len)
        if code_ratio > 0.08:
            score += 0.10

        return max(0.05, min(0.95, score))


class ZeroCostRouter:
    """Zero-Cost Multi-Tier Dynamic Router.
    
    Coordinates between:
    - RouteLLM difficulty scoring
    - Rolling 5-hour window tracker (soft limit = 0.80)
    - 3-tier waterfall execution
    """

    def __init__(self, tracker: Optional[RollingWindowTracker] = None, base_threshold_c: float = 0.50):
        self.tracker = tracker or RollingWindowTracker()
        self.classifier = RouteLLMClassifier()
        self.base_threshold_c = base_threshold_c

    def get_effective_threshold(self) -> Tuple[float, str]:
        """Calculates adaptive threshold 'c'.
        
        When primary quota utilization is low, c remains at 0.50 (giving complex tasks to Claude/Codex).
        When primary quota exceeds the 80% soft limit or is cooling down, c dynamically shifts up
        to shed load down to Nous Free / Local compute.
        """
        stats = self.tracker.get_window_stats(provider="primary")
        utilization = stats.get("utilization", 0.0)
        is_cooling = stats.get("is_cooling_down", False)

        if is_cooling:
            return 1.0, f"Primary is cooling down after rate limit (utilization: {utilization*100:.1f}%)"

        if utilization >= 0.80:
            # Proactively shed load: increase c so only ultra-high complexity tasks hit primary
            boost = (utilization - 0.70) * 1.5
            effective_c = min(0.90, self.base_threshold_c + boost)
            return effective_c, f"Primary soft-limit reached ({utilization*100:.1f}% >= 80%); adaptive threshold shifted to {effective_c:.2f}"

        return self.base_threshold_c, f"Primary quota healthy ({utilization*100:.1f}% < 80%)"

    def select_route(
        self,
        prompt: str,
        context_length: int = 0,
        force_tier: Optional[str] = None
    ) -> RoutingDecision:
        """Determines the optimal model tier for the prompt."""
        # 1. User overrides via flags
        if force_tier in ("primary", "pro", "heavy"):
            return RoutingDecision(
                selected_tier=ModelTier.TIER_1_PRIMARY,
                model_name="claude-3-7-sonnet",
                difficulty_score=1.0,
                threshold_c=0.0,
                reason="Explicit user override: --heavy / --pro",
                fallback_chain=[ModelTier.TIER_2_CLOUD_FREE, ModelTier.TIER_3_LOCAL]
            )
        if force_tier in ("free", "nous"):
            return RoutingDecision(
                selected_tier=ModelTier.TIER_2_CLOUD_FREE,
                model_name="stepfun/step-3.7-flash:free",
                difficulty_score=0.0,
                threshold_c=1.0,
                reason="Explicit user override: --free / --nous",
                fallback_chain=[ModelTier.TIER_3_LOCAL]
            )
        if force_tier in ("local", "llama", "fast"):
            return RoutingDecision(
                selected_tier=ModelTier.TIER_3_LOCAL,
                model_name="qwen3:1.7b",
                difficulty_score=0.0,
                threshold_c=1.0,
                reason="Explicit user override: --local / --fast",
                fallback_chain=[]
            )

        # 2. RouteLLM Scoring & Thresholding
        difficulty = self.classifier.score_prompt(prompt, context_length=context_length)
        threshold_c, threshold_reason = self.get_effective_threshold()

        # Decision rule: if difficulty > threshold_c AND primary is healthy -> Tier 1
        if difficulty > threshold_c and not self.tracker.is_cooling_down("primary"):
            return RoutingDecision(
                selected_tier=ModelTier.TIER_1_PRIMARY,
                model_name="claude-3-7-sonnet",
                difficulty_score=round(difficulty, 3),
                threshold_c=round(threshold_c, 3),
                reason=f"Task complexity ({difficulty:.2f}) > threshold ({threshold_c:.2f}). {threshold_reason}.",
                fallback_chain=[ModelTier.TIER_2_CLOUD_FREE, ModelTier.TIER_3_LOCAL]
            )

        # Otherwise route to Cloud Free Tier (Nous) or Local
        return RoutingDecision(
            selected_tier=ModelTier.TIER_2_CLOUD_FREE,
            model_name="stepfun/step-3.7-flash:free",
            difficulty_score=round(difficulty, 3),
            threshold_c=round(threshold_c, 3),
            reason=f"Task complexity ({difficulty:.2f}) <= threshold ({threshold_c:.2f}). {threshold_reason}. Routed to Cloud Free Tier ($0 cost).",
            fallback_chain=[ModelTier.TIER_3_LOCAL]
        )
