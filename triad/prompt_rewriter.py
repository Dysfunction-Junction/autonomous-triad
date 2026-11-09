"""
Autonomous Multi-Agent Triad: Prompt Rewriter (prompt_rewriter.py).

Expands sparse developer prompts into fully-specified agent briefs without
burning subscription tokens. Uses the local Intent Engine for routing metadata
and deterministic templates for structure.

Optional ``--llm`` mode can polish via the advisory council, but the default
path is pure local / zero-cost.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

try:
    from triad.intent_engine import IntentClassification, classify_intent
except ImportError:
    from intent_engine import IntentClassification, classify_intent  # type: ignore

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "or", "in", "on", "at", "is",
    "it", "this", "that", "with", "from", "into", "my", "me", "we", "you",
    "please", "just", "can", "could", "would", "should", "i", "im", "i'm",
    "want", "need", "make", "do", "be", "as", "by", "up", "out", "about",
}

_QUESTION_RE = re.compile(
    r"\b(what|why|how|when|where|which|who|does|do|is|are|can|should|would)\b|\?",
    re.IGNORECASE,
)
_ACTION_RE = re.compile(
    r"\b(fix|add|implement|create|build|refactor|rename|delete|remove|update|"
    r"migrate|rewrite|optimize|debug|review|test|write|port|wire|integrate|"
    r"deploy|document|explain|compare|design|investigate|trace|diagnose)\b",
    re.IGNORECASE,
)
_CONSTRAINT_RE = re.compile(
    r"\b(don't|do not|without|must not|never|only|no\s+\w+|avoid|keep|"
    r"preserve|don't touch|do not touch|backwards?[- ]compat|no new deps|"
    r"no new dependencies|minimal|small change|surgical)\b",
    re.IGNORECASE,
)
_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?(?:[\\/][\w.\-]+)+\.\w{1,8}|[\w.\-]+(?:/[\w.\-]+)+\.\w{1,8}|[\w.\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|kt|cs|rb|php|md|json|ya?ml|toml|sql|sh|ps1))",
    re.IGNORECASE,
)
_ERROR_HINT_RE = re.compile(
    r"\b(error|exception|traceback|stack trace|fails?|failing|crash(?:es|ed|ing)?|"
    r"broken|bug|regression|TypeError|ReferenceError|panic)\b",
    re.IGNORECASE,
)
_SCOPE_HINT_RE = re.compile(
    r"\b(entire|whole|all files|codebase|repo[- ]wide|everywhere|project[- ]wide)\b",
    re.IGNORECASE,
)


@dataclass
class Ambiguity:
    code: str
    question: str
    severity: str  # high | medium | low


@dataclass
class RewrittenPrompt:
    """Structured expansion of a raw developer prompt."""

    original: str
    rewritten: str
    intent: str
    confidence: float
    high_stakes: bool
    task_category: str
    suggested_mode: str
    suggested_engine: str
    suggested_model_tier: str
    goal: str
    action: str
    constraints: List[str] = field(default_factory=list)
    paths: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    out_of_scope: List[str] = field(default_factory=list)
    ambiguities: List[Ambiguity] = field(default_factory=list)
    missing_context: List[str] = field(default_factory=list)
    efficiency_notes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return payload


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _clean_prompt(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _extract_paths(text: str) -> List[str]:
    found = []
    for m in _PATH_RE.finditer(text or ""):
        p = m.group("path")
        if p not in found:
            found.append(p)
    return found


def _extract_constraints(text: str) -> List[str]:
    constraints: List[str] = []
    # Split on sentence ends and dash/semicolon clause breaks, then keep
    # only the clause that actually carries the constraint (avoids
    # "fix X — don't touch Y" becoming "X — don't touch Y").
    parts = re.split(r"[.!?\n]+|(?:\s+[—–-]\s+)|;", text or "")
    for sentence in parts:
        s = sentence.strip(" \t\"'")
        if not s or len(s) < 3:
            continue
        if not _CONSTRAINT_RE.search(s):
            continue
        # Drop leading junk like "Ts" fragments if any slipped through
        s = re.sub(r"^[A-Za-z]{1,3}\s+[—–-]\s+", "", s).strip()
        cleaned = s[0].upper() + s[1:] if len(s) > 1 else s.upper()
        if cleaned not in constraints:
            constraints.append(cleaned)
    return constraints


def _infer_action(text: str, classification: IntentClassification) -> str:
    m = _ACTION_RE.search(text or "")
    if m:
        verb = m.group(1).lower()
    else:
        verb = {
            "REVIEW": "review",
            "DEBUG": "debug",
            "ARCHITECT": "design",
            "GATE": "verify",
            "SCRAPE": "extract",
            "BROWSE": "locate",
            "REASONING": "analyze",
            "MEMORY": "recall",
            "DEVICE": "operate",
            "MICRO": "format",
            "SYNC": "synchronize",
            "MESH": "coordinate",
            "DOCTOR": "audit",
        }.get(classification.intent, "implement")

    if classification.intent == "DEBUG" or _ERROR_HINT_RE.search(text or ""):
        return "Diagnose root cause, apply a minimal fix, and verify."
    if classification.intent == "REVIEW":
        return "Review the change set for correctness, regressions, and risk."
    if classification.intent == "ARCHITECT":
        return "Compare options, recommend one approach, and justify tradeoffs."
    if classification.intent == "GATE":
        return "Run verification (types/tests/review) and report blockers."
    if _QUESTION_RE.search(text or "") and not _ACTION_RE.search(text or ""):
        return "Answer the question with concrete evidence; do not change code unless asked."
    if verb in ("fix", "debug", "diagnose"):
        return "Diagnose root cause, apply a minimal fix, and verify."
    if verb in ("add", "implement", "create", "build", "write"):
        return "Implement the requested behavior with tests or a verification step."
    if verb == "refactor":
        return "Refactor without changing external behavior; keep the diff surgical."
    if verb == "explain":
        return "Explain clearly with references to concrete code/paths; no edits."
    if verb == "compare":
        return "Compare options with tradeoffs and a recommendation."
    if verb == "review":
        return "Review for bugs, edge cases, and maintainability; prioritize findings."
    return f"{verb.capitalize()} the requested change with minimal scope."


def _infer_goal(text: str, classification: IntentClassification) -> str:
    cleaned = _clean_prompt(text)
    if not cleaned:
        return "Unspecified goal — prompt was empty."
    # Prefer the user's words as the goal spine
    if len(cleaned) <= 160:
        return cleaned.rstrip(".")
    # Truncate long prompts to a goal-sized summary line
    first = re.split(r"[.!?\n]", cleaned, maxsplit=1)[0].strip()
    return first[:200] if first else cleaned[:200]


def _default_acceptance(classification: IntentClassification, paths: Sequence[str], is_question: bool) -> List[str]:
    if is_question:
        return [
            "Answer addresses the actual question (not a related tangent).",
            "Claims are grounded in files, commands, or observable behavior when possible.",
            "Uncertainty is stated explicitly rather than invented.",
        ]
    criteria = [
        "Changes match the stated goal and stay within declared scope.",
        "No unrelated refactors or drive-by edits.",
    ]
    if paths:
        criteria.append(f"Primary touchpoints respected: {', '.join(paths[:6])}.")
    if classification.intent in ("DEBUG", "REVIEW", "GATE") or classification.task_category == "coding":
        criteria.append("Verification step included (test, typecheck, or concrete manual check).")
    if classification.high_stakes:
        criteria.append("Security/data-loss risks called out; irreversible actions require explicit confirmation.")
    return criteria


def _default_out_of_scope(classification: IntentClassification, text: str) -> List[str]:
    items = [
        "Unrelated refactors, renames, or formatting sweeps.",
        "New dependencies unless explicitly requested.",
        "Committing, pushing, or opening PRs unless explicitly requested.",
    ]
    if _QUESTION_RE.search(text or "") and not _ACTION_RE.search(text or ""):
        items.insert(0, "Code or config mutations (this is a question, not an implementation request).")
    if not _SCOPE_HINT_RE.search(text or ""):
        items.append("Repo-wide rewrites beyond the files/paths implied by the request.")
    if classification.intent == "MICRO":
        items = ["Behavioral changes", "Architecture shifts", "New features"]
    return items


def _find_ambiguities(
    text: str,
    classification: IntentClassification,
    paths: Sequence[str],
    constraints: Sequence[str],
) -> List[Ambiguity]:
    amb: List[Ambiguity] = []
    cleaned = _clean_prompt(text)
    words = [w for w in re.split(r"\W+", cleaned.lower()) if w and w not in _STOPWORDS]
    is_question = bool(_QUESTION_RE.search(cleaned)) and not bool(_ACTION_RE.search(cleaned))

    if len(cleaned) < 12:
        amb.append(Ambiguity("too_short", "What exactly should be done, and to which file/system?", "high"))
    elif len(words) <= 3 and not paths:
        amb.append(Ambiguity("underspecified", "Can you name the target file, feature, or error?", "high"))

    if not paths and classification.intent in ("DEBUG", "REVIEW", "GENERAL", "MICRO") and not is_question:
        # BROWSE/MEMORY/DEVICE often have no paths yet
        if classification.intent not in ("MEMORY", "DEVICE", "DOCTOR", "SYNC", "MESH"):
            amb.append(
                Ambiguity(
                    "missing_paths",
                    "Which files, packages, or entrypoints should be touched or inspected?",
                    "medium",
                )
            )

    if classification.intent == "DEBUG" and not _ERROR_HINT_RE.search(cleaned):
        amb.append(
            Ambiguity(
                "missing_error",
                "What is the exact error message, stack trace, or failing test name?",
                "high",
            )
        )

    if classification.intent == "ARCHITECT" and "compare" not in cleaned.lower() and " vs " not in cleaned.lower():
        # Soft — architect prompts are often comparative already via keywords
        if "should" not in cleaned.lower():
            amb.append(
                Ambiguity(
                    "missing_options",
                    "What options are on the table, and what constraints matter most (latency, cost, complexity)?",
                    "low",
                )
            )

    if _SCOPE_HINT_RE.search(cleaned):
        amb.append(
            Ambiguity(
                "broad_scope",
                "Repo-wide scope is expensive — can this be limited to a directory or module?",
                "medium",
            )
        )

    if classification.high_stakes and not constraints:
        amb.append(
            Ambiguity(
                "high_stakes_no_constraints",
                "This looks high-stakes (auth/payments/migrations). Any hard constraints (no downtime, backwards compatible, no schema drop)?",
                "high",
            )
        )

    if is_question and classification.intent == "GENERAL":
        # Ensure agent doesn't silently start implementing
        amb.append(
            Ambiguity(
                "question_vs_action",
                "Is this ask-only, or should the agent also implement a fix/change?",
                "medium",
            )
        )

    return amb


def _missing_context(classification: IntentClassification, text: str, paths: Sequence[str]) -> List[str]:
    missing: List[str] = []
    if classification.intent == "DEBUG":
        if not _ERROR_HINT_RE.search(text or ""):
            missing.append("Exact error text / stack trace / failing command output")
        missing.append("Reproduction steps (command, inputs, environment)")
    if classification.intent == "REVIEW" and "diff" not in (text or "").lower():
        missing.append("Diff source (staged, unstaged, PR URL, or paste)")
    if classification.intent == "ARCHITECT":
        missing.append("Current constraints: scale, latency, team familiarity, must-keep interfaces")
    if not paths and classification.intent in ("GENERAL", "DEBUG", "REVIEW"):
        missing.append("Relevant file paths or module names")
    if classification.high_stakes:
        missing.append("Blast radius / rollback plan expectations")
    return missing


def _efficiency_notes(classification: IntentClassification, text: str, paths: Sequence[str]) -> List[str]:
    notes: List[str] = []
    if classification.efficiency_rationale:
        notes.append(classification.efficiency_rationale)
    if _SCOPE_HINT_RE.search(text or ""):
        notes.append("Broad scope inflates tokens — prefer path-bounded requests.")
    if not paths and classification.intent in ("DEBUG", "GENERAL", "REVIEW"):
        notes.append("Adding 1–3 concrete paths usually cuts exploratory tool calls.")
    if classification.suggested_model_tier in ("tier_0_local", "tier_0_or_flash", "local_tools_or_slm"):
        notes.append(f"Suitable for cheaper tier: {classification.suggested_model_tier}.")
    if classification.high_stakes:
        notes.append("High-stakes: dual-advisor competition may be worth the extra tokens.")
    return notes


# ---------------------------------------------------------------------------
# Core rewrite
# ---------------------------------------------------------------------------

def rewrite_prompt(
    prompt: str,
    *,
    context: Optional[str] = None,
    diff: Optional[str] = None,
    cwd: Optional[str] = None,
    extra_constraints: Optional[Sequence[str]] = None,
    style: str = "brief",  # brief | markdown | compact
) -> RewrittenPrompt:
    """
    Expand a raw prompt into a fully-detailed agent brief.

    Zero external API calls. Deterministic and fast.
    """
    original = (prompt or "").strip()
    classification = classify_intent(original, context=context, diff=diff)

    # Local boost: error-shaped prompts should surface as DEBUG even when the
    # intent engine stayed GENERAL (e.g. bare "debug TypeError in foo.py").
    if classification.intent == "GENERAL" and _ERROR_HINT_RE.search(original):
        from copy import copy

        classification = copy(classification)
        classification.intent = "DEBUG"
        classification.suggested_mode = "debug"
        classification.task_category = "coding"
        classification.confidence = max(classification.confidence, 0.82)
        classification.reason = "Error/failure keywords detected by prompt rewriter"

    paths = _extract_paths(original)
    if context:
        for p in _extract_paths(context):
            if p not in paths:
                paths.append(p)

    user_constraints = _extract_constraints(original)
    if extra_constraints:
        for c in extra_constraints:
            c = (c or "").strip()
            if c and c not in user_constraints:
                user_constraints.append(c)

    # Sensible always-on agent constraints (token + safety hygiene)
    hygiene = [
        "Prefer the smallest change that satisfies acceptance criteria.",
        "Do not invent files, APIs, or test results — inspect or say what's unknown.",
        "Do not commit/push unless explicitly requested.",
    ]
    constraints = list(user_constraints)
    for h in hygiene:
        if h not in constraints:
            constraints.append(h)

    is_question = bool(_QUESTION_RE.search(original)) and not bool(_ACTION_RE.search(original))
    goal = _infer_goal(original, classification)
    action = _infer_action(original, classification)
    acceptance = _default_acceptance(classification, paths, is_question)
    out_of_scope = _default_out_of_scope(classification, original)
    # Ambiguity checks should ignore auto hygiene constraints
    ambiguities = _find_ambiguities(original, classification, paths, user_constraints)
    missing = _missing_context(classification, original, paths)
    efficiency = _efficiency_notes(classification, original, paths)

    if cwd:
        efficiency.append(f"Working directory hint: {cwd}")

    rewritten = _render(
        style=style,
        original=original,
        classification=classification,
        goal=goal,
        action=action,
        constraints=constraints,
        paths=paths,
        acceptance=acceptance,
        out_of_scope=out_of_scope,
        ambiguities=ambiguities,
        missing=missing,
        efficiency=efficiency,
        context=context,
    )

    return RewrittenPrompt(
        original=original,
        rewritten=rewritten,
        intent=classification.intent,
        confidence=classification.confidence,
        high_stakes=classification.high_stakes,
        task_category=classification.task_category,
        suggested_mode=classification.suggested_mode,
        suggested_engine=classification.suggested_engine,
        suggested_model_tier=classification.suggested_model_tier,
        goal=goal,
        action=action,
        constraints=constraints,
        paths=list(paths),
        acceptance_criteria=acceptance,
        out_of_scope=out_of_scope,
        ambiguities=ambiguities,
        missing_context=missing,
        efficiency_notes=efficiency,
        metadata={
            "style": style,
            "has_context": bool(context and context.strip()),
            "has_diff": bool(diff and diff.strip()),
            "intent_reason": classification.reason,
        },
    )


def _render(
    *,
    style: str,
    original: str,
    classification: IntentClassification,
    goal: str,
    action: str,
    constraints: Sequence[str],
    paths: Sequence[str],
    acceptance: Sequence[str],
    out_of_scope: Sequence[str],
    ambiguities: Sequence[Ambiguity],
    missing: Sequence[str],
    efficiency: Sequence[str],
    context: Optional[str],
) -> str:
    stakes = "yes" if classification.high_stakes else "no"
    header = (
        f"INTENT: {classification.intent} "
        f"(confidence={classification.confidence:.2f}, mode={classification.suggested_mode}, "
        f"engine={classification.suggested_engine}, tier={classification.suggested_model_tier}, "
        f"high_stakes={stakes})"
    )

    if style == "compact":
        bits = [
            f"GOAL: {goal}",
            f"ACTION: {action}",
            header,
        ]
        if paths:
            bits.append("PATHS: " + ", ".join(paths[:8]))
        if constraints:
            bits.append("CONSTRAINTS: " + " | ".join(constraints[:6]))
        if acceptance:
            bits.append("DONE WHEN: " + " | ".join(acceptance[:4]))

        if ambiguities:
            bits.append(
                "OPEN: " + " | ".join(f"{a.code}: {a.question}" for a in ambiguities[:4])
            )
        return "\n".join(bits)

    lines: List[str] = [
        "# Agent Task Brief",
        "",
        "## Goal",
        goal,
        "",
        "## Action",
        action,
        "",
        "## Routing",
        header,
        "",
        "## Original prompt",
        original.strip(),
    ]
    if context and context.strip():
        lines.extend(["", "## Context", context.strip()[:4000]])
    if paths:
        lines.extend(["", "## Paths", *[f"- {p}" for p in paths[:20]]])
    if constraints:
        lines.extend(["", "## Constraints", *[f"- {c}" for c in constraints]])
    if acceptance:
        lines.extend(["", "## Acceptance criteria", *[f"- {a}" for a in acceptance]])
    if out_of_scope:
        lines.extend(["", "## Out of scope", *[f"- {o}" for o in out_of_scope]])
    if ambiguities:
        lines.extend([
            "",
            "## Ambiguities / questions",
            *[f"- [{a.severity}] {a.code}: {a.question}" for a in ambiguities],
        ])
    if missing:
        lines.extend(["", "## Missing context", *[f"- {m}" for m in missing]])
    if efficiency:
        lines.extend(["", "## Efficiency notes", *[f"- {e}" for e in efficiency]])
    lines.append("")
    return "\n".join(lines)


def format_output(
    brief: RewrittenPrompt,
    *,
    as_json: bool = False,
    include_meta: bool = True,
) -> str:
    if as_json:
        payload = brief.to_dict()
        if not include_meta:
            payload.pop("metadata", None)
        return json.dumps(payload, indent=2, ensure_ascii=False)
    text = brief.rewritten
    if include_meta:
        meta = {
            "intent": brief.intent,
            "confidence": brief.confidence,
            "high_stakes": brief.high_stakes,
            "paths": brief.paths,
            "ambiguities": [a.code for a in brief.ambiguities],
        }
        text = (
            text.rstrip()
            + "\n\n<!-- triad-rewrite-meta\n"
            + json.dumps(meta, ensure_ascii=False)
            + "\n-->\n"
        )
    return text


def polish_with_llm(brief: RewrittenPrompt, engine: str = "auto") -> str:
    """Optional paid polish via the advisory council. Default path does not call this."""
    try:
        from triad.advisor_manager import query_configured_advisor
    except ImportError:
        from advisor_manager import query_configured_advisor  # type: ignore

    prompt = (
        "Polish this agent task brief for clarity. Keep all constraints, paths, "
        "acceptance criteria, and ambiguities. Do not invent new scope.\n\n"
        + brief.rewritten
    )
    return query_configured_advisor(engine, prompt, mode="general", task="micro")
