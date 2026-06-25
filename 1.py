#!/usr/bin/env python3
"""context_extractor.py — собирает минимальный контекст для AI-ассистента.
Использование: python context_extractor.py > context_for_ai.md
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _extract_methods(node: ast.ClassDef) -> list[dict]:
    methods = []
    for item in node.body:
        if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)):
            name = item.name
            raises = []
            for stmt in ast.walk(item):
                if isinstance(stmt, ast.Raise):
                    exc = "Exception"
                    if isinstance(stmt.exc, ast.Name):
                        exc = stmt.exc.id
                    elif isinstance(stmt.exc, ast.Call) and isinstance(stmt.exc.func, ast.Name):
                        exc = f"{stmt.exc.id}(...)"
                    raises.append(exc)
            methods.append({"name": name, "raises": raises})
    return methods


def _process_file(path: Path) -> dict | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return None

    classes = []
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "bases": [base.id if isinstance(base, ast.Name) else str(base) for base in node.bases],
                "methods": _extract_methods(node),
            })
        elif isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.col_offset == 0:
            functions.append(node.name)

    return {"path": str(path), "classes": classes, "top_functions": functions}


def _process_tests(path: Path) -> dict | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return None

    test_classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            methods = []
            for item in node.body:
                if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)) and item.name.startswith("test_"):
                    doc = ast.get_docstring(item)
                    methods.append({"name": item.name, "doc": (doc or "").strip()[:120]})
            test_classes.append({"name": node.name, "methods": methods})
    return {"path": str(path), "test_classes": test_classes}


def main() -> None:
    src = Path("src/ai_assistant/adapters")
    tests = Path("tests")

    print("# AI Context Summary (auto-generated)\n")

    # --- Adapters: fault-injection surface ---
    print("## Adapter failure surface\n")
    for py in sorted(src.glob("*.py")):
        data = _process_file(py)
        if not data:
            continue
        print(f"### `{py.name}`\n")
        for cls in data["classes"]:
            print(f"- **Class:** `{cls['name']}` (bases: {cls['bases']})")
            for m in cls["methods"]:
                if m["raises"]:
                    print(f"  - `{m['name']}()` → may raise: {', '.join(m['raises'])}")
                else:
                    print(f"  - `{m['name']}()`")
        print()

    # --- Tests: existing structure ---
    print("## Existing test structure\n")
    for test_file in [tests / "test_api.py", tests / "test_e2e.py"]:
        if not test_file.exists():
            continue
        data = _process_tests(test_file)
        if not data:
            continue
        print(f"### `{test_file.name}`\n")
        for cls in data["test_classes"]:
            print(f"- **{cls['name']}**")
            for m in cls["methods"]:
                print(f"  - `{m['name']}()` — {m['doc']}")
        print()


if __name__ == "__main__":
    main()