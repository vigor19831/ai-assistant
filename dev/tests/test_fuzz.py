"""Fuzz tests with hypothesis — boundary cases, unicode, large data.

Requires: hypothesis (optional dev dependency).
If not installed, all tests are skipped gracefully.
"""

from __future__ import annotations

import asyncio

import pytest

try:
    from hypothesis import given, seed
    from hypothesis import strategies as st

    _HYPOTHESIS_AVAILABLE = True
except ModuleNotFoundError:
    _HYPOTHESIS_AVAILABLE = False

    # Dummy decorators to keep class structure valid
    def given(*args, **kwargs):
        return lambda f: pytest.mark.skip(reason="hypothesis not installed")(f)

    def seed(*args, **kwargs):
        return lambda f: f

    class _DummySt:
        @staticmethod
        def text(*args, **kwargs):
            return None

        @staticmethod
        def lists(*args, **kwargs):
            return None

        @staticmethod
        def integers(*args, **kwargs):
            return None

        @staticmethod
        def tuples(*args, **kwargs):
            return None

        @staticmethod
        def dictionaries(*args, **kwargs):
            return None

    st = _DummySt()

from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.storage_sqlite import SQLiteStorage
from ai_assistant.core.domain.documents import Document
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.pipeline.steps import build_context

# ── Chunker fuzzing ──


class TestFuzzChunker:
    @seed(42)
    @given(
        text=st.text(min_size=0, max_size=2000),
        size=st.integers(min_value=5, max_value=500),
        overlap=st.integers(min_value=0, max_value=50),
    )
    @pytest.mark.asyncio
    async def test_random_texts_chunking(self, text: str, size: int, overlap: int):
        if not _HYPOTHESIS_AVAILABLE:
            pytest.skip("hypothesis not installed")
        cfg = type(
            "C", (), {"chunk_size": max(size, overlap + 1), "chunk_overlap": overlap}
        )()
        chunker = SimpleChunker(cfg)
        doc = Document(id="fuzz", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) >= 0
        if chunks:
            assert all(len(c.text) <= cfg.chunk_size for c in chunks)
            assert all(c.text.strip() for c in chunks)
            assert all(c.metadata.total_chunks == len(chunks) for c in chunks)

    @seed(42)
    @given(
        text=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=0,
            max_size=1000,
        )
    )
    @pytest.mark.asyncio
    async def test_unicode_and_special_chars(self, text: str):
        if not _HYPOTHESIS_AVAILABLE:
            pytest.skip("hypothesis not installed")
        cfg = type("C", (), {"chunk_size": 50, "chunk_overlap": 5})()
        chunker = SimpleChunker(cfg)
        doc = Document(id="fuzz_unicode", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) >= 0
        if chunks:
            assert all(isinstance(c.text, str) for c in chunks)


# ── Embedder fuzzing ──


class TestFuzzEmbedder:
    @seed(42)
    @given(texts=st.lists(st.text(min_size=0, max_size=500), min_size=0, max_size=20))
    @pytest.mark.asyncio
    async def test_mock_embedder_various_texts(self, texts: list[str]):
        if not _HYPOTHESIS_AVAILABLE:
            pytest.skip("hypothesis not installed")
        cfg = type("C", (), {"dim": 384})()
        embedder = MockEmbedder(cfg)
        result = await embedder.embed(texts)
        assert len(result) == len(texts)
        for emb in result:
            assert len(emb) == 384
            assert all(isinstance(x, float) for x in emb)

    @seed(42)
    @given(
        texts=st.lists(
            st.text(alphabet="\x00\x01\x02\xff", min_size=0, max_size=100),
            min_size=0,
            max_size=10,
        )
    )
    def test_embedder_binary_like_texts(self, texts: list[str]):
        if not _HYPOTHESIS_AVAILABLE:
            pytest.skip("hypothesis not installed")
        cfg = type("C", (), {"dim": 128})()
        embedder = MockEmbedder(cfg)
        result = asyncio.run(embedder.embed(texts))
        assert len(result) == len(texts)


# ── Storage fuzzing ──


class TestFuzzStorage:
    @seed(42)
    @given(
        pairs=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=50), st.text(min_size=0, max_size=200)
            ),
            min_size=0,
            max_size=30,
            unique_by=lambda x: x[0],
        )
    )
    def test_settings_roundtrip(self, pairs: list[tuple[str, str]]):
        if not _HYPOTHESIS_AVAILABLE:
            pytest.skip("hypothesis not installed")
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = type("C", (), {"db_path": f"{tmpdir}/test.db"})()
            storage = SQLiteStorage(cfg)

            async def _run() -> None:
                await storage.init_db()
                for key, value in pairs:
                    await storage.set(key, value)
                    got = await storage.get(key)
                    assert got == value

            asyncio.run(_run())

    @seed(42)
    @given(
        data=st.dictionaries(
            st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz_"),
            st.text(min_size=0, max_size=100),
            min_size=0,
            max_size=20,
        )
    )
    def test_settings_dict_roundtrip(self, data: dict[str, str]):
        if not _HYPOTHESIS_AVAILABLE:
            pytest.skip("hypothesis not installed")
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = type("C", (), {"db_path": f"{tmpdir}/test.db"})()
            storage = SQLiteStorage(cfg)

            async def _run() -> None:
                await storage.init_db()
                for key, value in data.items():
                    await storage.set(key, value)
                for key, value in data.items():
                    got = await storage.get(key)
                    assert got == value

            asyncio.run(_run())


# ── Pipeline fuzzing ──


class TestFuzzPipeline:
    @seed(42)
    @given(text=st.text(min_size=0, max_size=500))
    @pytest.mark.asyncio
    async def test_build_context_edge_cases(self, text: str):
        if not _HYPOTHESIS_AVAILABLE:
            pytest.skip("hypothesis not installed")
        data = PipelineData(query=UserMessage(text="q"))
        data.chunks = []
        await build_context(data)
        assert data.context == ""

    @seed(42)
    @given(chunks=st.lists(st.text(min_size=0, max_size=200), min_size=0, max_size=10))
    @pytest.mark.asyncio
    async def test_build_context_with_chunks(self, chunks: list[str]):
        if not _HYPOTHESIS_AVAILABLE:
            pytest.skip("hypothesis not installed")
        from ai_assistant.core.domain.documents import Chunk

        data = PipelineData(query=UserMessage(text="q"))
        data.chunks = [Chunk(id=f"c{i}", text=t) for i, t in enumerate(chunks)]
        await build_context(data)
        if chunks:
            assert all(c in data.context for c in chunks if c)
        else:
            assert data.context == ""
