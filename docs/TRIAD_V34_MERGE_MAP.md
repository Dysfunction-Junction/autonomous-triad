# Triad v3.4 merge map (generated)

Generated 2026-10-28 21:34 by `scripts/triad_unify_audit.py` from `autonomous-triad@762e2c3` (side **A**) and `sovereign-exocortex@ea4a645` (main) `packages/triad` (side **B**). Tracked files only, CRLF normalized to LF. Regenerate before acting.

## 1. Tracked files

- A tracks 97 files; B tracks 71 under `packages/triad`.
- Shared paths: 64 (44 identical, 20 diverged).
- Only in A: 33. Only in B: 7.

### Only in B (must be ported into A)

- `package.json` (last B commit: 8d8bbde 2026-10-09 feat(exocortex): initialize sovereign-exocortex monorepo workspace and single daemon substrate)
- `triad/docker_runner.py` (last B commit: b1b264d 2026-10-28 fix(triad): run verification containers as the invoking uid:gid (row 2.4a) (#39))
- `triad/morphogenetic.py` (last B commit: 92223d7 2026-10-28 2.3a: re-tier self_heal_restore to T2 (#59))
- `triad/tests/test_docker_runner.py` (last B commit: d44ba53 2026-10-28 4.0a: surface calibration samples in shadow mode (#57))
- `triad/tests/test_local_llm_backend.py` (last B commit: 8faffda 2026-10-28 feat(triad): move the local advisor from Ollama to llama.cpp :8080 (#22))
- `triad/tests/test_morphogenetic.py` (last B commit: 675f258 2026-10-28 feat(triad): morphogenetic engine default off, diff-size cap, reproduction gate (row 2.4) (#50))
- `triad/tests/test_morphogenetic_gates.py` (last B commit: bee3c6a 2026-10-28 2.4b: static and security scan gate for morphogenetic engine (#56))

### Only in A, under `triad/` or packaging (B lacks them)

- `bin/triad`
- `bin/triad.cmd`
- `bin/triad.ps1`
- `triad/agent/__init__.py`
- `triad/agent/cli.py`
- `triad/agent/router.py`
- `triad/agent/runtime.py`
- `triad/agent/tools.py`
- `triad/agent/tracker.py`
- `triad/sync_manager.py`
- `triad/tests/test_agent.py`
- `triad/tests/test_sync_manager.py`
- `uv.lock`

### Diverged shared files

| File | Last A commit | Last B commit |
|---|---|---|
| `pyproject.toml` | e1f2479 2026-10-27 feat(agent): autonomous zero-cost terminal agent with RouteLLM dynamic waterfall and llama-server migration | 8d8bbde 2026-10-09 feat(exocortex): initialize sovereign-exocortex monorepo workspace and single daemon substrate |
| `triad/advisor_manager.py` | e1f2479 2026-10-27 feat(agent): autonomous zero-cost terminal agent with RouteLLM dynamic waterfall and llama-server migration | 8faffda 2026-10-28 feat(triad): move the local advisor from Ollama to llama.cpp :8080 (#22) |
| `triad/advisors.json` | f58a7a9 2026-10-27 feat(routing): task-aware model routing and onboard client integration for Antigravity, Claude, Codex, and Ollama | 8faffda 2026-10-28 feat(triad): move the local advisor from Ollama to llama.cpp :8080 (#22) |
| `triad/bench/docker_harness.py` | 52d6c0c 2026-10-06 fix(bench): score a Docker run only when every target test passes | aee14c2 2026-10-28 fix(triad): make checkout_argv work on Git < 2.44 by validating hex SHA (row 0.5) (#24) |
| `triad/bench/swebench_runner.py` | a48b7cf 2026-10-06 fix(bench): treat a session-limit reply as a judge error | 82c0ec5 2026-10-15 fix: close P11 mesh and triad bench findings |
| `triad/intent_engine.py` | e1f2479 2026-10-27 feat(agent): autonomous zero-cost terminal agent with RouteLLM dynamic waterfall and llama-server migration | 8faffda 2026-10-28 feat(triad): move the local advisor from Ollama to llama.cpp :8080 (#22) |
| `triad/nous_bridge.py` | e1f2479 2026-10-27 feat(agent): autonomous zero-cost terminal agent with RouteLLM dynamic waterfall and llama-server migration | 8d8bbde 2026-10-09 feat(exocortex): initialize sovereign-exocortex monorepo workspace and single daemon substrate |
| `triad/paths.py` | e1f2479 2026-10-27 feat(agent): autonomous zero-cost terminal agent with RouteLLM dynamic waterfall and llama-server migration | 8faffda 2026-10-28 feat(triad): move the local advisor from Ollama to llama.cpp :8080 (#22) |
| `triad/procutil.py` | a17ab38 2026-10-14 feat(triad): token-cutting diff bloat protection, nous atomic cooldowns, and codex refresh validation | 8d8bbde 2026-10-09 feat(exocortex): initialize sovereign-exocortex monorepo workspace and single daemon substrate |
| `triad/server.py` | 67afd73 2026-10-08 fix(server): harden biometric attestation validation with surrogate and multibyte UTF-8 byte bounds | 8faffda 2026-10-28 feat(triad): move the local advisor from Ollama to llama.cpp :8080 (#22) |
| `triad/tests/test_advisor_manager.py` | e1f2479 2026-10-27 feat(agent): autonomous zero-cost terminal agent with RouteLLM dynamic waterfall and llama-server migration | 78d9703 2026-10-13 Wire shadow proposals and add calibration benchmarks |
| `triad/tests/test_diff_bloat.py` | a17ab38 2026-10-14 feat(triad): token-cutting diff bloat protection, nous atomic cooldowns, and codex refresh validation | 8d8bbde 2026-10-09 feat(exocortex): initialize sovereign-exocortex monorepo workspace and single daemon substrate |
| `triad/tests/test_docker_harness.py` | a48b7cf 2026-10-06 fix(bench): treat a session-limit reply as a judge error | aee14c2 2026-10-28 fix(triad): make checkout_argv work on Git < 2.44 by validating hex SHA (row 0.5) (#24) |
| `triad/tests/test_hook.py` | f58a7a9 2026-10-27 feat(routing): task-aware model routing and onboard client integration for Antigravity, Claude, Codex, and Ollama | 4c9b79d 2026-10-15 fix(security): sandbox benchmark test execution |
| `triad/tests/test_intent_engine.py` | e1f2479 2026-10-27 feat(agent): autonomous zero-cost terminal agent with RouteLLM dynamic waterfall and llama-server migration | 8d8bbde 2026-10-09 feat(exocortex): initialize sovereign-exocortex monorepo workspace and single daemon substrate |
| `triad/tests/test_nous_bridge.py` | a17ab38 2026-10-14 feat(triad): token-cutting diff bloat protection, nous atomic cooldowns, and codex refresh validation | 8d8bbde 2026-10-09 feat(exocortex): initialize sovereign-exocortex monorepo workspace and single daemon substrate |
| `triad/tests/test_server.py` | 67afd73 2026-10-08 fix(server): harden biometric attestation validation with surrogate and multibyte UTF-8 byte bounds | e913746 2026-10-09 decisions P1-P11: signed labels, attestation chain, scope allowlist, delivery, self-heal gating, mesh audit |
| `triad/tests/test_worktree.py` | e1f2479 2026-10-27 feat(agent): autonomous zero-cost terminal agent with RouteLLM dynamic waterfall and llama-server migration | 51019a9 2026-10-22 test(triad): pin parent state in cmd_auto worktree test |
| `triad/triad_engine.py` | a978bf1 2026-10-27 feat(agent): default to local Triad orchestrator, add boundary-tracked cancellation, and secure architect delegation | 8faffda 2026-10-28 feat(triad): move the local advisor from Ollama to llama.cpp :8080 (#22) |
| `triad/worktree.py` | 81b7a56 2026-10-06 fix(bench): restore Claude as the primary judge | 3a3b5fc 2026-10-14 fix(triad,daemon): harden worktree snapshotting, phone normalizer and device registry isolation |

## 2. Definition-level map for diverged Python files

`A-only` and `B-only` are definitions present on one side. `changed` means both sides define it with different bodies. Line numbers are per side.

### `triad/advisor_manager.py`

A-only 2, B-only 2, changed 8.

- **A-only:** `const TASK_ADVISOR_PRIORITY` (A:60), `rank_advisors_for_task` (A:78)
- **B-only:** `_execute_openai_http_advisor` (B:407), `effective_advisor` (B:80)
- **changed:** `_execute_single_advisor` (A:799 / B:726), `_execute_single_advisor_raw` (A:460 / B:446), `_resolve_readiness_port` (A:118 / B:94), `add_advisor` (A:425 / B:372), `advisor_is_ready` (A:135 / B:113), `load_config` (A:241 / B:222), `query_configured_advisor` (A:844 / B:769), `remove_advisor` (A:446 / B:393)

### `triad/bench/docker_harness.py`

A-only 0, B-only 3, changed 5.

- **B-only:** `cleanup_timed_out_container` (B:48), `const DOCKER_SANDBOX_ARGS` (B:21), `const _HEX_COMMIT_RE` (B:206)
- **changed:** `_apply_patch` (A:173 / B:219), `checkout_argv` (A:165 / B:209), `docker_outcome` (A:137 / B:174), `runner_executed` (A:102 / B:137), `try_native_docker_tests` (A:192 / B:238)

### `triad/bench/swebench_runner.py`

A-only 0, B-only 0, changed 4.

- **changed:** `ensure_base_file` (A:482 / B:482), `evaluate_in_worktree` (A:648 / B:651), `main` (A:1295 / B:1272), `run_swebench` (A:1024 / B:1001)

### `triad/intent_engine.py`

A-only 10, B-only 0, changed 8.

- **A-only:** `const BROWSE_KEYWORDS` (A:157), `const REASONING_KEYWORDS` (A:165), `const SCRAPE_KEYWORDS` (A:149), `const SYNC_KEYWORDS` (A:100), `const _BROWSE_RE` (A:184), `const _REASONING_RE` (A:185), `const _SCRAPE_RE` (A:183), `const _SYNC_RE` (A:176), `locate_workspace_paths` (A:328), `resolve_efficiency_profile` (A:268)
- **changed:** `classify_intent` (A:432 / B:215), `const ARCHITECT_KEYWORDS` (A:106 / B:96), `const _INTENT_CONFIDENCE` (A:211 / B:169), `const _INTENT_ENGINE` (A:257 / B:203), `const _INTENT_MODE` (A:241 / B:191), `const _INTENT_REASON` (A:226 / B:180), `const _SCORE_WEIGHTS` (A:196 / B:158), `execute_intent` (A:576 / B:324)

### `triad/nous_bridge.py`

A-only 6, B-only 0, changed 4.

- **A-only:** `clear_model_cooldowns` (A:170), `const _COOLDOWN_LOCK` (A:156), `const _MODEL_COOLDOWNS` (A:155), `is_model_on_cooldown` (A:159), `partition_by_cooldown` (A:175), `record_model_cooldown` (A:165)
- **changed:** `const TASK_MODEL_CASCADES` (A:41 / B:37), `detect_task_category` (A:90 / B:62), `main` (A:329 / B:217), `query_nous` (A:185 / B:101)

### `triad/paths.py`

A-only 6, B-only 6, changed 0.

- **A-only:** `const LLAMA_SERVER_PATH` (A:96), `const PORT_AGENT_MESH_MCP` (A:127), `const PORT_EXOCORTEX_DAEMON` (A:123), `const PORT_LLAMA_SERVER` (A:129), `const PORT_NEO4J_BOLT` (A:128), `const PORT_PIECES_FOR_ALL` (A:126)
- **B-only:** `const DEFAULT_LLAMA_CPP_URL` (B:128), `const LOOPBACK_HOSTS` (B:129), `llama_cpp_url` (B:149), `local_backend` (B:132), `local_llm_port` (B:153), `validate_loopback_url` (B:137)

### `triad/procutil.py`

A-only 4, B-only 1, changed 2.

- **A-only:** `_extract_diff_file_path` (A:187), `const KEY_MATERIAL_EXTENSIONS` (A:182), `const KEY_MATERIAL_NAMES` (A:178), `const _TRUNC_MARKER_RE` (A:231)
- **B-only:** `const _MARKER_RE` (B:212)
- **changed:** `const BINARY_ASSET_EXTENSIONS` (A:196 / B:178), `strip_diff_bloat` (A:305 / B:286)

### `triad/server.py`

A-only 0, B-only 0, changed 5.

- **changed:** `TriadRequestHandler._execute_remote_intent` (A:1291 / B:1307), `TriadRequestHandler._handle_action_approve` (A:1117 / B:1133), `TriadRequestHandler._handle_delegate` (A:805 / B:809), `_subsystem_status` (A:230 / B:230), `const _DEVICE_ACTUATION` (A:314 / B:314)

### `triad/tests/test_advisor_manager.py`

A-only 10, B-only 1, changed 0.

- **A-only:** `TestCodexAuthDecode` (A:248), `TestCodexAuthDecode.test_active_unexpired_token` (A:255), `TestCodexAuthDecode.test_corrupt_json_returns_unknown` (A:408), `TestCodexAuthDecode.test_execute_advisor_argv_limit_fails_on_diff` (A:467), `TestCodexAuthDecode.test_execute_advisor_blocks_cmd_batch_scripts` (A:454), `TestCodexAuthDecode.test_expired_token_with_valid_refresh_is_refreshable` (A:285), `TestCodexAuthDecode.test_missing_file_returns_missing` (A:249), `TestCodexAuthDecode.test_rank_advisors_for_task` (A:421), `TestCodexAuthDecode.test_refresh_token_at_boundary_edges_and_future_timestamp` (A:345), `TestCodexAuthDecode.test_stale_refresh_token_older_than_30_days_is_expired` (A:315)
- **B-only:** `TestAdvisorManager.test_auto_failover_header_is_single_line_even_if_failed_advisor_emits_verdict` (B:176)

### `triad/tests/test_diff_bloat.py`

A-only 8, B-only 0, changed 0.

- **A-only:** `TestDiffBloatStripper.test_edge_cases_zero_budget_and_negative_limits` (A:372), `TestDiffBloatStripper.test_enforces_multi_file_global_line_budget` (A:269), `TestDiffBloatStripper.test_many_files_tail_collapsed_into_single_marker` (A:349), `TestDiffBloatStripper.test_multi_file_budget_strict_idempotency` (A:305), `TestDiffBloatStripper.test_renames_into_sensitive_asset_or_lockfile` (A:247), `TestDiffBloatStripper.test_singular_line_truncation_idempotence` (A:327), `TestDiffBloatStripper.test_strips_bytecode_and_keystore_assets` (A:212), `TestDiffBloatStripper.test_strips_tsconfig_tsbuildinfo_and_gradle_lockfile` (A:191)

### `triad/tests/test_docker_harness.py`

A-only 0, B-only 4, changed 3.

- **B-only:** `TestDockerHarness.test_checkout_argv_rejects_non_hex_commit` (B:175), `TestDockerHarness.test_docker_sandbox_restricts_network_and_privileges` (B:123), `TestDockerHarness.test_timeout_cleanup_confirms_force_removal` (B:37), `TestDockerHarness.test_timeout_cleanup_reports_failed_kill_and_remove` (B:27)
- **changed:** `TestDockerHarness.test_checkout_argv_detaches_at_the_commit` (A:111 / B:143), `TestDockerHarness.test_docker_outcome_trusts_only_a_clean_pass` (A:89 / B:111), `TestDockerHarness.test_runner_executed_ignores_harness_failures` (A:97 / B:128)

### `triad/tests/test_hook.py`

A-only 0, B-only 4, changed 3.

- **B-only:** `TestPhase3AdvisoryCouncilRefinements.test_gate_competition_blocks_on_council_error_even_if_error_text_contains_verdict` (B:5436), `TestPhase3AdvisoryCouncilRefinements.test_gate_competition_blocks_on_degraded_or_no_quorum_even_with_approved_verdict` (B:5469), `TestPhase3AdvisoryCouncilRefinements.test_proposed_fix_patch_does_not_follow_planted_symlink` (B:5740), `_has_runnable_python3` (B:33)
- **changed:** `TestPhase3AdvisoryCouncilRefinements.test_direct_gate_persists_fix_without_mutating_working_tree` (A:5597 / B:5686), `TestRealRepoInvariants.test_direct_healing_blocks_and_notifies_user` (A:846 / B:859), `TestTriadHookAdvisoryFixes.test_cmd_review_extracts_diff_from_review_base_in_worktree` (A:2047 / B:2061)

### `triad/tests/test_intent_engine.py`

A-only 9, B-only 0, changed 0.

- **A-only:** `TestIntentEngine.test_check_sync_status_routes_to_sync` (A:235), `TestIntentEngine.test_classify_browsing_task` (A:173), `TestIntentEngine.test_classify_reasoning_task` (A:179), `TestIntentEngine.test_classify_scraping_task` (A:166), `TestIntentEngine.test_classify_sync_task` (A:187), `TestIntentEngine.test_locate_workspace_paths` (A:194), `TestIntentEngine.test_locate_workspace_paths_filters_terraform_docker_and_credentials` (A:239), `TestIntentEngine.test_locate_workspace_paths_preserves_leading_dots_and_extensions` (A:222), `TestIntentEngine.test_sync_intent_diff_exclusion` (A:217)

### `triad/tests/test_nous_bridge.py`

A-only 3, B-only 0, changed 1.

- **A-only:** `TestNousBridge.test_429_sets_retry_after_cooldown` (A:231), `TestNousBridge.test_cooldown_reorders_failing_model` (A:191), `TestNousBridge.test_pinned_model_preserved_despite_cooldown` (A:211)
- **changed:** `TestNousBridge.setUp` (A:16 / B:16)

### `triad/tests/test_server.py`

A-only 0, B-only 3, changed 3.

- **B-only:** `TestTriadServer._post_authed` (B:485), `TestTriadServer.test_mishmash_delegate_approve_reject_fail_closed_without_server_token` (B:514), `TestTriadServer.test_mishmash_delegate_every_action_requires_token` (B:488)
- **changed:** `TestTriadServer.test_evaluate_action_risk_unit` (A:622 / B:673), `TestTriadServer.test_loopback_delegate_classifies_without_leaving_the_pc` (A:467 / B:467), `TestTriadServer.test_mishmash_delegate_classify_and_risk_gating` (A:482 / B:529)

### `triad/tests/test_worktree.py`

A-only 0, B-only 18, changed 2.

- **B-only:** `TestGitWorktreeIsolation._provisioned_plain_worktree` (B:236), `TestGitWorktreeIsolation.test_apply_patch_text_uses_double_dash_before_patch_path` (B:312), `TestGitWorktreeIsolation.test_cached_base_file_failure_never_falls_back_to_network` (B:33), `TestGitWorktreeIsolation.test_capture_directory_snapshot_ancestor_node_modules_not_leaked` (B:997), `TestGitWorktreeIsolation.test_capture_directory_snapshot_end_to_end_pruning` (B:966), `TestGitWorktreeIsolation.test_capture_directory_snapshot_link_retargeting_detected` (B:1058), `TestGitWorktreeIsolation.test_capture_directory_snapshot_normalization` (B:925), `TestGitWorktreeIsolation.test_capture_directory_snapshot_scoped_and_nested_pruning` (B:1013), `TestGitWorktreeIsolation.test_capture_directory_snapshot_volatile_dir_creation_stability` (B:941), `TestGitWorktreeIsolation.test_create_worktree_rejects_option_like_refs` (B:283), `TestGitWorktreeIsolation.test_create_worktree_separates_path_and_ref_with_double_dash` (B:292), `TestGitWorktreeIsolation.test_deprovision_propagates_failed_link_removal` (B:246), `TestGitWorktreeIsolation.test_remove_worktree_force_partial_delete_retry_for_registered_worktree` (B:215), `TestGitWorktreeIsolation.test_remove_worktree_force_refuses_unregistered_directory` (B:191), `TestGitWorktreeIsolation.test_remove_worktree_force_removes_registered_worktree_outside_triad_root` (B:202), `TestGitWorktreeIsolation.test_remove_worktree_refuses_main_working_tree_and_ancestors` (B:169), `TestGitWorktreeIsolation.test_reset_worktree_does_not_git_clean_after_failed_deprovision` (B:261), `TestGitWorktreeIsolation.test_volatile_dir_pruning` (B:909)
- **changed:** `TestGitWorktreeIsolation.test_cmd_auto_with_worktree_flag` (A:152 / B:331), `TestGitWorktreeIsolation.test_warm_worktree_pool_recycling_and_concurrency_bound` (A:407 / B:593)

### `triad/triad_engine.py`

A-only 3, B-only 2, changed 16.

- **A-only:** `cmd_agent` (A:5994), `cmd_sync` (A:5872), `const CODEX_MAX_REFRESH_AGE` (A:139)
- **B-only:** `const PROPOSED_FIX_PATCH_NAME` (B:2279), `write_proposed_fix_patch` (B:2282)
- **changed:** `_decode_codex_auth` (A:142 / B:134), `_handle_validation_failure` (A:3230 / B:3194), `_render_doctor_report` (A:367 / B:320), `_run_gate_impl` (A:3573 / B:3542), `_run_in_isolated_worktree` (A:2473 / B:2436), `apply_patch_text` (A:664 / B:591), `apply_verified_patch_to_workspace` (A:1639 / B:1566), `build_parser` (A:6026 / B:5859), `cmd_bench` (A:4117 / B:4104), `cmd_consult` (A:578 / B:513), `cmd_debug` (A:617 / B:548), `cmd_review` (A:513 / B:451), `collect_doctor_report` (A:208 / B:171), `const IGNORED_SOURCE_DEPENDENCY_DIR_NAMES` (A:3016 / B:2982), `main` (A:6171 / B:5978), `query_advisory_council` (A:97 / B:92)

### `triad/worktree.py`

A-only 0, B-only 7, changed 6.

- **B-only:** `_is_managed_worktree_path` (B:1050), `_is_volatile_dir` (B:950), `_link_sig` (B:932), `_triad_worktree_root` (B:1045), `const TRIAD_WORKTREE_DIR_PREFIX` (B:1042), `const _DEP_STORES` (B:929), `reject_option_like_ref` (B:165)
- **changed:** `WarmWorktreePool.__init__` (A:1121 / B:1263), `_check_dependency_graph_compatibility` (A:552 / B:562), `capture_directory_snapshot` (A:911 / B:978), `create_worktree` (A:164 / B:173), `deprovision_worktree_dependencies` (A:803 / B:820), `remove_worktree` (A:950 / B:1075)

## 3. Collected test IDs (pytest --collect-only)

- A 414, B 478, both 364, A-only 50, B-only 114, union 528.
- Same-named tests whose bodies differ are listed as `changed` in section 2.

### A-only test IDs

- `triad/tests/test_advisor_manager.py::TestCodexAuthDecode::test_active_unexpired_token`
- `triad/tests/test_advisor_manager.py::TestCodexAuthDecode::test_corrupt_json_returns_unknown`
- `triad/tests/test_advisor_manager.py::TestCodexAuthDecode::test_execute_advisor_argv_limit_fails_on_diff`
- `triad/tests/test_advisor_manager.py::TestCodexAuthDecode::test_execute_advisor_blocks_cmd_batch_scripts`
- `triad/tests/test_advisor_manager.py::TestCodexAuthDecode::test_expired_token_with_valid_refresh_is_refreshable`
- `triad/tests/test_advisor_manager.py::TestCodexAuthDecode::test_missing_file_returns_missing`
- `triad/tests/test_advisor_manager.py::TestCodexAuthDecode::test_rank_advisors_for_task`
- `triad/tests/test_advisor_manager.py::TestCodexAuthDecode::test_refresh_token_at_boundary_edges_and_future_timestamp`
- `triad/tests/test_advisor_manager.py::TestCodexAuthDecode::test_stale_refresh_token_older_than_30_days_is_expired`
- `triad/tests/test_agent.py::test_consult_architect_secret_filter`
- `triad/tests/test_agent.py::test_routellm_classifier`
- `triad/tests/test_agent.py::test_router_adaptive_threshold`
- `triad/tests/test_agent.py::test_router_default_local_orchestrator`
- `triad/tests/test_agent.py::test_runtime_abort_current_turn`
- `triad/tests/test_agent.py::test_tool_registry`
- `triad/tests/test_agent.py::test_tracker_sliding_window`
- `triad/tests/test_diff_bloat.py::TestDiffBloatStripper::test_edge_cases_zero_budget_and_negative_limits`
- `triad/tests/test_diff_bloat.py::TestDiffBloatStripper::test_enforces_multi_file_global_line_budget`
- `triad/tests/test_diff_bloat.py::TestDiffBloatStripper::test_many_files_tail_collapsed_into_single_marker`
- `triad/tests/test_diff_bloat.py::TestDiffBloatStripper::test_multi_file_budget_strict_idempotency`
- `triad/tests/test_diff_bloat.py::TestDiffBloatStripper::test_renames_into_sensitive_asset_or_lockfile`
- `triad/tests/test_diff_bloat.py::TestDiffBloatStripper::test_singular_line_truncation_idempotence`
- `triad/tests/test_diff_bloat.py::TestDiffBloatStripper::test_strips_bytecode_and_keystore_assets`
- `triad/tests/test_diff_bloat.py::TestDiffBloatStripper::test_strips_tsconfig_tsbuildinfo_and_gradle_lockfile`
- `triad/tests/test_intent_engine.py::TestIntentEngine::test_check_sync_status_routes_to_sync`
- `triad/tests/test_intent_engine.py::TestIntentEngine::test_classify_browsing_task`
- `triad/tests/test_intent_engine.py::TestIntentEngine::test_classify_reasoning_task`
- `triad/tests/test_intent_engine.py::TestIntentEngine::test_classify_scraping_task`
- `triad/tests/test_intent_engine.py::TestIntentEngine::test_classify_sync_task`
- `triad/tests/test_intent_engine.py::TestIntentEngine::test_locate_workspace_paths`
- `triad/tests/test_intent_engine.py::TestIntentEngine::test_locate_workspace_paths_filters_terraform_docker_and_credentials`
- `triad/tests/test_intent_engine.py::TestIntentEngine::test_locate_workspace_paths_preserves_leading_dots_and_extensions`
- `triad/tests/test_intent_engine.py::TestIntentEngine::test_sync_intent_diff_exclusion`
- `triad/tests/test_nous_bridge.py::TestNousBridge::test_429_sets_retry_after_cooldown`
- `triad/tests/test_nous_bridge.py::TestNousBridge::test_cooldown_reorders_failing_model`
- `triad/tests/test_nous_bridge.py::TestNousBridge::test_pinned_model_preserved_despite_cooldown`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_file_hash_handles_errors_gracefully`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_norm_path_str_handles_nt_unc`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_norm_path_str_strips_device_prefixes`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_run_full_sync_component_flags`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_sync_engine_containment_guard`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_sync_engine_lock_contention`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_sync_engine_merges_custom_advisors`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_sync_engine_same_directory_guard`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_sync_hooks_audits_and_installs_with_lf_line_endings`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_sync_hooks_empty_repos_list_audits_nothing`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_sync_launchers_copies_and_detects`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_sync_launchers_dry_run_leaves_disk_untouched`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_sync_skills_copies_and_detects`
- `triad/tests/test_sync_manager.py::TestSyncManager::test_sync_skills_prunes_deletion_drift`

### B-only test IDs

- `triad/tests/test_advisor_manager.py::TestAdvisorManager::test_auto_failover_header_is_single_line_even_if_failed_advisor_emits_verdict`
- `triad/tests/test_docker_harness.py::TestDockerHarness::test_checkout_argv_rejects_non_hex_commit`
- `triad/tests/test_docker_harness.py::TestDockerHarness::test_docker_sandbox_restricts_network_and_privileges`
- `triad/tests/test_docker_harness.py::TestDockerHarness::test_timeout_cleanup_confirms_force_removal`
- `triad/tests/test_docker_harness.py::TestDockerHarness::test_timeout_cleanup_reports_failed_kill_and_remove`
- `triad/tests/test_docker_runner.py::TestBoundedOutput::test_engine_rejects_a_candidate_whose_verification_overflows`
- `triad/tests/test_docker_runner.py::TestBoundedOutput::test_output_within_budget_is_returned_intact`
- `triad/tests/test_docker_runner.py::TestBoundedOutput::test_runner_removes_the_container_and_reraises_on_overflow`
- `triad/tests/test_docker_runner.py::TestBoundedOutput::test_streaming_overflow_kills_the_process_and_raises_quickly`
- `triad/tests/test_docker_runner.py::TestBoundedOutput::test_timeout_still_raises_timeout_expired`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_container_is_always_removed_even_on_success`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_invalid_profiles_are_rejected_at_construction`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_isolation_flags_are_all_present`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_no_host_environment_is_passed_through`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_nonzero_exit_is_returned_not_raised`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_only_the_workspace_is_mounted`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_output_is_capped`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_profile_argv_comes_after_the_image_and_unknown_profiles_are_refused`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_timeout_kills_the_container_and_reraises`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_unavailable_daemon_raises_and_never_runs_anything`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_user_falls_back_to_nobody_off_linux`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_user_is_host_uid_gid_and_root_is_refused`
- `triad/tests/test_docker_runner.py::TestDockerRunnerCommand::test_workspace_paths_that_could_smuggle_mount_options_are_refused`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_candidate_that_phones_home_or_reads_host_files_cannot_succeed_by_doing_so`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_engine_verifies_a_real_repair_inside_a_container`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_fork_bomb_is_contained_by_the_pid_limit`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_host_environment_secrets_are_invisible`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_host_files_outside_the_workspace_are_invisible`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_memory_hog_is_killed`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_network_is_unreachable`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_private_workspace_is_readable_and_writable`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_root_filesystem_is_read_only_but_workspace_and_tmp_are_writable`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_runs_unprivileged`
- `triad/tests/test_docker_runner.py::TestDockerRunnerRealIsolation::test_timeout_kills_the_container`
- `triad/tests/test_docker_runner.py::TestEngineGitPointerGuard::test_rewriting_the_git_pointer_is_rejected`
- `triad/tests/test_docker_runner.py::TestEngineGitPointerGuard::test_untouched_pointer_still_survives`
- `triad/tests/test_hook.py::TestPhase3AdvisoryCouncilRefinements::test_gate_competition_blocks_on_council_error_even_if_error_text_contains_verdict`
- `triad/tests/test_hook.py::TestPhase3AdvisoryCouncilRefinements::test_gate_competition_blocks_on_degraded_or_no_quorum_even_with_approved_verdict`
- `triad/tests/test_hook.py::TestPhase3AdvisoryCouncilRefinements::test_proposed_fix_patch_does_not_follow_planted_symlink`
- `triad/tests/test_local_llm_backend.py::TestBackendSelection::test_default_effective_advisor_is_http`
- `triad/tests/test_local_llm_backend.py::TestBackendSelection::test_default_is_llamacpp_on_8080`
- `triad/tests/test_local_llm_backend.py::TestBackendSelection::test_loopback_only`
- `triad/tests/test_local_llm_backend.py::TestBackendSelection::test_non_loopback_env_url_is_refused_before_any_request`
- `triad/tests/test_local_llm_backend.py::TestBackendSelection::test_ollama_override_restores_11434`
- `triad/tests/test_local_llm_backend.py::TestHttpAdvisor::test_ollama_override_uses_subprocess_not_http`
- `triad/tests/test_local_llm_backend.py::TestHttpAdvisor::test_posts_openai_chat_and_strips_think_blocks`
- `triad/tests/test_local_llm_backend.py::TestHttpAdvisor::test_readiness_checks_8080_not_11434`
- `triad/tests/test_local_llm_backend.py::TestHttpAdvisor::test_server_down_returns_error_string`
- `triad/tests/test_morphogenetic.py::TestMorphogeneticEngine::test_forbidden_token_apoptosis`
- `triad/tests/test_morphogenetic.py::TestMorphogeneticEngine::test_intercept_friction`
- `triad/tests/test_morphogenetic.py::TestMorphogeneticEngine::test_mutation_preserves_lf_line_endings_in_verified_diff`
- `triad/tests/test_morphogenetic.py::TestMorphogeneticEngine::test_noop_mutation_rejection`
- `triad/tests/test_morphogenetic.py::TestMorphogeneticEngine::test_path_jail_traversal_rejection`
- `triad/tests/test_morphogenetic.py::TestMorphogeneticEngine::test_simulated_darwinian_survival_trial`
- `triad/tests/test_morphogenetic.py::TestMorphogeneticEngine::test_synthesize_repair_candidate`
- `triad/tests/test_morphogenetic.py::TestProtectedTargetPolicy::test_dotdot_normalisation_cannot_hide_a_protected_target`
- `triad/tests/test_morphogenetic.py::TestProtectedTargetPolicy::test_harness_and_build_config_decide_what_verification_runs_so_they_are_protected`
- `triad/tests/test_morphogenetic.py::TestProtectedTargetPolicy::test_in_root_alias_to_a_protected_file_is_rejected`
- `triad/tests/test_morphogenetic.py::TestProtectedTargetPolicy::test_in_root_alias_to_an_ordinary_file_is_rejected_as_a_link`
- `triad/tests/test_morphogenetic.py::TestProtectedTargetPolicy::test_input_validation_rejects_ambiguous_paths`
- `triad/tests/test_morphogenetic.py::TestProtectedTargetPolicy::test_invalid_input_is_rejected_before_any_resolution`
- `triad/tests/test_morphogenetic.py::TestProtectedTargetPolicy::test_ordinary_source_is_not_protected`
- `triad/tests/test_morphogenetic.py::TestProtectedTargetPolicy::test_ordinary_source_mutation_still_reaches_verification`
- `triad/tests/test_morphogenetic.py::TestProtectedTargetPolicy::test_protected_paths`
- `triad/tests/test_morphogenetic.py::TestProtectedTargetPolicy::test_root_level_tests_dir_is_rejected_end_to_end`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_extra_untracked_file_is_rejected_even_when_verification_returns_zero`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_failing_fake_runner_is_apoptosis`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_modifying_another_tracked_file_is_rejected`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_no_runner_configured_rejects_and_runs_no_verification`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_passing_fake_runner_survives_with_a_literal_pathspec_diff`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_reevaluating_a_survivor_unsuccessfully_clears_stale_state`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_runner_timeout_is_rejected_not_raised`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_staging_the_target_is_rejected`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_target_rewritten_during_verification_is_rejected_and_never_diffed`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_target_rewritten_then_restored_to_identical_bytes_still_survives`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_unsafe_host_runner_requires_explicit_opt_in`
- `triad/tests/test_morphogenetic.py::TestVerificationRunnerBoundary::test_unsafe_host_runner_uses_a_minimal_environment_and_trusted_profile`
- `triad/tests/test_morphogenetic_gates.py::TestDiffSizeCap::test_at_cap_is_accepted`
- `triad/tests/test_morphogenetic_gates.py::TestDiffSizeCap::test_changed_line_count`
- `triad/tests/test_morphogenetic_gates.py::TestDiffSizeCap::test_default_cap_is_200_and_configurable_by_env`
- `triad/tests/test_morphogenetic_gates.py::TestDiffSizeCap::test_over_cap_is_rejected_before_anything_runs`
- `triad/tests/test_morphogenetic_gates.py::TestEnableFlag::test_default_is_off_and_nothing_runs`
- `triad/tests/test_morphogenetic_gates.py::TestEnableFlag::test_env_flag_and_explicit_argument`
- `triad/tests/test_morphogenetic_gates.py::TestReproductionGate::test_a_test_that_already_passes_proves_nothing`
- `triad/tests/test_morphogenetic_gates.py::TestReproductionGate::test_can_be_disabled_explicitly_for_callers_without_a_repro`
- `triad/tests/test_morphogenetic_gates.py::TestReproductionGate::test_fails_before_and_passes_after_survives_in_that_order`
- `triad/tests/test_morphogenetic_gates.py::TestReproductionGate::test_reproduction_run_must_not_touch_the_workspace`
- `triad/tests/test_morphogenetic_gates.py::TestReproductionGate::test_requires_a_reproduction_profile_by_default`
- `triad/tests/test_morphogenetic_gates.py::TestReproductionGate::test_still_failing_after_the_patch_is_apoptosis`
- `triad/tests/test_morphogenetic_gates.py::TestStaticSecurityScanGate::test_clean_patch_passes`
- `triad/tests/test_morphogenetic_gates.py::TestStaticSecurityScanGate::test_eval_input_rejected_by_bandit`
- `triad/tests/test_morphogenetic_gates.py::TestStaticSecurityScanGate::test_missing_tool_rejects`
- `triad/tests/test_morphogenetic_gates.py::TestStaticSecurityScanGate::test_scan_gate_config_switch`
- `triad/tests/test_morphogenetic_gates.py::TestStaticSecurityScanGate::test_syntax_error_rejected_by_ruff`
- `triad/tests/test_morphogenetic_gates.py::TestStaticSecurityScanGate::test_tool_crash_rejects`
- `triad/tests/test_server.py::TestTriadServer::test_mishmash_delegate_approve_reject_fail_closed_without_server_token`
- `triad/tests/test_server.py::TestTriadServer::test_mishmash_delegate_every_action_requires_token`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_apply_patch_text_uses_double_dash_before_patch_path`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_cached_base_file_failure_never_falls_back_to_network`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_capture_directory_snapshot_ancestor_node_modules_not_leaked`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_capture_directory_snapshot_end_to_end_pruning`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_capture_directory_snapshot_link_retargeting_detected`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_capture_directory_snapshot_normalization`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_capture_directory_snapshot_scoped_and_nested_pruning`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_capture_directory_snapshot_volatile_dir_creation_stability`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_create_worktree_rejects_option_like_refs`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_create_worktree_separates_path_and_ref_with_double_dash`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_deprovision_propagates_failed_link_removal`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_remove_worktree_force_partial_delete_retry_for_registered_worktree`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_remove_worktree_force_refuses_unregistered_directory`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_remove_worktree_force_removes_registered_worktree_outside_triad_root`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_remove_worktree_refuses_main_working_tree_and_ancestors`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_reset_worktree_does_not_git_clean_after_failed_deprovision`
- `triad/tests/test_worktree.py::TestGitWorktreeIsolation::test_volatile_dir_pruning`

### Module-level (pytest-only) test functions

`python -m unittest discover` does not collect these.

| Test file | A | B |
|---|---|---|
| `triad/tests/test_agent.py` | 7 | 0 |

## 4. Change ledger since 2026-09-25

### A (`triad/`, packaging, skills, bin)

```
a978bf1 2026-10-27 feat(agent): default to local Triad orchestrator, add boundary-tracked cancellation, and secure architect delegation
a76d933 2026-10-27 feat(sync): ecosystem synchronization with atomic OS locking, rollback, and safe intent routing
e1f2479 2026-10-27 feat(agent): autonomous zero-cost terminal agent with RouteLLM dynamic waterfall and llama-server migration
f58a7a9 2026-10-27 feat(routing): task-aware model routing and onboard client integration for Antigravity, Claude, Codex, and Ollama
4c0175d 2026-10-27 perf(doctor): parallelize local subsystem port probing and align env prefixes
ce82564 2026-10-27 feat(doctor): expand local subsystems audit to include exocortex, proxy, gateway, mesh, and neo4j
60e2722 2026-10-25 feat(triad): register Warp / Oz as interactive council member
32c5abd 2026-10-22 chore(engine): expand IGNORED_SOURCE_DEPENDENCY_DIR_NAMES for IDE, mobile, and tooling dirs
a17ab38 2026-10-14 feat(triad): token-cutting diff bloat protection, nous atomic cooldowns, and codex refresh validation
575e5bf 2026-10-11 triad: use qwen3:1.7b (--think=false) for the Ollama advisor
67afd73 2026-10-08 fix(server): harden biometric attestation validation with surrogate and multibyte UTF-8 byte bounds
7dcb73f 2026-10-08 feat(gating): add fail-closed proposal approval and biometric gating to triad server
ca82c84 2026-10-08 feat(risk-gating): add linear-time fail-closed risk gating to mishmash classify
7c16f99 2026-10-08 Classify intent from a loopback delegate call.
9ea8e35 2026-10-07 feat(mesh): bridge Agent Mesh MCP subsystem into Triad orchestrator and intent engine
78f736a 2026-10-07 perf(advisor): strip instructions and disable unused tools in Codex advisor
45e142d 2026-10-06 perf(advisors): strip user settings, default agent prompt and slash commands from the Claude advisor
f72c0d7 2026-10-06 security: enforce repo allowlist inside _resolve_repo_path
a562ef9 2026-10-06 security: replace regex/path patterns CodeQL flags
8163adc 2026-10-06 security: harden CodeQL-flagged input handling
5d840d9 2026-10-06 test: make rate-limit-prose advisor test hermetic
a48b7cf 2026-10-06 fix(bench): treat a session-limit reply as a judge error
52d6c0c 2026-10-06 fix(bench): score a Docker run only when every target test passes
81b7a56 2026-10-06 fix(bench): restore Claude as the primary judge
3fab62e 2026-10-05 fix(bench): cap live model sessions at two without stalling workers
9971246 2026-10-03 ci: parallelize test suite in workflow, ignore test caches, and harden install junction handling
5413161 2026-10-03 fix(engine): polish AST cache bounding and verify direct file cache hits
cabfb98 2026-10-03 feat(engine): tier-2 performance optimizations (parallel runner, multi-target union, mtime AST caching, ephemeral pycache)
6c1bbf8 2026-10-03 perf(gate): optimize test discovery with AST-indexed targeted test execution and hermetic adversarial mock
73e68c5 2026-10-03 perf: fast-path docs gate, strip diff bloat, and add xdist test configuration
98787ac 2026-10-03 merge: sync master packaging and ctime hardening into port/master-fixes
f122f37 2026-10-01 fix: make _rollback detect post-close file replacement via ctime (#2)
ea69593 2026-10-02 feat(triad): adversarial red/blue arena, circuit lock hardening, slm routing, and ambient http bridge
2c22447 2026-10-01 fix: make _rollback detect post-close file replacement via ctime (#2)
4c4a9e9 2026-09-29 build: add packaging (pyproject.toml) to fix dependency gap and CLI discovery (#1)
81dfc01 2026-09-28 config: pin Ollama advisor to qwen2.5-coder:14b and enable it
```

### B (`packages/triad`)

```
d44ba53 2026-10-28 4.0a: surface calibration samples in shadow mode (#57)
92223d7 2026-10-28 2.3a: re-tier self_heal_restore to T2 (#59)
bee3c6a 2026-10-28 2.4b: static and security scan gate for morphogenetic engine (#56)
675f258 2026-10-28 feat(triad): morphogenetic engine default off, diff-size cap, reproduction gate (row 2.4) (#50)
8faffda 2026-10-28 feat(triad): move the local advisor from Ollama to llama.cpp :8080 (#22)
b1b264d 2026-10-28 fix(triad): run verification containers as the invoking uid:gid (row 2.4a) (#39)
f9b80ce 2026-10-28 test(triad): make the isolation workspace usable by the container user (#32)
aee14c2 2026-10-28 fix(triad): make checkout_argv work on Git < 2.44 by validating hex SHA (row 0.5) (#24)
28b77fe 2026-10-28 ci: GitHub Actions, PR template, agent queue (row 0.2) (#21)
3196350 2026-10-24 fix(triad): reject patches whose target bytes or mode changed during verification (M8)
386543c 2026-10-24 fix(triad): bound verifier output while streaming and reject on overflow
7885f5d 2026-10-24 fix: audit remediations, security hardening, performance optimizations & zero-vulnerability dependency updates (#12)
3c8537d 2026-10-22 fix: close two review findings (migration swap gap, harness-config mutations)
ea6f7a5 2026-10-22 fix(triad): fail closed without an isolated verification runner
a90dde9 2026-10-22 fix(triad): apply protected-path policy to canonical targets
51019a9 2026-10-22 test(triad): pin parent state in cmd_auto worktree test
82c0ec5 2026-10-15 fix: close P11 mesh and triad bench findings
722aa9b 2026-10-15 Merge pull request #5 from Dysfunction-Junction/papa-bear4216-fix-review-findings
4c9b79d 2026-10-15 fix(security): sandbox benchmark test execution
78644f7 2026-10-15 feat(core, daemon, mobile, triad): apply Lead Architect hardening and projection recovery
75d839a 2026-10-15 feat(triad): add end-to-end morphogenetic darwinian survival trial harness
3a3b5fc 2026-10-14 fix(triad,daemon): harden worktree snapshotting, phone normalizer and device registry isolation
78d9703 2026-10-13 Wire shadow proposals and add calibration benchmarks
7a026fd 2026-10-11 triad: use qwen3:1.7b (--think=false) for the Ollama advisor
e913746 2026-10-09 decisions P1-P11: signed labels, attestation chain, scope allowlist, delivery, self-heal gating, mesh audit
9f50b5f 2026-10-09 follow-up: triad fail-closed gates, proposal state machine, telemetry validation, mobile queue races
da71391 2026-10-09 biometric: device-bound approval signatures replace the fabricated attestation
f6d750e 2026-10-09 audit: fix confirmed bugs across phases 1-3 and enforce shadow mode on actuation
6ddded7 2026-10-09 feat(v3): import Architecture & Schema v3, SQLite DDL, and Phase 0 hardening
2a3225b 2026-10-09 feat(ecosystem): implement Magic Piece (3 Pillars), Frontier 1, Frontier 3, and unified mobile companion
cd1399e 2026-10-09 fix(triad,mesh,core): sanitize pycache, resolve windows crlf lockfile drift, and configure workspace test timeouts
8d8bbde 2026-10-09 feat(exocortex): initialize sovereign-exocortex monorepo workspace and single daemon substrate
```

## 5. Branch content not on the default branch

Share of each commit's added lines (8+ characters) found verbatim in the same file on the target branch. Low numbers mean the change is probably not merged.

### A branches vs `master`

| Ref | Commit | Subject | Present on master |
|---|---|---|---|
| `origin/base44/setup-b9ffc82c` | 7d9cfc7 | Add Docker support and bind address configuration | 0/44 |
| `origin/claude/dazzling-planck-291g3t` | 9673b5d | security: validate hash output before use in predictable temp-file paths | 5/5 |
| `origin/claude/dazzling-planck-291g3t` | abbc6bc | security: reject pre-existing non-owned files in _write_text_no_follow | 11/11 |
| `origin/claude/dazzling-planck-291g3t` | a950cca | fix: address CodeRabbit review findings (credential exposure, redirect bypass, consistency) | 18/21 |
| `origin/claude/dazzling-planck-291g3t` | 2945ad3 | security: declare least-privilege permissions for the CI workflow | 4/4 |
| `origin/claude/dazzling-planck-291g3t` | 4b1d86e | security: pin GitHub Actions to commit SHAs instead of mutable tags | 0/3 |
| `origin/claude/dazzling-planck-291g3t` | 15cf291 | fix(tests): give test_cmd_gate_apply_verified a real writable recovery path | 14/14 |
| `origin/claude/dazzling-planck-291g3t` | 78a6860 | fix(tests): fix 3 test failures CI caught that local root-sandbox testing masked | 4/10 |
| `origin/claude/dazzling-planck-291g3t` | 50fefdf | build: add CI (ruff + bandit + pytest) and fix everything it immediately caught | 409/614 |
| `origin/claude/dazzling-planck-291g3t` | 0260c1f | build: add uv.lock to pin dependency versions | 163/195 |
| `origin/claude/dazzling-planck-291g3t` | 6955b89 | fix: harden predictable-path temp/lock files against symlink attacks; drop MD5 | 19/20 |
| `origin/claude/dazzling-planck-291g3t` | 5657123 | build: add pyproject.toml to fix dependency gap and CLI discovery | 14/19 |
| `origin/fix/ci-rollback-inode-reuse` | ac42338 | fix: make _rollback detect post-close file replacement via ctime | 11/15 |

### B branches vs `origin/main` (commits touching `packages/triad`)

| Ref | Commit | Subject | Present on B main | Present on A master |
|---|---|---|---|---|
| `feat/1.2-adapters-emit-events` | 37af40c | Merge origin/main into feat/1.2-adapters-emit-events | 0/0 | 0/0 |
| `feat/2.1c-delegate-followups` | ac5eb82 | merge origin/main into feat/2.1c-delegate-followups | 0/0 | 0/0 |
| `feat/2.3-scripted-executors` | 047b3ee | Merge origin/main into feat/2.3-scripted-executors | 0/0 | 0/0 |
| `feat/2.4-morphogenetic-gates` | 7591a64 | feat(triad): morphogenetic engine default off, diff-size cap, reproduction gate (row 2.4) | 234/234 | 0/234 |
| `feat/2.4b-scan-gate` | fed8338 | fix(triad): select E9,F for ruff scan to match pyproject.toml configuration | 1/1 | 0/1 |
| `feat/2.4b-scan-gate` | 9c6ed9f | feat(triad): static and security scan gate for morphogenetic engine (spec R3 / row 2.4b) | 128/129 | 0/129 |
| `feat/4.0a-calibration-surfacing` | 2729d3b | test(triad): format docker isolation candidate fixture | 1/1 | 0/1 |
| `feat/4.0a-calibration-surfacing` | c5d3739 | Merge remote-tracking branch 'origin/main' into feat/4.0a-calibration-surfacing | 0/0 | 0/0 |
| `feat/ollama-cutover-triad` | fa0133a | Merge remote-tracking branch 'origin/main' into feat/ollama-cutover-triad | 0/0 | 0/0 |
| `feat/ollama-cutover-triad` | 505c0b9 | feat(triad): move the local advisor from Ollama to llama.cpp :8080 | 230/230 | 25/230 |
| `fix/0.5-git-checkout-argv` | 85f0d1f | fix(triad): make checkout_argv work on Git < 2.44 by validating hex SHA (row 0.5) | 16/16 | 1/16 |
| `fix/2.4a-container-workspace` | 15c1c62 | fix(triad): run verification containers as the invoking uid:gid (row 2.4a) | 47/47 | 0/47 |
| `fix/2.6-channels-scope` | 4a6f0e0 | Merge origin/main into fix/2.6-channels-scope | 0/0 | 0/0 |
| `fix/triad-docker-fixture-lint` | 3fe8709 | test(triad): format docker isolation candidate fixture | 1/1 | 0/1 |
| `origin/ci/0.2-github-actions` | 138a614 | ci: run real-Docker isolation tests in a separate informational job | 2/2 | 0/2 |
| `origin/feat/1.2-adapters-emit-events` | 37af40c | Merge origin/main into feat/1.2-adapters-emit-events | 0/0 | 0/0 |
| `origin/feat/2.1c-delegate-followups` | ac5eb82 | merge origin/main into feat/2.1c-delegate-followups | 0/0 | 0/0 |
| `origin/feat/2.3-scripted-executors` | 047b3ee | Merge origin/main into feat/2.3-scripted-executors | 0/0 | 0/0 |
| `origin/feat/2.4-morphogenetic-gates` | 7591a64 | feat(triad): morphogenetic engine default off, diff-size cap, reproduction gate (row 2.4) | 234/234 | 0/234 |
| `origin/feat/2.4b-scan-gate` | fed8338 | fix(triad): select E9,F for ruff scan to match pyproject.toml configuration | 1/1 | 0/1 |
| `origin/feat/2.4b-scan-gate` | 9c6ed9f | feat(triad): static and security scan gate for morphogenetic engine (spec R3 / row 2.4b) | 128/129 | 0/129 |
| `origin/feat/4.0a-calibration-surfacing` | 2729d3b | test(triad): format docker isolation candidate fixture | 1/1 | 0/1 |
| `origin/feat/4.0a-calibration-surfacing` | c5d3739 | Merge remote-tracking branch 'origin/main' into feat/4.0a-calibration-surfacing | 0/0 | 0/0 |
| `origin/feat/ollama-cutover-triad` | fa0133a | Merge remote-tracking branch 'origin/main' into feat/ollama-cutover-triad | 0/0 | 0/0 |
| `origin/feat/ollama-cutover-triad` | 505c0b9 | feat(triad): move the local advisor from Ollama to llama.cpp :8080 | 230/230 | 25/230 |
| `origin/fix/0.5-git-checkout-argv` | 85f0d1f | fix(triad): make checkout_argv work on Git < 2.44 by validating hex SHA (row 0.5) | 16/16 | 1/16 |
| `origin/fix/2.3a-self-heal-tier` | e5eac78 | fix(triad): select E9,F for ruff scan to match pyproject.toml configuration | 1/1 | 0/1 |
| `origin/fix/2.4a-container-workspace` | 15c1c62 | fix(triad): run verification containers as the invoking uid:gid (row 2.4a) | 47/47 | 0/47 |
| `origin/fix/2.6-channels-scope` | 4a6f0e0 | Merge origin/main into fix/2.6-channels-scope | 0/0 | 0/0 |
| `origin/fix/docker-isolation-workspace-perms` | 46b8a8c | test(triad): make the isolation workspace usable by the container user | 0/3 | 0/3 |
| `origin/fix/living-brain-single-hub` | 40be23c | Merge branch 'main' into fix/living-brain-single-hub | 0/0 | 0/0 |
| `origin/test/2.5-kill-switch-drill` | 016a493 | Merge remote-tracking branch 'origin/main' into test/2.5-kill-switch-drill | 0/0 | 0/0 |

## 6. `sovereign-exocortex-broker` audit

Scanned 282 files outside `node_modules` and caches. 0 have content that is not a blob in either repository's object database.


