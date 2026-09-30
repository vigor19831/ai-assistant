"""GET /rag/prefixes: chat-addressable namespaces come from yaml.

Contract: rag.sources entries with a declared prefix, plus the
all-namespaces sentinel when the owner declared one. Store contents
(bench/test artifacts) never appear — addressing follows the yaml,
not the operational index listing."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from ai_assistant.api.security import set_api_key
from ai_assistant.core.config import NamespaceConfig, SourceConfig
from ai_assistant.core.domain.pipeline import NAMESPACE_ALL
from ai_assistant.main import create_app


def _ns(prefix: str) -> NamespaceConfig:
    return NamespaceConfig(prefix=prefix, chunk_size=512, prompt="rag_strict")


@pytest.fixture
def make_prefixes_client(isolated_app_state, tmp_path):
    """Factory: TestClient over isolated_app_state with the given
    sources/namespaces map. The client is built from the SAME state
    whose config is mutated (the conftest `client` fixture builds
    from mock_state — mutating isolated_app_state would not reach it).
    The api key is set for the request header and reset afterwards
    (random-order hygiene).
    """

    def _factory(sources, namespaces):
        isolated_app_state.config.rag.sources = sources
        isolated_app_state.config.namespaces = namespaces
        set_api_key("test-key")
        app = create_app(state=isolated_app_state)
        return TestClient(app, headers={"Authorization": "Bearer test-key"})

    yield _factory
    set_api_key(None)


_FULL_SOURCES = None  # set per-test via the factory (paths under tmp)


def test_prefixes_list_source_namespaces_with_prefixes(
    make_prefixes_client, tmp_path
):
    """Sources with declared prefixes are listed; everything else is
    not: a source without a namespaces entry ("bare"), a namespaces
    entry without a source ("no_source", "bench_000")."""
    doc_root = str(tmp_path / "documents")
    client = make_prefixes_client(
        [
            SourceConfig(namespace="default", path=doc_root),
            SourceConfig(namespace="sber", path=doc_root + "/sber"),
            SourceConfig(namespace="bare", path=doc_root + "/bare"),
        ],
        {
            "default": _ns("d"),
            "sber": _ns("sber"),
            "no_source": _ns("x"),
            "bench_000": _ns("000"),
            NAMESPACE_ALL: _ns("all"),
        },
    )
    resp = client.get("/api/v1/rag/prefixes")
    assert resp.status_code == 200
    items = {i["namespace"]: i["prefix"] for i in resp.json()["items"]}
    assert items == {"default": "d", "sber": "sber", NAMESPACE_ALL: "all"}


def test_prefixes_marks_the_all_sentinel(make_prefixes_client, tmp_path):
    """Only the sentinel entry carries is_all=True."""
    doc_root = str(tmp_path / "documents")
    client = make_prefixes_client(
        [SourceConfig(namespace="default", path=doc_root)],
        {"default": _ns("d"), NAMESPACE_ALL: _ns("all")},
    )
    resp = client.get("/api/v1/rag/prefixes")
    entries = {i["namespace"]: i for i in resp.json()["items"]}
    assert entries[NAMESPACE_ALL]["is_all"] is True
    assert entries["default"]["is_all"] is False


def test_prefixes_without_all_entry_omits_it(make_prefixes_client, tmp_path):
    """No declared sentinel -> no sentinel row in the menu."""
    doc_root = str(tmp_path / "documents")
    client = make_prefixes_client(
        [SourceConfig(namespace="default", path=doc_root)],
        {"default": _ns("d")},
    )
    resp = client.get("/api/v1/rag/prefixes")
    assert resp.status_code == 200
    assert [i["namespace"] for i in resp.json()["items"]] == ["default"]

def test_index_status_lifecycle(client):
    """Progress publishes running state; result parks the outcome."""
    from ai_assistant.features.rag import handlers as rag_handlers

    rag_handlers.report_index_progress("sber", 2, 5)
    try:
        resp = client.get("/api/v1/rag/index-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["namespace"] == "sber"
        assert data["done"] == 2 and data["total"] == 5
        assert data["started_at"] is not None
    finally:
        rag_handlers._INDEX_STATUS.clear()
    rag_handlers.report_index_result(
        {
            "success": True,
            "results": {"sber": {"indexed": 5, "chunks": 40}},
            "errors": [],
        }
    )
    try:
        resp = client.get("/api/v1/rag/index-status")
        data = resp.json()
        assert data["running"] is False
        assert data["last_result"]["success"] is True
    finally:
        rag_handlers._INDEX_STATUS.clear()


def test_index_status_idle_defaults(client):
    """Empty slot: idle defaults, not an error."""
    from ai_assistant.features.rag import handlers as rag_handlers

    rag_handlers._INDEX_STATUS.clear()
    resp = client.get("/api/v1/rag/index-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["running"] is False
    assert data["last_result"] is None
