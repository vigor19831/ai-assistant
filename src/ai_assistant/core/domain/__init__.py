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
    "UserMessage",
    "AssistantMessage",
    "ToolMessage",
    "Document",
    "Chunk",
    "ChunkMetadata",
    "PipelineData",
    "ReindexStatusEntry",
    "ConfigurationError",
    "AdapterError",
    "VersionMismatchError",
]
