"""Deep architecture audit — runtime checks that static analysis misses."""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path

SRC = Path("src")
sys.path.insert(0, str(SRC))


def check_port_contracts():
    """Verify all adapters implement their ports exactly."""
    print("\n=== PORT CONTRACTS ===")
    
    checks = [
        ("ai_assistant.adapters.chunker_simple", "SimpleChunker", "ai_assistant.core.ports.chunker", "IChunker"),
        ("ai_assistant.adapters.embedder_mock", "MockEmbedder", "ai_assistant.core.ports.embedder", "IEmbedder"),
        ("ai_assistant.adapters.embedder_openai_compatible", "OpenAICompatibleEmbedder", "ai_assistant.core.ports.embedder", "IEmbedder"),
        ("ai_assistant.adapters.llm_mock", "MockLLM", "ai_assistant.core.ports.llm", "ILLM"),
        ("ai_assistant.adapters.llm_openai_compatible", "OpenAICompatibleLLM", "ai_assistant.core.ports.llm", "ILLM"),
        ("ai_assistant.adapters.reranker_api", "APIReranker", "ai_assistant.core.ports.reranker", "IReranker"),
        ("ai_assistant.adapters.reranker_null", "NullReranker", "ai_assistant.core.ports.reranker", "IReranker"),
        ("ai_assistant.adapters.storage_sqlite", "SQLiteStorage", "ai_assistant.core.ports.storage", "IChatStorage"),
        ("ai_assistant.adapters.vector_store_faiss", "FaissVectorStore", "ai_assistant.core.ports.vector_store", "IVectorStore"),
        ("ai_assistant.adapters.vector_store_memory", "MemoryVectorStore", "ai_assistant.core.ports.vector_store", "IVectorStore"),
    ]
    
    all_pass = True
    for module_name, class_name, port_module, port_name in checks:
        try:
            mod = importlib.import_module(module_name)
            cls = getattr(mod, class_name)
            port_mod = importlib.import_module(port_module)
            port_cls = getattr(port_mod, port_name)
            
            if issubclass(cls, port_cls):
                print(f"  PASS {class_name} -> {port_name}")
            else:
                print(f"  FAIL {class_name} does not implement {port_name}")
                all_pass = False
                
            # Check for **kwargs in port methods
            for name, method in inspect.getmembers(port_cls, predicate=inspect.isfunction):
                sig = inspect.signature(method)
                has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                if has_kwargs and name != "__init__":
                    print(f"  WARN {port_name}.{name} has **kwargs")
                    
        except Exception as exc:
            print(f"  ERROR {class_name}: {exc}")
            all_pass = False
    
    return all_pass


def check_pipeline_steps_immutability():
    """Verify no pipeline step mutates PipelineData in-place."""
    print("\n=== PIPELINE STEPS IMMUTABILITY ===")
    
    import ai_assistant.core.pipeline_steps as steps
    import ai_assistant.core.domain.pipeline as pipeline
    
    # Get PipelineData methods
    pd_methods = {name for name in dir(pipeline.PipelineData) if name.startswith("with_") or name == "add_error"}
    print(f"  PipelineData mutation methods: {pd_methods}")
    
    # Check each step function
    step_names = ["embed_query", "retrieve", "rerank", "build_context", "generate", "hyde_query"]
    
    all_pass = True
    for name in step_names:
        func = getattr(steps, name, None)
        if not func:
            print(f"  SKIP {name} not found")
            continue
            
        source = inspect.getsource(func)
        
        # Check for forbidden patterns
        forbidden = [
            "data.metadata[", "data.metadata.update", "data.context =", 
            "data.chunks =", "data.errors.append", "data.errors +=",
            "data.query_embedding =", "data.response ="
        ]
        
        found = [p for p in forbidden if p in source]
        if found:
            print(f"  FAIL {name} mutates PipelineData: {found}")
            all_pass = False
        else:
            print(f"  PASS {name}")
    
    return all_pass


def check_no_cross_feature_imports():
    """Verify features/ modules don't import each other."""
    print("\n=== CROSS-FEATURE IMPORTS ===")
    
    features_dir = SRC / "ai_assistant" / "features"
    feature_modules = {d.name for d in features_dir.iterdir() if d.is_dir() and not d.name.startswith("_")}
    
    all_pass = True
    for feature in feature_modules:
        feature_path = features_dir / feature
        for py_file in feature_path.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            content = py_file.read_text()
            for other in feature_modules:
                if other == feature:
                    continue
                pattern = f"from ai_assistant.features.{other}"
                if pattern in content:
                    print(f"  FAIL {py_file}: imports {other}")
                    all_pass = False
    
    if all_pass:
        print("  PASS no cross-feature imports")
    return all_pass


def check_config_no_runtime_defaults():
    """Verify AppConfig doesn't use mutable defaults or runtime-dependent values."""
    print("\n=== CONFIG SANITY ===")
    
    import ai_assistant.core.config as cfg
    source = inspect.getsource(cfg.AppConfig)
    
    issues = []
    if "list()" in source or "dict()" in source:
        issues.append("mutable defaults")
    if "Path(" in source and "default" in source:
        issues.append("Path in default")
    
    if issues:
        print(f"  WARN {', '.join(issues)}")
        return False
    else:
        print("  PASS")
        return True


def check_error_taxonomy_consistency():
    """Verify all AdapterError uses have preceding logger.exception."""
    print("\n=== ERROR TAXONOMY (sample) ===")
    
    adapters_dir = SRC / "ai_assistant" / "adapters"
    
    all_pass = True
    for py_file in adapters_dir.rglob("*.py"):
        if py_file.name.startswith("__"):
            continue
        lines = py_file.read_text().splitlines()
        for i, line in enumerate(lines):
            if "raise AdapterError" in line:
                # Check preceding 5 lines for logger.exception
                preceding = "\n".join(lines[max(0, i-5):i])
                if "logger.exception" not in preceding and "_logger.exception" not in preceding:
                    print(f"  WARN {py_file}:{i+1} AdapterError without logger.exception")
                    all_pass = False
    
    if all_pass:
        print("  PASS all AdapterError have logger.exception")
    return all_pass


def main():
    print("=" * 60)
    print("DEEP ARCHITECTURE AUDIT")
    print("=" * 60)
    
    results = [
        ("Port Contracts", check_port_contracts()),
        ("Pipeline Immutability", check_pipeline_steps_immutability()),
        ("No Cross-Feature Imports", check_no_cross_feature_imports()),
        ("Config Sanity", check_config_no_runtime_defaults()),
        ("Error Taxonomy", check_error_taxonomy_consistency()),
    ]
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        color = "\033[92m" if passed else "\033[91m"
        print(f"  {color}{status}\033[0m {name}")
    
    all_pass = all(r[1] for r in results)
    print(f"\n{'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())