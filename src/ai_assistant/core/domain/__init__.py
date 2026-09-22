"""Domain models — pure, no external dependencies."""

from .documents import Chunk, ChunkMetadata, Document
from .errors import AdapterError, ConfigurationError, VersionMismatchError
from .messages import (
    AssistantMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from .pipeline import DateFilter, PipelineConfig, PipelineData, ReindexStatusEntry

__all__ = [
    "AdapterError",
    "AssistantMessage",
    "Chunk",
    "ChunkMetadata",
    "ConfigurationError",
    "DateFilter",
    "Document",
    "PipelineConfig",
    "PipelineData",
    "ReindexStatusEntry",
    "SystemMessage",
    "ToolMessage",
    "UserMessage",
    "VersionMismatchError",
]
