#!/usr/bin/env python3
"""
error_taxonomy_build.py — Auto-generate ERROR_TAXONOMY.md from source code.

Scans P0 critical files for:
- Explicit raise statements
- Exception handlers (except blocks)
- Docstring :raises: declarations
- # TECH DEBT / # FIXME comments

Output: dev/ERROR_TAXONOMY.md
"""

import ast
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("error_taxonomy")

# Files to scan (same as context_build.py CRITICAL_PATTERNS + adapters)
SCAN_PATTERNS = [
    "src/ai_assistant/core/**/*.py",
    "src/ai_assistant/api/**/*.py",
    "src/ai_assistant/pipeline/**/*.py",
    "src/ai_assistant/features/**/handlers.py",
    "src/ai_assistant/features/**/manager.py",
    "src/ai_assistant/adapters/*.py",
    "dev/tests/test_*.py",
]

EXCLUDED_DIRS = frozenset({".git", "__pycache__", ".venv", "venv", "data", "vendor"})

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


class ExceptionFinder(ast.NodeVisitor):
    """AST visitor to find raise statements, except handlers, and docstring :raises:."""

    def __init__(self, source: str, rel_path: str):
        self.source_lines = source.splitlines()
        self.rel_path = rel_path
        self.findings: list[tuple[str, str, str, int]] = []
        self.current_function = ""
        self.current_class = ""

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        old_func = self.current_function
        self.current_function = (
            f"{self.current_class}.{node.name}" if self.current_class else node.name
        )

        # Extract :raises: from docstring while we're here
        doc = ast.get_docstring(node)
        if doc:
            for exc_name, trigger, severity, line in self._extract_docstring_raises(
                doc, node.lineno
            ):
                self.findings.append((exc_name, trigger, severity, line))

        self.generic_visit(node)
        self.current_function = old_func

    def _extract_docstring_raises(
        self, doc: str, base_line: int
    ) -> list[tuple[str, str, str, int]]:
        """Extract :raises: declarations from a docstring."""
        findings: list[tuple[str, str, str, int]] = []
        raises_pattern = r":raises\s+([\w\.]+):\s*(.+?)(?=\n\s*:|\Z)"
        for match in re.finditer(raises_pattern, doc, re.DOTALL):
            exc_name = match.group(1)
            trigger = match.group(2).strip().replace("\n", " ")[:80]
            severity = "High" if "Error" in exc_name else "Medium"
            findings.append((exc_name, trigger, severity, base_line))
        return findings

    def visit_Raise(self, node: ast.Raise) -> None:
        if node.exc is None:
            # bare raise — re-raise, skip to avoid noise
            return

        exc_name = "Exception"
        trigger = "Unknown error"
        line = node.lineno

        if isinstance(node.exc, ast.Call):
            if isinstance(node.exc.func, ast.Name):
                exc_name = node.exc.func.id
            elif isinstance(node.exc.func, ast.Attribute):
                exc_name = node.exc.func.attr

            if node.exc.args:
                first_arg = node.exc.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(
                    first_arg.value, str
                ):
                    trigger = first_arg.value[:80]
                elif isinstance(first_arg, ast.JoinedStr):
                    trigger = self._format_joined_str(first_arg)[:80]
        elif isinstance(node.exc, ast.Name):
            # raise e — re-raise of a caught instance, skip (type unknown)
            return
        elif isinstance(node.exc, ast.Attribute):
            exc_name = node.exc.attr
            trigger = f"Raised {exc_name}"

        severity = self._infer_severity(exc_name, trigger)
        self.findings.append((exc_name, trigger, severity, line))

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        exc_name = "Exception"
        if node.type:
            if isinstance(node.type, ast.Name):
                exc_name = node.type.id
            elif isinstance(node.type, ast.Attribute):
                exc_name = node.type.attr
            elif isinstance(node.type, ast.Tuple):
                names = []
                for e in node.type.elts:
                    if isinstance(e, ast.Name):
                        names.append(e.id)
                    elif isinstance(e, ast.Attribute):
                        names.append(e.attr)
                exc_name = "/".join(names) if names else "Exception"

        # Heuristic: show first line of except body as trigger
        trigger = f"Handled in {self.current_function or 'module'}"
        if node.body:
            first_stmt = node.body[0]
            if isinstance(first_stmt, ast.Expr) and isinstance(first_stmt.value, ast.Constant):
                trigger = str(first_stmt.value.value)[:60]
            elif hasattr(first_stmt, "lineno"):
                line_idx = first_stmt.lineno - 1
                if 0 <= line_idx < len(self.source_lines):
                    trigger = self.source_lines[line_idx].strip()[:60]

        critical = {"SystemExit", "KeyboardInterrupt"}
        if exc_name in critical or any(
            part.strip() in critical for part in exc_name.split("/")
        ):
            severity = "Critical"
        else:
            severity = "Medium"

        self.findings.append((exc_name, trigger, severity, node.lineno))
        self.generic_visit(node)

    def _format_joined_str(self, node: ast.JoinedStr) -> str:
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("{...}")
            else:
                parts.append("...")
        return "".join(parts)

    def _infer_severity(self, exc_name: str, trigger: str) -> str:
        critical = {"SystemExit", "KeyboardInterrupt", "Critical"}
        high = {
            "ValueError",
            "RuntimeError",
            "AdapterError",
            "ConfigurationError",
            "VersionMismatchError",
            "HTTPException",
            "TimeoutError",
        }
        low = {"OSError", "PermissionError", "FileNotFoundError"}

        if any(c in exc_name for c in critical):
            return "Critical"
        if any(h in exc_name for h in high):
            return "High"
        if any(l in exc_name for l in low):
            return "Low"

        trigger_lower = trigger.lower()
        if any(w in trigger_lower for w in ["timeout", "fail", "abort", "critical"]):
            return "High"
        if any(w in trigger_lower for w in ["invalid", "missing", "not found"]):
            return "Medium"

        return "Medium"


def find_project_root() -> Path:
    """Script lives in dev/scripts/ — project root is two levels up."""
    return Path(__file__).resolve().parent.parent.parent


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def resolve_patterns(root: Path, patterns: list[str]) -> list[Path]:
    matched: set[Path] = set()
    for pat in patterns:
        for p in root.glob(pat):
            if p.is_file() and not _is_excluded(p):
                matched.add(p)
    return sorted(matched)


def extract_tech_debt_comments(
    source: str, rel_path: str = ""
) -> list[tuple[str, str, str, int]]:
    """Extract # TECH DEBT and # FIXME comments."""
    findings = []
    for i, line in enumerate(source.splitlines(), 1):
        if "# TECH DEBT:" in line or "# FIXME:" in line:
            trigger = line.split(":", 1)[1].strip() if ":" in line else "Technical debt"
            findings.append(("TechDebt", trigger, "Medium", i))
    return findings


def build_taxonomy(findings: list[tuple[str, str, str, str, int]]) -> str:
    """Build markdown table from findings."""
    lines = [
        "## 🧨 ERROR TAXONOMY",
        f"> Auto-generated from source code. Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        "> **Rule:** Check this table before adding try/except or changing error handling.",
        "",
        "| Component | Exception | Trigger | Severity | Line |",
        "|-----------|-----------|---------|----------|------|",
    ]

    # Keep highest severity per (component, exception, trigger)
    by_key: dict[tuple[str, str, str], tuple[str, str, str, str, int]] = {}
    for rel_path, exc_name, trigger, severity, line in findings:
        comp = rel_path.replace("src/ai_assistant/", "").replace("/", ".")
        if comp.endswith(".py"):
            comp = comp[:-3]

        key = (comp, exc_name, trigger)
        if key not in by_key or SEVERITY_ORDER.get(severity, 2) < SEVERITY_ORDER.get(
            by_key[key][3], 2
        ):
            by_key[key] = (comp, exc_name, trigger, severity, line)

    sorted_items = sorted(
        by_key.values(),
        key=lambda x: (SEVERITY_ORDER.get(x[3], 2), x[0], x[1]),
    )

    for comp, exc_name, trigger, severity, line in sorted_items:
        display_trigger = trigger[:60] + "..." if len(trigger) > 60 else trigger
        lines.append(
            f"| `{comp}` | `{exc_name}` | {display_trigger} | {severity} | {line} |"
        )

    lines.extend([
        "",
        "> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.",
        "",
    ])

    return "\n".join(lines)


def main() -> int:
    root = find_project_root()
    logger.info("Project root: %s", root)

    files = resolve_patterns(root, SCAN_PATTERNS)
    logger.info("Scanning %d files...", len(files))

    all_findings: list[tuple[str, str, str, str, int]] = []

    for fpath in files:
        rel = fpath.relative_to(root).as_posix()

        try:
            source = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Skip %s: %s", rel, exc)
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.warning("Syntax error in %s: %s", rel, exc)
            continue

        finder = ExceptionFinder(source, rel)
        finder.visit(tree)
        for exc, trigger, severity, line in finder.findings:
            all_findings.append((rel, exc, trigger, severity, line))

        for exc, trigger, severity, line in extract_tech_debt_comments(source, rel):
            all_findings.append((rel, exc, trigger, severity, line))

    # Deduplicate by (path, exception, trigger) — keep first occurrence
    seen: set[tuple[str, str, str]] = set()
    deduped: list[tuple[str, str, str, str, int]] = []
    for item in all_findings:
        key = (item[0], item[1], item[2])
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    logger.info("Found %d unique findings", len(deduped))

    md = build_taxonomy(deduped)
    out_path = root / "dev" / "ERROR_TAXONOMY.md"
    out_path.write_text(md, encoding="utf-8")

    logger.info("Written: %s", out_path.relative_to(root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
