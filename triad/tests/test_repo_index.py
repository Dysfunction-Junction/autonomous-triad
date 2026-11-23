# Tags: tooling, local-llm, test-fixture
# Links: triad/repo_index.py
# Queries: "what verifies incremental repository indexing"
import json
import subprocess

import pytest


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    return root


@pytest.fixture
def index(repo, tmp_path):
    from triad.repo_index import RepoIndex

    return RepoIndex(repo, tmp_path / "state", embedder=lambda texts: [[1.0, float("expiry" in t), 0.5] for t in texts])


def write(repo, name, text):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_new_files_have_tags_symbols_and_searchable_source(repo, index):
    write(repo, "auth.py", '# Tags: routing, cache\n# Queries: "when do credentials expire"\ndef expiry_seconds():\n    return 30\n')
    result = index.sync()
    assert result["pending"] == 0
    assert result["files"] == 1
    hits = index.search("credentials expire")
    assert hits and hits[0]["path"] == "auth.py"
    assert "routing" in hits[0]["tags"]
    assert hits[0]["hash"]
    assert hits[0]["start_line"] >= 1


def test_noop_does_not_reembed_and_edit_replaces_old_chunks(repo, index):
    write(repo, "auth.py", "def expiry_seconds():\n    return 30\n")
    assert index.sync()["embedded"] > 0
    assert index.sync()["embedded"] == 0
    write(repo, "auth.py", "def revoke_session():\n    return False\n")
    assert index.search("expiry_seconds") == []  # stale source suppressed before next sync
    result = index.sync()
    assert result["changed"] == 1
    assert "revoke_session" in index.search("revoke session")[0]["text"]
    assert "expiry_seconds" not in json.dumps(index.search("expiry_seconds"))


def test_rename_and_delete_remove_old_paths(repo, index):
    path = write(repo, "old.py", "def hello():\n    return 'hello'\n")
    index.sync()
    path.rename(repo / "new.py")
    result = index.sync()
    assert result["removed"] == 1
    assert {h["path"] for h in index.search("hello")} == {"new.py"}
    (repo / "new.py").unlink()
    assert index.sync()["files"] == 0
    assert index.search("hello") == []


def test_secrets_ignored_files_and_generated_output_never_enter_database(repo, index):
    write(repo, ".gitignore", "ignored.py\n")
    write(repo, ".env", "KEY=private-value")
    write(repo, "ignored.py", "hidden = 10")
    write(repo, "dist/bundle.js", "const bundled = 1")
    write(repo, "service-account.json", '{"private_key": "private-value"}')
    write(repo, "leak.py", 'api_key = "sk-' + "a" * 40 + '"')
    write(repo, "safe.py", "def safe():\n    return 1\n")
    index.sync()
    assert index.status()["files"] == 1
    blob = index.db_path.read_bytes()
    assert b"private-value" not in blob
    assert ("sk-" + "a" * 40).encode() not in blob


def test_tracked_file_becoming_secret_is_removed(repo, index):
    path = write(repo, "safe.py", "def safe():\n    return 1\n")
    index.sync()
    path.write_text('password = "really-private-value"\n', encoding="utf8")
    assert index.sync()["files"] == 0
    assert index.search("safe") == []


def test_failed_embeddings_remain_pending_and_retry(repo, index):
    write(repo, "cache.py", "def cached_response():\n    return 1\n")
    index.embedder = lambda texts: None
    result = index.sync()
    assert result["pending"] > 0
    assert index.search("cached response")
    index.embedder = lambda texts: [[1.0, 0.0] for _ in texts]
    assert index.sync()["pending"] == 0


def test_model_change_invalidates_vectors(repo, index, tmp_path):
    from triad.repo_index import RepoIndex

    write(repo, "cache.py", "def cached_response():\n    return 1\n")
    index.sync()
    other = RepoIndex(repo, tmp_path / "state", model="changed", embedder=lambda texts: None)
    assert other.sync()["pending"] > 0


def test_checkouts_are_isolated(repo, index, tmp_path):
    from triad.repo_index import RepoIndex

    write(repo, "one.py", "def first_project():\n    return 1\n")
    index.sync()
    second = tmp_path / "other"
    second.mkdir()
    git(second, "init", "-q")
    other = RepoIndex(second, tmp_path / "state", embedder=lambda texts: [[1.0, 0.0] for _ in texts])
    assert other.db_path != index.db_path
    assert other.sync()["files"] == 0
    assert other.search("first_project") == []


@pytest.mark.parametrize("vectors", [None, [[float("nan"), 1.0]], [[0.0, 0.0]], [[True, 1.0]], [[1.0]], [[1.0, 2.0], [1.0, 2.0]]])
def test_invalid_embedding_response_is_pending(repo, index, vectors):
    write(repo, "auth.py", "def expiry_seconds():\n    return 30\n")
    # A single source chunk: extra vectors are a protocol failure.
    index.embedder = lambda texts: vectors
    assert index.sync()["pending"] > 0


def test_oversized_or_non_utf8_files_are_skipped(repo, index):
    write(repo, "huge.py", "x" * 1_100_000)
    (repo / "binary.py").write_bytes(b"\xff\x00\xfe")
    assert index.sync()["files"] == 0


def test_symlink_cannot_import_external_content(repo, index, tmp_path):
    external = write(tmp_path, "outside.py", "private_external = 42")
    try:
        (repo / "linked.py").symlink_to(external)
    except OSError:
        pytest.skip("OS does not permit unprivileged symlinks")
    assert index.sync()["files"] == 0


def test_status_checks_freshness(repo, index):
    path = write(repo, "a.py", "def hello():\n    return 1\n")
    index.sync()
    assert index.status(check_fresh=True)["fresh"] is True
    path.write_text("def goodbye():\n    return 2\n", encoding="utf8")
    assert index.status(check_fresh=True)["fresh"] is False



def test_query_never_uses_vectors_from_another_model(repo, index, tmp_path):
    from triad.repo_index import RepoIndex

    write(repo, "one.py", "def hello():\\n    return 1\\n".replace("\\\\n", "\\n"))
    index.sync()
    other = RepoIndex(repo, tmp_path / "state", model="changed", embedder=lambda texts: [[1.0, 0.0, 0.5] for _ in texts])
    assert other.status()["pending"] > 0
    assert other.search("hello")[0]["retrieval"] == "keyword"


def test_non_loopback_embedding_endpoint_is_rejected(repo, tmp_path):
    from triad.repo_index import RepoIndex

    with pytest.raises(ValueError, match="loopback"):
        RepoIndex(repo, tmp_path / "state", embed_url="https://example.com")


def test_git_subdirectory_cannot_borrow_parent_scope(repo, tmp_path):
    from triad.repo_index import RepoIndex

    child = repo / "child"
    child.mkdir()
    with pytest.raises(ValueError, match="checkout root"):
        RepoIndex(child, tmp_path / "state")


def test_concurrent_writers_leave_one_current_snapshot(repo, index):
    from concurrent.futures import ThreadPoolExecutor

    write(repo, "one.py", "def hello():\n    return 1\n")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: index.sync(), range(2)))
    assert sum(r["embedded"] for r in results) == 1
    assert index.status(check_fresh=True)["fresh"] is True


def test_register_adds_repo_without_clobbering_existing_config(repo, tmp_path, capsys):
    from triad.repo_index import main

    state = tmp_path / "registry"
    state.mkdir()
    config = state / "config.json"
    config.write_text(json.dumps({"repos": [], "python_path": "python"}), encoding="utf8")
    assert main(["register", "--repo", str(repo), "--state-dir", str(state)]) == 0
    assert main(["register", "--repo", str(repo), "--state-dir", str(state)]) == 0
    data = json.loads(config.read_text())
    assert data["repos"] == [str(repo.resolve())]
    assert data["python_path"] == "python"



def test_default_sync_publishes_completed_batches_before_draining(repo, index):
    for number in range(70):
        write(repo, f"item{number}.py", f"def item{number}():\n    return {number}\n")
    calls = []
    def embed(texts):
        calls.append(len(texts))
        if len(calls) == 65:
            # A reader must see the first committed batch even during initial backfill.
            assert index.status()["files"] == 70
            assert index.status()["pending"] < 70
        return [[1.0, 0.5] for _ in texts]
    index.embedder = embed
    assert index.sync()["pending"] == 0



def test_new_edits_embed_before_historical_backlog(repo, index):
    for number in range(5):
        write(repo, f"old{number}.py", f"def old{number}():\n    return {number}\n")
    assert index.sync(max_chunks=1)["pending"] == 4
    write(repo, "new.py", "def brand_new_behavior():\n    return 9\n")
    index.sync(max_chunks=1)
    with index.connection() as con:
        assert con.execute("SELECT count(*) FROM chunks WHERE path='new.py' AND vector IS NOT NULL").fetchone()[0] == 1



def test_watcher_lock_contention_is_bounded(repo, index, tmp_path):
    import sqlite3
    import time
    from triad.repo_index import RepoIndex

    other = RepoIndex(repo, tmp_path / "state", lock_timeout=0.02)
    with index.connection() as con:
        con.execute("BEGIN IMMEDIATE")
        start = time.monotonic()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            other.sync(max_chunks=1)
        assert time.monotonic() - start < 1



def test_failed_chunk_does_not_starve_later_files(repo, index):
    write(repo, "a.py", "def rejected_chunk():\n    return 1\n")
    write(repo, "b.py", "def healthy_chunk():\n    return 2\n")
    index.embedder = lambda texts: None if "rejected_chunk" in texts[0] else [[1.0, 0.5]]
    assert index.sync(max_chunks=1)["pending"] == 2
    assert index.sync(max_chunks=1)["pending"] == 1
    with index.connection() as con:
        assert con.execute("SELECT vector FROM chunks WHERE path='b.py'").fetchone()[0] is not None


def test_embedding_request_does_not_hold_database_writer_lock(repo, index):
    import sqlite3

    write(repo, "one.py", "def hello():\n    return 1\n")
    def embed(texts):
        with sqlite3.connect(index.db_path, timeout=0.02) as con:
            con.execute("INSERT OR REPLACE INTO meta VALUES('concurrent_probe','ok')")
        return [[1.0, 0.5]]
    index.embedder = embed
    assert index.sync()["pending"] == 0


def test_embedding_cannot_attach_to_replaced_source_chunk(repo, index, tmp_path):
    from triad.repo_index import RepoIndex

    path = write(repo, "one.py", "def old_source():\n    return 1\n")
    other = RepoIndex(repo, tmp_path / "state", embedder=lambda texts: [[0.5, 1.0]])
    def embed(texts):
        path.write_text("def new_source():\n    return 2\n", encoding="utf8")
        other.sync()
        return [[1.0, 0.5]]
    index.embedder = embed
    index.sync()
    with index.connection() as con:
        row = con.execute("SELECT text,vector FROM chunks").fetchone()
    assert "new_source" in row["text"]
    assert json.loads(row["vector"]) == [0.5, 1.0]



def test_backfill_drains_each_registered_repo_before_exit(repo, tmp_path, monkeypatch):
    import triad.repo_index as module

    write(repo, "one.py", "def hello():\n    return 1\n")
    second = tmp_path / "second"
    second.mkdir()
    git(second, "init", "-q")
    write(second, "two.py", "def goodbye():\n    return 2\n")
    state = tmp_path / "backfill-state"
    state.mkdir()
    config = state / "config.json"
    config.write_text(json.dumps({"repos": [str(repo), str(second)]}), encoding="utf8")
    original = module.RepoIndex
    monkeypatch.setattr(module, "RepoIndex", lambda *args, **kwargs: original(*args, **kwargs, embedder=lambda texts: [[1.0, 0.5] for _ in texts]))
    assert module.main(["backfill", "--config", str(config), "--state-dir", str(state)]) == 0
    for root in (repo, second):
        result = original(root, state).status(check_fresh=True)
        assert result["fresh"] and result["pending"] == 0

