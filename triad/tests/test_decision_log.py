"""Regression tests for the shared SQLite decision-ledger writer lock."""

import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest

from triad.decision_log import add_block, query_blocks


def _append(path, **kwargs):
    return add_block("append fixture", "verify the writer", project="fixture", agent="test", log_path=path, **kwargs)


@pytest.mark.parametrize("tail", [b'{"id":', b"\xff", b'{"project":"fixture"}', b""])
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


def test_parallel_writers_have_one_parent_chain(tmp_path):
    path = tmp_path / "ledger.jsonl"
    seed = _append(path)
    count = 40
    script = """
import sys
from pathlib import Path
from triad.decision_log import add_block

for index in range(int(sys.argv[2])):
    block = add_block(f"append {index}", "verify the writer", project="fixture",
                      agent="test", log_path=Path(sys.argv[1]))
    print(block["id"])
"""
    cmd = [sys.executable, "-B", "-c", script, str(path), str(count)]
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as first:
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as second:
            try:
                first_ids, _ = first.communicate(timeout=20)
                second_ids, _ = second.communicate(timeout=20)
            finally:
                for writer in (first, second):
                    if writer.poll() is None:
                        writer.kill()
            assert first.returncode == second.returncode == 0

    blocks = query_blocks(log_path=path, limit=1 + 2 * count)
    ids = [block["id"] for block in blocks]
    assert len(ids) == len(set(ids)) == 1 + 2 * count
    assert set(ids) == {seed["id"], *first_ids.splitlines(), *second_ids.splitlines()}
    assert [block["parent"] for block in blocks] == [None, *ids[:-1]]
