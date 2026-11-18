"""Claims file locking: claim/release/conflict, and no lost updates across processes."""

# Tags: claims, test-fixture
# Links: triad/claims.py
# Queries: "how is claims file locking tested"

from __future__ import annotations

import json
import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path

from triad.claims import (
    ClaimsLockError,
    _interprocess_claims_lock,
    claim,
    release,
    status,
)


def _mp_claim_batch(claims_path, agent, touching, prefix, count, out_path):
    """Child entry point. Must stay importable for the spawn start method."""
    try:
        ids = []
        conflict_ids = []
        for i in range(count):
            entry, conflicts = claim(
                task=f"{prefix}-{i}",
                touching=[touching],
                project="mp-suite",
                agent=agent,
                claims_path=Path(claims_path),
                lock_timeout=10,
            )
            ids.append(entry["id"])
            conflict_ids.extend(c.get("id") for c in conflicts if isinstance(c, dict))
        Path(out_path).write_text(
            json.dumps({"ok": True, "ids": ids, "conflicts": conflict_ids}),
            encoding="utf-8",
        )
    except Exception as exc:
        Path(out_path).write_text(json.dumps({"ok": False, "error": repr(exc)}), encoding="utf-8")
        raise


def _hold_claims_lock(claims_path, started, stop):
    with _interprocess_claims_lock(Path(claims_path), timeout=5):
        Path(started).write_text("ready", encoding="utf-8")
        deadline = time.monotonic() + 10
        while not Path(stop).exists() and time.monotonic() < deadline:
            time.sleep(0.05)


class TestClaims(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="triad-claims-")
        self.claims_path = Path(self._tmp.name) / "CLAIMS.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_claim_release_and_conflict(self):
        first, conflicts = claim(
            task="edit parser",
            touching=["src/a.py"],
            project="demo",
            agent="alpha",
            claims_path=self.claims_path,
        )
        self.assertEqual(conflicts, [])
        self.assertEqual(first["status"], "in_progress")
        self.assertEqual(first["touching"], ["src/a.py"])

        other, other_conflicts = claim(
            task="edit docs",
            touching=["docs/readme.md"],
            project="demo",
            agent="beta",
            claims_path=self.claims_path,
        )
        self.assertEqual(other_conflicts, [])

        overlap, overlap_conflicts = claim(
            task="also the parser",
            touching=["src/a.py"],
            project="demo",
            agent="beta",
            claims_path=self.claims_path,
        )
        self.assertEqual([c["id"] for c in overlap_conflicts], [first["id"]])

        active = status(project="demo", claims_path=self.claims_path)
        self.assertEqual({row["id"] for row in active}, {first["id"], other["id"], overlap["id"]})

        self.assertTrue(release(first["id"], claims_path=self.claims_path))
        self.assertFalse(release(first["id"], claims_path=self.claims_path))
        remaining = {row["id"] for row in status(claims_path=self.claims_path)}
        self.assertNotIn(first["id"], remaining)
        self.assertIn(other["id"], remaining)
        self.assertIn(overlap["id"], remaining)

    def test_blank_task_is_rejected(self):
        with self.assertRaises(ValueError):
            claim(task="   ", project="demo", agent="alpha", claims_path=self.claims_path)
        self.assertFalse(self.claims_path.exists())

    def test_lock_timeout_is_logged_and_raised(self):
        ctx = multiprocessing.get_context("spawn")
        started = Path(self._tmp.name) / "started"
        stop = Path(self._tmp.name) / "stop"
        holder = ctx.Process(
            target=_hold_claims_lock,
            args=(str(self.claims_path), str(started), str(stop)),
        )
        holder.start()
        try:
            deadline = time.monotonic() + 5
            while not started.exists():
                if holder.exitcode is not None or time.monotonic() > deadline:
                    raise AssertionError(f"lock holder did not start (exit {holder.exitcode})")
                time.sleep(0.02)
            with self.assertLogs("triad.claims", level="ERROR") as caught:
                with self.assertRaises(ClaimsLockError):
                    claim(
                        task="blocked",
                        touching=["src/a.py"],
                        project="demo",
                        agent="gamma",
                        claims_path=self.claims_path,
                        lock_timeout=0.2,
                    )
            self.assertTrue(any("Timed out" in line for line in caught.output))
            self.assertFalse(self.claims_path.exists())
        finally:
            stop.write_text("stop", encoding="utf-8")
            holder.join(timeout=5)
            if holder.is_alive():
                holder.terminate()
                holder.join(timeout=2)
        self.assertEqual(holder.exitcode, 0)

    def _run_pair(self, touching_a, touching_b, count):
        ctx = multiprocessing.get_context("spawn")
        out_a = Path(self._tmp.name) / "a.json"
        out_b = Path(self._tmp.name) / "b.json"
        proc_a = ctx.Process(
            target=_mp_claim_batch,
            args=(str(self.claims_path), "alpha", touching_a, "alpha", count, str(out_a)),
        )
        proc_b = ctx.Process(
            target=_mp_claim_batch,
            args=(str(self.claims_path), "beta", touching_b, "beta", count, str(out_b)),
        )
        proc_a.start()
        proc_b.start()
        proc_a.join(timeout=30)
        proc_b.join(timeout=30)
        self.assertEqual(proc_a.exitcode, 0, out_a.read_text(encoding="utf-8") if out_a.exists() else "no output")
        self.assertEqual(proc_b.exitcode, 0, out_b.read_text(encoding="utf-8") if out_b.exists() else "no output")
        report_a = json.loads(out_a.read_text(encoding="utf-8"))
        report_b = json.loads(out_b.read_text(encoding="utf-8"))
        self.assertTrue(report_a["ok"] and report_b["ok"])
        stored = json.loads(self.claims_path.read_text(encoding="utf-8"))
        return report_a, report_b, stored

    def test_multiprocess_distinct_paths_both_persist(self):
        count = 8
        report_a, report_b, stored = self._run_pair("src/a.py", "src/b.py", count)
        expected = set(report_a["ids"]) | set(report_b["ids"])
        self.assertEqual(len(expected), count * 2)
        self.assertEqual(set(stored), expected)
        self.assertEqual(report_a["conflicts"], [])
        self.assertEqual(report_b["conflicts"], [])

    def test_multiprocess_overlapping_paths_are_not_lost(self):
        count = 8
        report_a, report_b, stored = self._run_pair("src/shared.py", "src/shared.py", count)
        expected = set(report_a["ids"]) | set(report_b["ids"])
        self.assertEqual(len(expected), count * 2)
        self.assertEqual(set(stored), expected)
        # Same-agent claims are not conflicts. Across agents, the later claim of
        # each pair must see the earlier one, so the observation count is count*count.
        seen = report_a["conflicts"] + report_b["conflicts"]
        self.assertEqual(len(seen), count * count)
        self.assertTrue(report_a["conflicts"] or report_b["conflicts"])
        self.assertTrue(set(seen).issubset(expected))


if __name__ == "__main__":
    unittest.main()
