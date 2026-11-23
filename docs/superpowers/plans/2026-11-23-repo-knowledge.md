# Repository Knowledge Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. The owner requests end-to-end setup and standing instructions waive intermediate approvals.

**Goal:** Keep eligible repository content tagged, embedded and searchable as agents create or edit it.
**Architecture:** Local SQLite per checkout, existing nomic localhost endpoint, registered polling watcher, static Cartograph companion.
**Tech Stack:** Python standard library, Git, SQLite FTS5, existing llama.cpp; isolated npm Cartograph 1.3.0.
**Spec:** docs/superpowers/specs/2026-11-23-repo-knowledge-design.md

## Global Constraints
$0 incremental cost; no secrets indexed or committed; no cross-repo retrieval or world-model ingestion; leave unrelated CLAUDE.md and app edits alone. No daemon restart.

## Review Focus
Stale/deleted vectors, filename and content secrets, concurrent writers, source races, model changes.

- [x] Add lifecycle/filter/isolation regression tests in triad/tests/test_repo_index.py and observe missing implementation failure.
- [x] Implement triad/repo_index.py sync/search/status/watch CLI, bounded embeddings, truthful failures.
- [x] Add scripts/setup-repo-knowledge.ps1 and docs/REPO_KNOWLEDGE.md; install local command wrappers and hidden logon watcher.
- [x] Verify full repository suite/lint/security, actual nomic retrieval and automatic lifecycle updates; obtain Triad diff review.
- [ ] Update shared AGENTS.md, ecosystem checklists/diagram, dated handoff and shared memory; commit and push only owned files.

Ruling: work in canonical checkout with new scoped files; only preexisting untracked CLAUDE.md is unrelated and will not be staged. Do not create another competing runtime checkout.


Verification: full suite678 passed/12 skipped/90 subtests; new Python lint/security clean; live watcher lifecycle passed. Existing repo-wide lint142 errors unchanged. Review fixes accepted. Historical vectors remain queued in resumable background task.
