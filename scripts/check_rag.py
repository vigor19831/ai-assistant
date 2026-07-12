#!/usr/bin/env python3
"""Ideal RAG benchmark — immutable specification.

This script is the single source of truth for correct RAG behavior.
Do NOT edit it to make tests pass. Fix the RAG pipeline instead.

Run → read failures → improve retriever / re-ranker / prompt / LLM → rerun.
When the score is 13/13, the RAG is production-grade.

Usage:
    python scripts/check_rag.py              # full run (index + test)
    python scripts/check_rag.py --skip-index # test only, reuse existing indices
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    sys.exit("ERROR: httpx is required. Run: pip install httpx")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


# =============================================================================
# Logging to data/ (git-ignored)
# =============================================================================

class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> None:
        for s in self.streams:
            s.write(data)
            s.flush()

    def flush(self) -> None:
        for s in self.streams:
            s.flush()


def _setup_logging() -> Path:
    log_dir = PROJECT_ROOT / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "check_rag_last.log"
    log_file = open(log_path, "w", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.stdout, log_file)
    sys.stderr = _Tee(sys.stderr, log_file)
    return log_path


# =============================================================================
# Immutable test corpus and expectations
# =============================================================================

@dataclass(frozen=True)
class SourceDoc:
    namespace: str
    content: str


@dataclass(frozen=True)
class TestCase:
    test_id: str
    query: str
    namespace: str
    # ALL of these strings must appear in the answer
    answer_must_contain: tuple[str, ...] = ()
    # At least ONE of these strings must appear (for variable phrasing like "don't know")
    answer_must_contain_any: tuple[str, ...] = ()
    # NONE of these strings may appear
    answer_must_not_contain: tuple[str, ...] = ()
    # Ideal RAG returns sources only when retrieval is actually relevant
    expect_sources: bool = True
    # If sources exist, their combined text must contain ALL of these
    sources_must_contain: tuple[str, ...] = ()
    # NONE of these may appear in sources (noise resistance)
    sources_must_not_contain: tuple[str, ...] = ()
    description: str = ""


# --- Corpus ------------------------------------------------------------------

TEST_SOURCES: list[SourceDoc] = [
    # Personal namespace
    SourceDoc(
        "personal",
        "My favorite color is blue. I chose it in childhood because it reminds me of the sea and the sky. It is my only favorite color.",
    ),
    SourceDoc(
        "personal",
        "I have been working as a programmer since 2020. My primary language is Python. Before that I worked as a system administrator.",
    ),
    # Tech namespace
    SourceDoc(
        "tech",
        "Python is a high-level general-purpose programming language. It was created by Guido van Rossum and first released in 1991. Python supports multiple programming paradigms.",
    ),
    # Noise document in personal — RAG must ignore it
    SourceDoc(
        "personal",
        "I love eating apples. Apples are red and crunchy. My favorite fruit is definitely the apple because it is healthy and sweet.",
    ),
    # Contradictory / stale doc in personal — for future conflict tests (not used now)
    # SourceDoc("personal", "My favorite color is red. I changed it last year."),
]


# --- Expectations ------------------------------------------------------------

TEST_CASES: list[TestCase] = [
    # 1. Perfect retrieval — answer must come from context, not general knowledge.
    TestCase(
        test_id="retrieval-1",
        query="What is my favorite color?",
        namespace="personal",
        answer_must_contain=("blue",),
        answer_must_not_contain=("red", "green", "yellow", "i don't have a favorite"),
        expect_sources=True,
        sources_must_contain=("blue", "childhood", "sea"),
        sources_must_not_contain=("apple", "fruit"),  # noise resistance
        description="Direct retrieval. Answer must cite personal context. Must not pull from noise doc.",
    ),

    # 2. Missing data — must admit ignorance, not hallucinate common guesses.
    #    Requires: relevance threshold that drops all chunks → no sources → 'I don't know'.
    TestCase(
        test_id="missing-1",
        query="What is my favorite food?",
        namespace="personal",
        answer_must_contain_any=(
            "don't know",
            "not sure",
            "no information",
            "not mentioned",
            "not specified",
            "don't have",
            "no data",
            "cannot answer",
        ),
        answer_must_not_contain=(
            "pizza", "sushi", "burger", "pasta", "salad", "steak", "chicken", "food is", "apple",
        ),
        expect_sources=False,
        description="No food data in index. Must say 'don't know'. Must not guess or leak noise.",
    ),

    # 3. Factual retrieval — different namespace.
    TestCase(
        test_id="retrieval-2",
        query="What is Python?",
        namespace="tech",
        answer_must_contain=("language", "programming", "guido"),
        expect_sources=True,
        sources_must_contain=("python", "language", "guido"),
        description="Factual retrieval from tech namespace.",
    ),

    # 4. Named entity — exact fact.
    TestCase(
        test_id="retrieval-3",
        query="Who created Python?",
        namespace="tech",
        answer_must_contain=("guido", "van rossum"),
        expect_sources=True,
        sources_must_contain=("guido", "rossum"),
        description="Named entity retrieval.",
    ),

    # 5. Date — no hallucination of wrong years.
    TestCase(
        test_id="retrieval-4",
        query="When was Python released?",
        namespace="tech",
        answer_must_contain=("1991",),
        answer_must_not_contain=("1980", "1985", "1990", "2000", "1992"),
        expect_sources=True,
        sources_must_contain=("1991",),
        description="Exact date. Must not hallucinate.",
    ),

    # 6. Trap question — false premise must be ignored or corrected.
    TestCase(
        test_id="trap-1",
        query="What is my favorite color and why did I choose it in 2015?",
        namespace="personal",
        answer_must_contain=("blue",),
        answer_must_not_contain=("2015", "chose in 2015", "year 2015", "in 2015"),
        expect_sources=True,
        sources_must_contain=("blue",),
        description="False premise (2015). Must answer from context and ignore trap.",
    ),

    # 7. Option trap — must not pick from provided options if context doesn't specify.
    TestCase(
        test_id="trap-2",
        query="Which shade of blue: azure, indigo or ultramarin?",
        namespace="personal",
        answer_must_contain=("blue",),
        answer_must_not_contain=("azure", "indigo", "ultramarine", "shade"),
        expect_sources=True,
        sources_must_contain=("blue",),
        description="Options are a trap. Context says only 'blue'. Must not select from list.",
    ),

    # 8. Short query — minimal input must still retrieve.
    TestCase(
        test_id="edge-1",
        query="Blue?",
        namespace="personal",
        answer_must_contain=("blue",),
        expect_sources=True,
        sources_must_contain=("blue",),
        description="One-word query. Must retrieve.",
    ),

    # 9. Complex open question — gather facts from multiple chunks, no hallucination.
    TestCase(
        test_id="edge-2",
        query="What do you know about me?",
        namespace="personal",
        answer_must_contain=("programmer", "python", "blue"),
        answer_must_not_contain=("lawyer", "doctor", "java", "red", "green", "apple", "fruit"),
        expect_sources=True,
        sources_must_contain=("programmer", "python", "blue"),
        sources_must_not_contain=("apple",),
        description="Open question. Must synthesize facts from multiple chunks. No noise leak.",
    ),

    # 10. Cross-namespace isolation — query to wrong namespace must not leak data.
    TestCase(
        test_id="isolation-1",
        query="What is Python?",
        namespace="personal",  # Python doc lives in 'tech', not here
        answer_must_contain_any=(
            "don't know",
            "not sure",
            "no information",
            "not mentioned",
            "not specified",
            "cannot answer",
        ),
        answer_must_not_contain=(
            "programming language",
            "guido",
            "1991",
            "high-level",
            "paradigm",
        ),
        expect_sources=False,
        description="Cross-namespace isolation. personal namespace has no Python doc. Must not leak from tech.",
    ),

    # 11. Semantic / synonym retrieval — query uses synonyms, not exact words.
    TestCase(
        test_id="semantic-1",
        query="What hue do I prefer?",
        namespace="personal",
        answer_must_contain=("blue",),
        expect_sources=True,
        sources_must_contain=("blue",),
        description="Synonym retrieval ('hue' vs 'color'). Tests embedding quality.",
    ),

    # 12. Multi-hop reasoning — requires connecting facts from two documents.
    TestCase(
        test_id="multihop-1",
        query="What programming language does the person whose favorite color is blue use?",
        namespace="personal",
        answer_must_contain=("python",),
        answer_must_not_contain=("java", "c++", "javascript", "ruby"),
        expect_sources=True,
        sources_must_contain=("blue", "python"),
        description="Multi-hop: favorite color (doc 1) → programming language (doc 2). Tests multi-chunk reasoning.",
    ),

    # 13. Noise resistance — explicit check that noise doc is excluded.
    TestCase(
        test_id="noise-1",
        query="Tell me about my diet.",
        namespace="personal",
        answer_must_contain_any=(
            "don't know",
            "not sure",
            "no information",
            "not mentioned",
            "cannot answer",
        ),
        answer_must_not_contain=("apple", "fruit", "healthy", "sweet", "crunchy"),
        expect_sources=False,
        description="Noise doc exists but is irrelevant. Must not surface noise as fact.",
    ),
]


# =============================================================================
# API helpers
# =============================================================================

def _source_text(src: Any) -> str:
    if isinstance(src, str):
        return src
    if isinstance(src, dict):
        return src.get("content") or src.get("text") or str(src)
    return str(src)


async def index_all(url: str, api_key: str, sources: list[SourceDoc]) -> bool:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    by_ns: dict[str, list[dict[str, Any]]] = {}
    for i, doc in enumerate(sources):
        by_ns.setdefault(doc.namespace, []).append({
            "id": f"test-{i}",
            "content": doc.content,
            "metadata": {"source": "check_rag_benchmark"},
        })

    async with httpx.AsyncClient(headers=headers) as client:
        for ns, docs in by_ns.items():
            print(f"[CLEAR] namespace '{ns}'")
            await client.post(
                f"{url.rstrip('/')}/api/v1/rag/delete",
                json={"document_ids": ["check_rag_benchmark"], "namespace": ns},
            )
            print(f"[INDEX] {len(docs)} docs → namespace '{ns}'")
            r = await client.post(
                f"{url.rstrip('/')}/api/v1/rag/index",
                json={"documents": docs, "namespace": ns},
            )
            if r.status_code != 200:
                print(f"[INDEX] FAIL HTTP {r.status_code}: {r.text[:200]}")
                return False
            data = r.json()
            print(f"[INDEX] OK  {data.get('chunk_count', 0)} chunks")

    return True


async def query_rag(
    client: httpx.AsyncClient,
    url: str,
    api_key: str,
    query: str,
    namespace: str,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    r = await client.post(
        f"{url.rstrip('/')}/api/v1/rag/query",
        json={"query": query, "namespace": namespace, "top_k": 5},
        headers=headers,
    )
    r.raise_for_status()
    return r.json()


# =============================================================================
# Test runner
# =============================================================================

async def run_tests(url: str, api_key: str, timeout: float) -> None:
    passed = 0
    total = len(TEST_CASES)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for case in TEST_CASES:
            print(f"\n{'─' * 60}")
            print(f"[{case.test_id}] {case.description}")
            print(f"    Query : {case.query}")
            print(f"    NS    : {case.namespace}")

            t0 = time.perf_counter()
            try:
                data = await query_rag(client, url, api_key, case.query, case.namespace)
            except Exception as exc:
                print(f"    FAIL  API error: {exc}")
                continue

            latency = (time.perf_counter() - t0) * 1000

            answer: str = data.get("answer") or ""
            sources: list[Any] = data.get("sources") or []
            has_sources = bool(sources)

            print(f"    Answer: {answer[:120]}...")
            print(f"    Src   : {len(sources)} chunks")

            errors: list[str] = []

            # --- answer: ALL required phrases must be present ---
            for kw in case.answer_must_contain:
                if kw.lower() not in answer.lower():
                    errors.append(f"missing required '{kw}'")

            # --- answer: at least ONE of these must be present ---
            if case.answer_must_contain_any:
                if not any(kw.lower() in answer.lower() for kw in case.answer_must_contain_any):
                    errors.append(f"missing one of {case.answer_must_contain_any}")

            # --- answer: forbidden phrases must be absent ---
            for forbidden in case.answer_must_not_contain:
                if forbidden.lower() in answer.lower():
                    errors.append(f"forbidden '{forbidden}'")

            # --- sources presence ---
            if has_sources != case.expect_sources:
                errors.append(f"sources={has_sources}, expected={case.expect_sources}")

            # --- sources content ---
            if case.sources_must_contain and has_sources:
                src_text = " ".join(_source_text(s).lower() for s in sources)
                for kw in case.sources_must_contain:
                    if kw.lower() not in src_text:
                        errors.append(f"sources missing '{kw}'")

            # --- sources noise check ---
            if case.sources_must_not_contain and has_sources:
                src_text = " ".join(_source_text(s).lower() for s in sources)
                for forbidden in case.sources_must_not_contain:
                    if forbidden.lower() in src_text:
                        errors.append(f"sources contain noise '{forbidden}'")

            # --- report ---
            status = "PASS" if not errors else "FAIL"
            print(f"    Result: {status} ({latency:.0f}ms)")
            for err in errors:
                print(f"    ! {err}")

            if not errors:
                passed += 1

    print(f"\n{'=' * 60}")
    print(f"FINAL: {passed}/{total} passed")
    if passed != total:
        print("\nSome tests failed. Do NOT edit this script.")
        print("Improve the RAG pipeline instead:")
        print("  • relevance threshold / re-ranker  (missing-1, noise-1, isolation-1)")
        print("  • embedding quality (semantic-1)")
        print("  • prompt grounding rules            (trap-1, trap-2)")
        print("  • namespace isolation               (isolation-1)")
        print("  • multi-chunk reasoning             (multihop-1, edge-2)")
        sys.exit(1)
    else:
        print("\nAll tests passed. RAG meets the benchmark.")


def main() -> None:
    log_path = _setup_logging()
    print(f"[INFO] Log: {log_path}")

    parser = argparse.ArgumentParser(description="Ideal RAG benchmark")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="local")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--skip-index", action="store_true", help="Skip indexing")
    args = parser.parse_args()

    if not args.skip_index:
        ok = asyncio.run(index_all(args.url, args.api_key, TEST_SOURCES))
        if not ok:
            print("[FATAL] Indexing failed")
            sys.exit(1)

    asyncio.run(run_tests(args.url, args.api_key, args.timeout))


if __name__ == "__main__":
    main()
