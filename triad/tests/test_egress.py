"""Hermetic tests for pre-send egress redaction. No live model calls."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from triad.egress import (
    filter_diff,
    memory_query_allowed,
    redact,
    sanitize_egress,
)
from triad.advisor_manager import build_advisor_prompt


class TestEgressRedaction(unittest.TestCase):
    def test_redacts_pem_private_key(self):
        pem = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF6PZGFw=\n"
            "-----END RSA PRIVATE KEY-----"
        )
        out = redact(f"key material:\n{pem}\n")
        self.assertIn("[REDACTED PRIVATE KEY]", out)
        self.assertNotIn("BEGIN RSA PRIVATE KEY", out)

    def test_redacts_bearer_token(self):
        out = redact("Authorization: Bearer super-secret-token-value")
        self.assertNotIn("super-secret-token-value", out)
        self.assertIn("[REDACTED]", out)

    def test_default_ignores_filter_eval_and_env(self):
        diff = (
            "diff --git a/eval/results.jsonl b/eval/results.jsonl\n"
            "--- a/eval/results.jsonl\n"
            "+++ b/eval/results.jsonl\n"
            "+secret-line\n"
            "diff --git a/src/ok.py b/src/ok.py\n"
            "--- a/src/ok.py\n"
            "+++ b/src/ok.py\n"
            "+print(1)\n"
        )
        filtered = filter_diff(diff)
        self.assertNotIn("secret-line", filtered)
        self.assertIn("print(1)", filtered)

    def test_triadignore_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".triadignore").write_text("secrets/\n", encoding="utf-8")
            diff = (
                "diff --git a/secrets/key.txt b/secrets/key.txt\n"
                "--- a/secrets/key.txt\n"
                "+++ b/secrets/key.txt\n"
                "+sk-live-abcdef\n"
                "diff --git a/app.py b/app.py\n"
                "--- a/app.py\n"
                "+++ b/app.py\n"
                "+x = 1\n"
            )
            filtered = filter_diff(diff, root=root)
            self.assertNotIn("sk-live-abcdef", filtered)
            self.assertIn("x = 1", filtered)

    def test_build_advisor_prompt_does_not_echo_secret(self):
        sentinel = "Bearer live-sentinel-token-xyz"
        built = build_advisor_prompt(
            f"review this {sentinel}",
            context=f"context {sentinel}",
            diff=(
                "diff --git a/a.py b/a.py\n"
                "--- a/a.py\n"
                "+++ b/a.py\n"
                f"+{sentinel}\n"
            ),
            mode="review_diff",
        )
        self.assertNotIn("live-sentinel-token-xyz", built)
        self.assertIn("Bearer [REDACTED]", built)

    def test_memory_query_allowed_blocks_security_findings(self):
        self.assertFalse(memory_query_allowed("CWE-79 XSS finding in login"))
        self.assertTrue(memory_query_allowed("what did I work on Monday"))


if __name__ == "__main__":
    unittest.main()
