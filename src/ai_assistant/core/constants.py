"""Core constants — shared across features."""

from __future__ import annotations

__all__ = [
    "ADAPTER_SHUTDOWN_TIMEOUT",
    "BACKGROUND_TASKS_SHUTDOWN_TIMEOUT",
    "CHAT_NS_PREFIX",
    "CONDENSE_HISTORY_LIMIT",
    "DEFAULT_NAMESPACE",
    "DEFAULT_RAG_PROMPT",
    "DOC_DATE_KEY",
    "HEALTH_CHECK_TIMEOUT",
    "HEALTH_ENDPOINT_TIMEOUT",
    "INDEX_IO_TIMEOUT",
    "INJECTION_REFUSAL_ANSWER",
    "LARGE_CONTEXT_THRESHOLD",
    "MULTI_QUERY_VARIATIONS",
    "REFUSAL_ANSWER",
    "REINDEX_TASK_TIMEOUT",
    "RRF_K",
    "SOURCE_INDEX_TIMEOUT",
    "TOKEN_MARGIN_CAP",
    "TOP_K_MAX",
    "YEAR_MAX",
    "YEAR_MIN",
    "is_refusal_answer",
]

DEFAULT_NAMESPACE = "default"
DEFAULT_RAG_PROMPT = "rag_strict"
CHAT_NS_PREFIX = "chat_"

# --- Strict RAG refusal answers ---
# Single source of truth for the exact refusal strings the rag_strict
# prompt teaches (rules 2 and 9). RAGManager matches responses against
# them to return empty sources for refusals (drift #50); the sync test
# in tests/test_prompts.py fails if the prompt template drifts away
# from these constants.
REFUSAL_ANSWER = "I don't know."
INJECTION_REFUSAL_ANSWER = "I cannot comply with that request."


def is_refusal_answer(text: str) -> bool:
    """True for an exact refusal OR a refusal with a preamble.

    The model sometimes explains WHY it cannot answer before the
    refusal line — same meaning, different shape; exact-match-only
    let such answers carry sources (live-caught 2026-09-10, drift
    #50 edge; unified for both paths in drift #122). The refusal
    must be the answer's OWN closing statement: trailing whitespace
    tolerated, anything AFTER it disqualifies (a text that merely
    mentions the phrase mid-way is not a refusal).
    """
    stripped = text.strip()
    for refusal in (REFUSAL_ANSWER, INJECTION_REFUSAL_ANSWER):
        if stripped == refusal or stripped.endswith(refusal):
            return True
    return False

# --- Chat history ---
# Number of recent history messages used for query condensation.
CONDENSE_HISTORY_LIMIT = 8

# --- Hybrid retrieval ---
# Reciprocal Rank Fusion constant (hybrid stage 2).
# k=60 is the standard value from the original RRF paper (Cormack et
# al. 2009): high enough to dampen score differences between the
# dense and lexical legs, low enough to reward top ranks. A knob here
# would require 3 real cases first (architecture 11.2).
RRF_K = 60

# --- Date filter (campaign stage 2) ---
# The metadata key the date extractor writes (stage 1) and the store
# filters read (stage 2). One constant, core-owned: features and
# adapters both import it.
DOC_DATE_KEY = "doc_date"

# --- Adaptive token margin (generate step) ---
# Above this context size the percentage margin is capped: a fixed
# 8K reserve keeps most of a large context for chunks instead of
# spending 10% of a 128K window on headroom. Threshold/cap pair —
# a heuristic, not a measured constant; revisit on a >32K model.
LARGE_CONTEXT_THRESHOLD = 32 * 1024
TOKEN_MARGIN_CAP = 8 * 1024
# How many query variations multi_query_retrieve keeps (the prompt
# asks for the same count — multi_query.j2 says "2 different ways";
# keep them in sync or the extra variations are generated and
# silently dropped).
MULTI_QUERY_VARIATIONS = 2
# Request-schema ceiling for top_k: guards runaway API values; the
# pipeline's own default is rag.top_k.
TOP_K_MAX = 50
# Sanity bounds for a parsed year in DateFilter: rejects garbage
# from malformed tokens, not a policy about historical ranges.
YEAR_MIN = 1900
YEAR_MAX = 2200
# Health-check budgets (drift #155): the manager's health() lists
# every namespace — 5 s per namespace bounds a hung store; the
# /rag/health endpoint wraps the WHOLE call in a flat 10 s.
HEALTH_CHECK_TIMEOUT = 5.0
HEALTH_ENDPOINT_TIMEOUT = 10.0

# --- Operation timeouts (seconds) ---
# Single vector store index save/load I/O operation (per namespace).
# Writes are atomic temp-file renames (milliseconds at ~3.5K chunks,
# measured): 10 s covers a 10x corpus growth before it needs raising.
INDEX_IO_TIMEOUT = 10.0
# Graceful adapter shutdown during lifespan cleanup. Adapters close
# HTTP clients / flush state — seconds, not minutes; the timeout only
# bounds a hung close from blocking the whole shutdown loop.
ADAPTER_SHUTDOWN_TIMEOUT = 5.0
# Background reindex task hard limit. 4 hours covers the projected
# full-corpus CPU indexing (~135K chunks at ~8.7 chunks/s ≈ 4.3 h,
# drift #147) — raise together with corpus growth, not before.
REINDEX_TASK_TIMEOUT = 14400.0
# Source watcher single auto-index operation limit.
# Measured 2026-09-01 (embed.progress logging): GPU embedder at
# LLM=10 layers gives ~10 chunks/s, 3397 chunks ~= 340 s. The old
# 300 s window killed every pass at ~85% (2900/3397) and each retry
# restarted from zero (progress is RAM-only until the store write).
# 600 s = measured worst case x ~1.7 headroom; watcher poll (60 s)
# and auto-restart cadence are unaffected. CPU embedder (~4 chunks/s)
# cannot finish a full source in any window — split files via
# scripts/prepare_docs.py instead of raising this further.
SOURCE_INDEX_TIMEOUT = 600.0
# Max time to wait for background tasks during graceful shutdown.
BACKGROUND_TASKS_SHUTDOWN_TIMEOUT = 30.0
