"""Domain models — pure, no external dependencies."""

from .documents import Chunk, ChunkMetadata, Document
from .errors import AdapterError, ConfigurationError, VersionMismatchError
from .messages import (
    AssistantMessage,
    ImagePayload,
    TextPayload,
    UserMessage,
    VoicePayload,
)
from .pipeline import PipelineData

__all__ = [
    "UserMessage",
    "AssistantMessage",
    "TextPayload",
    "ImagePayload",
    "VoicePayload",
    "Document",
    "Chunk",
    "ChunkMetadata",
    "PipelineData",
    "ConfigurationError",
    "AdapterError",
    "VersionMismatchError",
]
