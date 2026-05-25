import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from ai_assistant.api.deps import get_state
from ai_assistant.main import app


@pytest.mark.asyncio
async def test_concurrent_chat_requests(mock_state):
    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_state] = lambda: mock_state
    mock_state.llm.complete = AsyncMock(
        return_value=MagicMock(text="ok", tool_calls=[], metadata={})
    )

    try:
        with patch(
            "ai_assistant.api.security.get_expected_api_key", lambda: "test-key"
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://localhost",
                headers={"Authorization": "Bearer test-key"},
            ) as ac:
                tasks = [
                    ac.post(
                        "/chat",
                        json={
                            "message": f"stress {i}",
                            "conversation_id": f"conv-{i}",
                        },
                    )
                    for i in range(50)
                ]
                responses = await asyncio.gather(*tasks)

            assert all(r.status_code == 200 for r in responses)
    finally:
        app.dependency_overrides = original_overrides


@pytest.mark.asyncio
async def test_concurrent_vector_store_ops(mock_vector_store):
    from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
    from ai_assistant.core.domain.documents import Chunk

    cfg = MagicMock(dim=3, max_chunks=10000, relevance_threshold=0.3)
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
