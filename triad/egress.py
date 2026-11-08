"""Last-mile cloud disclosure controls. No network or credential loading here."""

import fnmatch
import os
import re
from pathlib import Path

DEFAULT_IGNORES = ("eval/", "*.jsonl", "*.db", "*.sqlite*", ".env*", "secrets/")


def ignore_patterns(root=None):
    patterns = list(DEFAULT_IGNORES)
    path = Path(root or Path.cwd()) / ".triadignore"
    if path.is_file():
        patterns.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    return patterns


def ignored_path(path, patterns):
    path = path.replace("\\", "/").lstrip("/")
    if path.startswith(("a/", "b/")):
        path = path[2:]
    for pattern in patterns:
        pattern = pattern.replace("\\", "/").lstrip("/")
        if pattern.endswith("/"):
            if pattern.rstrip("/") in path.split("/") or path.startswith(pattern):
                return True
        elif fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern):
            return True
    return False


def filter_diff(text, root=None):
    """Remove complete git diff sections, including renamed source/destination paths."""
    patterns = ignore_patterns(root)
    blocks = re.split(r"(?=^diff --git )", text, flags=re.MULTILINE)
    result = []
    for block in blocks:
        if block.startswith("diff --git "):
            paths = re.findall(r"^(?:--- |\+\+\+ |rename from |rename to )(.+)$", block, re.MULTILINE)
            # Handle binary/header-only diffs too. Quoted/ambiguous headers fail closed.
            header = block.splitlines()[0][len("diff --git ") :]
            if '"' in header:
                continue
            paths.extend(header.split())
            if any(ignored_path(path, patterns) for path in paths):
                continue
        # Provider callers may supply standard unified diffs without git's
        # extended header. Apply the same exclusions before accepting hunks.
        unified = re.split(r"(?=^--- [^\n]+\n\+\+\+ )", block, flags=re.MULTILINE)
        for section in unified:
            if section.startswith("--- "):
                paths = [line[4:].split("\t", 1)[0] for line in section.splitlines()[:2]]
                if any(ignored_path(path, patterns) for path in paths):
                    continue
            result.append(section)
    return "".join(result)


def redact(text):
    text = re.sub(
        r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY]",
        text,
        flags=re.S,
    )
    text = re.sub(r"\bBearer\s+[^\s\"'`,;]+", "Bearer [REDACTED]", text, flags=re.I)
    text = re.sub(
        r'''((?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|authorization)\s*["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s`,;}]+)''',
        r"\1[REDACTED]",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]+", "[REDACTED]", text)
    text = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[REDACTED]", text)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED]", text)
    text = re.sub(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    text = re.sub(
        r"(?<!\w)(?:\+?\d[\d ().-]{5,}\d)(?!\w)",
        lambda m: "[PHONE]" if 7 <= sum(c.isdigit() for c in m[0]) <= 15 else m[0],
        text,
    )
    # Also remove configured secrets wherever they appear without a field label.
    for key, value in os.environ.items():
        if re.search(r"(?:TOKEN|SECRET|PASSWORD|API_KEY)$", key) and len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    return text


def sanitize_egress(text, root=None):
    return redact(filter_diff(text or "", root))


def memory_query_allowed(text):
    """Mem0 recall remains enabled, but security findings never enter cloud memory."""
    return not re.search(
        r"security|finding|vulnerabilit|credential|secret|bearer|api[_ -]?key|"
        r"\b(?:CWE|CVE)[-_ ]?\d|\b(?:XSS|SQLi|RCE|CSRF|SSRF)\b|exploit|"
        r"injection|path traversal|auth(?:entication|orization)?[ -]bypass|"
        r"privilege escalation|private key|password",
        text,
        re.I,
    )
