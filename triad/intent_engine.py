"""
Autonomous Multi-Agent Triad: Intent Engine (intent_engine.py).
Zero-cost, ultra-fast intent classification and autonomous routing across:
- Advisory Council: Review (review_diff), Architect (consult), Debug (fix errors)
- High-Stakes Dual-Engine: Concurrent Competition Mode (Claude + Codex)
- Verification Gates: Ground-Truth pre-commit verification (tsc + tests + diff signoff)
- Hermes Agent: Android phone automation & device bridge
- Local Memory: PiecesOS (Port 39300) & Mem0 Semantic Recall
- System Health: Triad Doctor audit
"""

import sys
import re
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Iterable, Pattern, List, Tuple

try:
    from triad.paths import MEM0_SCRIPT, ANDROID_RELAY_ENV, PORT_HERMES_RELAY, PORT_PIECES_OS, PORT_OLLAMA
except ImportError:
    from paths import MEM0_SCRIPT, ANDROID_RELAY_ENV, PORT_HERMES_RELAY, PORT_PIECES_OS, PORT_OLLAMA

# Ensure UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

@dataclass
class IntentClassification:
    intent: str               # GATE, REVIEW, DEBUG, ARCHITECT, DEVICE, MEMORY, DOCTOR, GENERAL, SCRAPE, BROWSE, REASONING
    confidence: float         # 0.0 to 1.0
    reason: str               # Explanatory rationale for the classification
    suggested_mode: str       # review_diff, architect, debug, gate, doctor, general, scraping, browsing, reasoning
    suggested_engine: str     # auto, competition, hermes, pieces, memory, ollama
    high_stakes: bool = False # Flagged if touching auth, security, crypto, migrations
    task_category: str = "general" # architecture, reasoning, scraping, browsing, coding, micro, mobile, memory
    suggested_model_tier: str = "tier_1_subscription" # tier_0_local, tier_0_or_flash, local_tools_or_slm, tier_1_subscription, tier_2_dual_competition
    efficiency_rationale: str = "" # Rationale for efficiency and token routing decisions
    metadata: Dict[str, Any] = field(default_factory=dict)

# Regex Patterns for Deterministic Classification
DIFF_PATTERNS = [
    re.compile(r"^diff --git\s+a/.+\s+b/", re.MULTILINE),
    re.compile(r"^@@\s+-\d+,\d+\s+\+\d+,\d+\s+@@", re.MULTILINE),
    re.compile(r"^---\s+(a/|\S+)\s*\n\+\+\+\s+(b/|\S+)", re.MULTILINE),
    re.compile(r"^index [0-9a-f]{7,}\.\.[0-9a-f]{7,}", re.MULTILINE),
]

STACK_TRACE_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
    re.compile(r"\b(TypeError|ReferenceError|SyntaxError|NullPointerException|IndexError|ValueError|AttributeError|KeyError):\s*.+", re.MULTILINE),
    re.compile(r"^\s+at\s+([a-zA-Z0-9_\.<>]+)\s+\((.+:\d+:\d+)\)", re.MULTILINE),
    re.compile(r"\berror TS\d+:", re.IGNORECASE),
    re.compile(r"\bFAILED\s*\(failures=\d+", re.IGNORECASE),
    re.compile(r"\b(npm|yarn|pnpm) ERR!", re.IGNORECASE),
    re.compile(r"panic:\s*.+", re.MULTILINE),
    re.compile(r"failed with exit code [1-9]\d*", re.IGNORECASE),
]

HIGH_STAKES_KEYWORDS = {
    "auth", "authentication", "authorization", "oauth", "jwt", "crypto",
    "password", "secret", "private key", "database migration", "schema migration",
    "db migration", "db-migration", "auth token", "api token", "access token",
    "auth-token", "api-token", "access-token",
    "rls", "row level security", "concurrency", "deadlock", "race condition",
    "stripe", "billing", "payment", "pci", "data loss", "irreversible"
}

GATE_KEYWORDS = [
    "pre-commit", "ready to commit", "commit check", "verify build",
    "run gate", "triad gate", "typecheck and test", "check tests and types",
    "precommit", "verification pipeline"
]

# NOTE: bare "notification" was deliberately removed - it routed UI work such as
# "add a toast notification component" to the phone bridge.
DEVICE_KEYWORDS = [
    "phone", "android", "sms", "text message", "push notification",
    "device bridge", "mobile relay", "port 8766", "galaxy s26",
    "tap screen", "launch app on phone", "read notification", "send text",
    "notification shade", "adb",
]

MEMORY_KEYWORDS = [
    "what did i do on", "what was done", "past timeline", "recall",
    "search pieces", "pieces memory", "workstream summary", "historical log",
    "mem0 query", "what was worked on", "past work"
]

# Bare "doctor" is intentionally absent: it matched domain text like "doctors office".
DOCTOR_KEYWORDS = [
    "triad doctor", "run doctor", "run the doctor", "doctor check",
    "system health", "platform health", "health audit",
    "system audit", "subsystem status", "check connections",
    "audit subscriptions", "verify platforms"
]

ARCHITECT_KEYWORDS = [
    "should we use", "should i use", "compare", "tradeoffs of",
    "architecture", "architectural", "system design", "pattern recommendation",
    "database schema", "scaling strategy", "evaluating approach", "pros and cons",
    "database migration", "schema migration", "api design", "design pattern", "component design"
]

REVIEW_KEYWORDS = [
    "review this", "review diff", "code review", "critique changes",
    "spot bugs in", "audit diff", "check changes", "review my code",
    "review these", "review the", "review integration"
]

DEBUG_KEYWORDS = [
    "why is this failing", "why did this fail", "debug this",
    "fix this error", "diagnose error", "fix crash", "how to solve this bug",
    "what does this error mean", "stack trace", "debugging the", "debugging this"
]

def _compile_keywords(keywords: Iterable[str], strict_boundary: bool = False, suffixes: str = r"(?:s|es)?") -> Pattern[str]:
    r"""
    Build one alternation regex that matches any keyword on word boundaries, tolerating
    specified inflection suffixes. Strict boundaries (?<![\w-]) prevent partial hits on hyphenated tokens.
    """
    parts = sorted({kw.strip().lower() for kw in keywords if kw.strip()}, key=len, reverse=True)
    alternation = "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in parts)
    if strict_boundary:
        return re.compile(rf"(?<![\w-])(?:{alternation}){suffixes}(?![\w-])", re.IGNORECASE)
    return re.compile(rf"\b(?:{alternation}){suffixes}\b", re.IGNORECASE)


MICRO_KEYWORDS = [
    "format this", "commit message", "generate docstring", "explain lint",
    "type hint", "sort imports", "generate doc", "ast parse", "regex for"
]

MESH_KEYWORDS = [
    "agent mesh", "agent-mesh", "mesh swarm", "peer channel", "peer channels",
    "playbook run", "playbook orchestration", "sealed review packet",
    "patch promotion", "instruction proposal", "mesh status", "mesh doctor",
    "mesh tools", "swarm coordination"
]

SCRAPE_KEYWORDS = [
    "scrape", "scraping", "web scrape", "web scraping", "extract data",
    "extract table", "parse html", "html parsing", "dom traversal",
    "web extraction", "crawl", "crawler", "crawling", "html dump",
    "extract prices", "parse json from", "scrape page", "scrape website",
    "soup", "beautifulsoup", "cheerio", "html text", "parse dom"
]

BROWSE_KEYWORDS = [
    "browse files", "browse directory", "file tree", "directory tree", "project tree",
    "source tree", "repo tree", "codebase tree", "find file", "where is file",
    "locate file", "locate path", "search files", "search codebase", "list files in",
    "show files in", "list directory", "file structure", "folder structure",
    "path browsing", "find imports", "repo structure", "find all files", "which folder"
]

REASONING_KEYWORDS = [
    "formal proof", "state machine", "state transition logic",
    "concurrency logic", "deadlock analysis", "race condition logic",
    "algorithmic proof", "invariant proof", "formal verification",
    "recurrence relation", "algorithmic complexity", "time complexity proof"
]

_GATE_RE = _compile_keywords(GATE_KEYWORDS, strict_boundary=False, suffixes=r"(?:s|es|ed|ing)?")
_DEVICE_RE = _compile_keywords(DEVICE_KEYWORDS, strict_boundary=True)
_MEMORY_RE = _compile_keywords(MEMORY_KEYWORDS, strict_boundary=False, suffixes=r"(?:s|es|ed|ing)?")
_DOCTOR_RE = _compile_keywords(DOCTOR_KEYWORDS, strict_boundary=True)
_ARCHITECT_RE = _compile_keywords(ARCHITECT_KEYWORDS, strict_boundary=False, suffixes=r"(?:s|es|ed|ing)?")
_REVIEW_RE = _compile_keywords(REVIEW_KEYWORDS, strict_boundary=False, suffixes=r"(?:s|es|ed|ing)?")
_DEBUG_RE = _compile_keywords(DEBUG_KEYWORDS, strict_boundary=False, suffixes=r"(?:s|es|ed|ing)?")
_HIGH_STAKES_RE = _compile_keywords(HIGH_STAKES_KEYWORDS, strict_boundary=False, suffixes=r"(?:s|es|ed|ing)?")
_MICRO_RE = _compile_keywords(MICRO_KEYWORDS, strict_boundary=False, suffixes=r"(?:s|es|ed|ing)?")
_MESH_RE = _compile_keywords(MESH_KEYWORDS, strict_boundary=True)
_SCRAPE_RE = _compile_keywords(SCRAPE_KEYWORDS, strict_boundary=True, suffixes=r"(?:s|es|ed|ing)?")
_BROWSE_RE = _compile_keywords(BROWSE_KEYWORDS, strict_boundary=True, suffixes=r"(?:s|es|ed|ing)?")
_REASONING_RE = _compile_keywords(REASONING_KEYWORDS, strict_boundary=False, suffixes=r"(?:s|es|ed|ing)?")


def is_high_stakes(text: str) -> bool:
    """Detect if prompt or context involves sensitive security/database/concurrency domains."""
    return bool(_HIGH_STAKES_RE.search(text or ""))


# Soft-score weights preserve the historic first-match precedence when
# categories do not collide, but let REVIEW/ARCHITECT beat DEVICE so
# "review the android SMS handler" is not forwarded to the phone bridge.
_SCORE_WEIGHTS = {
    "GATE": 6.5,
    "DEBUG": 6.0,
    "DOCTOR": 5.5,
    "MEMORY": 5.0,
    "REVIEW": 4.5,
    "REASONING": 4.2,
    "SCRAPE": 3.8,
    "BROWSE": 3.6,
    "MESH": 3.4,
    "ARCHITECT": 3.2,
    "DEVICE": 2.5,
}

_INTENT_CONFIDENCE = {
    "GATE": 0.95,
    "MEMORY": 0.93,
    "DEVICE": 0.92,
    "MESH": 0.95,
    "REVIEW": 0.86,
    "DOCTOR": 0.94,
    "DEBUG": 0.88,
    "ARCHITECT": 0.88,
    "REASONING": 0.92,
    "SCRAPE": 0.94,
    "BROWSE": 0.93,
}

_INTENT_REASON = {
    "GATE": "Ground-truth verification gate keywords detected",
    "MEMORY": "Historical timeline, workstream query, or memory recall keywords detected",
    "DEVICE": "Mobile phone, SMS, or Android relay bridge keywords detected",
    "MESH": "Agent Mesh MCP, swarm coordination, or playbook orchestration keywords detected",
    "REVIEW": "Code review requested (will extract current git diff)",
    "DOCTOR": "System health, platform audit, or doctor keywords detected",
    "DEBUG": "Runtime exception, compiler diagnostics, or debugging keywords detected",
    "ARCHITECT": "Architectural design inquiry or comparative decision dilemma detected",
    "REASONING": "Deep algorithmic reasoning, formal logic, or complex state machine analysis detected",
    "SCRAPE": "Data scraping, web extraction, or HTML/table parsing keywords detected",
    "BROWSE": "File and path browsing, repository tree, or filesystem exploration keywords detected",
}

_INTENT_MODE = {
    "GATE": "gate",
    "MEMORY": "memory",
    "DEVICE": "device",
    "MESH": "mesh",
    "REVIEW": "review_diff",
    "DOCTOR": "doctor",
    "DEBUG": "debug",
    "ARCHITECT": "architect",
    "REASONING": "consult",
    "SCRAPE": "scraping",
    "BROWSE": "browsing",
    "GENERAL": "general",
}

_INTENT_ENGINE = {
    "MEMORY": "pieces",
    "DEVICE": "hermes",
    "DOCTOR": "auto",
    "MESH": "mesh",
    "SCRAPE": "auto",
    "BROWSE": "auto",
}


def resolve_efficiency_profile(intent: str, high_stakes: bool = False) -> Tuple[str, str, str]:
    """
    Resolves (task_category, suggested_model_tier, efficiency_rationale)
    based on task characteristics and token efficiency invariants.
    """
    if intent in ("ARCHITECT",):
        tier = "tier_2_dual_competition" if high_stakes else "tier_1_subscription"
        rationale = "System architecture and structural invariants routed to Claude 3.7 Sonnet / Codex for maximum reasoning depth."
        return ("architecture", tier, rationale)

    if intent in ("REASONING",):
        tier = "tier_2_dual_competition" if high_stakes else "tier_1_subscription"
        rationale = "Formal algorithmic logic, state machines, and concurrency proofs routed to OpenAI Codex (gpt-6-astra) / Claude 3.7."
        return ("reasoning", tier, rationale)

    if intent in ("SCRAPE",):
        return (
            "scraping",
            "tier_0_or_flash",
            "High token volume data extraction routed to Ollama / Nous Flash ($0 cost) to prevent consuming subscription rate limits."
        )

    if intent in ("BROWSE",):
        return (
            "browsing",
            "local_tools_or_slm",
            "Filesystem tree and path discovery executed locally via zero-token repository index."
        )

    if intent in ("REVIEW", "GATE", "DEBUG"):
        tier = "tier_2_dual_competition" if high_stakes else "tier_1_subscription"
        rationale = "Code diff critique and bug remediation routed to primary advisory council (Claude / Codex)."
        return ("coding", tier, rationale)

    if intent in ("MICRO",):
        return (
            "micro",
            "tier_0_local",
            "Low-complexity formatting/docstring task routed to Tier-0 local SLM to eliminate network latency and token usage."
        )

    if intent in ("DEVICE",):
        return ("mobile", "hermes_relay", "Mobile device telemetry and Android phone tasks routed to Hermes bridge.")

    if intent in ("MEMORY",):
        return ("memory", "local_ltm", "Historical context recall routed to Mem0 and local PiecesOS store.")

    if intent in ("DOCTOR",):
        return ("doctor", "tier_0_local", "Platform health and subscription cost audit executed locally in <1ms.")

    if intent in ("MESH",):
        return ("mesh", "local_tools_or_slm", "Agent Mesh MCP swarm and peer channel coordination executed locally.")

    tier = "tier_2_dual_competition" if high_stakes else "tier_1_subscription"
    return ("general", tier, "General query routed to primary advisory council with zero-downtime failover.")


def locate_workspace_paths(query: str, root_dir: Optional[Any] = None, max_results: int = 25) -> List[str]:
    """
    Fast, zero-token local workspace file locator for BROWSE intent.
    Executes git ls-files or cached directory search in <5ms.
    Strictly filters credential and secret files to prevent leaking sensitive paths.
    """
    root = Path(root_dir) if root_dir else Path.cwd()
    # Extract candidate keywords from query, filtering out common locator and tree noise words
    cleaned = re.sub(
        r"\b(find|where|is|are|locate|show|list|search|files?|paths?|directories|folders?|in|the|all|at|for|to|project|tree|repo|repository|codebase|workspace|dir|structure)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    ).strip()
    terms = [t for t in re.split(r"[\s,\'\"]+", cleaned) if len(t) >= 2]
    if not terms:
        return []

    def _is_safe(p: str) -> bool:
        norm = "/" + p.replace("\\", "/").lower().lstrip("/")
        base = norm.rsplit("/", 1)[-1]
        # Match sensitive extensions, keys, credentials, and env files without over-matching environment.py
        if base == ".env" or base.startswith((".env", "secrets.")) or base.endswith((".env", ".key", ".pem", ".keystore", ".jks", ".p12", ".pfx", ".kdbx")):
            return False
        if ".env." in base:
            return False
        if base in (".npmrc", ".netrc", ".pgpass", ".git-credentials", "id_rsa", "id_ed25519", "credentials.json"):
            return False
        if any(seg in norm for seg in ("/.ssh/", "/.aws/", "/secrets/", "/credentials/")):
            return False
        return True

    file_like_terms = [t for t in terms if "." in t or "_" in t or "-" in t]

    matches: List[str] = []
    lines: List[str] = []

    try:
        cmd = ["git", "ls-files"]
        res = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=2.0)
        if res.returncode == 0:
            lines = [l for l in res.stdout.splitlines() if _is_safe(l)]
    except Exception:
        pass

    if not lines:
        skip = {".git", "node_modules", "dist", "build", ".venv", "__pycache__", ".next", ".turbo"}
        import os
        for r, dirs, files in os.walk(str(root)):
            dirs[:] = [d for d in dirs if d not in skip]
            for f in files:
                rel = os.path.relpath(os.path.join(r, f), str(root)).replace("\\", "/")
                if _is_safe(rel):
                    lines.append(rel)
                if len(lines) >= 2000:
                    break
            if len(lines) >= 2000:
                break

    # Stage 1: All extracted terms match
    for line in lines:
        line_lower = line.lower()
        if all(term.lower() in line_lower for term in terms):
            matches.append(line)
            if len(matches) >= max_results:
                return matches

    if matches:
        return matches

    # Stage 2: If specific file-like terms (e.g. "intent_engine.py") exist, match those
    if file_like_terms:
        for line in lines:
            line_lower = line.lower()
            if all(term.lower() in line_lower for term in file_like_terms):
                matches.append(line)
                if len(matches) >= max_results:
                    return matches

    if matches:
        return matches

    # Stage 3: Match any term on token boundaries, ranked by number of matched terms
    def _line_tokens(l: str) -> set:
        return set(re.split(r"[\s/\\._-]+", l.lower()))

    scored = []
    for line in lines:
        tokens = _line_tokens(line)
        score = sum(1 for term in terms if term.lower() in tokens or (len(term) >= 4 and any(t.startswith(term.lower()) for t in tokens)))
        if score > 0:
            scored.append((score, line))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [line for _, line in scored[:max_results]]


def _council_engine(high_stakes: bool) -> str:
    return "competition" if high_stakes else "auto"


def classify_intent(prompt: str, context: Optional[str] = None, diff: Optional[str] = None) -> IntentClassification:
    """
    Classifies raw developer input into a concrete Triad subsystem intent.
    Executes in <1ms with deterministic rule engines and zero external API calls.

    Hard overrides (diff syntax, stack traces) still win outright. Everything
    else is scored so overlapping keywords pick the higher-value intent
    instead of whichever regex ran first.
    """
    combined_text = f"{prompt or ''}\n{context or ''}\n{diff or ''}".strip()
    lowered_prompt = (prompt or "").lower().strip()
    high_stakes = is_high_stakes(combined_text)

    # 1. Explicit / Embedded Git Diff Check
    has_diff = bool(diff and diff.strip()) or any(p.search(combined_text) for p in DIFF_PATTERNS)
    if has_diff:
        # If diff is paired with an explicit gate request, gate takes precedence
        if _GATE_RE.search(lowered_prompt):
            cat, tier, rat = resolve_efficiency_profile("GATE", high_stakes=high_stakes)
            return IntentClassification(
                intent="GATE",
                confidence=0.98,
                reason="Pre-commit verification keywords detected alongside git diff",
                suggested_mode="gate",
                suggested_engine=_council_engine(high_stakes),
                high_stakes=high_stakes,
                task_category=cat,
                suggested_model_tier=tier,
                efficiency_rationale=rat,
                metadata={"has_diff": True}
            )
        cat, tier, rat = resolve_efficiency_profile("REVIEW", high_stakes=high_stakes)
        return IntentClassification(
            intent="REVIEW",
            confidence=0.97,
            reason="Unified git diff syntax detected in prompt or context",
            suggested_mode="review_diff",
            suggested_engine=_council_engine(high_stakes),
            high_stakes=high_stakes,
            task_category=cat,
            suggested_model_tier=tier,
            efficiency_rationale=rat,
            metadata={"has_diff": True}
        )

    # 2. Stack traces are unambiguous - do not let "review this traceback" become REVIEW.
    has_stack_trace = any(p.search(combined_text) for p in STACK_TRACE_PATTERNS)
    if has_stack_trace:
        cat, tier, rat = resolve_efficiency_profile("DEBUG", high_stakes=high_stakes)
        return IntentClassification(
            intent="DEBUG",
            confidence=0.96,
            reason="Runtime exception, compiler diagnostics, or debugging keywords detected",
            suggested_mode="debug",
            suggested_engine=_council_engine(high_stakes),
            high_stakes=high_stakes,
            task_category=cat,
            suggested_model_tier=tier,
            efficiency_rationale=rat,
            metadata={"has_stack_trace": True}
        )

    # 3. Scored soft match. Weights keep historic precedence on non-overlapping
    #    prompts while letting REVIEW/ARCHITECT beat DEVICE on collisions.
    scores: Dict[str, float] = {}
    if _GATE_RE.search(lowered_prompt):
        scores["GATE"] = _SCORE_WEIGHTS["GATE"]
    if _DEBUG_RE.search(lowered_prompt):
        scores["DEBUG"] = _SCORE_WEIGHTS["DEBUG"]
    if _DOCTOR_RE.search(lowered_prompt):
        scores["DOCTOR"] = _SCORE_WEIGHTS["DOCTOR"]
    if _MEMORY_RE.search(lowered_prompt):
        scores["MEMORY"] = _SCORE_WEIGHTS["MEMORY"]
    if lowered_prompt.startswith("review") or _REVIEW_RE.search(lowered_prompt):
        scores["REVIEW"] = _SCORE_WEIGHTS["REVIEW"]
        if lowered_prompt.startswith("review"):
            scores["REVIEW"] += 1.5
    if _ARCHITECT_RE.search(lowered_prompt):
        scores["ARCHITECT"] = _SCORE_WEIGHTS["ARCHITECT"]
    if _REASONING_RE.search(lowered_prompt):
        scores["REASONING"] = _SCORE_WEIGHTS["REASONING"]
    if _SCRAPE_RE.search(lowered_prompt):
        scores["SCRAPE"] = _SCORE_WEIGHTS["SCRAPE"]
    if _BROWSE_RE.search(lowered_prompt):
        scores["BROWSE"] = _SCORE_WEIGHTS["BROWSE"]
    if _DEVICE_RE.search(lowered_prompt):
        scores["DEVICE"] = _SCORE_WEIGHTS["DEVICE"]
    if _MESH_RE.search(lowered_prompt):
        scores["MESH"] = _SCORE_WEIGHTS["MESH"]

    if scores:
        winner = max(scores, key=lambda k: (scores[k], _SCORE_WEIGHTS.get(k, 0)))
        meta: Dict[str, Any] = {"scores": scores}
        if winner == "REVIEW":
            meta["needs_git_diff"] = True
        cat, tier, rat = resolve_efficiency_profile(winner, high_stakes=high_stakes)
        return IntentClassification(
            intent=winner,
            confidence=_INTENT_CONFIDENCE.get(winner, 0.80),
            reason=_INTENT_REASON.get(winner, "Scored intent match"),
            suggested_mode=_INTENT_MODE.get(winner, "general"),
            suggested_engine=_INTENT_ENGINE.get(winner, _council_engine(high_stakes)),
            high_stakes=high_stakes if winner not in ("MEMORY", "DEVICE", "DOCTOR", "MESH", "SCRAPE", "BROWSE") else False,
            task_category=cat,
            suggested_model_tier=tier,
            efficiency_rationale=rat,
            metadata=meta,
        )

    # 4. Micro-tasks: only evaluated if no higher-precedence intents scored and prompt is not high-stakes
    # No port probes in classify_intent to preserve the <1ms zero-I/O guarantee.
    if not high_stakes and _MICRO_RE.search(lowered_prompt):
        cat, tier, rat = resolve_efficiency_profile("MICRO", high_stakes=False)
        return IntentClassification(
            intent="MICRO",
            confidence=0.94,
            reason="Low-complexity micro-task routed to Tier-0 local SLM (port 11434)",
            suggested_mode="general",
            suggested_engine="ollama",
            high_stakes=False,
            task_category=cat,
            suggested_model_tier=tier,
            efficiency_rationale=rat,
            metadata={"tier": 0}
        )

    cat, tier, rat = resolve_efficiency_profile("GENERAL", high_stakes=high_stakes)
    return IntentClassification(
        intent="GENERAL",
        confidence=0.70,
        reason="General development query routed to primary advisory council",
        suggested_mode="general",
        suggested_engine=_council_engine(high_stakes),
        high_stakes=high_stakes,
        task_category=cat,
        suggested_model_tier=tier,
        efficiency_rationale=rat,
    )

def execute_intent(classification: IntentClassification, raw_prompt: str, args: Any = None, env: Any = None) -> None:
    """
    Executes the action corresponding to the classified intent by delegating
    directly to the appropriate subsystem or command handler.
    """
    intent = classification.intent
    stakes_label = " [HIGH STAKES - DUAL ADVISOR ADJUDICATION]" if classification.high_stakes else ""
    print(f"\n[Triad Intent Engine]: {intent}{stakes_label}")
    print(f"  Confidence: {int(classification.confidence * 100)}% | Rationale: {classification.reason}")
    print(f"  Task Profile: {classification.task_category} | Model Tier: {classification.suggested_model_tier}")
    if classification.efficiency_rationale:
        print(f"  Efficiency Routing: {classification.efficiency_rationale}")
    print(f"  Target Mode: {classification.suggested_mode} | Recommended Engine: {classification.suggested_engine}\n")

    # Import triad engine dispatchers lazily to avoid circular dependencies
    try:
        from triad import triad_engine
    except ImportError:
        import triad_engine

    if intent == "MESH":
        triad_engine.cmd_mesh(args)
        return

    if intent == "DOCTOR":
        triad_engine.cmd_doctor(args)
        return

    if intent == "GATE":
        # Pass competition flag if suggested or explicitly set
        if classification.suggested_engine == "competition" and hasattr(args, "competition"):
            args.competition = True
        triad_engine.cmd_gate(args, env=env)
        return

    if intent == "REVIEW":
        if not getattr(args, "prompt", None):
            setattr(args, "prompt", raw_prompt)
        if classification.suggested_engine == "competition":
            setattr(args, "competition", True)
        triad_engine.cmd_review(args, env=env)
        return

    if intent == "DEBUG":
        if not getattr(args, "error", None):
            setattr(args, "error", raw_prompt)
        if not getattr(args, "prompt", None):
            setattr(args, "prompt", raw_prompt)
        if classification.suggested_engine == "competition":
            setattr(args, "competition", True)
        triad_engine.cmd_debug(args)
        return

    if intent == "BROWSE":
        paths = locate_workspace_paths(raw_prompt)
        p_lower = raw_prompt.lower().strip()
        is_pure_locator = any(p_lower.startswith(prefix) for prefix in (
            "where is ", "where are ", "find file ", "locate file ", "locate path ",
            "list files in ", "show files in ", "list directory ", "search files "
        ))

        if paths:
            print(f"[Triad Local Browser]: Located {len(paths)} matching file path(s) in workspace:")
            for p in paths[:15]:
                print(f"    - {p}")
            if len(paths) > 15:
                print(f"    ... and {len(paths) - 15} more.")
            print()
            if is_pure_locator:
                return
            if args is not None:
                existing_ctx = getattr(args, "context", "") or ""
                setattr(args, "context", (existing_ctx + f"\nDiscovered local files:\n" + "\n".join(paths[:10])).strip())
        else:
            print(f"[Triad Local Browser]: No matching file paths found in workspace for query: '{raw_prompt.strip()}'.")
            if is_pure_locator:
                return

        if args is not None:
            if getattr(args, "task", "auto") in ("auto", None, ""):
                setattr(args, "task", "browsing")
            if not getattr(args, "prompt", None):
                setattr(args, "prompt", raw_prompt)
            triad_engine.cmd_consult(args)
        return

    if intent in ("SCRAPE", "REASONING", "ARCHITECT", "GENERAL", "MICRO"):
        if args is not None:
            if not getattr(args, "prompt", None):
                setattr(args, "prompt", raw_prompt)
            if classification.suggested_engine == "competition":
                setattr(args, "competition", True)
            if getattr(args, "task", "auto") in ("auto", None, ""):
                setattr(args, "task", classification.task_category)
            if hasattr(args, "engine") and getattr(args, "engine", "auto") == "auto":
                if classification.suggested_engine == "ollama":
                    if triad_engine.is_port_open("127.0.0.1", PORT_OLLAMA):
                        setattr(args, "engine", "ollama")
                    else:
                        setattr(args, "engine", "auto")
                elif classification.suggested_engine != "auto":
                    setattr(args, "engine", classification.suggested_engine)
            triad_engine.cmd_consult(args)
        else:
            print(f"[Triad Notice] Intent {intent} classified in headless mode (no args provided).")
        return

    if intent == "DEVICE":
        print("[Triad -> Hermes Android Bridge]:")
        bridge_alive = triad_engine.is_port_open("127.0.0.1", PORT_HERMES_RELAY)
        if not bridge_alive:
            print(f"❌ Android Relay port {PORT_HERMES_RELAY} is STANDBY (Phone app com.hermesandroid.bridge not dialed in).")
            print(f"Ensure android_relay_runner.py is active in {ANDROID_RELAY_ENV}")
        else:
            print(f"✓ Android Relay port {PORT_HERMES_RELAY} is ONLINE.")
        print(f"Forwarding device task to Hermes: {raw_prompt}")
        if triad_engine.HERMES_PATH.exists():
            # Use -z (--oneshot) for script/pipeline single prompt execution
            cmd = [str(triad_engine.HERMES_PATH), "-z", raw_prompt]
            res = subprocess.run(cmd)
            return res.returncode
        else:
            print(f"Hermes binary not found at {triad_engine.HERMES_PATH}")
            return 1

    if intent == "MEMORY":
        print(f"[Triad -> Local Memory Hub]: Recalling context for '{raw_prompt}'...")
        mem0_ran = False
        mem0_success = False
        if MEM0_SCRIPT.exists():
            print("\n--- Mem0 Long-Term Memory Recall ---")
            res = subprocess.run(["node", str(MEM0_SCRIPT), "search", raw_prompt])
            mem0_ran = True
            mem0_success = (res.returncode == 0)

        print("\n--- PiecesOS Status ---")
        pieces_reachable = False
        try:
            import urllib.request
            # B310 suppressed below: local healthcheck on trusted loopback port, no injection surface
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT_PIECES_OS}/.well-known/health", timeout=2.0) as resp:  # nosec B310
                if resp.status == 200:
                    pieces_reachable = True
                    print(f"✓ PiecesOS core daemon is reachable on port {PORT_PIECES_OS}.")
        except Exception:
            pass

        if not pieces_reachable:
            print(f"Note: PiecesOS port {PORT_PIECES_OS} is standby or busy.")
        if mem0_success:
            print("Memory recall completed via Mem0.")
        elif mem0_ran:
            print("Note: Mem0 query completed with no results or errors.")
        else:
            print(f"Note: Mem0 script not found at {MEM0_SCRIPT}.")
        return
