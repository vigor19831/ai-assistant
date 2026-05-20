import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.deps import get_state
from main import app


@pytest.mark.asyncio
async def test_concurrent_chat_requests(mock_state):
    app.dependency_overrides[get_state] = lambda: mock_state
    mock_state.llm.complete = AsyncMock(
        return_value=MagicMock(text="ok", tool_calls=[], metadata={})
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        tasks = [
            ac.post(
                "/chat", json={"message": f"stress {i}", "conversation_id": f"conv-{i}"}
            )
            for i in range(50)
        ]
        responses = await asyncio.gather(*tasks)

    assert all(r.status_code == 200 for r in responses)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_concurrent_vector_store_ops(mock_vector_store):
    from adapters.vector_store_memory import MemoryVectorStore
    from core.domain.documents import Chunk

    cfg = MagicMock(dim=3)
    store = MemoryVectorStore(cfg)

    async def add_chunks(start, count):
        chunks = [
            Chunk(id=f"c_{start}_{i}", text=f"t{i}", embedding=[1.0, 0.0, 0.0])
            for i in range(count)
        ]
        await store.add(chunks, namespace="stress")

    async def search_chunks():
        return await store.search([1.0, 0.0, 0.0], top_k=5, namespace="stress")

    tasks = []
    for i in range(20):
        tasks.append(add_chunks(i, 5))
        tasks.append(search_chunks())

    await asyncio.gather(*tasks)
    # If no deadlock/exception, test passes
    chunks = await store.search([1.0, 0.0, 0.0], top_k=100, namespace="stress")
    assert len(chunks) > 0
