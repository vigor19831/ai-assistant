"""Core constants — shared across features."""

from __future__ import annotations

__all__ = ["CHAT_NS_PREFIX", "DEFAULT_NAMESPACE", "DEFAULT_RAG_PROMPT"]

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

# --- Chat history ---
# Number of recent history messages used for query condensation.
CONDENSE_HISTORY_LIMIT = 8

# --- Operation timeouts (seconds) ---
# Single vector store index save/load I/O operation (per namespace).
INDEX_IO_TIMEOUT = 10.0
# Graceful adapter shutdown during lifespan cleanup.
ADAPTER_SHUTDOWN_TIMEOUT = 5.0
# Background reindex task hard limit (4 hours).
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
