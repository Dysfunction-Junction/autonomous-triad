# Tag: `review`

[← index](../REPO_TAGS.md) · 14 files

| File | Links | Queries |
| --- | --- | --- |
| `docs/ARCHITECTURE.md` | `triad/triad_engine.py`<br>`triad/server.py`<br>`docs/BLUEPRINT.md` | `how do the advisors talk to each other`<br>`what are the invariant rules`<br>`how is a prompt classified` |
| `docs/BLUEPRINT.md` | `docs/ARCHITECTURE.md`<br>`triad/competition.py`<br>`triad/circuit.py` | `what is the zero-token marginal cost design`<br>`how does dual-advisor consensus work`<br>`what is an ephemeral execution` |
| `docs/TRIAD_UPGRADE_SPEC.md` | `docs/TRIAD_V34_UNIFICATION_SPEC.md`<br>`triad/cli/review.py` | `what does v3.4 change about reviews`<br>`how much are tokens meant to drop`<br>`what is the phase order` |
| `docs/TRIAD_V34_UNIFICATION_SPEC.md` | `docs/TRIAD_UPGRADE_SPEC.md`<br>`scripts/triad_unify_audit.py`<br>`docs/TRIAD_V34_MERGE_MAP.md` | `which spec wins when the two disagree`<br>`what evidence backs the plan`<br>`how do the two trees get unified` |
| `triad/cli/gate.py` | `triad/notifier.py`<br>`triad/competition.py` | `what does the ground-truth gate verify`<br>`when is a phone notified`<br>`what blocks a commit` |
| `triad/cli/review.py` | `triad/intent_engine.py`<br>`triad/competition.py` | `what review modes exist`<br>`how do I consult an advisor from the shell`<br>`what does triage decide` |
| `triad/competition.py` | `triad/advisor_manager.py`<br>`triad/triad_engine.py` | `how do two advisors run at once`<br>`how is a structured synthesis built`<br>`what happens when both agree` |
| `triad/intent_engine.py` | `triad/cli/review.py`<br>`triad/triad_engine.py`<br>`docs/ARCHITECTURE.md` | `how is a prompt classified`<br>`what makes a task high stakes`<br>`when is it auto-adjudicated` |
| `triad/prompt_rewriter.py` | `triad/intent_engine.py`<br>`triad/prw.py` | `how is a rough prompt expanded`<br>`what does the rewriter add before a review` |
| `triad/tests/test_competition.py` | `triad/competition.py` | `how is concurrent dual-advisor output synthesised`<br>`what if one advisor fails` |
| `triad/tests/test_diff_bloat.py` | `triad/advisor_manager.py`<br>`triad/patching.py` | `how is diff bloat stripped`<br>`is stripping idempotent`<br>`how are docs classified` |
| `triad/tests/test_prompt_rewriter.py` | `triad/prompt_rewriter.py` | `what does the rewriter add`<br>`are short prompts expanded` |
| `triad/tests/test_synthesis_trim.py` | `triad/competition.py` | `how are cited hunks extracted`<br>`what is trimmed from synthesis`<br>`what counts as unanimous` |
| `triad/triad_engine.py` | `triad/advisor_manager.py`<br>`triad/intent_engine.py`<br>`bin/triad` | `where is the command surface defined`<br>`how does review dispatch to advisors`<br>`what does the engine do with a gate result` |
