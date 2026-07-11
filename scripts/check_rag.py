#!/usr/bin/env python3
"""Simplified RAG tester — indexes test.txt sources, queries RAG API, checks responses.

Usage:
    python check_rag.py --url http://localhost:8000
    python check_rag.py --url http://localhost:8000 --auto-index
    python check_rag.py --generate  # create sample test.txt

Environment:
    RAG_TEST_TIMEOUT    — request timeout (default: 30)
    RAG_TEST_API_KEY    — API key for auth (optional)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SourceDoc:
    namespace: str
    content: str


@dataclass
class TestCase:
    test_id: str
    query: str
    expected_contains: list[str]
    expected_not_contains: list[str]
    expect_sources: bool
    description: str


@dataclass
class TestResult:
    test_id: str
    passed: bool
    query: str
    response_text: str
    sources: list[str]
    latency_ms: float
    notes: list[str]


# ---------------------------------------------------------------------------
# Fuzzy matcher
# ---------------------------------------------------------------------------

class FuzzyMatcher:
    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    def match(self, text: str, expected: str) -> bool:
        text_lower = text.lower()
        expected_lower = expected.lower()
        if expected_lower in text_lower:
            return True
        ratio = SequenceMatcher(None, text_lower, expected_lower).ratio()
        return ratio >= self.threshold

    def check_any(self, text: str, expected_list: list[str]) -> tuple[bool, str]:
        if not expected_list:
            return True, ""
        for exp in expected_list:
            if self.match(text, exp):
                return True, ""
        return False, f"None matched (threshold={self.threshold}): {expected_list}"

    def check_none(self, text: str, not_expected_list: list[str]) -> tuple[bool, str]:
        for ne in not_expected_list:
            if self.match(text, ne):
                return False, f"Forbidden matched (threshold={self.threshold}): {ne!r}"
        return True, ""


# ---------------------------------------------------------------------------
# Test file parser
# ---------------------------------------------------------------------------

def parse_test_file(path: Path) -> tuple[list[SourceDoc], list[TestCase]]:
    if not path.exists():
        print(f"[FAIL] File not found: {path}")
        print(f"Run: python {Path(__file__).name} --generate")
        sys.exit(1)

    sources: list[SourceDoc] = []
    tests: list[TestCase] = []
    section: str | None = None

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line == "[SOURCES]":
                section = "sources"
                continue
            if line == "[TESTS]":
                section = "tests"
                continue
            if not section:
                continue

            parts = [p.strip() for p in line.split("|")]
            if section == "sources" and len(parts) >= 2:
                sources.append(SourceDoc(namespace=parts[0], content=parts[1]))
            elif section == "tests" and len(parts) >= 6:
                test_id = parts[0]
                query = parts[1]
                exp_contains = [s.strip() for s in parts[2].split(",") if s.strip()] if parts[2] else []
                exp_not = [s.strip() for s in parts[3].split(",") if s.strip()] if parts[3] else []
                expect_src = parts[4].lower() in ("true", "yes", "1") if parts[4] else False
                desc = parts[5] if len(parts) > 5 else ""
                tests.append(TestCase(
                    test_id=test_id, query=query,
                    expected_contains=exp_contains, expected_not_contains=exp_not,
                    expect_sources=expect_src, description=desc,
                ))

    return sources, tests


# ---------------------------------------------------------------------------
# Document bootstrap
# ---------------------------------------------------------------------------

def bootstrap_documents(sources: list[SourceDoc]) -> dict[str, Path]:
    docs_root = PROJECT_ROOT / "data" / "documents"
    docs_root.mkdir(parents=True, exist_ok=True)
    created: dict[str, Path] = {}

    for doc in sources:
        ns_dir = docs_root / doc.namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        file_path = ns_dir / f"{doc.namespace}.txt"
        # Append to file if namespace has multiple sources
        mode = "a" if file_path.exists() else "w"
        with open(file_path, mode, encoding="utf-8") as f:
            f.write(doc.content + "\n\n")
        created[doc.namespace] = file_path

    print(f"[OK] Created {len(created)} document files in {docs_root}")
    for ns, p in created.items():
        print(f"     {ns}: {p}")
    return created


def auto_index() -> bool:
    indexer = SCRIPT_DIR / "index_documents.py"
    if not indexer.exists():
        indexer = PROJECT_ROOT / "scripts" / "index_documents.py"
    if not indexer.exists():
        print("[WARN] index_documents.py not found. Cannot auto-index.")
        print("       Searched:")
        print(f"         {SCRIPT_DIR / 'index_documents.py'}")
        print(f"         {PROJECT_ROOT / 'scripts' / 'index_documents.py'}")
        return False

    print(f"[INFO] Running indexer: {indexer}")
    try:
        result = subprocess.run(
            [sys.executable, str(indexer)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            print("[OK] Indexing completed successfully")
            if result.stdout:
                print(result.stdout[-500:])
            return True
        else:
            print(f"[FAIL] Indexer exited with code {result.returncode}")
            print("STDOUT:", result.stdout[-1000:])
            print("STDERR:", result.stderr[-1000:])
            return False
    except Exception as exc:
        print(f"[FAIL] Failed to run indexer: {exc}")
        return False


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class RAGTester:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        test_file: str = "test.txt",
        timeout: float = 30.0,
        fuzzy_threshold: float = 0.6,
        api_key: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.test_file = Path(test_file)
        if not self.test_file.is_absolute():
            for base in (Path.cwd(), SCRIPT_DIR, PROJECT_ROOT):
                candidate = (base / test_file).resolve()
                if candidate.exists():
                    self.test_file = candidate
                    break
            else:
                self.test_file = (Path.cwd() / test_file).resolve()

        self.timeout = timeout
        self.fuzzy = FuzzyMatcher(threshold=fuzzy_threshold)
        self.results: list[TestResult] = []

        headers: dict[str, str] = {}
        if api_key:
            if " " in api_key or api_key.lower().startswith(("bearer ", "basic ", "api-key ")):
                headers["Authorization"] = api_key
            else:
                headers["Authorization"] = f"Bearer {api_key}"

        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers if headers else None,
        )

    async def detect_endpoint(self) -> str:
        candidates = [
            f"{self.base_url}/v1/chat/completions",
            f"{self.base_url}/api/v1/chat/completions",
            f"{self.base_url}/chat",
            f"{self.base_url}/api/chat",
            f"{self.base_url}/v1/chat",
            f"{self.base_url}/api/v1/chat",
        ]
        print(f"[INFO] Probing {len(candidates)} endpoints...")
        for url in candidates:
            try:
                r = await self.client.post(url, json={"message": "hello"}, timeout=5.0)
                if r.status_code == 200:
                    print(f"[OK]   Endpoint: {url}")
                    return url
                elif r.status_code in (401, 403):
                    print(f"  AUTH {url} (needs auth)")
                elif r.status_code == 422:
                    print(f"  VALID {url} (validation error — endpoint exists)")
                    # Still usable, just wrong payload
                    return url
            except Exception:
                pass
        print(f"[WARN] No endpoint responded. Fallback: {candidates[0]}")
        return candidates[0]

    async def send_query(self, endpoint: str, query: str) -> dict[str, Any]:
        payloads = [
            {"message": query},
            {"messages": [{"role": "user", "content": query}]},
            {"messages": [{"role": "user", "content": query}], "stream": False},
        ]

        for payload in payloads:
            try:
                r = await self.client.post(endpoint, json=payload, timeout=self.timeout)
                if r.status_code != 200:
                    continue

                text = ""
                sources: list[str] = []

                content_type = r.headers.get("content-type", "").lower()
                if "event-stream" in content_type:
                    text, sources = self._parse_sse(r.text)
                else:
                    try:
                        data = r.json()
                    except Exception:
                        text = r.text
                        data = {}

                    text = (
                        data.get("text")
                        or data.get("response")
                        or data.get("content")
                        or data.get("message")
                        or data.get("answer")
                        or data.get("reply")
                    )
                    if not text and "choices" in data:
                        choices = data.get("choices", [])
                        if choices:
                            choice = choices[0]
                            if isinstance(choice, dict):
                                msg = choice.get("message", {})
                                delta = choice.get("delta", {})
                                text = msg.get("content") or delta.get("content") or str(choice)
                    if not text:
                        text = str(data)

                    raw_sources = (
                        data.get("sources")
                        or data.get("context_sources")
                        or data.get("retrieved_chunks")
                        or data.get("chunks")
                        or data.get("references")
                        or data.get("citations")
                        or []
                    )
                    for s in raw_sources:
                        if isinstance(s, dict):
                            src_text = s.get("text") or s.get("content") or s.get("source") or s.get("name") or str(s)
                            sources.append(src_text)
                        elif isinstance(s, str):
                            sources.append(s)

                if not sources and text:
                    sources = self._extract_sources_from_text(text)

                return {"text": text, "sources": sources, "status_code": 200}
            except Exception:
                continue

        return {"text": "[ERROR] API did not respond", "sources": [], "status_code": 0}

    def _parse_sse(self, raw: str) -> tuple[str, list[str]]:
        text_parts: list[str] = []
        sources: list[str] = []
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data_str)
                    if "choices" in chunk:
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                text_parts.append(content)
                    if "sources" in chunk:
                        sources.extend(chunk["sources"])
                    if "text" in chunk:
                        text_parts.append(chunk["text"])
                except json.JSONDecodeError:
                    text_parts.append(data_str)
        return "".join(text_parts), sources

    def _extract_sources_from_text(self, text: str) -> list[str]:
        sources: list[str] = []
        lines = text.splitlines()
        in_sources = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("sources") or (line.startswith("[") and "]" in line):
                in_sources = True
            if in_sources and line.startswith("[") and "]" in line:
                idx = line.find("]")
                source_text = line[idx + 1:].strip()
                if source_text:
                    sources.append(source_text)
        return sources

    def _check_case(self, case: TestCase, text: str, sources: list[str]) -> tuple[bool, list[str]]:
        notes: list[str] = []
        passed = True

        if case.expected_contains:
            ok, detail = self.fuzzy.check_any(text, case.expected_contains)
            if not ok:
                passed = False
                notes.append(detail)

        for ne in case.expected_not_contains:
            ok, detail = self.fuzzy.check_none(text, [ne])
            if not ok:
                passed = False
                notes.append(detail)

        has_sources = len(sources) > 0
        if has_sources != case.expect_sources:
            passed = False
            notes.append(f"Sources: expected={case.expect_sources}, got={has_sources}")

        return passed, notes

    async def run(self, auto_index: bool = False):
        sources, tests = parse_test_file(self.test_file)
        print(f"[INFO] Loaded {len(sources)} sources, {len(tests)} tests from {self.test_file}")

        if auto_index and sources:
            print("\n[AUTO-INDEX] Creating documents from test.txt [SOURCES]...")
            bootstrap_documents(sources)
            ok = auto_index()
            if not ok:
                print("[WARN] Auto-index failed. Tests may not work.")

        endpoint = await self.detect_endpoint()
        print(f"\nAPI endpoint: {endpoint}")
        print(f"Fuzzy threshold: {self.fuzzy.threshold}")
        print("=" * 70)

        for case in tests:
            print(f"\n--- {case.test_id} ---")
            print(f"Query:  {case.query}")
            print(f"Desc:   {case.description}")

            start = time.perf_counter()
            resp = await self.send_query(endpoint, case.query)
            latency = (time.perf_counter() - start) * 1000

            text = resp.get("text", "")
            sources_found = resp.get("sources", [])

            print(f"Response: {text[:140]}{'...' if len(text) > 140 else ''}")
            print(f"Sources:  {len(sources_found)} | Latency: {latency:.0f} ms")
            if sources_found:
                for i, s in enumerate(sources_found[:3], 1):
                    print(f"  [{i}] {s[:100]}")

            passed, notes = self._check_case(case, text, sources_found)
            status = "PASS" if passed else "FAIL"
            icon = "OK" if passed else "XX"
            print(f"Result:   [{icon}] {status}")
            if notes:
                for n in notes:
                    print(f"  ! {n}")

            self.results.append(TestResult(
                test_id=case.test_id, passed=passed, query=case.query,
                response_text=text, sources=[str(s) for s in sources_found],
                latency_ms=latency, notes=notes,
            ))

        await self.client.aclose()
        self._print_report()

    def _print_report(self):
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        avg_lat = sum(r.latency_ms for r in self.results) / max(total, 1) if total else 0

        print("\n" + "=" * 70)
        print(f"FINAL REPORT: {passed}/{total} passed | {failed}/{total} failed | Avg: {avg_lat:.0f} ms")
        print("=" * 70)

        if failed:
            print("\nFAILED TESTS:")
            for r in self.results:
                if not r.passed:
                    print(f"\n  {r.test_id}: {r.query}")
                    print(f"    Response: {r.response_text}")
                    print(f"    Sources:  {r.sources}")
                    for n in r.notes:
                        print(f"    * {n}")
            sys.exit(1)

    def generate_test_file(self, path: Path) -> None:
        path.write_text(test_txt_content, encoding="utf-8")
        print(f"[OK] Created {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Simplified RAG tester")
    parser.add_argument("--url", default="http://localhost:8000", help="Base API URL")
    parser.add_argument("--test-file", default="test.txt", help="Test cases file")
    parser.add_argument("--auto-index", action="store_true", help="Auto-create documents and run indexer")
    parser.add_argument("--generate", action="store_true", help="Generate sample test.txt")
    parser.add_argument("--timeout", type=float, default=float(os.getenv("RAG_TEST_TIMEOUT", "30")))
    parser.add_argument("--fuzzy-threshold", type=float, default=0.6)
    parser.add_argument("--api-key", default=os.getenv("RAG_TEST_API_KEY", ""))
    args = parser.parse_args()

    tester = RAGTester(
        base_url=args.url,
        test_file=args.test_file,
        timeout=args.timeout,
        fuzzy_threshold=args.fuzzy_threshold,
        api_key=args.api_key,
    )

    if args.generate:
        tester.generate_test_file(Path(args.test_file))
        return 0

    try:
        asyncio.run(tester.run(auto_index=args.auto_index))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
