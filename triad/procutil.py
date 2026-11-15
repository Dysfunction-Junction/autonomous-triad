"""
Autonomous Multi-Agent Triad: Process & Network Utilities (procutil.py).

Cross-platform helpers shared by the engine, advisor manager, and HTTP server.
Previously each module carried its own copy of these; this is the single
implementation.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
from typing import List, Optional

try:  # psutil is optional; we degrade to OS primitives without it.
    import psutil  # type: ignore
except Exception:  # pragma: no cover - exercised only when psutil is absent
    psutil = None  # type: ignore


def clean_git_env(extra_env: Optional[dict] = None, *, base_env: Optional[dict] = None) -> dict:
    """Return an environment dictionary sanitized of local Git environment variables."""
    try:
        from triad.worktree import clean_git_env as _clean
    except ImportError:
        from worktree import clean_git_env as _clean
    return _clean(extra_env=extra_env, base_env=base_env)


def kill_process_tree(pid: int, timeout: float = 5.0) -> None:
    """
    Force-terminate ``pid`` and every descendant.

    Strategy (best-effort, never raises):
      1. psutil, if installed - walks the tree and kills children first.
      2. Windows: ``taskkill /F /T``.
      3. POSIX: SIGKILL the process group if the pid leads one, else the pid.
    """
    if pid is None or pid <= 0:
        return

    if psutil is not None:
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except Exception:
                    pass
            try:
                parent.kill()
            except Exception:
                pass
            try:
                psutil.wait_procs(children + [parent], timeout=timeout)
            except Exception:
                pass
            return
        except getattr(psutil, "NoSuchProcess", Exception):
            return
        except Exception:
            pass

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
        except Exception:
            pass
        return

    # POSIX fallback
    try:
        pgid = os.getpgid(pid)
        if pgid == pid:
            os.killpg(pgid, signal.SIGKILL)
            return
    except Exception:
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Quick TCP connect probe with guaranteed socket cleanup."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def classify_advisor_response(text: Optional[str]) -> str:
    """
    Classify a raw advisor response string into one of:
      ``"ok"``      - a usable answer
      ``"limit"``   - the advisor reported a session / rate / usage limit
      ``"error"``   - the advisor failed for any other reason
      ``"empty"``   - nothing came back

    Only the *leading bracketed tag* is inspected (e.g. ``[Claude Session Limit]: ...``),
    so an otherwise-valid review that merely mentions the word "limit" in its body is
    never misclassified as a failure.
    """
    s = (text or "").strip()
    if not s:
        return "empty"
    if not s.startswith("["):
        return "ok"
    close = s.find("]")
    if close == -1:
        return "ok"
    tag = s[1:close].lower()
    # A successful failover prefixes the *good* answer with a header that quotes the
    # earlier failures - that header must read as success, not as the failure it quotes.
    if tag.startswith("advisor auto-failover"):
        return "error" if "exhausted" in tag else "ok"
    if any(k in tag for k in ("session limit", "rate limit", "usage limit")):
        return "limit"
    if "triad circuit" in tag:
        return "limit" if any(k in tag for k in ("cooldown", "limit", "open")) else "error"
    if "timed out" in tag:
        return "timeout"
    if (
        tag in ("error", "failure", "failed")
        or tag.startswith(("error:", "failure:", "failed:", "error from ", "error calling ", "error in ", "failure from ", "error -", "error \u2013"))
        or (tag.startswith("competition") and ("fail" in tag or "error" in tag))
        or tag.startswith(("triad error", "advisor error"))
        or bool(re.search(r"\b(?:error|failure|failed)\s*:", tag))
        or bool(re.search(r"\b(?:error|failure|failed)$", tag))
    ):
        return "error"
    return "ok"


def is_failed_advisor_response(text: Optional[str]) -> bool:
    """True when ``text`` should trigger failover to the next advisor."""
    return classify_advisor_response(text) in ("limit", "error", "empty", "timeout")


LOCKFILE_NAMES = frozenset({
    "uv.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "bun.lock",
    "pipfile.lock",
    "poetry.lock",
    "cargo.lock",
    "go.sum",
    "composer.lock",
    "gemfile.lock",
    "mix.lock",
    "flake.lock",
    "packages.lock.json",
    "npm-shrinkwrap.json",
})

MINIFIED_EXTENSIONS = frozenset({
    ".min.js",
    ".min.css",
    ".bundle.js",
    ".bundle.css",
    ".map",
})

KEY_MATERIAL_NAMES = frozenset({
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", ".env", "credentials.json",
})

KEY_MATERIAL_EXTENSIONS = frozenset({
    ".keystore", ".jks", ".p12", ".pfx", ".pem", ".key", ".pkcs12", ".gpg",
})


def _extract_diff_file_path(lines: List[str]) -> str:
    """Robustly extract file path preferring +++ b/ over --- a/ (supports spaces & quotes)."""
    window = lines[:10]
    for prefix, strip_n in (("+++ b/", 6), ("+++ ", 4), ("--- a/", 6), ("--- ", 4)):
        for line in window:
            if line.startswith(prefix) and line not in ("+++ /dev/null", "--- /dev/null"):
                return line[strip_n:].strip().strip("\"'")
    return _path_from_diff_git_header(lines[0][:2048] if lines else "")

BINARY_ASSET_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg", ".bmp", ".tiff",
    ".pdf", ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".wav", ".ogg", ".webm",
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".whl", ".jar",
    ".iso", ".exe", ".dll", ".so", ".dylib", ".bin",
    ".apk", ".aab", ".dex", ".class", ".pyc", ".pyo",
})

DOC_EXTENSIONS = frozenset({
    ".md", ".markdown", ".mdown", ".mkd",
    ".rst", ".adoc",
})

ASSET_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg", ".bmp", ".tiff",
    ".pdf", ".drawio",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".wav", ".ogg", ".webm",
})

NON_CODE_METADATA_FILES = frozenset({
    ".gitignore", ".gitattributes", ".editorconfig",
    "license", "licence", "notice", "authors", "contributors",
    "changelog", "readme",
})

CODE_OR_CONFIG_EXTENSIONS = frozenset({
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".sh", ".bash", ".zsh", ".bat", ".cmd", ".ps1",
    ".c", ".h", ".cpp", ".hpp", ".rs", ".go", ".java", ".kt", ".swift",
    ".html", ".css", ".scss", ".less", ".sql", ".graphql", ".proto",
})

_TRUNC_MARKER_RE = re.compile(r"^\[\.\.\. (\d+) lines? truncated to protect LLM context \.\.\.\]\r?$")


def is_doc_or_asset_file(path_str: str) -> bool:
    """Return True if path_str is strictly a documentation or non-code asset file."""
    if not path_str:
        return False
    p = path_str.replace("\\", "/").lower().strip()
    base = os.path.basename(p)
    parts = [seg for seg in p.split("/") if seg]

    # Test suites, benchmarks, and test fixtures are NEVER classified as doc/asset files
    if any(seg in ("tests", "test", "fixtures", "fixture", "cases") for seg in parts):
        return False

    # Package management, dependency specifications, and build files are code/config
    if base.startswith("requirements") and base.endswith(".txt"):
        return False
    if base in ("cmakelists.txt", "dockerfile", "makefile", "procfile", "gemfile", "vagrantfile"):
        return False

    # Standard non-code root metadata files
    if base in NON_CODE_METADATA_FILES:
        return True
    root_name, ext = os.path.splitext(base)
    if root_name in NON_CODE_METADATA_FILES and ext in (".md", ".txt", ".rst", ""):
        return True

    # Any file with code/configuration extensions must always be treated as code
    if ext in CODE_OR_CONFIG_EXTENSIONS:
        return False

    # Pure documentation and static visual assets
    if ext in DOC_EXTENSIONS or ext in ASSET_EXTENSIONS:
        return True

    # Dedicated documentation directories (e.g. docs/, doc/) containing docs/assets/txt
    if parts and parts[0] in ("docs", "doc"):
        if ext in DOC_EXTENSIONS or ext in ASSET_EXTENSIONS or ext in (".txt", ""):
            return True

    # Plain text files that are explicitly documentation or notes
    if ext == ".txt" and (base.startswith(("readme", "license", "notes", "changelog", "install", "authors"))):
        return True

    return False


def _path_from_diff_git_header(first_line: str) -> str:
    """Extract the file path from a ``diff --git`` header using string ops (no regex backtracking)."""
    prefix = "diff --git"
    if not first_line.startswith(prefix) or len(first_line) == len(prefix) or not first_line[len(prefix)].isspace():
        return ""
    rest = first_line[len(prefix):].strip()
    # Quoted/prefixed form: a/<old> b/<new>, optionally with each side quoted.
    unquoted = rest.lstrip('"')
    if unquoted.startswith("a/"):
        body = unquoted[2:]
        cuts = [(body.find(sep), sep) for sep in (' "b/', " b/")]
        cuts = [(i, sep) for i, sep in cuts if i >= 0]
        if cuts:
            idx, sep = min(cuts)
            old, new = body[:idx], body[idx + len(sep):]
            return new.rstrip('"') or old.rstrip('"')
    # Fallback: split on the first whitespace run, dropping optional a/ b/ prefixes.
    parts = rest.split(None, 1)
    if len(parts) < 2:
        return ""
    old, new = parts
    old = old.removeprefix("a/")
    new = new.removeprefix("b/")
    return new or old


DEFAULT_DIFF_MAX_FILE_LINES = 250
DEFAULT_DIFF_MAX_TOTAL_LINES = 800
_DELETED_SUMMARY_RE = re.compile(r"^\[\d+ lines deleted\]$")


def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return default


def strip_diff_bloat(
    diff_text: Optional[str],
    max_lines_per_file: Optional[int] = None,
    max_total_lines: Optional[int] = None,
) -> str:
    """
    Sanitize git diff text before passing to LLM advisors.

    Strips massive lockfiles, minified bundles, and binary assets while
    preserving the diff headers (so the LLM is aware which files changed).
    Collapses pure renames/mode-only changes to headers and pure deletions to
    `[N lines deleted]`. Truncates abnormally large single-file diffs and
    enforces a global line budget across all files.
    Guaranteed strictly idempotent across single and multi-file diffs.
    """
    if not diff_text or not diff_text.strip():
        return ""

    if max_lines_per_file is None:
        max_lines_per_file = _env_positive_int("TRIAD_DIFF_MAX_FILE_LINES", DEFAULT_DIFF_MAX_FILE_LINES)
    if max_total_lines is None:
        max_total_lines = _env_positive_int("TRIAD_DIFF_MAX_TOTAL_LINES", DEFAULT_DIFF_MAX_TOTAL_LINES)

    file_chunks = re.split(r"(?m)(?=^diff --git |^\[Diff omitted: \d+ remaining files)", diff_text)
    sanitized_chunks = []
    total_retained_lines = 0

    for idx, chunk in enumerate(file_chunks):
        chunk_clean = chunk.rstrip("\n")
        if not chunk_clean.strip():
            continue

        # If this chunk was already omitted by a previous pass, preserve it as-is
        if re.search(r"(?m)^\[Diff omitted: ", chunk_clean):
            sanitized_chunks.append(chunk_clean)
            total_retained_lines += len(chunk_clean.split("\n"))
            continue

        lines = chunk_clean.split("\n")
        file_path = _extract_diff_file_path(lines)
        clean_path = file_path.strip().strip("\"'")
        file_name = os.path.basename(clean_path).lower()

        is_tsbuildinfo = file_name.endswith(".tsbuildinfo")
        is_lockfile = (file_name in LOCKFILE_NAMES) or file_name.endswith(".lockfile") or is_tsbuildinfo
        is_minified = any(file_name.endswith(m_ext) for m_ext in MINIFIED_EXTENSIONS)
        is_git_binary = bool(
            re.search(r"(?m)^Binary files .* differ$", chunk_clean)
            or re.search(r"(?m)^GIT binary patch", chunk_clean)
        )
        is_key_material = (
            file_name in KEY_MATERIAL_NAMES
            or any(file_name.endswith(k_ext) for k_ext in KEY_MATERIAL_EXTENSIONS)
        )
        is_binary = any(file_name.endswith(b_ext) for b_ext in BINARY_ASSET_EXTENSIONS) or is_git_binary

        # 1. Specialized classification runs BEFORE the exhausted global budget check
        if is_lockfile or is_minified or is_binary or is_key_material:
            if is_key_material:
                category = "key/certificate or credential file (content withheld)"
            elif is_tsbuildinfo:
                category = "generated build cache"
            elif is_lockfile:
                category = "lockfile update"
            elif is_binary:
                category = "binary / asset file"
            else:
                category = "minified / generated asset"

            header_lines = []
            in_header = True
            for line in lines[:12]:
                if in_header:
                    header_lines.append(line)
                    if line.startswith("+++ ") or line.startswith("Binary files ") or line.startswith("GIT binary patch"):
                        in_header = False
                        break

            hunk_line_count = max(0, len(lines) - len(header_lines))
            if hunk_line_count > 0 or is_git_binary:
                header_lines.append(f"[Diff omitted: {category} ({hunk_line_count} lines omitted to preserve LLM context)]")
                sanitized_chunks.append("\n".join(header_lines).rstrip("\n"))
                total_retained_lines += len(header_lines)
            else:
                sanitized_chunks.append(chunk_clean)
                total_retained_lines += len(lines)
            continue

        # 2. Check if total global line budget has already been exhausted
        if total_retained_lines >= max_total_lines:
            rem_pairs = []
            for rem in file_chunks[idx:]:
                rem_clean = rem.rstrip("\n")
                if not rem_clean.strip():
                    continue
                if re.search(r"(?m)^\[Diff omitted: ", rem_clean):
                    sanitized_chunks.append(rem_clean)
                    continue
                rem_lines = rem_clean.split("\n")
                p = _extract_diff_file_path(rem_lines)
                if p:
                    rem_pairs.append((p, rem_clean, rem_lines))
                elif rem_clean.startswith("diff --git"):
                    rem_pairs.append(("<unparsed>", rem_clean, rem_lines))

            if rem_pairs:
                if len(rem_pairs) == 1:
                    single_p, single_chunk, single_lines = rem_pairs[0]
                    hdr = []
                    for line in single_lines[:12]:
                        hdr.append(line)
                        if line.startswith("+++ ") or line.startswith("Binary files ") or line.startswith("GIT binary patch"):
                            break
                    hdr.append(f"[Diff omitted: remaining file changes truncated to protect LLM context ({len(single_lines)} lines omitted)]")
                    sanitized_chunks.append("\n".join(hdr).rstrip("\n"))
                else:
                    omitted_paths = [p for p, _, _ in rem_pairs]
                    total_omitted_lines = sum(len(sl) for _, _, sl in rem_pairs)
                    path_summary = ", ".join(omitted_paths[:12])
                    if len(omitted_paths) > 12:
                        path_summary += f", and {len(omitted_paths) - 12} other files"
                    sanitized_chunks.append(
                        f"[Diff omitted: {len(omitted_paths)} remaining files ({total_omitted_lines} lines) truncated to protect LLM context: {path_summary}]"
                    )
            break

        # 3. Process regular code diff with hunk extraction and idempotency defense
        header_lines = []
        hunk_lines = []
        in_header = True
        prev_truncated = 0
        for line in lines:
            if in_header:
                header_lines.append(line)
                if line.startswith("+++ "):
                    in_header = False
            else:
                # Discard previous truncation markers when re-sanitizing to guarantee strict idempotence,
                # but preserve the truncated count so re-sanitizing doesn't lose track of omitted lines.
                m = _TRUNC_MARKER_RE.match(line)
                if m:
                    prev_truncated += int(m.group(1))
                    continue
                hunk_lines.append(line)

        # Pure renames / mode-only changes (headers only, no hunk lines): emit header only
        if not hunk_lines and any(
            h.startswith(("rename from ", "rename to ", "old mode ", "new mode ", "similarity index 100%"))
            for h in header_lines
        ):
            sanitized_chunks.append("\n".join(header_lines).rstrip("\n"))
            total_retained_lines += len(header_lines)
            continue

        # Pure-deletion files (`+++ /dev/null` with only `-` content lines or existing summary): collapse to header + `[N lines deleted]`
        is_deleted_file = any(h.strip() == "+++ /dev/null" for h in header_lines)
        if is_deleted_file and hunk_lines:
            if len(hunk_lines) == 1 and _DELETED_SUMMARY_RE.match(hunk_lines[0]):
                sanitized_chunks.append(chunk_clean)
                total_retained_lines += len(lines)
                continue
            deleted_count = sum(1 for hl in hunk_lines if hl.startswith("-"))
            if deleted_count > 0 and not any(hl.startswith("+") and not hl.startswith("+++ ") for hl in hunk_lines):
                emitted = header_lines + [f"[{deleted_count} lines deleted]"]
                sanitized_chunks.append("\n".join(emitted).rstrip("\n"))
                total_retained_lines += len(emitted)
                continue

        # Calculate budget for this file
        budget_remaining = max(0, max_total_lines - total_retained_lines - len(header_lines))
        file_keep_limit = max(0, min(max_lines_per_file, budget_remaining))

        if len(hunk_lines) > file_keep_limit:
            new_truncated = len(hunk_lines) - file_keep_limit
            total_truncated = new_truncated + prev_truncated
            kept_hunk = hunk_lines[:file_keep_limit]
            line_str = "line" if total_truncated == 1 else "lines"
            kept_hunk.append(f"[... {total_truncated} {line_str} truncated to protect LLM context ...]")
            emitted = header_lines + kept_hunk
            sanitized_chunks.append("\n".join(emitted).rstrip("\n"))
            total_retained_lines += len(emitted)
        elif prev_truncated > 0:
            # File was previously truncated and is still at or within budget
            kept_hunk = list(hunk_lines)
            line_str = "line" if prev_truncated == 1 else "lines"
            kept_hunk.append(f"[... {prev_truncated} {line_str} truncated to protect LLM context ...]")
            emitted = header_lines + kept_hunk
            sanitized_chunks.append("\n".join(emitted).rstrip("\n"))
            total_retained_lines += len(emitted)
        else:
            # Unchanged file passes through verbatim to avoid newline/CRLF normalisation
            sanitized_chunks.append(chunk_clean)
            total_retained_lines += len(lines)

    return "\n\n".join(sanitized_chunks)


_CITE_RE = re.compile(r"([A-Za-z0-9_.\-/\\]+?\.[A-Za-z0-9_]+)(?::L?|#L|\s+line\s+|\s+L)(\d+)", re.IGNORECASE)
_HUNK_HDR_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_LEADING_DOT_SLASH_RE = re.compile(r"^(?:\./)+")
_VERDICT_APPROVED_RE = re.compile(r"^[\s*_`>#-]*VERDICT:\s*APPROVED[\s*_`.!]*$", re.IGNORECASE)
_VERDICT_REJECTED_RE = re.compile(r"VERDICT:\s*REJECTED", re.IGNORECASE)

SYNTH_DIFF_BUDGET_CHARS = 10_000
SYNTH_CONTEXT_BUDGET_CHARS = 2_000
CITATION_LINE_SLACK = 3


def is_approved_verdict(text: Optional[str]) -> bool:
    """True only when line 1 is `VERDICT: APPROVED` (light markdown tolerated) and no REJECTED verdict appears anywhere."""
    if not text or not text.strip():
        return False
    if _VERDICT_REJECTED_RE.search(text):
        return False
    first = text.strip().splitlines()[0]
    return bool(_VERDICT_APPROVED_RE.match(first))


def extract_cited_hunks(
    diff: str,
    responses: List[str],
    *,
    slack: int = CITATION_LINE_SLACK,
    plain_cap: int = SYNTH_DIFF_BUDGET_CHARS,
) -> str:
    """Return CHANGED FILES list plus only unified-diff hunks cited as path:line in responses.

    A citation matches a hunk when its line falls within `slack` lines of the hunk's new-file range.
    Diffs without `diff --git` markers cannot be split per file, so they are returned whole up to `plain_cap`.
    """
    if not diff:
        return ""
    if "diff --git " not in diff:
        if len(diff) <= plain_cap:
            return diff
        return diff[:plain_cap] + f"\n[... diff truncated, {len(diff) - plain_cap} chars omitted ...]"
    citations: List[tuple] = []
    for resp in responses or []:
        if not resp:
            continue
        for m in _CITE_RE.finditer(resp):
            cite_path = _LEADING_DOT_SLASH_RE.sub("", m.group(1).replace("\\", "/"))
            try:
                cite_line = int(m.group(2))
            except ValueError:
                continue
            citations.append((cite_path, cite_line))

    file_blocks: List[tuple] = []
    current_path: Optional[str] = None
    current_headers: List[str] = []
    current_hunks: List[tuple] = []
    active_hunk_lines: Optional[List[str]] = None
    active_hunk_range = (0, 0)

    def _flush_hunk():
        nonlocal active_hunk_lines
        if active_hunk_lines is not None:
            current_hunks.append((active_hunk_range[0], active_hunk_range[1], active_hunk_lines))
            active_hunk_lines = None

    def _flush_file():
        _flush_hunk()
        if current_path is not None:
            file_blocks.append((current_path, list(current_headers), list(current_hunks)))

    for raw_line in diff.splitlines():
        if raw_line.startswith("diff --git "):
            _flush_file()
            parts = raw_line.split()
            b_path = parts[-1] if parts else ""
            if b_path.startswith("b/"):
                b_path = b_path[2:]
            current_path = b_path.replace("\\", "/")
            current_headers = [raw_line]
            current_hunks = []
            continue
        if current_path is None:
            continue
        if raw_line.startswith("@@ "):
            _flush_hunk()
            hm = _HUNK_HDR_RE.match(raw_line)
            start = int(hm.group(1)) if hm else 1
            count = int(hm.group(2)) if (hm and hm.group(2) is not None) else 1
            end = start + max(count, 1) - 1
            active_hunk_range = (start, end)
            active_hunk_lines = [raw_line]
        elif active_hunk_lines is not None:
            active_hunk_lines.append(raw_line)
        else:
            current_headers.append(raw_line)
            if raw_line.startswith("+++ b/"):
                current_path = raw_line[6:].strip().replace("\\", "/")

    _flush_file()

    if not file_blocks:
        if len(diff) <= plain_cap:
            return diff
        return diff[:plain_cap] + f"\n[... diff truncated, {len(diff) - plain_cap} chars omitted ...]"

    files_section = "CHANGED FILES:\n" + "\n".join(f"- {fp}" for fp, _, _ in file_blocks)
    if not citations:
        return files_section

    def _path_matches(diff_path: str, cite_path: str) -> bool:
        return diff_path == cite_path or diff_path.endswith("/" + cite_path) or cite_path.endswith("/" + diff_path)

    kept_sections: List[str] = []
    for fp, headers, hunks in file_blocks:
        matched_hunks = [
            "\n".join(h_lines)
            for h_start, h_end, h_lines in hunks
            if any(
                _path_matches(fp, cp) and (h_start - slack) <= cl <= (h_end + slack)
                for cp, cl in citations
            )
        ]
        if matched_hunks:
            kept_sections.append("\n".join(headers + matched_hunks))

    if not kept_sections:
        return files_section
    return files_section + "\n\n" + "\n\n".join(kept_sections)


def prepare_synthesis_evidence(
    diff: Optional[str],
    context: Optional[str],
    responses: List[str],
    *,
    diff_budget: int = SYNTH_DIFF_BUDGET_CHARS,
    context_budget: int = SYNTH_CONTEXT_BUDGET_CHARS,
) -> tuple:
    """Return (diff_text, context_text) for a synthesis prompt without silently losing evidence.

    - A diff delivered as `context` (callers sometimes do this) is treated as the diff.
    - Diffs within budget go in whole; larger ones are trimmed to cited hunks.
    - Long context is truncated with an explicit note instead of being dropped.
    """
    if not diff and context and "diff --git " in context:
        diff, context = context, None
    diff_text = ""
    if diff:
        if len(diff) <= diff_budget:
            diff_text = diff
        else:
            diff_text = extract_cited_hunks(diff, responses, plain_cap=diff_budget)
            if len(diff_text) > diff_budget:
                omitted = len(diff_text) - diff_budget
                diff_text = diff_text[:diff_budget] + f"\n[... diff truncated, {omitted} chars omitted ...]"
    ctx_text = None
    if context:
        if len(context) <= context_budget:
            ctx_text = context
        else:
            ctx_text = context[:context_budget] + f"\n(context truncated, {len(context) - context_budget} chars omitted)"
    return diff_text, ctx_text


def extract_diff_file_paths(diff_text: Optional[str]) -> List[str]:
    """Return unique file paths touched by `diff --git` chunks in `diff_text`."""
    if not diff_text:
        return []
    paths: List[str] = []
    seen = set()
    for chunk in re.split(r"(?m)(?=^diff --git )", diff_text):
        if not chunk.startswith("diff --git "):
            continue
        fp = _extract_diff_file_path(chunk.splitlines())
        if fp and fp not in seen:
            seen.add(fp)
            paths.append(fp)
    return paths


_AGENT_INSTRUCTION_FILES = frozenset({
    "claude.md", "claude.local.md", "agents.md", "agent.md", "gemini.md",
    "skill.md", "soul.md", "tools.md", "memory.md", "copilot-instructions.md",
    "hermes.md", ".hermes.md", "conventions.md", "identity.md", "user.md",
    ".cursorrules", ".windsurfrules", "llms.txt",
})
_AGENT_INSTRUCTION_SUFFIXES = (".prompt.md", ".instructions.md")
_PROTECTED_DIR_PREFIXES = (
    ".claude/", ".agents/", ".github/", ".gemini/", ".codex/", ".cursor/",
    ".clinerules/", ".roo/", ".kiro/", ".windsurf/", ".continue/",
)
_TRIVIAL_DOC_EXTENSIONS = frozenset({".md", ".rst"})
_INDEX_SPECIAL_MODE_RE = re.compile(r"^index [0-9a-f]+\.\.[0-9a-f]+ (?:120000|100755)$")
TRIVIAL_DIFF_MAX_CHARS = 20_000
_TRIVIAL_SECRET_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{30,}"
    r"|xox[baprs]-[0-9A-Za-z-]{10,}"
    r"|-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"
    r"|Bearer\s+[A-Za-z0-9._\-]{24,})"
)


def is_trivial_diff(diff_text: Optional[str], *, max_chars: int = TRIVIAL_DIFF_MAX_CHARS) -> bool:
    """Return True only when every `diff --git` chunk touches non-instruction .md/.rst docs within budget and without secrets or metadata changes."""
    if not diff_text or not diff_text.strip() or len(diff_text) > max_chars:
        return False
    if re.search(r"(?m)^diff --(?:cc|combined) ", diff_text):
        return False

    parts = re.split(r"(?m)(?=^diff --git )", diff_text)
    if parts and not parts[0].startswith("diff --git "):
        if re.search(r"(?m)^(?:---|\+\+\+|@@) ", parts[0]):
            return False
    chunks = [c for c in parts if c.startswith("diff --git ")]
    if not chunks:
        return False
    for chunk in chunks:
        lines = chunk.splitlines()
        fp = _extract_diff_file_path(lines)
        if not fp:
            return False
        # Scan header lines up to the first @@ hunk for mode/symlink/deletion/rename/copy/binary metadata
        header_end = next((i for i, ln in enumerate(lines[1:], 1) if ln.startswith("@@ ")), len(lines))
        if any(
            line.startswith((
                "old mode ", "new mode ", "rename from ", "rename to ",
                "copy from ", "copy to ",
                "new file mode 120", "new file mode 100755", "deleted file mode ",
                "Binary files ", "GIT binary patch",
            ))
            or _INDEX_SPECIAL_MODE_RE.match(line)
            for line in lines[1:header_end]
        ):
            return False
        norm = _LEADING_DOT_SLASH_RE.sub("", fp.replace("\\", "/")).lower()
        base = os.path.basename(norm)
        if (
            base in _AGENT_INSTRUCTION_FILES
            or base.endswith(_AGENT_INSTRUCTION_SUFFIXES)
            or any(f"/{p}" in f"/{norm}" for p in _PROTECTED_DIR_PREFIXES)
        ):
            return False
        _, ext = os.path.splitext(base)
        if ext not in _TRIVIAL_DOC_EXTENSIONS:
            return False
        if not is_doc_or_asset_file(fp):
            return False
        # Added lines must not contain obvious secret/credential patterns
        if any(
            ln.startswith("+") and not ln.startswith("+++ ") and _TRIVIAL_SECRET_RE.search(ln)
            for ln in lines[header_end:]
        ):
            return False
    return True


__all__ = [
    "clean_git_env",
    "kill_process_tree",
    "is_port_open",
    "classify_advisor_response",
    "is_failed_advisor_response",
    "LOCKFILE_NAMES",
    "MINIFIED_EXTENSIONS",
    "KEY_MATERIAL_NAMES",
    "KEY_MATERIAL_EXTENSIONS",
    "BINARY_ASSET_EXTENSIONS",
    "DOC_EXTENSIONS",
    "ASSET_EXTENSIONS",
    "NON_CODE_METADATA_FILES",
    "CODE_OR_CONFIG_EXTENSIONS",
    "is_doc_or_asset_file",
    "strip_diff_bloat",
    "extract_cited_hunks",
    "prepare_synthesis_evidence",
    "is_approved_verdict",
    "extract_diff_file_paths",
    "is_trivial_diff",
]
