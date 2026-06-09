"""Domain models — pure, no external dependencies."""

from .documents import Chunk, ChunkMetadata, Document
from .errors import AdapterError, ConfigurationError, VersionMismatchError
from .messages import (
    AssistantMessage,
    TextPayload,
    ToolMessage,
    UserMessage,
)
from .pipeline import PipelineData

__all__ = [
    "UserMessage",
    "AssistantMessage",
    "TextPayload",
    "ToolMessage",
    "Document",
    "Chunk",
    "ChunkMetadata",
    "PipelineData",
    "ConfigurationError",
    "AdapterError",
    "VersionMismatchError",
]
