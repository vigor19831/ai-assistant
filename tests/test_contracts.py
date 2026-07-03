"""tests/test_contracts.py — AST-level contract tests.

Contracts: isinstance() ban in core/, print()/pprint() ban,
logging.basicConfig() ban, cross-feature imports ban,
port abstract methods, getattr drift check.

Design: Given/When/Then docstrings, one function per test case.
"""

from __future__ import annotations

import ast
import inspect
import logging
import sys
from pathlib import Path

import pytest

from ai_assistant.core.logger import get_logger

logger = get_logger(__name__)


# ── AST helpers ──


def _find_ast_calls(source: str, filename: str, func_names: set[str]) -> list[tuple[int, str]]:
    """Find all calls to specific function names in source AST."""
    tree = ast.parse(source, filename=filename)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in func_names:
                hits.append((node.lineno, ast.unparse(node)))
            elif isinstance(node.func, ast.Attribute) and node.func.attr in func_names:
                hits.append((node.lineno, ast.unparse(node)))
    return hits


def _find_isinstance_calls(source: str, filename: str) -> list[tuple[int, str]]:
    """Find isinstance() calls in source."""
    return _find_ast_calls(source, filename, {"isinstance"})


def _find_print_calls(source: str, filename: str) -> list[tuple[int, str]]:
    """Find print()/pprint() calls in source."""
    return _find_ast_calls(source, filename, {"print", "pprint"})


def _find_basicConfig_calls(source: str, filename: str) -> list[tuple[int, str]]:
    """Find logging.basicConfig() calls in source."""
    tree = ast.parse(source, filename=filename)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "basicConfig":
                    hits.append((node.lineno, ast.unparse(node)))
    return hits


def _find_getattr_calls(source: str, filename: str) -> list[tuple[int, str]]:
    """Find getattr() calls in source."""
    return _find_ast_calls(source, filename, {"getattr"})


def _find_cross_feature_imports(source: str, filename: str) -> list[tuple[int, str]]:
    """Find cross-feature imports (chat importing rag or vice versa)."""
    tree = ast.parse(source, filename=filename)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "features.chat" in module and "rag" in module:
                hits.append((node.lineno, ast.unparse(node)))
            elif "features.rag" in module and "chat" in module:
                hits.append((node.lineno, ast.unparse(node)))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if "features.chat" in name and "rag" in name:
                    hits.append((node.lineno, ast.unparse(node)))
                elif "features.rag" in name and "chat" in name:
                    hits.append((node.lineno, ast.unparse(node)))
    return hits


def _resolve_src_file(rel_path: str) -> Path:
    """Resolve source file path from project root."""
    test_dir = Path(__file__).parent
    project_root = test_dir.parent
    src_path = project_root / "src" / "ai_assistant" / rel_path
    if src_path.exists():
        return src_path
    # Fallback: check if file exists at project root level
    alt_path = project_root / rel_path
    if alt_path.exists():
        return alt_path
    pytest.skip(f"Source file not found: {rel_path}")


# ═══════════════════════════════════════════════════════════════════════════
# TestIsinstanceBan
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestIsinstanceBan:
    """Contract: isinstance() is banned in core/ (use structural typing / ports)."""

    def _check_file(self, rel_path: str) -> list[tuple[int, str]]:
        path = _resolve_src_file(rel_path)
        source = path.read_text(encoding="utf-8")
        return _find_isinstance_calls(source, str(path))

    def test_pipeline_steps_no_isinstance(self):
        """Given: pipeline_steps.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() calls are found."""
        hits = self._check_file("core/pipeline_steps.py")
        assert not hits, f"isinstance() banned in core/: {hits}"

    def test_utils_no_isinstance(self):
        """Given: utils.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() calls are found."""
        hits = self._check_file("core/utils.py")
        assert not hits, f"isinstance() banned in core/: {hits}"

    def test_domain_pipeline_no_isinstance(self):
        """Given: domain/pipeline.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() calls are found."""
        hits = self._check_file("core/domain/pipeline.py")
        assert not hits, f"isinstance() banned in core/: {hits}"

    def test_domain_messages_no_isinstance(self):
        """Given: domain/messages.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() calls are found."""
        hits = self._check_file("core/domain/messages.py")
        assert not hits, f"isinstance() banned in core/: {hits}"

    def test_domain_documents_no_isinstance(self):
        """Given: domain/documents.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() calls are found."""
        hits = self._check_file("core/domain/documents.py")
        assert not hits, f"isinstance() banned in core/: {hits}"

    def test_config_no_isinstance(self):
        """Given: config.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() calls are found."""
        hits = self._check_file("core/config.py")
        assert not hits, f"isinstance() banned in core/: {hits}"

    def test_retry_no_isinstance(self):
        """Given: retry.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() calls are found."""
        hits = self._check_file("core/retry.py")
        assert not hits, f"isinstance() banned in core/: {hits}"

    def test_prompts_no_isinstance(self):
        """Given: prompts/__init__.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() on port objects; _make_hashable utility exempt."""
        hits = self._check_file("core/prompts/__init__.py")
        # _make_hashable uses isinstance on plain Python values for LRU cache keys,
        # not on port objects — exempt per ai_rules §2 scope
        exempt_lines = {17, 19, 21, 23}  # _make_hashable body
        filtered = [(line, code) for line, code in hits if line not in exempt_lines]
        assert not filtered, f"isinstance() banned in core/ (non-utility): {filtered}"

    def test_metrics_no_isinstance(self):
        """Given: metrics.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() calls are found."""
        hits = self._check_file("core/metrics.py")
        assert not hits, f"isinstance() banned in core/: {hits}"

    def test_logger_no_isinstance(self):
        """Given: logger.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() calls are found."""
        hits = self._check_file("core/logger.py")
        assert not hits, f"isinstance() banned in core/: {hits}"

    def test_io_utils_no_isinstance(self):
        """Given: io_utils.py in core/.
        When: AST is scanned for isinstance().
        Then: no isinstance() calls are found."""
        hits = self._check_file("core/io_utils.py")
        assert not hits, f"isinstance() banned in core/: {hits}"


# ═══════════════════════════════════════════════════════════════════════════
# TestPrintBan
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestPrintBan:
    """Contract: print()/pprint() are banned in production source (use logger)."""

    def _check_file(self, rel_path: str) -> list[tuple[int, str]]:
        path = _resolve_src_file(rel_path)
        source = path.read_text(encoding="utf-8")
        return _find_print_calls(source, str(path))

    def _check_all_py_files(self, rel_dir: str) -> list[tuple[str, int, str]]:
        """Recursively check all .py files in a directory."""
        dir_path = _resolve_src_file(rel_dir)
        hits: list[tuple[str, int, str]] = []
        for py_file in dir_path.rglob("*.py"):
            if py_file.name.startswith("test_"):
                continue
            source = py_file.read_text(encoding="utf-8")
            file_hits = _find_print_calls(source, str(py_file))
            for lineno, code in file_hits:
                hits.append((str(py_file.relative_to(dir_path.parent.parent)), lineno, code))
        return hits

    def test_core_no_print(self):
        """Given: all .py files in core/.
        When: AST is scanned for print()/pprint().
        Then: no print()/pprint() calls are found."""
        hits = self._check_all_py_files("core")
        assert not hits, f"print()/pprint() banned in core/: {hits}"

    def test_api_no_print(self):
        """Given: all .py files in api/.
        When: AST is scanned for print()/pprint().
        Then: no print()/pprint() calls are found."""
        hits = self._check_all_py_files("api")
        assert not hits, f"print()/pprint() banned in api/: {hits}"

    def test_features_no_print(self):
        """Given: all .py files in features/.
        When: AST is scanned for print()/pprint().
        Then: no print()/pprint() calls are found."""
        hits = self._check_all_py_files("features")
        assert not hits, f"print()/pprint() banned in features/: {hits}"

    def test_adapters_no_print(self):
        """Given: all .py files in adapters/.
        When: AST is scanned for print()/pprint().
        Then: no print()/pprint() calls are found."""
        hits = self._check_all_py_files("adapters")
        assert not hits, f"print()/pprint() banned in adapters/: {hits}"


# ═══════════════════════════════════════════════════════════════════════════
# TestLoggingBasicConfigBan
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestLoggingBasicConfigBan:
    """Contract: logging.basicConfig() is banned (use setup_logging from logger)."""

    def _check_all_py_files(self, rel_dir: str) -> list[tuple[str, int, str]]:
        dir_path = _resolve_src_file(rel_dir)
        hits: list[tuple[str, int, str]] = []
        for py_file in dir_path.rglob("*.py"):
            if py_file.name.startswith("test_"):
                continue
            source = py_file.read_text(encoding="utf-8")
            file_hits = _find_basicConfig_calls(source, str(py_file))
            for lineno, code in file_hits:
                hits.append((str(py_file.relative_to(dir_path.parent.parent)), lineno, code))
        return hits

    def test_no_basicConfig_in_src(self):
        """Given: all .py files in src/.
        When: AST is scanned for logging.basicConfig().
        Then: no basicConfig() calls are found."""
        hits = self._check_all_py_files("")
        assert not hits, f"logging.basicConfig() banned in src/: {hits}"


# ═══════════════════════════════════════════════════════════════════════════
# TestCrossFeatureImports
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestCrossFeatureImports:
    """Contract: chat features do not import rag directly and vice versa."""

    def _check_file(self, rel_path: str) -> list[tuple[int, str]]:
        path = _resolve_src_file(rel_path)
        source = path.read_text(encoding="utf-8")
        return _find_cross_feature_imports(source, str(path))

    def test_chat_handlers_no_rag_import(self):
        """Given: chat handlers.
        When: AST is scanned for rag imports.
        Then: no direct rag imports are found."""
        hits = self._check_file("features/chat/handlers.py")
        assert not hits, f"chat must not import rag: {hits}"

    def test_chat_manager_no_rag_import(self):
        """Given: chat manager.
        When: AST is scanned for rag imports.
        Then: no direct rag imports are found."""
        hits = self._check_file("features/chat/manager.py")
        assert not hits, f"chat must not import rag: {hits}"

    def test_rag_handlers_no_chat_import(self):
        """Given: rag handlers.
        When: AST is scanned for chat imports.
        Then: no direct chat imports are found."""
        hits = self._check_file("features/rag/handlers.py")
        assert not hits, f"rag must not import chat: {hits}"

    def test_rag_manager_no_chat_import(self):
        """Given: rag manager.
        When: AST is scanned for chat imports.
        Then: no direct chat imports are found."""
        hits = self._check_file("features/rag/manager.py")
        assert not hits, f"rag must not import chat: {hits}"


# ═══════════════════════════════════════════════════════════════════════════
# TestPortAbstractMethods
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestPortAbstractMethods:
    """Contract: all port interfaces declare at least one abstract method."""

    def _get_port_classes(self) -> dict[str, type]:
        """Import and return all port classes."""
        from ai_assistant.core.ports import (
            IChatStorage,
            IChunker,
            IClosable,
            IEmbedder,
            ILLM,
            IReranker,
            ITokenizer,
            IVectorStore,
        )
        return {
            "ILLM": ILLM,
            "IEmbedder": IEmbedder,
            "IVectorStore": IVectorStore,
            "IReranker": IReranker,
            "IChatStorage": IChatStorage,
            "IChunker": IChunker,
            "IClosable": IClosable,
            "ITokenizer": ITokenizer,
        }

    def test_all_ports_are_abstract(self):
        """Given: all port classes.
        When: inspect.isabstract() is called.
        Then: all return True (have at least one abstract method)."""
        ports = self._get_port_classes()
        non_abstract = []
        for name, cls in ports.items():
            if not inspect.isabstract(cls):
                non_abstract.append(name)
        assert not non_abstract, f"Ports must be abstract: {non_abstract}"

    def test_illm_has_abstract_methods(self):
        """Given: ILLM port.
        When: abstract methods are inspected.
        Then: at least complete() and get_context_limit() are abstract."""
        from ai_assistant.core.ports.llm import ILLM

        abstract_methods = [
            name
            for name, method in inspect.getmembers(ILLM, predicate=inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        ]
        assert "complete" in abstract_methods, "ILLM.complete must be abstract"
        assert "get_context_limit" in abstract_methods, "ILLM.get_context_limit must be abstract"

    def test_iembedder_has_embed_abstract(self):
        """Given: IEmbedder port.
        When: abstract methods are inspected.
        Then: embed() is abstract."""
        from ai_assistant.core.ports.embedder import IEmbedder

        abstract_methods = [
            name
            for name, method in inspect.getmembers(IEmbedder, predicate=inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        ]
        assert "embed" in abstract_methods, "IEmbedder.embed must be abstract"

    def test_ivectorstore_has_search_abstract(self):
        """Given: IVectorStore port.
        When: abstract methods are inspected.
        Then: search() is abstract."""
        from ai_assistant.core.ports.vector_store import IVectorStore

        abstract_methods = [
            name
            for name, method in inspect.getmembers(IVectorStore, predicate=inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        ]
        assert "search" in abstract_methods, "IVectorStore.search must be abstract"

    def test_ireranker_has_rerank_abstract(self):
        """Given: IReranker port.
        When: abstract methods are inspected.
        Then: rerank() is abstract."""
        from ai_assistant.core.ports.reranker import IReranker

        abstract_methods = [
            name
            for name, method in inspect.getmembers(IReranker, predicate=inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        ]
        assert "rerank" in abstract_methods, "IReranker.rerank must be abstract"

    def test_ichatstorage_has_history_abstract(self):
        """Given: IChatStorage port.
        When: abstract methods are inspected.
        Then: get_history() and save_message() are abstract."""
        from ai_assistant.core.ports.storage import IChatStorage

        abstract_methods = [
            name
            for name, method in inspect.getmembers(IChatStorage, predicate=inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        ]
        assert "get_history" in abstract_methods, "IChatStorage.get_history must be abstract"
        assert "save_message" in abstract_methods, "IChatStorage.save_message must be abstract"
        assert "init_db" in abstract_methods

    def test_ichunker_has_chunk_abstract(self):
        """Given: IChunker port.
        When: abstract methods are inspected.
        Then: chunk() is abstract."""
        from ai_assistant.core.ports.chunker import IChunker

        abstract_methods = [
            name
            for name, method in inspect.getmembers(IChunker, predicate=inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        ]
        assert "chunk" in abstract_methods, "IChunker.chunk must be abstract"

    def test_itokenizer_has_count_abstract(self):
        """Given: ITokenizer port.
        When: abstract methods are inspected.
        Then: count() is abstract."""
        from ai_assistant.core.ports.tokenizer import ITokenizer

        abstract_methods = [
            name
            for name, method in inspect.getmembers(ITokenizer, predicate=inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        ]
        assert "count" in abstract_methods, "ITokenizer.count must be abstract"

    def test_itokenizer_has_model_name_abstract(self):
        """Given: ITokenizer port.
        When: abstract properties are inspected.
        Then: model_name is abstract."""
        from ai_assistant.core.ports.tokenizer import ITokenizer

        abstract_properties = [
            name
            for name, prop in inspect.getmembers(ITokenizer)
            if isinstance(prop, property) and getattr(prop.fget, "__isabstractmethod__", False)
        ]
        assert "model_name" in abstract_properties, "ITokenizer.model_name must be abstract"

    def test_all_tokenizer_implementations_expose_model_name(self):
        """Given: all ITokenizer implementations.
        When: model_name property is accessed.
        Then: returns str for all."""
        from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok1 = TiktokenTokenizer(TokenizerConfigData())
        tok2 = CharFallbackTokenizer(TokenizerConfigData())
        assert isinstance(tok1.model_name, str)
        assert isinstance(tok2.model_name, str)
        assert tok1.model_name == "tiktoken"
        assert tok2.model_name == "char-fallback"

    def test_iclosable_has_shutdown_abstract(self):
        """Given: IClosable port.
        When: abstract methods are inspected.
        Then: shutdown() is abstract."""
        from ai_assistant.core.ports.closable import IClosable

        abstract_methods = [
            name
            for name, method in inspect.getmembers(IClosable, predicate=inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        ]
        assert "shutdown" in abstract_methods, "IClosable.shutdown must be abstract"


# ═══════════════════════════════════════════════════════════════════════════
# TestGetattrDrift
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestGetattrDrift:
    """Contract: getattr(config, ...) is a drift risk — use typed access instead.

    See DRIFT.md #4: getattr with config objects bypasses type checking
    and breaks IDE/refactoring support.
    """

    def _check_file(self, rel_path: str) -> list[tuple[int, str]]:
        path = _resolve_src_file(rel_path)
        source = path.read_text(encoding="utf-8")
        return _find_getattr_calls(source, str(path))

    def test_deps_no_getattr_on_config(self):
        """Given: api/deps.py.
        When: AST is scanned for getattr() calls on config objects.
        Then: no getattr(cfg, ...) or getattr(config, ...) patterns found."""
        hits = self._check_file("api/deps.py")
        # Filter out legitimate getattr uses (e.g., request.app.state)
        config_hits = [
            (ln, code)
            for ln, code in hits
            if "cfg" in code or "config" in code.lower()
        ]
        assert not config_hits, f"getattr on config is drift risk: {config_hits}"

    def test_lifespan_no_getattr_on_config(self):
        """Given: api/lifespan.py.
        When: AST is scanned for getattr() on config.
        Then: no getattr(cfg, ...) patterns found."""
        hits = self._check_file("api/lifespan.py")
        config_hits = [
            (ln, code)
            for ln, code in hits
            if "cfg" in code or "config" in code.lower()
        ]
        assert not config_hits, f"getattr on config is drift risk: {config_hits}"

    def test_pipeline_steps_no_getattr(self):
        """Given: core/pipeline_steps.py.
        When: AST is scanned for getattr().
        Then: no getattr() calls found."""
        hits = self._check_file("core/pipeline_steps.py")
        assert not hits, f"getattr() banned in pipeline_steps: {hits}"

    def test_manager_no_getattr_on_config(self):
        """Given: features/chat/manager.py.
        When: AST is scanned for getattr() on config.
        Then: no getattr(cfg, ...) patterns found."""
        hits = self._check_file("features/chat/manager.py")
        config_hits = [
            (ln, code)
            for ln, code in hits
            if "cfg" in code or "config" in code.lower()
        ]
        assert not config_hits, f"getattr on config is drift risk: {config_hits}"


# ═══════════════════════════════════════════════════════════════════════════
# TestHasattrBan (from existing contracts)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestHasattrBan:
    """AST-level contract: api/deps and api/lifespan must not use hasattr()
    to bypass ports."""

    def _find_hasattr_calls(self, source: str, filename: str) -> list[tuple[int, str]]:
        tree = ast.parse(source, filename=filename)
        hits: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "hasattr":
                    hits.append((node.lineno, ast.unparse(node)))
        return hits

    def test_api_deps_no_hasattr(self):
        """Given: api/deps.py source.
        When: AST is scanned for hasattr().
        Then: no hasattr() calls are found."""
        import inspect as _inspect
        from ai_assistant.api import deps

        source = _inspect.getsource(deps)
        hits = self._find_hasattr_calls(source, "deps.py")
        assert not hits, f"hasattr() found in api/deps.py at lines: {hits}"

    def test_api_lifespan_no_hasattr(self):
        """Given: api/lifespan.py source.
        When: AST is scanned for hasattr().
        Then: no hasattr() calls are found."""
        import inspect as _inspect
        from ai_assistant.api import lifespan

        source = _inspect.getsource(lifespan)
        hits = self._find_hasattr_calls(source, "lifespan.py")
        assert not hits, f"hasattr() found in api/lifespan.py at lines: {hits}"


# ═══════════════════════════════════════════════════════════════════════════
# TestPipelineStepsNoKwargs (from existing contracts)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
def test_pipeline_steps_no_kwargs() -> None:
    """AST check: pipeline step functions must not use **kwargs.

    Given: pipeline_steps.py source.
    When: AST is scanned for step-decorated functions with **kwargs.
    Then: no step function uses **kwargs.
    """
    import ast
    from pathlib import Path

    steps_path = (
        Path(__file__).parent.parent
        / "src"
        / "ai_assistant"
        / "core"
        / "pipeline_steps.py"
    )
    if not steps_path.exists():
        pytest.skip("pipeline_steps.py not found")
    source = steps_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            is_step = any(
                (isinstance(d, ast.Call) and getattr(d.func, "id", None) == "step")
                or (isinstance(d, ast.Name) and d.id == "step")
                for d in node.decorator_list
            )
            if is_step and node.args.kwarg is not None:
                pytest.fail(
                    f"Step function {node.name!r} uses **kwargs. "
                    f"Use StepContext instead."
                )


# ═══════════════════════════════════════════════════════════════════════════
# TestRegistryRemoved (from existing contracts)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
def test_registry_removed() -> None:
    """Phase 4.4: registry.py must be physically deleted.

    Given: core directory.
    When: checking for registry.py.
    Then: file does not exist.
    """
    from pathlib import Path

    core_dir = Path(__file__).parent.parent / "src" / "ai_assistant" / "core"
    assert not (core_dir / "registry.py").exists()


# ═══════════════════════════════════════════════════════════════════════════
# TestMessageTypeAlias (from existing contracts)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
def test_message_type_alias_excludes_dict() -> None:
    """Message alias must be UserMessage | AssistantMessage | ToolMessage,
    no dict fallback.

    Given: Message type alias.
    When: inspecting type arguments.
    Then: no dict in union members.
    """
    from typing import get_args, get_origin

    from ai_assistant.core.domain.messages import (
        AssistantMessage,
        ToolMessage,
        UserMessage,
    )
    from ai_assistant.core.ports.llm import Message

    args = get_args(Message)
    assert UserMessage in args
    assert AssistantMessage in args
    assert ToolMessage in args
    assert not any(get_origin(arg) is dict for arg in args)


# ═══════════════════════════════════════════════════════════════════════════
# TestIRerankerIsClosable (from existing contracts)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
def test_ireranker_is_closable() -> None:
    """IReranker must inherit IClosable so lifespan can call shutdown().

    Given: IReranker and IClosable.
    When: checking inheritance.
    Then: IReranker is subclass of IClosable.
    """
    from ai_assistant.core.ports.closable import IClosable
    from ai_assistant.core.ports.reranker import IReranker

    assert issubclass(IReranker, IClosable)
    assert callable(getattr(IReranker, "shutdown", None))


@pytest.mark.slow
@pytest.mark.contract
def test_ichatstorage_is_initializable() -> None:
    """IChatStorage must inherit IInitializable so init_db is part of the contract.

    See DRIFT.md: hidden contract was that init_adapters() calls
    await state.storage.init_db() without checking isinstance.
    """
    from ai_assistant.core.ports.initializable import IInitializable
    from ai_assistant.core.ports.storage import IChatStorage

    assert issubclass(IChatStorage, IInitializable)
    assert callable(getattr(IChatStorage, "init_db", None))


@pytest.mark.slow
@pytest.mark.contract
def test_ichatstorage_is_closable() -> None:
    """IChatStorage must inherit IClosable so lifespan can call shutdown().

    SQLiteStorage already implements shutdown() with WAL checkpoint;
    this makes the contract explicit.
    """
    from ai_assistant.core.ports.closable import IClosable
    from ai_assistant.core.ports.storage import IChatStorage

    assert issubclass(IChatStorage, IClosable)
    assert callable(getattr(IChatStorage, "shutdown", None))


@pytest.mark.slow
@pytest.mark.contract
def test_ichunker_is_closable() -> None:
    """IChunker must inherit IClosable so lifespan can call shutdown().

    SimpleChunker already implements shutdown() as no-op;
    this makes the contract explicit.
    """
    from ai_assistant.core.ports.chunker import IChunker
    from ai_assistant.core.ports.closable import IClosable

    assert issubclass(IChunker, IClosable)
    assert callable(getattr(IChunker, "shutdown", None))

# ═══════════════════════════════════════════════════════════════════════════
# TestAdapterGetattrBan
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestAdapterGetattrBan:
    """Contract: getattr(config, ...) is banned in adapters — use typed access."""

    def test_adapters_no_getattr_on_config(self) -> None:
        """Given: all adapter source files.
        When: AST is scanned for getattr() calls touching config objects.
        Then: no getattr(cfg, ...) or getattr(config, ...) patterns found."""
        adapter_files = [
            "adapters/chunker_simple.py",
            "adapters/embedder_mock.py",
            "adapters/embedder_openai_compatible.py",
            "adapters/llm_mock.py",
            "adapters/llm_openai_compatible.py",
            "adapters/reranker_api.py",
            "adapters/reranker_null.py",
            "adapters/storage_sqlite.py",
            "adapters/vector_store_faiss.py",
            "adapters/vector_store_memory.py",
        ]
        for rel_path in adapter_files:
            path = _resolve_src_file(rel_path)
            source = path.read_text(encoding="utf-8")
            hits = _find_getattr_calls(source, str(path))
            config_hits = [
                (ln, code)
                for ln, code in hits
                if "cfg" in code or "config" in code.lower()
            ]
            assert not config_hits, f"getattr on config is drift risk in {rel_path}: {config_hits}"


# ═══════════════════════════════════════════════════════════════════════════
# TestPipelineDataNoMetadataBag (from drift #8)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
def test_pipelinedata_has_no_metadata_bag() -> None:
    """PipelineData must not have untyped metadata: dict[str, Any] field.

    DRIFT.md #8: replaced with explicit typed fields.
    """
    import dataclasses

    from ai_assistant.core.domain.pipeline import PipelineData

    fields = {f.name for f in dataclasses.fields(PipelineData)}
    assert "metadata" not in fields, (
        "PipelineData.metadata bag was re-introduced. "
        "Use explicit fields: embedder, vector_store, reranker, llm, "
        "pipeline_config, query_embedding, "
        "rerank_filtered_out, rerank_scores"
    )

# ═══════════════════════════════════════════════════════════════════════════
# TestAdapterRegistry (NEW)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestAdapterRegistry:
    """Contract: all adapters register via @register(port, name) decorator.

    Registry is populated eagerly on factory.py import.
    No if/elif branching in create_adapter().
    """

    def _get_registry(self) -> dict[str, dict[str, type]]:
        """Import and return the adapter registry."""
        from ai_assistant.adapters._registry import get_registry

        return get_registry()

    def test_all_ports_registered(self):
        """Given: factory.py loaded (eager imports triggered).
        When: registry is inspected.
        Then: all 6 expected ports have registered adapters."""
        registry = self._get_registry()
        expected_ports = {"llm", "embedder", "vector_store", "chunker", "storage", "reranker", "tokenizer"}
        missing = expected_ports - registry.keys()
        assert not missing, f"Missing ports in registry: {missing}"

    def test_llm_mock_registered(self):
        """Given: registry loaded.
        When: llm port is inspected.
        Then: MockLLM is registered under 'mock'."""
        from ai_assistant.adapters.llm_mock import MockLLM

        registry = self._get_registry()
        assert registry["llm"]["mock"] is MockLLM

    def test_llm_openai_compatible_registered(self):
        """Given: registry loaded.
        When: llm port is inspected.
        Then: OpenAICompatibleLLM is registered under 'openai_compatible'."""
        from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM

        registry = self._get_registry()
        assert registry["llm"]["openai_compatible"] is OpenAICompatibleLLM

    def test_embedder_mock_registered(self):
        """Given: registry loaded.
        When: embedder port is inspected.
        Then: MockEmbedder is registered under 'mock'."""
        from ai_assistant.adapters.embedder_mock import MockEmbedder

        registry = self._get_registry()
        assert registry["embedder"]["mock"] is MockEmbedder

    def test_embedder_openai_compatible_registered(self):
        """Given: registry loaded.
        When: embedder port is inspected.
        Then: OpenAICompatibleEmbedder is registered under 'openai_compatible'."""
        from ai_assistant.adapters.embedder_openai_compatible import OpenAICompatibleEmbedder

        registry = self._get_registry()
        assert registry["embedder"]["openai_compatible"] is OpenAICompatibleEmbedder

    def test_vector_store_memory_registered(self):
        """Given: registry loaded.
        When: vector_store port is inspected.
        Then: MemoryVectorStore is registered under 'memory'."""
        from ai_assistant.adapters.vector_store_memory import MemoryVectorStore

        registry = self._get_registry()
        assert registry["vector_store"]["memory"] is MemoryVectorStore

    def test_vector_store_faiss_registered(self):
        """Given: registry loaded.
        When: vector_store port is inspected.
        Then: FaissVectorStore is registered under 'faiss'."""
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        registry = self._get_registry()
        assert registry["vector_store"]["faiss"] is FaissVectorStore

    def test_chunker_simple_registered(self):
        """Given: registry loaded.
        When: chunker port is inspected.
        Then: SimpleChunker is registered under 'simple'."""
        from ai_assistant.adapters.chunker_simple import SimpleChunker

        registry = self._get_registry()
        assert registry["chunker"]["simple"] is SimpleChunker

    def test_storage_sqlite_registered(self):
        """Given: registry loaded.
        When: storage port is inspected.
        Then: SQLiteStorage is registered under 'sqlite'."""
        from ai_assistant.adapters.storage_sqlite import SQLiteStorage

        registry = self._get_registry()
        assert registry["storage"]["sqlite"] is SQLiteStorage

    def test_reranker_api_registered(self):
        """Given: registry loaded.
        When: reranker port is inspected.
        Then: APIReranker is registered under 'api'."""
        from ai_assistant.adapters.reranker_api import APIReranker

        registry = self._get_registry()
        assert registry["reranker"]["api"] is APIReranker

    def test_reranker_null_registered(self):
        """Given: registry loaded.
        When: reranker port is inspected.
        Then: NullReranker is registered under 'null'."""
        from ai_assistant.adapters.reranker_null import NullReranker

        registry = self._get_registry()
        assert registry["reranker"]["null"] is NullReranker

    def test_tokenizer_tiktoken_registered(self):
        """Given: registry loaded.
        When: tokenizer port is inspected.
        Then: TiktokenTokenizer is registered under 'tiktoken'."""
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer

        registry = self._get_registry()
        assert registry["tokenizer"]["tiktoken"] is TiktokenTokenizer

    def test_tokenizer_char_fallback_registered(self):
        """Given: registry loaded.
        When: tokenizer port is inspected.
        Then: CharFallbackTokenizer is registered under 'char_fallback'."""
        from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer

        registry = self._get_registry()
        assert registry["tokenizer"]["char_fallback"] is CharFallbackTokenizer
        """Given: registry loaded.
        When: reranker port is inspected.
        Then: NullReranker is registered under 'null'."""
        from ai_assistant.adapters.reranker_null import NullReranker

        registry = self._get_registry()
        assert registry["reranker"]["null"] is NullReranker


# ═══════════════════════════════════════════════════════════════════════════
# TestPortKwargsBan (runtime contract)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestPortKwargsBan:
    """Contract: port abstract methods must not use **kwargs."""

    def _get_port_methods(self) -> list[tuple[str, str, inspect.Signature]]:
        """Return (port_name, method_name, signature) for all port methods."""
        from ai_assistant.core.ports import (
            IChatStorage,
            IChunker,
            IEmbedder,
            ILLM,
            IReranker,
            IVectorStore,
        )

        ports = {
            "ILLM": ILLM,
            "IEmbedder": IEmbedder,
            "IVectorStore": IVectorStore,
            "IReranker": IReranker,
            "IChatStorage": IChatStorage,
            "IChunker": IChunker,
        }
        methods: list[tuple[str, str, inspect.Signature]] = []
        for name, cls in ports.items():
            for method_name, method in inspect.getmembers(
                cls, predicate=inspect.isfunction
            ):
                if getattr(method, "__isabstractmethod__", False):
                    sig = inspect.signature(method)
                    methods.append((name, method_name, sig))
        return methods

    def test_no_kwargs_in_port_methods(self):
        """Given: all abstract port methods.
        When: signatures are inspected.
        Then: no **kwargs parameters.
        """
        violations = []
        for port_name, method_name, sig in self._get_port_methods():
            for param in sig.parameters.values():
                if param.kind == inspect.Parameter.VAR_KEYWORD:
                    violations.append(f"{port_name}.{method_name} has **{param.name}")
        assert not violations, f"**kwargs banned in port methods: {violations}"


# ═══════════════════════════════════════════════════════════════════════════
# TestPortReturnTypes (runtime contract)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestPortReturnTypes:
    """Contract: port methods have consistent return type annotations."""

    def test_embedder_embed_returns_list_of_lists(self):
        """Given: IEmbedder.embed signature.
        When: return annotation inspected.
        Then: returns list[list[float]].
        """
        from ai_assistant.core.ports.embedder import IEmbedder

        sig = inspect.signature(IEmbedder.embed)
        assert sig.return_annotation == "list[list[float]]"

    def test_vector_store_search_returns_list_of_chunks(self):
        """Given: IVectorStore.search signature.
        When: return annotation inspected.
        Then: returns list[Chunk].
        """
        from ai_assistant.core.ports.vector_store import IVectorStore

        sig = inspect.signature(IVectorStore.search)
        assert "list[Chunk]" in str(sig.return_annotation)

    def test_llm_complete_returns_assistant_message(self):
        """Given: ILLM.complete signature.
        When: return annotation inspected.
        Then: returns AssistantMessage.
        """
        from ai_assistant.core.ports.llm import ILLM

        sig = inspect.signature(ILLM.complete)
        assert "AssistantMessage" in str(sig.return_annotation)


# ═══════════════════════════════════════════════════════════════════════════
# TestRAGStateTypedStatus
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestRAGStateTypedStatus:
    """Contract: RAGState._status must be typed as dict[str, ReindexStatusEntry].

    DRIFT.md #14: replaces dict[str, dict[str, object]] with explicit dataclass.
    """

    def test_status_field_type(self):
        """Given: RAGState dataclass fields.
        When: _status field type is inspected.
        Then: it references ReindexStatusEntry, not dict[str, object].
        """
        import dataclasses

        from ai_assistant.api.deps import RAGState
        from ai_assistant.core.domain.pipeline import ReindexStatusEntry

        fields = {f.name: f for f in dataclasses.fields(RAGState)}
        status_field = fields["_status"]
        assert "ReindexStatusEntry" in str(status_field.type), (
            f"RAGState._status must be typed with ReindexStatusEntry, got: {status_field.type}"
        )

    def test_reindex_status_entry_is_frozen_dataclass(self):
        """Given: ReindexStatusEntry domain model.
        When: inspected.
        Then: it is a frozen dataclass with slots.
        """
        import dataclasses

        from ai_assistant.core.domain.pipeline import ReindexStatusEntry

        assert dataclasses.is_dataclass(ReindexStatusEntry)
        assert ReindexStatusEntry.__dataclass_params__.frozen is True
        assert hasattr(ReindexStatusEntry, "__slots__")

    def test_reindex_status_entry_has_expected_fields(self):
        """Given: ReindexStatusEntry fields.
        When: inspected.
        Then: all expected fields are present.
        """
        import dataclasses

        from ai_assistant.core.domain.pipeline import ReindexStatusEntry

        fields = {f.name for f in dataclasses.fields(ReindexStatusEntry)}
        expected = {"status", "started_at", "finished_at", "result", "error"}
        assert fields == expected, f"Field mismatch: {fields ^ expected}"


def test_all_pipeline_steps_declare_requirements() -> None:
    """Every registered pipeline step must declare its requirements."""
    from ai_assistant.core.pipeline_steps import STEP_REGISTRY

    for name, func in STEP_REGISTRY.items():
        assert hasattr(func, "_step_requires"), (
            f"Step '{name}' missing _step_requires. "
            f"Update @step('{name}', requires={{...}})."
        )


# ═══════════════════════════════════════════════════════════════════════════
# TestStepRegistryRAGStepSync
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.contract
class TestStepRegistryRAGStepSync:
    """Contract: STEP_REGISTRY keys and RAGStep values must be bijective.

    Three sources of truth were identified:
    1. STEP_REGISTRY — runtime registry populated by @step decorator
    2. RAGStep enum — config-level validation for rag.steps
    3. @step requires — per-step dependency declarations (fixed by _step_requires)

    This contract guarantees that (1) and (2) never desynchronize.
    A mismatch means either:
    - A config-valid step has no runtime implementation (crash at first request)
    - A runtime step is not config-valid (cannot be used in YAML config)

    Both are bugs that must be caught at test time, not in production.
    """

    def test_all_ragstep_values_in_step_registry(self) -> None:
        """Given: all RAGStep enum values.
        When: checked against STEP_REGISTRY keys.
        Then: every RAGStep value is a registered step name.
        """
        from ai_assistant.core.config import RAGStep
        from ai_assistant.core.pipeline_steps import STEP_REGISTRY

        ragstep_values = {step.value for step in RAGStep}
        registry_keys = set(STEP_REGISTRY.keys())
        missing = ragstep_values - registry_keys
        assert not missing, (
            f"RAGStep values missing from STEP_REGISTRY: {missing}. "
            f"Add @step('{missing.pop()}', requires={{...}}) to pipeline_steps.py."
        )

    def test_all_step_registry_keys_in_ragstep(self) -> None:
        """Given: all STEP_REGISTRY keys.
        When: checked against RAGStep enum values.
        Then: every registered step name is a valid RAGStep value.
        """
        from ai_assistant.core.config import RAGStep
        from ai_assistant.core.pipeline_steps import STEP_REGISTRY

        ragstep_values = {step.value for step in RAGStep}
        registry_keys = set(STEP_REGISTRY.keys())
        extra = registry_keys - ragstep_values
        assert not extra, (
            f"STEP_REGISTRY keys not in RAGStep enum: {extra}. "
            f"Add a member to RAGStep in core/config.py."
        )
