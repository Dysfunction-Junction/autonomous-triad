"""Regression tests for the shared SQLite decision-ledger writer lock."""

import sqlite3
from pathlib import Path
import subprocess
import sys
import time
from contextlib import ExitStack, closing

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

from triad.decision_log import add_block, query_blocks, resolve_block


def _append(path, **kwargs):
    return add_block("append fixture", "verify the writer", project="fixture", agent="test", log_path=path, **kwargs)


@pytest.mark.parametrize("tail", [b'{"id":', b"\xff", b"\x1a", b'{"project":"fixture"}', b""])
def test_append_repairs_missing_final_newline(tmp_path, tail):
    path = tmp_path / "ledger.jsonl"
    first = _append(path)
    prefix = path.read_bytes().rstrip(b"\n") + (b"\n" + tail if tail else b"")
    path.write_bytes(prefix)

    second = _append(path)

    assert second["parent"] == first["id"]
    assert path.read_bytes().startswith(prefix + b"\n{")
    assert path.read_bytes().endswith(b"}\n")
    assert query_blocks(log_path=path, limit=1) == [second]


def test_append_to_existing_empty_file(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.touch()

    block = _append(path)

    assert block["parent"] is None
    assert path.read_bytes().startswith(b"{")
    assert query_blocks(log_path=path) == [block]


def test_append_after_crlf(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _append(path)
    prefix = path.read_bytes().removesuffix(b"\n") + b"\r\n"
    path.write_bytes(prefix)

    second = _append(path)

    assert path.read_bytes().startswith(prefix + b"{")
    assert second["parent"] == first["id"]
    assert query_blocks(log_path=path) == [first, second]


def test_lock_is_created_and_released_on_success_and_error(tmp_path):
    path = tmp_path / "new" / "ledger.jsonl"
    lock_path = path.with_name(path.name + ".lock.sqlite")
    _append(path)
    original = path.read_bytes()
    assert lock_path.is_file()

    with pytest.raises(ValueError, match="unknown block id"):
        _append(path, supersedes="missing")
    assert path.read_bytes() == original

    with closing(sqlite3.connect(lock_path, timeout=0, isolation_level=None)) as lock:
        lock.execute("BEGIN IMMEDIATE")
        lock.execute("COMMIT")


def test_lock_timeout_leaves_log_unchanged(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _append(path)
    original = path.read_bytes()
    with closing(sqlite3.connect(f"{path}.lock.sqlite", isolation_level=None)) as lock:
        lock.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            _append(path)
        assert time.monotonic() - started >= 4.5
        assert path.read_bytes() == original

    assert _append(path)["parent"] == first["id"]


def _run_contending_writers(path, script, argument):
    worker_setup = """
import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1])
ready = Path(sys.argv[2])
connect = sqlite3.connect

def report_lock_attempt(*args, **kwargs):
    lock = connect(*args, **kwargs)
    lock.set_trace_callback(lambda sql: ready.touch() if sql == "BEGIN IMMEDIATE" else None)
    return lock

sqlite3.connect = report_lock_attempt
"""
    original = path.read_bytes()
    markers = [path.with_name(f"writer-{index}.ready") for index in range(2)]
    with ExitStack() as stack:
        lock = stack.enter_context(closing(sqlite3.connect(f"{path}.lock.sqlite", isolation_level=None)))
        lock.execute("BEGIN IMMEDIATE")
        writers = []
        try:
            for marker in markers:
                cmd = [sys.executable, "-B", "-c", worker_setup + script, str(path), str(marker), str(argument)]
                writers.append(stack.enter_context(subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, cwd=REPO_ROOT)))

            deadline = time.monotonic() + 4
            while not all(marker.exists() for marker in markers):
                assert all(writer.poll() is None for writer in writers)
                assert time.monotonic() < deadline, "writers did not reach BEGIN IMMEDIATE"
                time.sleep(0.01)
            assert path.read_bytes() == original
            lock.execute("COMMIT")

            return [(writer.communicate(timeout=20)[0], writer.returncode) for writer in writers]
        finally:
            for writer in writers:
                if writer.poll() is None:
                    writer.kill()


def test_parallel_writers_have_one_parent_chain(tmp_path):
    path = tmp_path / "ledger.jsonl"
    seed = _append(path)
    count = 40
    script = """
from triad.decision_log import add_block

for index in range(int(sys.argv[3])):
    block = add_block(f"append {index}", "verify the writer", project="fixture",
                      agent="test", log_path=path)
    print(block["id"])
"""
    (first_ids, first_status), (second_ids, second_status) = _run_contending_writers(path, script, count)
    assert first_status == second_status == 0

    blocks = query_blocks(log_path=path, limit=1 + 2 * count)
    ids = [block["id"] for block in blocks]
    assert len(ids) == len(set(ids)) == 1 + 2 * count
    assert set(ids) == {seed["id"], *first_ids.splitlines(), *second_ids.splitlines()}
    assert [block["parent"] for block in blocks] == [None, *ids[:-1]]


def test_parallel_resolvers_close_block_once(tmp_path):
    path = tmp_path / "ledger.jsonl"
    seed = _append(path)
    script = """
from triad.decision_log import resolve_block

try:
    block = resolve_block(sys.argv[3], "done", log_path=path)
except ValueError as error:
    print(error)
    sys.exit(2)
print(block["id"])
"""
    results = _run_contending_writers(path, script, seed["id"])

    assert sorted(status for _, status in results) == [0, 2]
    first, resolution = query_blocks(log_path=path)
    assert first == seed
    assert resolution["supersedes"] == resolution["parent"] == seed["id"]
    assert resolution["trace_id"] == seed["trace_id"]
    assert (resolution["id"] + "\n", 0) in results
    assert (f"block {seed['id']} was already resolved by [{resolution['id']}]\n", 2) in results


def test_add_cannot_supersede_a_closed_or_superseded_block(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _append(path)
    resolution = resolve_block(first["id"], "done", log_path=path)
    original = path.read_bytes()

    with pytest.raises(ValueError, match="was already resolved by"):
        _append(path, supersedes=first["id"])
    with pytest.raises(ValueError, match="is already resolved as 'done'"):
        _append(path, supersedes=resolution["id"])

    assert path.read_bytes() == original
