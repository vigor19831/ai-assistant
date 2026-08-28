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
SOURCE_INDEX_TIMEOUT = 300.0
# Max time to wait for background tasks during graceful shutdown.
BACKGROUND_TASKS_SHUTDOWN_TIMEOUT = 30.0
