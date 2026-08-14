"""Domain models — pure, no external dependencies."""

from .documents import Chunk, ChunkMetadata, Document
from .errors import AdapterError, ConfigurationError, VersionMismatchError
from .messages import (
    AssistantMessage,
    ToolMessage,
    UserMessage,
)
from .pipeline import PipelineData, ReindexStatusEntry

__all__ = [
    "AdapterError",
    "AssistantMessage",
    "Chunk",
    "ChunkMetadata",
    "ConfigurationError",
    "Document",
    "PipelineData",
    "ReindexStatusEntry",
    "ToolMessage",
    "UserMessage",
    "VersionMismatchError",
]
