import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from ai_assistant.api.deps import get_state
from ai_assistant.api.security import SecurityLimiter
from ai_assistant.features.chat.manager import ChatManager
from ai_assistant.main import app


@pytest.mark.asyncio
async def test_concurrent_chat_requests(mock_state):
    original_overrides = app.dependency_overrides.copy()
    original_lifespan = app.lifespan
    app.lifespan = None
    app.dependency_overrides[get_state] = lambda: mock_state
    app.state.app_state = mock_state

    try:
        with patch.object(SecurityLimiter, "is_allowed", return_value=True):
            with patch(
                "ai_assistant.api.security.get_expected_api_key",
                return_value="test-key",
            ):
                with patch.object(
                    ChatManager,
                    "chat",
                    new_callable=AsyncMock,
                    return_value=MagicMock(text="ok", tool_calls=[], metadata={}),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app),
                        base_url="http://localhost",
                        headers={"Authorization": "Bearer test-key"},
                    ) as ac:
                        tasks = [
                            ac.post(
                                "/api/v1/chat",
                                json={
                                    "message": f"stress {i}",
                                    "conversation_id": f"conv-{i}",
                                },
                            )
                            for i in range(50)
                        ]
                        responses = await asyncio.gather(*tasks)

                    bad = [
                        (i, r.status_code, r.text[:200])
                        for i, r in enumerate(responses)
                        if r.status_code != 200
                    ]
                    assert not bad, f"Non-200 responses: {bad[:3]}"
    finally:
        app.dependency_overrides = original_overrides
        app.lifespan = original_lifespan


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
