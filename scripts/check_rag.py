#!/usr/bin/env python3
"""Interactive RAG tester with auto-indexing, SSE parsing, and auth.

Usage:
    python check_rag.py                           # interactive menu
    python check_rag.py --mode simple --url http://localhost:8000 --api-key sk-local-api-key
    python check_rag.py --mode complex --url http://localhost:8000 --api-key sk-local-api-key --auto-index
    python check_rag.py --probe --url http://localhost:8000 --api-key sk-local-api-key
    python check_rag.py --generate

Environment:
    RAG_TEST_TIMEOUT    — request timeout (default: 30)
    RAG_TEST_RETRIES    — max retries (default: 3)
    RAG_TEST_THRESHOLD  — fuzzy threshold 0..1 (default: 0.6)
    RAG_TEST_API_KEY    — API key for auth
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
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


def _resolve_test_file_path(test_file: str | Path) -> Path:
    path = Path(test_file)
    if path.is_absolute():
        return path
    for base in (Path.cwd(), SCRIPT_DIR, PROJECT_ROOT):
        candidate = (base / path).resolve()
        if candidate.exists():
            return candidate
    return (Path.cwd() / path).resolve()


def _find_indexer() -> Path | None:
    for base in (SCRIPT_DIR, PROJECT_ROOT, PROJECT_ROOT / "scripts"):
        candidate = base / "index_documents.py"
        if candidate.exists():
            return candidate.resolve()
    return None


@dataclass
class SourceDoc:
    namespace: str
    content: str


@dataclass
class TestCase:
    conversation_id: str
    turn: int
    query: str
    expected_contains: list[str]
    expected_not_contains: list[str]
    expect_sources: bool
    description: str


@dataclass
class TestResult:
    name: str
    passed: bool
    query: str
    response_text: str
    sources: list[str]
    latency_ms: float
    notes: list[str]
    conversation_id: str
    turn: int


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


class RAGTester:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        test_file: str = "test.txt",
        timeout: float = 30.0,
        retries: int = 3,
        fuzzy_threshold: float = 0.6,
        endpoint: str | None = None,
        verbose: bool = False,
        api_key: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.test_file = _resolve_test_file_path(test_file)
        self.results: list[TestResult] = []
        self.conversation_histories: dict[str, list[dict[str, str]]] = {}
        self._endpoint: str | None = endpoint
        self._endpoint_forced = endpoint is not None
        self.timeout = timeout
        self.retries = retries
        self.fuzzy = FuzzyMatcher(threshold=fuzzy_threshold)
        self.verbose = verbose
        self._sources: list[SourceDoc] = []
        self._tests: list[TestCase] = []

        self.extra_headers: dict[str, str] = {}
        if api_key:
            if " " in api_key or api_key.lower().startswith(("bearer ", "basic ", "api-key ")):
                self.extra_headers["Authorization"] = api_key
            else:
                self.extra_headers["Authorization"] = f"Bearer {api_key}"

        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=self.extra_headers if self.extra_headers else None,
        )

    def parse_test_file(self) -> tuple[list[SourceDoc], list[TestCase]]:
        if not self.test_file.exists():
            print(f"[FAIL] File not found: {self.test_file}")
            print("Searched:")
            for base in (Path.cwd(), SCRIPT_DIR, PROJECT_ROOT):
                print(f"  {base / 'test.txt'}")
            print("\nRun: python check_rag.py --generate")
            sys.exit(1)

        sources: list[SourceDoc] = []
        tests: list[TestCase] = []
        section: str | None = None

        with open(self.test_file, "r", encoding="utf-8") as f:
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
                    conv_id = parts[0]
                    turn = int(parts[1])
                    query = parts[2]
                    exp_contains = [s.strip() for s in parts[3].split(",") if s.strip()] if parts[3] else []
                    exp_not = [s.strip() for s in parts[4].split(",") if s.strip()] if parts[4] else []
                    expect_src = parts[5].lower() in ("true", "yes", "1") if parts[5] else False
                    desc = parts[6] if len(parts) > 6 else ""
                    tests.append(
                        TestCase(
                            conversation_id=conv_id, turn=turn, query=query,
                            expected_contains=exp_contains, expected_not_contains=exp_not,
                            expect_sources=expect_src, description=desc,
                        )
                    )

        self._sources = sources
        self._tests = tests
        return sources, tests

    def bootstrap_documents(self) -> dict[str, Path]:
        created: dict[str, Path] = {}
        docs_root = PROJECT_ROOT / "data" / "documents"
        docs_root.mkdir(parents=True, exist_ok=True)

        for doc in self._sources:
            ns_dir = docs_root / doc.namespace
            ns_dir.mkdir(parents=True, exist_ok=True)
            file_path = ns_dir / f"{doc.namespace}.txt"
            file_path.write_text(doc.content, encoding="utf-8")
            created[doc.namespace] = file_path

        print(f"[OK] Created {len(created)} document files in {docs_root}")
        for ns, p in created.items():
            print(f"     {ns}: {p}")
        return created

    def auto_index(self) -> bool:
        indexer = _find_indexer()
        if not indexer:
            print("[WARN] index_documents.py not found. Cannot auto-index.")
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

    async def detect_endpoint(self) -> str:
        if self._endpoint and self._endpoint_forced:
            return self._endpoint
        if self._endpoint:
            return self._endpoint

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
                test_payload = {"message": "hello"}
                r = await self.client.post(url, json=test_payload, timeout=5.0)
                status = r.status_code
                if self.verbose:
                    print(f"  POST {url} -> {status}")
                if status == 200:
                    print(f"[OK]   Endpoint: {url} (POST status={status})")
                    self._endpoint = url
                    return url
                elif status in (401, 403):
                    print(f"  AUTH {url} (status={status}) — needs auth")
                    if not self._endpoint:
                        self._endpoint = url
                elif status == 422:
                    print(f"  VALID {url} (status={status}) — validation error")
                    if not self._endpoint:
                        self._endpoint = url
                else:
                    print(f"  SKIP {url} (POST status={status})")
            except Exception as exc:
                if self.verbose:
                    print(f"  FAIL {url} ({type(exc).__name__}: {exc})")
        if self._endpoint:
            print(f"[WARN] No 200 response, candidate: {self._endpoint}")
            return self._endpoint
        print(f"[WARN] No endpoint responded. Fallback: {candidates[0]}")
        self._endpoint = candidates[0]
        return self._endpoint

    async def _try_payloads(self, endpoint: str, payload: dict) -> dict | None:
        try:
            if self.verbose:
                print(f"  >> POST {endpoint}")
                print(f"  >> Headers: {self.extra_headers}")
            r = await self.client.post(endpoint, json=payload, timeout=self.timeout)
            if self.verbose:
                print(f"  << Status: {r.status_code}")
                print(f"  << Content-Type: {r.headers.get('content-type', 'unknown')}")
                print(f"  << Body: {r.text[:600]}")
            if r.status_code != 200:
                return None

            content_type = r.headers.get("content-type", "").lower()
            text = ""
            sources: list[Any] = []

            if "event-stream" in content_type or "text/event-stream" in content_type:
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

                sources = (
                    data.get("sources")
                    or data.get("context_sources")
                    or data.get("retrieved_chunks")
                    or data.get("chunks")
                    or data.get("references")
                    or data.get("citations")
                    or []
                )

            # If no sources in JSON fields, try to parse from text
            if not sources and text:
                sources = self._extract_sources_from_text(text)

            normalized_sources: list[str] = []
            for s in sources:
                if isinstance(s, dict):
                    src_text = s.get("text") or s.get("content") or s.get("source") or s.get("name") or str(s)
                    normalized_sources.append(src_text)
                elif isinstance(s, str):
                    normalized_sources.append(s)

            return {"text": text, "sources": normalized_sources}
        except Exception as exc:
            if self.verbose:
                print(f"  << Exception: {type(exc).__name__}: {exc}")
            return None

    def _extract_sources_from_text(self, text: str) -> list[str]:
        """Parse inline sources like [1] filename from response text."""
        sources: list[str] = []
        lines = text.splitlines()
        in_sources_section = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Detect sources section: "Sources:" or lines starting with [1], [2] etc
            if line.lower().startswith("sources") or (line.startswith("[") and "]" in line):
                in_sources_section = True
            if in_sources_section:
                # Extract [N] content
                if line.startswith("[") and "]" in line:
                    idx = line.find("]")
                    if idx > 0:
                        source_text = line[idx + 1:].strip()
                        if source_text:
                            sources.append(source_text)
        return sources

    def _parse_sse(self, raw: str) -> tuple[str, list[Any]]:
        text_parts: list[str] = []
        sources: list[Any] = []
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

    async def send_message(self, conversation_id: str, message: str) -> dict[str, Any]:
        endpoint = await self.detect_endpoint()
        history = self.conversation_histories.get(conversation_id, [])

        payloads = [
            {"conversation_id": conversation_id, "message": message, "history": history},
            {"conversation_id": conversation_id, "messages": history + [{"role": "user", "content": message}]},
            {"conversation_id": conversation_id, "messages": history + [{"role": "user", "content": message}], "stream": False},
        ]

        last_error_detail = "unknown"
        for attempt in range(1, self.retries + 1):
            start = time.perf_counter()
            result = None
            last_payload_idx = -1
            for idx, p in enumerate(payloads):
                result = await self._try_payloads(endpoint, p)
                last_payload_idx = idx
                if result is not None:
                    break
            latency = (time.perf_counter() - start) * 1000

            if result is not None:
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": result["text"]})
                self.conversation_histories[conversation_id] = history
                result["latency_ms"] = latency
                result["status_code"] = 200
                return result

            try:
                probe = await self.client.post(endpoint, json=payloads[last_payload_idx], timeout=self.timeout)
                last_error_detail = f"status={probe.status_code}, body={probe.text[:200]}"
            except Exception as exc:
                last_error_detail = f"{type(exc).__name__}: {exc}"

            if attempt < self.retries:
                wait = min(2 ** attempt, 10)
                print(f"    [Retry {attempt}/{self.retries}] {last_error_detail}")
                print(f"    Waiting {wait}s...")
                await asyncio.sleep(wait)

        return {
            "text": f"[ERROR] API did not respond at {endpoint} after {self.retries} attempts. Last: {last_error_detail}",
            "sources": [],
            "latency_ms": 0,
            "status_code": 0,
            "error": last_error_detail,
        }

    def _check_case(self, case: TestCase, text: str, sources: list) -> tuple[bool, list[str]]:
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

    async def run_simple(self):
        print("\n" + "=" * 70)
        print("MODE 1: SIMPLE RAG DIAGNOSTIC")
        print("=" * 70)

        tests = [
            (
                "[t] What is my favorite color?",
                ["blue"],
                ["red", "green"],
                True,
                "RAG with [t] prefix — must find 'blue' in index and return sources",
            ),
            (
                "[t] What is the capital of France?",
                ["Paris"],
                [],
                False,
                "Fallback — no France data in index, sources must be absent",
            ),
            (
                "What is your favorite color?",
                ["model", "do not have", "AI"],
                ["blue"],
                False,
                "Without [t] prefix — must not use RAG, must not know my favorite color",
            ),
        ]

        for i, (query, expected, not_expected, expect_src, desc) in enumerate(tests, 1):
            print(f"\n--- Test {i}/3 ---")
            print(f"Description: {desc}")
            print(f"Query:       {query}")

            resp = await self.send_message(f"simple-{i}", query)
            text = resp.get("text", "")
            sources = resp.get("sources", [])
            latency = resp.get("latency_ms", 0)

            print(f"Response:    {text[:180]}{'...' if len(text) > 180 else ''}")
            print(f"Sources:     {len(sources)} items | Latency: {latency:.0f} ms")
            if sources:
                for idx, s in enumerate(sources[:3], 1):
                    print(f"  [{idx}] {s[:100]}")

            pseudo = TestCase(
                conversation_id=f"simple-{i}", turn=1, query=query,
                expected_contains=expected, expected_not_contains=not_expected,
                expect_sources=expect_src, description=desc,
            )
            passed, notes = self._check_case(pseudo, text, sources)

            status = "PASS" if passed else "FAIL"
            icon = "OK" if passed else "XX"
            print(f"Result:      [{icon}] {status}")
            if notes:
                for n in notes:
                    print(f"  ! {n}")

            self.results.append(
                TestResult(
                    name=f"simple-{i}", passed=passed, query=query,
                    response_text=text, sources=[str(s) for s in sources],
                    latency_ms=latency, notes=notes,
                    conversation_id=f"simple-{i}", turn=1,
                )
            )

    async def run_complex(self):
        print("\n" + "=" * 70)
        print("MODE 2: MULTI-STAGE CHECK")
        print("=" * 70)

        if not self._tests:
            self.parse_test_file()

        if not self._tests:
            print("No test cases in test.txt")
            return

        conversations: dict[str, list[TestCase]] = {}
        for c in self._tests:
            conversations.setdefault(c.conversation_id, []).append(c)
        for turns in conversations.values():
            turns.sort(key=lambda x: x.turn)

        total = sum(len(v) for v in conversations.values())
        print(f"Loaded {total} test cases in {len(conversations)} dialogs\n")

        for conv_id, turns in conversations.items():
            print(f"\n{'─' * 70}")
            print(f"Dialog: {conv_id}")
            print(f"{'─' * 70}")

            for case in turns:
                print(f"\n  Turn {case.turn}: {case.description}")
                print(f"  Query:  {case.query}")

                resp = await self.send_message(conv_id, case.query)
                text = resp.get("text", "")
                sources = resp.get("sources", [])
                latency = resp.get("latency_ms", 0)

                print(f"  Response: {text[:140]}{'...' if len(text) > 140 else ''}")
                print(f"  Sources:  {len(sources)} | Latency: {latency:.0f} ms")
                if sources:
                    for idx, s in enumerate(sources[:3], 1):
                        print(f"    [{idx}] {s[:100]}")

                passed, notes = self._check_case(case, text, sources)

                status = "PASS" if passed else "FAIL"
                icon = "OK" if passed else "XX"
                print(f"  Result:   [{icon}] {status}")
                if notes:
                    for n in notes:
                        print(f"    ! {n}")

                self.results.append(
                    TestResult(
                        name=f"{conv_id}-{case.turn}", passed=passed, query=case.query,
                        response_text=text, sources=[str(s) for s in sources],
                        latency_ms=latency, notes=notes,
                        conversation_id=conv_id, turn=case.turn,
                    )
                )

    def print_final_report(self):
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        avg_lat = sum(r.latency_ms for r in self.results) / max(total, 1) if total else 0

        print("\n" + "=" * 70)
        print("FINAL REPORT FOR AI ANALYSIS")
        print("=" * 70)
        print(f"\nPassed: {passed}/{total} | Failed: {failed}/{total} | Avg latency: {avg_lat:.0f} ms")

        if failed:
            print(f"\n{'=' * 70}")
            print("FAILED TESTS (full data for analysis):")
            print(f"{'=' * 70}")
            for r in self.results:
                if not r.passed:
                    print(f"\n--- {r.name} (dialog: {r.conversation_id}) ---")
                    print(f"Query:    {r.query}")
                    print(f"Response: {r.response_text}")
                    print(f"Sources:  {r.sources}")
                    print(f"Issues:")
                    for n in r.notes:
                        print(f"  * {n}")

        print(f"\n{'=' * 70}")
        print("COPY ALL OUTPUT ABOVE INTO AI CHAT FOR ANALYSIS")
        print(f"{'=' * 70}")

        if failed:
            sys.exit(1)

    def export_json(self, path: Path) -> None:
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        avg_lat = sum(r.latency_ms for r in self.results) / max(total, 1) if total else 0

        data = {
            "summary": {
                "passed": passed, "failed": failed, "total": total,
                "avg_latency_ms": round(avg_lat, 2),
                "success_rate": round(passed / total, 4) if total else 0,
            },
            "config": {
                "base_url": self.base_url, "timeout": self.timeout,
                "retries": self.retries, "fuzzy_threshold": self.fuzzy.threshold,
            },
            "tests": [asdict(r) for r in self.results],
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"\n[OK] JSON report saved: {path}")

    async def probe_api(self) -> dict[str, Any]:
        print("\n" + "=" * 70)
        print("API PROBE MODE")
        print("=" * 70)
        print(f"Base URL: {self.base_url}")
        if self.extra_headers:
            print(f"Headers: {self.extra_headers}")

        candidates = [
            f"{self.base_url}/v1/chat/completions",
            f"{self.base_url}/api/v1/chat/completions",
            f"{self.base_url}/chat",
            f"{self.base_url}/api/chat",
            f"{self.base_url}/v1/chat",
            f"{self.base_url}/api/v1/chat",
        ]

        probe_results = []
        for url in candidates:
            try:
                r = await self.client.get(url, timeout=5.0)
                ok = r.status_code == 200
                probe_results.append({"url": url, "method": "GET", "status": r.status_code, "ok": ok})
                label = "OK" if ok else "FAIL"
                print(f"  GET  {url} -> {r.status_code} {label}")
            except Exception as exc:
                probe_results.append({"url": url, "method": "GET", "status": 0, "ok": False, "error": str(exc)})
                print(f"  GET  {url} -> FAIL ({type(exc).__name__}: {exc})")

        test_payloads = [
            {"message": "hello"},
            {"messages": [{"role": "user", "content": "hello"}]},
        ]
        for url in candidates:
            for p in test_payloads:
                try:
                    r = await self.client.post(url, json=p, timeout=5.0)
                    ok = r.status_code == 200
                    label = "OK" if ok else "FAIL"
                    print(f"  POST {url} -> {r.status_code} {label}")
                    if r.status_code == 200:
                        print(f"       Response: {r.text[:150]}")
                    elif r.status_code in (401, 403):
                        print(f"       NOTE: Endpoint exists but requires authentication")
                    elif r.status_code == 422:
                        print(f"       NOTE: Endpoint exists but validation failed")
                    probe_results.append({"url": url, "method": "POST", "status": r.status_code, "ok": ok})
                    if ok:
                        break
                except Exception as exc:
                    print(f"  POST {url} -> FAIL ({type(exc).__name__}: {exc})")
                    probe_results.append({"url": url, "method": "POST", "status": 0, "ok": False, "error": str(exc)})

        working = [r for r in probe_results if r.get("ok")]
        auth_required = [r for r in probe_results if r.get("status") in (401, 403)]
        validation_err = [r for r in probe_results if r.get("status") == 422]

        print(f"\nWorking endpoints (200 OK): {len(working)}")
        if working:
            for w in working:
                print(f"  - {w['method']} {w['url']} (status={w['status']})")

        if auth_required:
            print(f"\nEndpoints requiring auth: {len(auth_required)}")
            for a in auth_required:
                print(f"  - {a['method']} {a['url']} (status={a['status']})")
            print("\nAdd auth:")
            print('  --api-key sk-local-api-key')
            print('  --api-key "Bearer YOUR_TOKEN"')

        if validation_err and not working:
            print(f"\nEndpoints with validation errors: {len(validation_err)}")
            for v in validation_err:
                print(f"  - {v['method']} {v['url']} (status={v['status']})")
            print("  The endpoint exists but expects different JSON format.")

        if not working and not auth_required and not validation_err:
            print("\n  NONE — API unreachable. Check:")
            print("    1. Is server running?")
            print("    2. Is port correct?    try --url http://localhost:8080")
            print("    3. Does API need auth? add --api-key")

        await self.client.aclose()
        return {"working": working, "auth_required": auth_required, "validation_err": validation_err, "all": probe_results}

    async def run(self, mode: str, auto_index: bool = False):
        self.parse_test_file()

        if auto_index and self._sources:
            print("\n[AUTO-INDEX] Creating documents from test.txt [SOURCES]...")
            self.bootstrap_documents()
            ok = self.auto_index()
            if not ok:
                print("[WARN] Auto-index failed. Continuing tests, but RAG may not work.")

        endpoint = await self.detect_endpoint()
        print(f"API endpoint: {endpoint}")

        if mode in ("simple", "both"):
            await self.run_simple()
        if mode in ("complex", "both"):
            await self.run_complex()

        self.print_final_report()
        await self.client.aclose()

    @staticmethod
    def generate_test_file(path: Path) -> None:
        path = _resolve_test_file_path(path)
        content = """# RAG Test Configuration
# Format [SOURCES]: namespace | content
# Format [TESTS]: conversation_id | turn | query | expected_contains | expected_not_contains | expect_sources | description

[SOURCES]
personal | My favorite color is blue. I chose it in childhood because it reminds me of the sea and the sky. It is my only favorite color.
personal | I have been working as a programmer since 2020. My primary language is Python. Before that I worked as a system administrator.
tech | Python is a high-level general-purpose programming language. It was created by Guido van Rossum and first released in 1991. Python supports multiple programming paradigms.

[TESTS]
simple-1 | 1 | [t] What is my favorite color? | blue,favorite | red,green,yellow | true | Direct question from indexed data. Must return blue and sources.
simple-2 | 1 | [t] What is the capital of France? | Paris,capital | | false | Fallback to general knowledge. No France data in index, sources must be absent.
simple-3 | 1 | What is your favorite color? | model,do not have,AI,assistant | blue,my | false | Question without [t] prefix — must not use RAG. Must not know my favorite color.

complex-c1 | 1 | [t] What is my favorite color? | blue | | true | Start of dialog. Basic RAG query.
complex-c1 | 2 | [t] Why exactly it? | blue,sea,sky,childhood | | true | Pronoun "it" must be condensed to "blue color". Sources must be present.
complex-c1 | 3 | [t] Tell me more about this | blue,sea,sky | | true | Reference "this" via dialog history. Must understand context.

complex-c2 | 1 | [t] What is my favorite color? | blue | | true |
complex-c2 | 2 | [t] When did I say that? | not specified,unknown,not mentioned,do not remember | 2015,2020,yesterday,date,year | true | No date in index for choosing color. System MUST NOT hallucinate a date.
complex-c2 | 3 | [t] What else do I love? | only,not specified,nothing else | red,green,yellow,sport,music | true | Index says blue is the only favorite color. Must not invent other hobbies.
complex-c2 | 4 | [t] Tell me more | blue,sea,sky | | true | Dialog continuation, context preservation check.
complex-c2 | 5 | [t] Why exactly this shade? | blue,sea,sky,childhood | azure,indigo,ultramarine,light blue,dark blue | true | "This shade" = blue. Must not specify to a concrete shade since index only says "blue".

complex-c3 | 1 | [t] What is my favorite color and why did I choose it in 2015? | blue | 2015,in 2015,chose in,year | true | Direct hallucination date check. Must be blue, but MUST NOT contain 2015.
complex-c3 | 2 | [t] Which shade of blue: azure, indigo or ultramarin? | not specified,not mentioned,unknown,only blue | azure,indigo,ultramarine,shade | true | No shade detail in index. MUST NOT pick one of the options.

complex-c4 | 1 | [t] What is my favorite color? | blue | | true | Query with [t] prefix — uses RAG.
complex-c4 | 2 | What is my favorite color? | blue | | false | Query WITHOUT prefix, but history has context. Must use history, not RAG. No sources expected.

complex-c5 | 1 | [t] What is Python? | language,programming,high-level,Guido | | true | Query from tech namespace. Must return facts from index.
complex-c5 | 2 | [t] Who created it? | Guido,van Rossum,Rossum | | true | Follow-up "it" = Python. Named entity condensation check.
complex-c5 | 3 | [t] When was it released? | 1991 | 1980,1985,1990,2000 | true | Concrete date from index. Must not hallucinate.

edge-1 | 1 | [t] What is my favorite color? Tell me in detail. | blue,sea,sky,childhood | | true | Complex query with elaboration. Must return full context.
edge-2 | 1 | [t] Blue? | blue | | true | Very short query / pronoun check. Must work.
edge-3 | 1 | [t] What do you know about me? | programmer,Python,blue,sea,childhood | | true | Open question. Must gather facts from index without hallucinations.
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Created {path}")
        print(f"Location: {path.resolve()}")
        print("Edit it, then run: python check_rag.py --mode complex --auto-index")


def interactive_select_mode() -> str:
    print("=" * 70)
    print("RAG INTERACTIVE TESTER")
    print("=" * 70)
    print("\nSelect mode (type number and press Enter):")
    print("  [1] — Simple diagnostic (3 quick tests)")
    print("  [2] — Multi-stage check (from test.txt)")
    print("  [3] — Both modes sequentially")
    print("\nOr run with argument: --mode simple|complex|both")

    while True:
        try:
            choice = input("\nYour choice (1/2/3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            sys.exit(130)

        if choice == "1":
            return "simple"
        elif choice == "2":
            return "complex"
        elif choice == "3":
            return "both"
        else:
            print("Invalid input. Enter 1, 2 or 3.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive RAG tester")
    parser.add_argument("--mode", choices=["simple", "complex", "both"], help="Test mode")
    parser.add_argument("--url", default="http://localhost:8000", help="Base API URL")
    parser.add_argument("--test-file", default="test.txt", help="Test cases file")
    parser.add_argument("--generate", action="store_true", help="Generate sample test.txt")
    parser.add_argument("--json", dest="json_path", help="Export report to JSON file")
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("RAG_TEST_TIMEOUT", "30")),
        help="Request timeout (default: 30 or env RAG_TEST_TIMEOUT)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=int(os.getenv("RAG_TEST_RETRIES", "3")),
        help="Max retries (default: 3 or env RAG_TEST_RETRIES)",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=float(os.getenv("RAG_TEST_THRESHOLD", "0.6")),
        help="Fuzzy threshold 0..1 (default: 0.6 or env RAG_TEST_THRESHOLD)",
    )
    parser.add_argument("--endpoint", help="Force API endpoint (e.g. /api/v1/chat)")
    parser.add_argument("--probe", action="store_true", help="Only probe API endpoints")
    parser.add_argument("--auto-index", action="store_true", help="Auto-create documents and run indexer")
    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=os.getenv("RAG_TEST_API_KEY", ""),
        help="API key for Authorization header. Prefixes with 'Bearer ' automatically if no scheme given.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show full HTTP bodies")
    parser.add_argument(
        "--txt-report",
        dest="txt_report",
        help="Save human-readable report to file (default: data/rag_test_report.txt)",
        nargs="?",
        const="data/rag_test_report.txt",
        default="",
    )
    args = parser.parse_args()

    tester = RAGTester(
        base_url=args.url,
        test_file=args.test_file,
        timeout=args.timeout,
        retries=args.retries,
        fuzzy_threshold=args.fuzzy_threshold,
        endpoint=args.endpoint,
        verbose=args.verbose,
        api_key=args.api_key,
    )

    if args.generate:
        tester.generate_test_file(Path(args.test_file))
        return 0

    if args.probe:
        asyncio.run(tester.probe_api())
        return 0

    mode = args.mode
    if not mode:
        mode = interactive_select_mode()

    try:
        asyncio.run(tester.run(mode, auto_index=args.auto_index))
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        return 130

    if args.json_path:
        tester.export_json(Path(args.json_path))

    if args.txt_report:
        report_path = Path(args.txt_report)
        if not report_path.is_absolute():
            report_path = PROJECT_ROOT / report_path
        tester.export_txt(report_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
