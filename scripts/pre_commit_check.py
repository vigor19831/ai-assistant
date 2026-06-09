#!/usr/bin/env python3
"""Pre-commit checks — lightweight regex scanner."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

R, Y, G, RST = "\x1b[31m", "\x1b[33m", "\x1b[32m", "\x1b[0m"


# Production directories to scan (relative to src/ai_assistant/)
_PROD_DIRS = ("adapters", "features", "core", "api")


def _find_src_root() -> Path:
    """Find src/ai_assistant relative to script location."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    src = project_root / "src" / "ai_assistant"
    if src.exists():
        return src
    cwd_src = Path.cwd() / "src" / "ai_assistant"
    if cwd_src.exists():
        return cwd_src
    raise FileNotFoundError(f"src/ai_assistant not found in {project_root} or {Path.cwd()}")


def _clean_line(line: str) -> str:
    """Remove string literals and inline comments to reduce false positives."""
    if "#" in line:
        in_string = False
        string_char = None
        hash_pos = -1
        for i, ch in enumerate(line):
            if not in_string and ch in ('"', "'"):
                in_string = True
                string_char = ch
            elif in_string and ch == string_char and (i == 0 or line[i-1] != '\\'):
                in_string = False
                string_char = None
            elif not in_string and ch == '#':
                hash_pos = i
                break
        if hash_pos >= 0:
            line = line[:hash_pos]

    for pattern in (
        r'f"[^"\\]*(?:\\.[^"\\]*)*"',
        r"f'[^'\\\\]*(?:\\\\.[^'\\\\]*)*'",
        r'"[^"\\]*(?:\\.[^"\\]*)*"',
        r"'[^'\\]*(?:\\.[^'\\]*)*'",
    ):
        line = re.sub(pattern, '""', line)

    return line


def _scan_file(path: Path, pattern: re.Pattern, rule: str) -> list[tuple[Path, int, str]]:
    found: list[tuple[Path, int, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError) as e:
        print(f"{Y}{path}:READ_ERROR:{e}{RST}")
        return found

    for n, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("#"):
            continue
        if pattern.search(_clean_line(line)):
            found.append((path, n, rule))
    return found


def _get_docstring_ranges(source: str) -> list[tuple[int, int]]:
    """Return list of (start, end) line ranges for all docstrings."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                doc_node = node.body[0]
                start = getattr(doc_node, 'lineno', node.lineno)
                end = getattr(doc_node, 'end_lineno', start)
                ranges.append((start, end))
        elif isinstance(node, ast.Module):
            if node.body and isinstance(node.body[0], ast.Expr):
                doc_node = node.body[0]
                start = getattr(doc_node, 'lineno', 1)
                end = getattr(doc_node, 'end_lineno', start)
                ranges.append((start, end))
    return ranges


def _has_wraps_or_cache_decorator(lines: list[str], func_line: int) -> bool:
    """Check if function containing func_line has @functools.wraps or @lru_cache."""
    # Find the function definition line (def / async def)
    func_def_line = -1
    for i in range(func_line, -1, -1):
        line = lines[i].strip()
        if line.startswith("def ") or line.startswith("async def "):
            func_def_line = i
            break

    if func_def_line < 0:
        return False

    # Check decorators above this function
    for i in range(func_def_line - 1, -1, -1):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            if "functools.wraps" in line or "lru_cache" in line:
                return True
            continue
        # Stop at non-decorator, non-empty, non-comment line
        break
    return False


def main() -> int:
    src = _find_src_root()
    issues: list[tuple[Path, int, str]] = []

    # 1. hasattr / isinstance
    _allowed_type_tokens = {
        "str", "int", "float", "bool", "bytes", "type", "None", "NoneType",
        "list", "tuple", "dict", "set", "frozenset",
    }
    for subdir in _PROD_DIRS:
        sub = src / subdir
        if not sub.exists():
            continue
        for p in sub.rglob("*.py"):
            if "test" in p.name or "conftest" in p.name or p.name == "config.py":
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            lines = text.splitlines()
            doc_ranges = _get_docstring_ranges(text)
            for n, line in enumerate(lines, 1):
                if line.strip().startswith("#"):
                    continue
                if any(start <= n <= end for start, end in doc_ranges):
                    continue
                clean = _clean_line(line)
                if "hasattr(" in clean:
                    issues.append((p, n, "no-hasattr-in-production"))
                if "isinstance(" in clean:
                    m = re.search(r"isinstance\([^,]+,\s*(.+)\)", clean)
                    if m:
                        type_arg = m.group(1).strip()
                        if type_arg.startswith("(") and type_arg.endswith(")"):
                            type_arg = type_arg[1:-1]
                        type_tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", type_arg)
                        if all(t in _allowed_type_tokens for t in type_tokens):
                            continue
                    issues.append((p, n, "no-isinstance-in-production"))

    # 2. **kwargs
    for subdir in _PROD_DIRS:
        sub = src / subdir
        if not sub.exists():
            continue
        for p in sub.rglob("*.py"):
            if "test" in p.name or "conftest" in p.name:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            lines = text.splitlines()
            doc_ranges = _get_docstring_ranges(text)
            for n, line in enumerate(lines, 1):
                if line.strip().startswith("#"):
                    continue
                if any(start <= n <= end for start, end in doc_ranges):
                    continue
                clean = _clean_line(line)
                if "**kwargs" not in clean:
                    continue
                if "get_prompt" in clean or ".render(" in clean:
                    continue
                if _has_wraps_or_cache_decorator(lines, n):
                    continue
                if "return" in clean and "*args" in clean:
                    continue
                issues.append((p, n, "no-kwargs-in-production"))

    # 3. cross-feature imports
    feat_root = src / "features"
    if feat_root.exists():
        for feat in feat_root.iterdir():
            if not feat.is_dir():
                continue
            for p in feat.rglob("*.py"):
                if "test" in p.name or "conftest" in p.name:
                    continue
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except (OSError, UnicodeDecodeError):
                    continue
                for n, line in enumerate(text.splitlines(), 1):
                    if line.strip().startswith("#"):
                        continue
                    clean = _clean_line(line)
                    m = re.search(r"(?:from|import)\s+ai_assistant\.features\.([a-z_]+)", clean)
                    if m and m.group(1) != feat.name:
                        issues.append((p, n, "no-cross-feature-imports"))
                    m_rel = re.search(r"from\s+\.{2,}([a-z_]+)", clean)
                    if m_rel and m_rel.group(1) != feat.name:
                        issues.append((p, n, "no-cross-feature-imports"))

    # 4. PipelineData mutation
    _mut_pat = re.compile(
        r"\bdata\."
        r"(context\s*=|chunks\s*=|response\s*=|metadata\s*=|"
        r"metadata\s*\[.*\]\s*=|metadata\.update\s*\(|"
        r"metadata\.setdefault\s*\(|errors\.(append|extend)\s*\(|errors\s*\+=)"
    )
    for subdir in _PROD_DIRS:
        sub = src / subdir
        if not sub.exists():
            continue
        for p in sub.rglob("*.py"):
            if "test" in p.name or "conftest" in p.name:
                continue
            issues.extend(_scan_file(p, _mut_pat, "no-direct-pipeline-mutation"))

    # 5. print / pprint / logging.basicConfig
    _prod_pat = re.compile(r"\b(print|pprint)\s*\(|logging\.basicConfig\s*\(")
    for subdir in _PROD_DIRS:
        sub = src / subdir
        if not sub.exists():
            continue
        for p in sub.rglob("*.py"):
            if "test" in p.name or "conftest" in p.name:
                continue
            issues.extend(_scan_file(p, _prod_pat, "no-print-in-production"))

    for p, n, rule in issues:
        print(f"{R}{p}:{n}:{rule}{RST}")

    if issues:
        print(f"{R}BLOCKED{RST}")
        return 1

    print(f"{G}ALL OK{RST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
