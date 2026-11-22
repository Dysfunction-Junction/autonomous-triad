# GC-F9: Retired metrics

Purpose: Mark metrics that are no longer tracked and exclude them from reports.

A metric can be flagged as ``retired`` with a retirement timestamp. Retired metrics
are excluded from ``triad doctor`` reports while their historical data is preserved
for audit purposes.

````python
from triad.metrics import retire_metric, is_metric_retired, get_retired_metrics

# Retire a metric called "latency_ms"
retire_metric("latency_ms", reason="replaced by new instrumentation")

# Check if a metric is retired
if is_metric_retired("latency_ms"):
    print("This metric is no longer tracked")

# List all retired metrics
retired = get_retired_metrics()
for name, reason, retired_at in retired:
    print(f"Retired: {name} ({reason}) since {retired_at}")
````

````python
# Internal API (not part of the public stable interface)

def _retire_meta(name: str, reason: str, retired_at: float) -> None:
    """Add *name* to the retired‑metrics store under ``~/.agents/triad/``."""
    store = Path.home() / ".agents" / "triad" / "retired_metrics.json"
    data = []
    if store.is_file():
        try:
            data = __import__("json").load(store)
        except Exception:
            data = []
    data.append({"name": name, "reason": reason, "retired_at": retired_at})
    store.parent.mkdir(parents=True, exist_ok=True)
    with open(store, "w", encoding="utf-8") as f:
        __import__("json").dump(data, f, indent=2)


def retire_metric(name: str, reason: str = "") -> None:
    """Public API: flag *name* as retired.

    *reason* is free‑form explanatory text; if omitted a timestamp‑based
    description is generated.
    """
    import time
    reason = reason or f"retired at {time.strftime('%Y-%m-%d %H:%M:%S')}"
    _retire_meta(name, reason, time.time())


def is_metric_retired(name: str) -> bool:
    """Return ``True`` if *name* appears in the retired‑metrics store."""
    store = Path.home() / ".agents" / "triad" / "retired_metrics.json"
    if not store.is_file():
        return False
    try:
        data = __import__("json").load(store)
        return any(d.get("name") == name for d in data)
    except Exception:
        return False


def get_retired_metrics() -> list[tuple[str, str, float]]:
    """Return ``[(name, reason, retired_at), ...]`` for all retired metrics."""
    store = Path.home() / ".agents" / "triad" / "retired_metrics.json"
    if not store.is_file():
        return []
    try:
        data = __import__("json").load(store)
        return [
            (d.get("name", ""), d.get("reason", ""), d.get("retired_at", 0.0))
            for d in data
        ]
    except Exception:
        return []
````