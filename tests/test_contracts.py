from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from features.chat.schemas import (
    ChatRequest,
    ChatResponse,
    OAIChatCompletionRequest,
)
from features.rag.schemas import IndexRequest, QueryRequest, QueryResponse


class TestChatContracts:
    def test_chat_request_validation(self):
        valid = {"message": "test"}
        assert ChatRequest(**valid)
        # Empty message is allowed in current schema (no min_length constraint)
        assert ChatRequest(message="")

    def test_oai_chat_request_strict(self):
        valid = {"messages": [{"role": "user", "content": "hi"}]}
        assert OAIChatCompletionRequest(**valid)
        # content=None is allowed (str | None)
        assert OAIChatCompletionRequest(messages=[{"role": "user", "content": None}])

    def test_chat_response_structure(self, client):
        resp = client.post(
            "/chat", json={"message": "contract test", "conversation_id": "t1"}
        )
        assert resp.status_code == 200
        ChatResponse(**resp.json())  # strict pydantic validation


class TestRAGContracts:
    def test_query_request_validation(self):
        valid = {"query": "test"}
        assert QueryRequest(**valid)

        with pytest.raises(ValidationError):
            QueryRequest(query="test", top_k=0)  # ge=1 constraint

        with pytest.raises(ValidationError):
            QueryRequest(query="test", top_k=51)  # le=50 constraint

    def test_index_request_validation(self):
        valid = {"documents": [{"id": "1", "content": "text"}]}
        assert IndexRequest(**valid)
        # dict[str, Any] has no required keys validation for inner dicts
        assert IndexRequest(documents=[{"id": "1"}])

    def test_rag_query_response_structure(self, client, mock_state):
        mock_state.pipeline.run.return_value = MagicMock(
            chunks=[], response=MagicMock(text="ok"), errors=[]
        )
        resp = client.post("/rag/query", json={"query": "test"})
        assert resp.status_code == 200
        QueryResponse(**resp.json())


class TestSSEContract:
    def test_sse_format_compliance(self, client):
        resp = client.post(
            "/chat/stream", json={"message": "sse test", "conversation_id": "t1"}
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        lines = resp.text.strip().split("\n")
        for line in lines:
            if line.startswith("data:"):
                # Validate SSE data payload isn't raw text leak
                assert line[5:].strip(), "Empty SSE data chunk"
