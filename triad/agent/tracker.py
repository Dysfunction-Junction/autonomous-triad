"""Usage & Sliding Window Tracker for Zero-Cost Model Routing.

Inspired by LiteLLM's cooldown circuit breakers and Anthropic's rolling 5-hour usage windows.
Maintains a local append-only ledger in ~/.triad/usage_ledger.json to calculate real-time
utilization and proactively shed load before hitting hard provider rate limits.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any

def _default_ledger_path() -> Path:
    try:
        from triad.paths import write_state_file
    except ImportError:
        from paths import write_state_file
    path = write_state_file("usage_ledger.json")
    legacy = Path.home() / ".triad" / "usage_ledger.json"
    try:
        if not path.exists() and legacy.is_file() and legacy.resolve() != path.resolve():
            path.write_bytes(legacy.read_bytes())
    except OSError:
        pass
    return path


DEFAULT_LEDGER_PATH = _default_ledger_path()
FIVE_HOURS_SECONDS = 18000  # 5 hours * 3600s
MAX_PRIMARY_TURNS_PER_WINDOW = 45
MAX_PRIMARY_TOKENS_PER_WINDOW = 120_000
DEFAULT_SOFT_LIMIT = 0.80  # Proactively switch non-essential traffic at 80% usage


class RollingWindowTracker:
    def __init__(self, ledger_path: Path = DEFAULT_LEDGER_PATH):
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_ledger_file()

    def _ensure_ledger_file(self) -> None:
        if not self.ledger_path.exists():
            initial_data = {
                "version": 1,
                "requests": [],
                "cooldowns": {},  # provider -> timestamp when cooldown ends
            }
            try:
                self.ledger_path.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")
            except Exception:
                pass

    def _load_ledger(self) -> Dict[str, Any]:
        self._ensure_ledger_file()
        try:
            return json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1, "requests": [], "cooldowns": {}}

    def _save_ledger(self, data: Dict[str, Any]) -> None:
        try:
            # Prune records older than 24 hours to keep file compact
            cutoff = time.time() - 86400
            data["requests"] = [r for r in data.get("requests", []) if r.get("timestamp", 0) > cutoff]
            tmp_path = self.ledger_path.with_suffix(f".tmp.{os.getpid()}")
            tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp_path, self.ledger_path)
        except Exception:
            pass

    def record_request(
        self,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        task_type: str = "interactive",
        status: str = "success"
    ) -> None:
        data = self._load_ledger()
        entry = {
            "timestamp": time.time(),
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "task_type": task_type,
            "status": status,
        }
        data.setdefault("requests", []).append(entry)
        self._save_ledger(data)

    def mark_circuit_break(self, provider: str, cooldown_seconds: int = 300) -> None:
        """Mark a provider as cooling down (e.g. after receiving HTTP 429 or CLI rate limit error)."""
        data = self._load_ledger()
        data.setdefault("cooldowns", {})[provider] = time.time() + cooldown_seconds
        self._save_ledger(data)

    def is_cooling_down(self, provider: str) -> bool:
        """Check if provider is currently in a cooldown window."""
        data = self._load_ledger()
        expiry = data.get("cooldowns", {}).get(provider, 0)
        return time.time() < expiry

    def get_window_stats(self, provider: str = "primary", window_seconds: int = FIVE_HOURS_SECONDS) -> Dict[str, Any]:
        """Compute aggregate turn count and tokens used in the rolling window."""
        data = self._load_ledger()
        now = time.time()
        cutoff = now - window_seconds

        window_requests = [
            r for r in data.get("requests", [])
            if r.get("provider") == provider and r.get("timestamp", 0) > cutoff and r.get("status") == "success"
        ]

        total_turns = len(window_requests)
        total_tokens = sum(r.get("total_tokens", 0) for r in window_requests)

        turn_utilization = total_turns / MAX_PRIMARY_TURNS_PER_WINDOW
        token_utilization = total_tokens / MAX_PRIMARY_TOKENS_PER_WINDOW
        max_utilization = max(turn_utilization, token_utilization)

        return {
            "provider": provider,
            "window_seconds": window_seconds,
            "total_turns": total_turns,
            "total_tokens": total_tokens,
            "utilization": round(max_utilization, 3),
            "soft_limit_reached": max_utilization >= DEFAULT_SOFT_LIMIT,
            "is_cooling_down": self.is_cooling_down(provider),
        }

    def get_utilization(self, provider: str = "primary") -> float:
        return self.get_window_stats(provider=provider).get("utilization", 0.0)

    def is_soft_limit_reached(self, provider: str = "primary", threshold: float = DEFAULT_SOFT_LIMIT) -> bool:
        stats = self.get_window_stats(provider=provider)
        return stats.get("utilization", 0.0) >= threshold or stats.get("is_cooling_down", False)
