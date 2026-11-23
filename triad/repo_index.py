# Tags: tooling, local-llm, cache
# Links: docs/REPO_KNOWLEDGE.md, scripts/setup-repo-knowledge.ps1
# Queries: "how do repository edits update local embeddings", "how do I search one repo"
"""Local incremental repository index. No third-party Python dependencies."""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import uuid
from urllib.parse import urlsplit
from urllib.request import Request

DEFAULT_STATE = Path.home() / ".local" / "share" / "repo-knowledge"
DEFAULT_URL = "http://127.0.0.1:8081"
EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".md", ".rst", ".toml",
              ".json", ".yaml", ".yml", ".sql", ".sh", ".ps1", ".kt", ".java", ".rs", ".go",
              ".css", ".scss", ".html", ".vue", ".svelte", ".gradle"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "target", ".next",
             ".cache", "coverage", "__pycache__", ".idea", ".vscode", ".cartograph",
             "secrets", "evidence", "fixtures", "vendor", "tags"}
SKIP_NAMES = {"package-lock.json", "pnpm-lock.yaml", "uv.lock", "yarn.lock", "repo_tags.md",
              "repomix-output.xml", "credentials.json", "token.json", ".bearer-token"}
SECRET = re.compile(
    r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----|"
    r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b|"
    r"""(?im:^\s*(?:(?:const|let|var|export)\s+)?["']?(?:api[_-]?key|secret|password|access[_-]?token|private[_-]?key)["']?\s*[:=]\s*["'][^"'\r\n]{8,}["'])"""
)
HEADER = re.compile(r"^\s*(?:/\*+|<!--|//+|#+|--+|\*+|>)\s*\*{0,2}(tags|links|queries)\*{0,2}\s*:\s*\*{0,2}(.*?)\s*(?:-->)?$", re.I)
SYMBOL = re.compile(r"\b(?:async\s+)?(?:def|class|function|interface|type|enum|struct|fn|func)\s+([\w$]+)|(?:export\s+)?(?:const|let)\s+([\w$]+)\s*=")
MAX_BYTES = 1_000_000


def digest(text):
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def valid_vectors(vectors, count):
    if not isinstance(vectors, list) or len(vectors) != count or not vectors:
        return False
    size = len(vectors[0]) if isinstance(vectors[0], list) else 0
    return size >= 2 and all(
        isinstance(v, list) and len(v) == size
        and all(type(x) in (float, int) and math.isfinite(x) for x in v)
        and sum(x * x for x in v) > 0 for v in vectors
    )


def metadata(path, text):
    fields = {"tags": [], "links": [], "queries": []}
    for line in text.splitlines()[:40]:
        match = HEADER.match(line)
        if match:
            raw = match[2].strip().strip("*").strip()
            quoted = re.findall(r'"([^"]+)"', raw)
            fields[match[1].lower()].extend(quoted or [x.strip(" *\x60'") for x in raw.split(",") if x.strip(" *\x60'")])
    language = {".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
                ".jsx": "javascript", ".md": "markdown"}.get(Path(path).suffix, Path(path).suffix.lstrip("."))
    fields["tags"] = sorted(set(fields["tags"] + [f"language:{language}", f"area:{path.split('/')[0] if '/' in path else 'root'}"]))
    fields["language"] = language
    return fields


def chunks(path, text):
    """Python top-level AST boundaries; bounded line windows for other languages."""
    lines = text.splitlines(keepends=True)
    boundaries = {0, len(lines)}
    if Path(path).suffix == ".py":
        try:
            for node in ast.parse(text).body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    boundaries.add(min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1)
        except (SyntaxError, ValueError, RecursionError):
            pass  # Half-written source remains indexable.
    elif Path(path).suffix == ".md":
        boundaries.update(i for i, line in enumerate(lines) if re.match(r"^#{1,6} ", line))
    points = sorted(boundaries)
    for begin, end in zip(points, points[1:]):
        at = begin
        while at < end:
            stop = at
            size = 0
            while stop < end and stop - at < 60 and (size + len(lines[stop]) <= 2400 or stop == at):
                size += len(lines[stop])
                stop += 1
            value = "".join(lines[at:stop])
            for offset in range(0, len(value), 2400):
                part = value[offset:offset + 2400]
                if part.strip():
                    symbols = ["".join(m).strip() for m in SYMBOL.findall(part)][:12]
                    yield at + 1, stop, " ".join(symbols), part
            at = stop


class RepoIndex:
    def __init__(self, repo, state_dir=DEFAULT_STATE, embed_url=DEFAULT_URL, model="nomic-embed-text", embedder=None, lock_timeout=45):
        self.lock_timeout = lock_timeout
        self.repo = Path(repo).resolve(strict=True)
        # A subdirectory must never silently inherit its parent's scope.
        top = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--show-toplevel"],
                             check=True, capture_output=True, text=True, timeout=15).stdout.strip()
        if Path(top).resolve() != self.repo:
            raise ValueError("Choose the Git checkout root, not a subdirectory")
        parsed = urlsplit(embed_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"} or parsed.username or parsed.password:
            raise ValueError("Embedding endpoint must be an unauthenticated loopback HTTP URL")
        self.embed_url = embed_url.rstrip("/")
        self.model = model
        self.embedder = embedder or self._embed
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / (digest(str(self.repo).casefold() if os.name == "nt" else str(self.repo))[:24] + ".sqlite3")
        with self.connection() as con:
            existing = con.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('meta','files','chunks','search')").fetchone()[0]
            if existing == 4:
                columns = {row[1] for row in con.execute("PRAGMA table_info(chunks)")}
                if not {"attempted_at", "lease", "lease_until"} <= columns:
                    con.execute("BEGIN IMMEDIATE")
                    columns = {row[1] for row in con.execute("PRAGMA table_info(chunks)")}
                    for name, statement in (
                        ("attempted_at", "ALTER TABLE chunks ADD COLUMN attempted_at REAL NOT NULL DEFAULT 0"),
                        ("lease", "ALTER TABLE chunks ADD COLUMN lease TEXT NOT NULL DEFAULT ''"),
                        ("lease_until", "ALTER TABLE chunks ADD COLUMN lease_until REAL NOT NULL DEFAULT 0")):
                        if name not in columns:
                            con.execute(statement)
                return
            con.executescript("""
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, hash TEXT NOT NULL, metadata TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks(
                    id INTEGER PRIMARY KEY, path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
                    start_line INTEGER, end_line INTEGER, symbols TEXT, text TEXT NOT NULL, vector TEXT,
                    attempted_at REAL NOT NULL DEFAULT 0, lease TEXT NOT NULL DEFAULT '', lease_until REAL NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
                CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(path, symbols, text, metadata);
            """)
            con.execute("INSERT OR IGNORE INTO meta VALUES('repo',?)", (str(self.repo),))

    @contextmanager
    def connection(self):
        con = sqlite3.connect(self.db_path, timeout=self.lock_timeout)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        # Removed sensitive text must not survive as free-page bytes.
        con.execute("PRAGMA secure_delete=ON")
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def _paths(self):
        result = subprocess.run(["git", "-C", str(self.repo), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                                check=True, capture_output=True, timeout=30)
        return set(result.stdout.decode("utf8", errors="surrogateescape").split("\0")) - {""}

    def _read(self, rel):
        path = self.repo / rel
        parts = Path(rel).parts
        name = path.name.lower()
        if (Path(rel).is_absolute() or ".." in parts or any(p.lower() in SKIP_DIRS for p in parts)
                or name in SKIP_NAMES or name.startswith(".env") or path.suffix.lower() not in EXTENSIONS
                or any(x in name for x in ("service-account", "service_account", ".min.", ".generated.", ".secret."))
                or name.endswith(".d.ts")):
            return None
        try:
            # Reject parent-directory junctions and symlinks too.
            if any((self.repo.joinpath(*parts[:i])).is_symlink()
                   or (hasattr(Path, "is_junction") and self.repo.joinpath(*parts[:i]).is_junction())
                   for i in range(1, len(parts) + 1)):
                return None
            if not path.resolve().is_relative_to(self.repo) or not path.is_file() or path.stat().st_size > MAX_BYTES:
                return None
            raw = path.read_bytes()
            if len(raw) > MAX_BYTES or b"\0" in raw:
                return None
            text = raw.decode("utf-8-sig")
        except (OSError, UnicodeError, ValueError):
            return None
        if SECRET.search(text):
            return None
        return text

    def _snapshot(self):
        found = {}
        for path in sorted(self._paths()):
            text = self._read(path)
            if text is not None:
                found[path] = (digest(text), text)
        return found

    def _embed(self, texts):
        body = json.dumps({"model": self.model, "input": texts}).encode()
        request = Request(self.embed_url + "/v1/embeddings", body, {"Content-Type": "application/json"})
        try:
            # Disable environment proxies and redirects: content stays on loopback.
            from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

            class NoRedirect(HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=30) as response:
                data = json.load(response)["data"]
            if not isinstance(data, list) or sorted(row["index"] for row in data) != list(range(len(texts))):
                return None
            return [row["embedding"] for row in sorted(data, key=lambda row: row["index"])]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def sync(self, max_chunks=0):
        totals = {"changed": 0, "removed": 0, "embedded": 0}
        while True:
            result = self._sync_once(max_chunks if max_chunks > 0 else 64)
            for key in totals:
                totals[key] += result[key]
            if max_chunks > 0 or not result["pending"] or not result["embedded"]:
                result.update(totals)
                return result

    def _sync_once(self, max_chunks):
        # Source snapshots serialize; model calls happen after this transaction commits.
        identity = self.embed_url + "|" + self.model
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            snapshot = self._snapshot()
            old = con.execute("SELECT value FROM meta WHERE key='embed_identity'").fetchone()
            if not old or old[0] != identity:
                con.execute("UPDATE chunks SET vector=NULL, lease='', lease_until=0")
                con.execute("INSERT OR REPLACE INTO meta VALUES('embed_identity',?)", (identity,))
            previous = {row["path"]: row["hash"] for row in con.execute("SELECT path, hash FROM files")}
            removed = set(previous) - set(snapshot)
            changed = [path for path, (key, _) in snapshot.items() if previous.get(path) != key]
            for path in removed | set(changed):
                con.execute("DELETE FROM search WHERE rowid IN (SELECT id FROM chunks WHERE path=?)", (path,))
                con.execute("DELETE FROM files WHERE path=?", (path,))
            for path in changed:
                key, text = snapshot[path]
                fields = metadata(path, text)
                meta = json.dumps(fields)
                con.execute("INSERT INTO files VALUES(?,?,?)", (path, key, meta))
                for first, last, symbols, part in chunks(path, text):
                    row = con.execute("INSERT INTO chunks(path,start_line,end_line,symbols,text) VALUES(?,?,?,?,?)",
                                      (path, first, last, symbols, part))
                    con.execute("INSERT INTO search(rowid,path,symbols,text,metadata) VALUES(?,?,?,?,?)",
                                (row.lastrowid, path, symbols, part, meta))
            con.execute("CREATE TEMP TABLE prioritize(path TEXT PRIMARY KEY)")
            con.executemany("INSERT INTO prioritize VALUES(?)", [(path,) for path in changed])
            pending = [dict(row) for row in con.execute(
                "SELECT c.*, f.hash, f.metadata FROM chunks c JOIN files f ON f.path=c.path "
                "LEFT JOIN prioritize p ON p.path=c.path WHERE c.vector IS NULL AND c.lease_until<=? "
                "ORDER BY (p.path IS NULL), c.attempted_at, c.id LIMIT ?", (time.time(), max_chunks)).fetchall()]
            stamp = datetime.now(timezone.utc).isoformat()
            con.execute("INSERT OR REPLACE INTO meta VALUES('last_sync',?)", (stamp,))

        embedded = 0
        for row in pending:
            token = uuid.uuid4().hex
            now = time.time()
            # Claim one chunk briefly. Another worker may have changed/deleted it since selection.
            with self.connection() as con:
                claim = con.execute(
                    "UPDATE chunks SET attempted_at=?,lease=?,lease_until=? "
                    "WHERE id=? AND path=? AND text=? AND vector IS NULL AND lease_until<=? "
                    "AND (SELECT value FROM meta WHERE key='embed_identity')=? "
                    "AND EXISTS(SELECT 1 FROM files f WHERE f.path=chunks.path AND f.hash=?)",
                    (now, token, now + 45, row["id"], row["path"], row["text"], now, identity, row["hash"]))
                claimed = claim.rowcount == 1
            if not claimed:
                continue
            fields = json.loads(row["metadata"])
            prompt = f"search_document: {row['path']} {row['symbols']} {' '.join(fields['tags'])} {' '.join(fields['queries'])}\\n{row['text']}"
            try:
                vectors = self.embedder([prompt[:3000]])
            except (OSError, ValueError, TypeError):
                vectors = None
            vector = json.dumps(vectors[0]) if valid_vectors(vectors, 1) else None
            with self.connection() as con:
                published = con.execute(
                    "UPDATE chunks SET vector=?,lease='',lease_until=0 WHERE id=? AND lease=? "
                    "AND (SELECT value FROM meta WHERE key='embed_identity')=?",
                    (vector, row["id"], token, identity))
                if vector is not None and published.rowcount == 1:
                    embedded += 1
        with self.connection() as con:
            result = self._counts(con)
        result.update(changed=len(changed), removed=len(removed), embedded=embedded, last_sync=stamp)
        return result

    def _counts(self, con):
        identity = con.execute("SELECT value FROM meta WHERE key='embed_identity'").fetchone()
        identity_matches = identity is not None and identity[0] == self.embed_url + "|" + self.model
        return {"repo": str(self.repo), "database": str(self.db_path), "identity_matches": identity_matches,
                "files": con.execute("SELECT count(*) FROM files").fetchone()[0],
                "chunks": con.execute("SELECT count(*) FROM chunks").fetchone()[0],
                "pending": con.execute("SELECT count(*) FROM chunks WHERE vector IS NULL" if identity_matches else "SELECT count(*) FROM chunks").fetchone()[0],
                "model": self.model}

    def status(self, check_fresh=False):
        with self.connection() as con:
            result = self._counts(con)
            last = con.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()
            result["last_sync"] = last[0] if last else None
            if check_fresh:
                stored = {r["path"]: r["hash"] for r in con.execute("SELECT path,hash FROM files")}
                live = {p: item[0] for p, item in self._snapshot().items()}
                result["fresh"] = stored == live and last is not None
            return result

    def search(self, query, limit=8):
        if limit < 1 or limit > 50 or len(query) > 1000:
            raise ValueError("Use 1..50 results and a query no longer than 1000 characters")
        with self.connection() as con:
            rows = {r["id"]: dict(r) for r in con.execute(
                "SELECT c.*, f.hash, f.metadata FROM chunks c JOIN files f USING(path)")}
            tokens = re.findall(r"[^\W_]+", query, re.UNICODE)[:24]
            expression = " OR ".join('"' + t + '"' for t in tokens)
            lexical = []
            if expression:
                lexical = [r[0] for r in con.execute(
                    "SELECT rowid FROM search WHERE search MATCH ? ORDER BY bm25(search) LIMIT 100", (expression,))]
            try:
                vectors = self.embedder(["search_query: " + query])
            except (OSError, ValueError, TypeError):
                vectors = None
            semantic = []
            identity = con.execute("SELECT value FROM meta WHERE key='embed_identity'").fetchone()
            if identity and identity[0] == self.embed_url + "|" + self.model and valid_vectors(vectors, 1):
                q = vectors[0]
                qnorm = math.sqrt(sum(v * v for v in q))
                for row in rows.values():
                    try:
                        v = json.loads(row["vector"]) if row["vector"] else None
                        if not valid_vectors([v], 1) or len(v) != len(q):
                            continue
                        score = sum(a * b for a, b in zip(q, v)) / (qnorm * math.sqrt(sum(x * x for x in v)))
                        semantic.append((row["id"], score))
                    except (ValueError, TypeError):
                        continue
                semantic.sort(key=lambda pair: pair[1], reverse=True)
            scores = {}
            for ranking in (lexical, [pair[0] for pair in semantic[:100]]):
                for rank, rowid in enumerate(ranking, 1):
                    scores[rowid] = scores.get(rowid, 0.0) + 1.0 / (60 + rank)
            visible = self._paths()
            fresh = {}
            hits = []
            for rowid in sorted(scores, key=scores.get, reverse=True):
                row = rows[rowid]
                path = row["path"]
                if path not in fresh:
                    source = self._read(path) if path in visible else None
                    fresh[path] = digest(source) if source is not None else None
                if fresh[path] != row["hash"]:
                    continue
                fields = json.loads(row.pop("metadata"))
                row.pop("vector")
                for private in ("attempted_at", "lease", "lease_until"):
                    row.pop(private, None)
                row["tags"] = fields["tags"]
                row["language"] = fields["language"]
                row["score"] = round(scores[rowid], 6)
                row["retrieval"] = "hybrid" if semantic else "keyword"
                hits.append(row)
                if len(hits) >= limit:
                    break
            return hits


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["register", "sync", "search", "status", "watch", "backfill"])
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--embed-url", default=DEFAULT_URL)
    parser.add_argument("--model", default="nomic-embed-text")
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--interval", type=float, default=15)
    return parser


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "backfill":
            if not args.config:
                parser.error("backfill needs --config")
            args.state_dir.mkdir(parents=True, exist_ok=True)
            log = logging.getLogger("repo-knowledge-backfill")
            log.setLevel(logging.INFO)
            log.addHandler(RotatingFileHandler(args.state_dir / "backfill.log", maxBytes=2_000_000, backupCount=2, encoding="utf8"))
            while True:
                config = json.loads(args.config.read_text(encoding="utf-8-sig"))
                pending = False
                for repo in config["repos"]:
                    try:
                        index = RepoIndex(repo, args.state_dir, config.get("embed_url", args.embed_url), config.get("model", args.model))
                        result = index.sync(max_chunks=64)
                        pending = pending or result["pending"] > 0
                        log.info(json.dumps(result))
                    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
                        pending = True
                        log.error(json.dumps({"repo": str(repo), "error": type(exc).__name__}))
                if not pending:
                    return 0
                time.sleep(2)
        if args.command == "watch":
            if not args.config or args.interval < 2:
                parser.error("watch needs --config and --interval >= 2")
            log = logging.getLogger("repo-knowledge")
            log.setLevel(logging.INFO)
            args.state_dir.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(args.state_dir / "watch.log", maxBytes=2_000_000, backupCount=2, encoding="utf8")
            log.addHandler(handler)
            # One watcher per state directory. File lock auto-releases on process death.
            lock_path = args.state_dir / "watch.lock"
            args.state_dir.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+b") as lock:
                if os.name == "nt":
                    import msvcrt
                    lock.seek(0)
                    if lock.read(1) == b"":
                        lock.write(b"0")
                        lock.flush()
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                while True:
                    try:
                        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
                        for repo in config["repos"]:
                            try:
                                index = RepoIndex(repo, args.state_dir, config.get("embed_url", args.embed_url), config.get("model", args.model), lock_timeout=0.25)
                                result = index.sync(max_chunks=int(config.get("watch_batch", 4)))
                                if result["changed"] or result["removed"] or result["embedded"] or result["pending"]:
                                    log.info(json.dumps(result))
                                receipt = index.db_path.with_suffix(".watch.json")
                                temp = receipt.with_suffix(".tmp")
                                temp.write_text(json.dumps(result), encoding="utf8")
                                temp.replace(receipt)
                            except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
                                log.error(json.dumps({"repo": str(repo), "error": type(exc).__name__}))
                    except (OSError, ValueError, KeyError) as exc:
                        log.error(json.dumps({"error": type(exc).__name__}))
                    time.sleep(args.interval)
        if not args.repo:
            parser.error("--repo is required")
        index = RepoIndex(args.repo, args.state_dir, args.embed_url, args.model)
        if args.command == "register":
            config_path = args.config or args.state_dir / "config.json"
            # The SQLite writer lock also serializes registry updates from agents.
            with sqlite3.connect(args.state_dir / "registry.sqlite3", timeout=30) as con:
                con.execute("BEGIN IMMEDIATE")
                config = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
                repos = config.setdefault("repos", [])
                if str(index.repo) not in repos:
                    repos.append(str(index.repo))
                config.setdefault("embed_url", args.embed_url)
                config.setdefault("model", args.model)
                config_path.parent.mkdir(parents=True, exist_ok=True)
                temp = config_path.with_suffix(".tmp")
                temp.write_text(json.dumps(config, indent=2), encoding="utf8")
                temp.replace(config_path)
            result, code = {"registered": str(index.repo), "config": str(config_path)}, 0
        elif args.command == "sync":
            result = index.sync(args.max_chunks)
            code = 2 if result["pending"] else 0
        elif args.command == "status":
            result = index.status(check_fresh=True)
            code = 0 if result["fresh"] and result["pending"] == 0 else 2
        else:
            result = {"repo": str(index.repo), "results": index.search(args.query, args.limit), "status": index.status()}
            code = 0
        print(json.dumps(result, ensure_ascii=True))
        return code
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": "Index operation failed; inspect paths, Git and local embedding health."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
