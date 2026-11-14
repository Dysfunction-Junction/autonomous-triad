"""Content-addressed response cache for Triad advisor and synthesis calls."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

try:
    from triad.paths import state_dir
    from triad.procutil import is_failed_advisor_response
except ImportError:
    from paths import state_dir
    from procutil import is_failed_advisor_response

PROMPT_SCHEMA_VERSION = "1"
DEFAULT_TTL_SECONDS = 7 * 24 * 3600
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


def cache_enabled() -> bool:
    """Return False when TRIAD_CACHE disables caching."""
    raw = os.environ.get("TRIAD_CACHE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def cache_ttl_seconds(override: Optional[int] = None) -> int:
    """Return configured cache TTL in seconds."""
    if override is not None:
        return max(0, int(override))
    raw = os.environ.get("TRIAD_CACHE_TTL", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return DEFAULT_TTL_SECONDS


def cache_max_bytes(override: Optional[int] = None) -> int:
    """Return configured max cache size in bytes."""
    if override is not None:
        return max(0, int(override))
    raw = os.environ.get("TRIAD_CACHE_MAX_BYTES", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return DEFAULT_MAX_BYTES


def cache_dir(base_dir: Optional[Path] = None) -> Path:
    """Return root directory for cached responses (under TRIAD_STATE_DIR by default)."""
    if base_dir is not None:
        return Path(base_dir)
    return state_dir() / "cache"


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def make_cache_key(
    advisor_name: str,
    mode: str,
    task: Optional[str],
    prompt: str,
    diff: Optional[str] = None,
    context: Optional[str] = None,
    *,
    repo_head: str = "",
    model_sig: str = "",
    schema_version: str = PROMPT_SCHEMA_VERSION,
) -> str:
    """Compute a deterministic SHA-256 key for an advisor query."""
    parts = (
        (advisor_name or "").strip().lower(),
        (mode or "general").strip().lower(),
        (task or "").strip().lower(),
        (repo_head or "").strip(),
        (model_sig or "").strip(),
        str(schema_version),
        _normalize_text(prompt),
        _normalize_text(diff),
        _normalize_text(context),
    )
    h = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8", errors="replace")
        h.update(f"{len(encoded)}:".encode("ascii"))
        h.update(encoded)
    return h.hexdigest()


def make_synthesis_cache_key(
    adv1_name: str,
    adv2_name: str,
    resp1: str,
    resp2: str,
    *,
    mode: str = "general",
    adversarial: bool = False,
    schema_version: str = PROMPT_SCHEMA_VERSION,
) -> str:
    """Compute a deterministic SHA-256 key for a competition synthesis."""
    h1 = hashlib.sha256((resp1 or "").encode("utf-8", errors="replace")).hexdigest()
    h2 = hashlib.sha256((resp2 or "").encode("utf-8", errors="replace")).hexdigest()
    pair = f"{(adv1_name or '').lower()}+{(adv2_name or '').lower()}"
    return make_cache_key(
        advisor_name=f"synthesis:{pair}",
        mode=f"{mode}:{'adv' if adversarial else 'std'}",
        task="judge",
        prompt=f"{h1}|{h2}",
        schema_version=schema_version,
    )


def _entry_path(root: Path, key: str) -> Path:
    return root / key[:2] / f"{key}.json"


def get_cached_response(
    key: str,
    *,
    ttl: Optional[int] = None,
    base_dir: Optional[Path] = None,
) -> Optional[str]:
    """Return cached response if present and unexpired, else None."""
    if not cache_enabled() or not key:
        return None
    path = _entry_path(cache_dir(base_dir), key)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    response = data.get("response")
    if not isinstance(response, str) or not response.strip():
        return None
    if is_failed_advisor_response(response):
        return None
    try:
        created = float(data.get("created", 0.0))
    except (TypeError, ValueError):
        return None
    effective_ttl = cache_ttl_seconds(ttl)
    if effective_ttl <= 0 or (time.time() - created) > effective_ttl:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    try:
        os.utime(path, None)
    except OSError:
        pass
    return response


def _prune_lru(root: Path, max_bytes: int) -> None:
    """Evict oldest-mtime cache entries until total size is within max_bytes."""
    if max_bytes <= 0 or not root.exists():
        return
    entries = []
    total = 0
    for p in root.rglob("*.json"):
        try:
            st = p.stat()
        except OSError:
            continue
        entries.append((st.st_mtime, st.st_size, p))
        total += st.st_size
    if total <= max_bytes:
        return
    entries.sort(key=lambda item: item[0])
    for _, size, p in entries:
        if total <= max_bytes:
            break
        try:
            p.unlink(missing_ok=True)
            total -= size
        except OSError:
            pass


def put_cached_response(
    key: str,
    response: str,
    *,
    advisor: str = "",
    ttl: Optional[int] = None,
    base_dir: Optional[Path] = None,
    max_bytes: Optional[int] = None,
) -> bool:
    """Atomically write a successful advisor response to cache."""
    if not cache_enabled() or not key:
        return False
    if (advisor or "").strip().lower() == "mock":
        return False
    if not isinstance(response, str) or not response.strip():
        return False
    if is_failed_advisor_response(response):
        return False

    effective_ttl = cache_ttl_seconds(ttl)
    if effective_ttl <= 0:
        return False

    root = cache_dir(base_dir)
    target = _entry_path(root, key)
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(
        {
            "response": response,
            "advisor": advisor,
            "created": time.time(),
            "ttl": effective_ttl,
        },
        ensure_ascii=False,
    )

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(target.parent),
            prefix=f".{key[:8]}.",
            suffix=".tmp",
            delete=False,
        ) as tf:
            tmp_path = tf.name
            tf.write(payload)
        os.replace(tmp_path, target)
        tmp_path = None
    except Exception:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False

    _prune_lru(root, cache_max_bytes(max_bytes))
    return True


def clear_cache(base_dir: Optional[Path] = None) -> int:
    """Delete all cached response files and return the number removed."""
    root = cache_dir(base_dir)
    if not root.exists():
        return 0
    removed = 0
    for pattern in ("*.json", "*.tmp"):
        for p in list(root.rglob(pattern)):
            try:
                p.unlink(missing_ok=True)
                if pattern == "*.json":
                    removed += 1
            except OSError:
                pass
    for d in sorted(root.rglob("*"), reverse=True):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass
    return removed
