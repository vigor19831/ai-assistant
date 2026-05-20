"""Critical tests for Sacred Core — must pass 100% always.

Covers: registry, pipeline, domain models, config, prompts, utils, retry.
These are immutable — any failure is a project-breaking bug.
"""

from __future__ import annotations

import pytest

from core.config import AppConfig, load_config
from core.domain.documents import Chunk, ChunkMetadata, Document
from core.domain.messages import AssistantMessage, ImagePayload, UserMessage
from core.domain.pipeline import PipelineData
from core.pipeline import RAGPipeline
from core.prompts import get_prompt
from core.registry import create, list_adapters, register
from core.retry import with_retry
from core.utils import resolve_api_key

# ── Registry ──


class TestRegistry:
    def test_register_and_create(self):
        @register("test_port", "test_adapter")
        class Dummy:
            def __init__(self, config):
                self.config = config

        obj = create("test_port", "test_adapter", {"x": 1})
        assert obj.config == {"x": 1}

    def test_create_unknown_raises(self):
        with pytest.raises(ValueError, match="No adapter registered"):
            create("nonexistent", "nonexistent", {})

    def test_list_adapters_returns_dict(self):
        adapters = list_adapters()
        assert isinstance(adapters, dict)
        assert any(port in adapters for port in ["llm", "embedder", "vector_store"])

    def test_list_adapters_by_port(self):
        llm_adapters = list_adapters("llm")
        assert isinstance(llm_adapters, list)


# ── Pipeline ──


class TestPipeline:
    @pytest.mark.asyncio
    async def test_sequential_execution(self):
        async def step1(d: PipelineData) -> PipelineData:
            d.metadata["s1"] = True
            return d

        async def step2(d: PipelineData) -> PipelineData:
            d.metadata["s2"] = True
            return d

        pipeline = RAGPipeline([step1, step2])
        result = await pipeline.run(PipelineData(query=UserMessage(text="q")))
        assert result.metadata == {"s1": True, "s2": True}

    @pytest.mark.asyncio
    async def test_empty_pipeline_returns_unchanged(self):
        pipeline = RAGPipeline([])
        data = PipelineData(query=UserMessage(text="test"))
        result = await pipeline.run(data)
        assert result.query.text == "test"

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        async def bad_step(d: PipelineData) -> PipelineData:
            raise RuntimeError("fail")

        pipeline = RAGPipeline([bad_step])
        with pytest.raises(RuntimeError, match="fail"):
            await pipeline.run(PipelineData())


# ── Domain Models ──


class TestDomainModels:
    def test_user_message_text(self):
        msg = UserMessage(text="hello")
        assert msg.text == "hello"
        assert msg.role.value == "user"

    def test_user_message_no_payload_raises(self):
        with pytest.raises(ValueError, match="must contain at least one payload"):
            UserMessage()

    def test_user_message_with_image(self):
        msg = UserMessage(text="look", image=ImagePayload(url="http://img.png"))
        assert msg.image.url == "http://img.png"

    def test_assistant_message(self):
        msg = AssistantMessage(text="reply", tool_calls=[{"id": "1"}])
        assert msg.text == "reply"
        assert len(msg.tool_calls) == 1

    def test_document_and_chunk(self):
        doc = Document(id="d1", content="hello world")
        chunk = Chunk(
            id="c1",
            text="hello",
            metadata=ChunkMetadata(source="d1", index=0, total_chunks=1),
        )
        doc.chunks.append(chunk)
        assert len(doc.chunks) == 1
        assert doc.chunks[0].metadata.source == "d1"

    def test_chunk_frozen_metadata(self):
        meta = ChunkMetadata(source="s", index=0, total_chunks=1)
        with pytest.raises(AttributeError):
            meta.source = "x"  # frozen dataclass


# ── Config ──


class TestConfig:
    def test_default_values(self):
        cfg = AppConfig()
        assert cfg.app_name == "ai-assistant"
        assert cfg.port == 8000
        assert cfg.debug is False
        assert cfg.chunker.provider == "simple"
        assert cfg.llm.provider == "mock"
        assert cfg.vector_store.provider == "memory"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("AI_APP_NAME", "test")
        monkeypatch.setenv("AI_PORT", "9999")
        cfg = AppConfig()
        assert cfg.app_name == "test"
        assert cfg.port == 9999

    def test_rag_steps_string_parsing(self):
        cfg = AppConfig(rag={"steps": "a,b,c"})
        assert cfg.rag.steps == ["a", "b", "c"]

    def test_load_config_from_yaml(self, tmp_path, monkeypatch):
        yaml = tmp_path / "cfg.yaml"
        yaml.write_text("app_name: from-yaml\nport: 7777")
        monkeypatch.chdir(tmp_path)
        cfg = load_config("cfg.yaml")
        assert cfg.app_name == "from-yaml"
        assert cfg.port == 7777

    def test_load_config_fallback(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config("nonexistent.yaml")
        assert cfg.app_name == "ai-assistant"


# ── Prompts ──


class TestPrompts:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("rag_default", ["Context:", "chunk1"]),
            ("rag_strict", ["Rules:", "citations"]),
            ("rag_creative", ["imaginative"]),
            ("summarize", ["Summary:"]),
            ("voice_transcribe", ["Cleaned text:"]),
        ],
    )
    def test_prompt_renders(self, name, expected):
        prompt = get_prompt(
            name,
            version="v1",
            query="test",
            chunks=[{"text": "chunk1"}],
            text="text",
            transcript="transcript",
            max_sentences="3",
        )
        for substr in expected:
            assert substr.lower() in prompt.lower(), f"{name} missing: {substr}"

    def test_unknown_version_raises(self):
        with pytest.raises(ValueError, match="version directory not found"):
            get_prompt("rag_default", version="v999")

    def test_unknown_prompt_raises(self):
        with pytest.raises(Exception):  # jinja2 TemplateNotFound
            get_prompt("nonexistent", version="v1")


# ── Utils ──


class TestUtils:
    def test_resolve_api_key_from_value(self):
        assert resolve_api_key("key", "ENV") == "key"

    def test_resolve_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ENV", "env-key")
        assert resolve_api_key(None, "ENV") == "env-key"

    def test_resolve_api_key_missing_raises(self):
        with pytest.raises(ValueError, match="API key not found"):
            resolve_api_key(None, "NONEXISTENT_VAR_99999")

    def test_config_takes_precedence_over_env(self, monkeypatch):
        monkeypatch.setenv("ENV", "env")
        assert resolve_api_key("config", "ENV") == "config"


# ── Retry ──


class TestRetry:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        calls = 0

        @with_retry(max_retries=2, delay=0.01)
        async def fn():
            nonlocal calls
            calls += 1
            return "ok"

        assert await fn() == "ok"
        assert calls == 1

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        calls = 0

        @with_retry(max_retries=2, delay=0.01)
        async def fn():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ConnectionError("fail")
            return "ok"

        assert await fn() == "ok"
        assert calls == 3

    @pytest.mark.asyncio
    async def test_permanent_error_no_retry(self):
        calls = 0

        @with_retry(max_retries=2, delay=0.01)
        async def fn():
            nonlocal calls
            calls += 1
            raise ValueError("perm")

        with pytest.raises(ValueError, match="perm"):
            await fn()
        assert calls == 1

    @pytest.mark.asyncio
    async def test_exhausted_retries(self):
        @with_retry(max_retries=1, delay=0.01)
        async def fn():
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError, match="fail"):
            await fn()

    def test_sync_branch(self):
        calls = 0

        @with_retry(max_retries=1, delay=0.0)
        def fn():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("fail")
            return "ok"

        assert fn() == "ok"
        assert calls == 2
