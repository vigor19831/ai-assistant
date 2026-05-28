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
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

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

EXCLUDED_DIRS = {".git", "__pycache__", ".venv", "venv", "data", "vendor"}


class ExceptionFinder(ast.NodeVisitor):
    """AST visitor to find raise statements and except handlers."""

    def __init__(self, source: str, rel_path: str):
        self.source = source
        self.rel_path = rel_path
        self.findings: list[tuple[str, str, str, int]] = []
        self.current_function = ""
        self.current_class = ""

    def visit_ClassDef(self, node: ast.ClassDef):
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_function(node)

    def _visit_function(self, node):
        old_func = self.current_function
        self.current_function = (
            f"{self.current_class}.{node.name}" if self.current_class else node.name
        )
        self.generic_visit(node)
        self.current_function = old_func

    def visit_Raise(self, node: ast.Raise):
        exc_name = "Exception"
        trigger = "Unknown error"
        line = node.lineno

        if node.exc is None:
            return  # bare raise

        if isinstance(node.exc, ast.Call):
            # raise ValueError("message")
            if isinstance(node.exc.func, ast.Name):
                exc_name = node.exc.func.id
            elif isinstance(node.exc.func, ast.Attribute):
                exc_name = node.exc.func.attr

            # Extract message from first argument
            if node.exc.args:
                first_arg = node.exc.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(
                    first_arg.value, str
                ):
                    trigger = first_arg.value[:80]
                elif isinstance(first_arg, ast.JoinedStr):
                    trigger = "f-string message"
        elif isinstance(node.exc, ast.Name):
            exc_name = node.exc.id

        severity = self._infer_severity(exc_name, trigger)
        self.findings.append((exc_name, trigger, severity, line))

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        exc_name = "Exception"
        if node.type:
            if isinstance(node.type, ast.Name):
                exc_name = node.type.id
            elif isinstance(node.type, ast.Tuple):
                names = [e.id for e in node.type.elts if isinstance(e, ast.Name)]
                exc_name = "/".join(names) if names else "Exception"

        trigger = f"Handled in {self.current_function or 'module'}"
        severity = "Medium"  # Handled exceptions are less severe
        self.findings.append((exc_name, trigger, severity, node.lineno))
        self.generic_visit(node)

    def _infer_severity(self, exc_name: str, trigger: str) -> str:
        """Infer severity from exception type and message."""
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

        # Message-based heuristics
        if any(w in trigger.lower() for w in ["timeout", "fail", "abort", "critical"]):
            return "High"
        if any(w in trigger.lower() for w in ["invalid", "missing", "not found"]):
            return "Medium"

        return "Medium"


def find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "README.md").exists() and (parent / "pyproject.toml").exists():
            return parent
    return current.parent.parent


def resolve_patterns(root: Path, patterns: list[str]) -> list[Path]:
    matched: set[Path] = set()
    for pat in patterns:
        pat_os = pat.replace("/", os.sep)
        if "**" in pat:
            for p in root.glob(pat_os):
                if p.is_file():
                    matched.add(p)
        else:
            p = root / pat_os
            if p.exists() and p.is_file():
                matched.add(p)
            elif p.exists() and p.is_dir():
                for child in p.rglob("*"):
                    if child.is_file():
                        matched.add(child)
    return sorted(matched)


def extract_docstring_raises(
    source: str, rel_path: str
) -> list[tuple[str, str, str, int]]:
    """Extract :raises: declarations from docstrings."""
    findings = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            if not doc:
                continue

            # Find :raises Exception: description patterns
            raises_pattern = r":raises\s+(\w+):\s*(.+?)(?=\n\s*:|\Z)"
            for match in re.finditer(raises_pattern, doc, re.DOTALL):
                exc_name = match.group(1)
                trigger = match.group(2).strip().replace("\n", " ")[:80]
                severity = "High" if "Error" in exc_name else "Medium"
                findings.append((exc_name, trigger, severity, node.lineno))

    return findings


def extract_tech_debt_comments(
    source: str, rel_path: str
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
    lines = []
    lines.append("## 🧨 ERROR TAXONOMY")
    lines.append(
        f"> Auto-generated from source code. Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
    )
    lines.append(
        "> **Rule:** Check this table before adding try/except or changing error handling."
    )
    lines.append("")
    lines.append("| Component | Exception | Trigger | Severity |")
    lines.append("|-----------|-----------|---------|----------|")

    # Group by component (file path)
    by_component: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    for rel_path, exc_name, trigger, severity, line in findings:
        # Simplify component name
        comp = rel_path.replace("src/ai_assistant/", "").replace("/", ".")
        if comp.endswith(".py"):
            comp = comp[:-3]

        # Deduplicate by component + exception (ignore trigger variations)
        key = (comp, exc_name)
        if key not in by_component:
            by_component[key] = (comp, exc_name, trigger, severity)

    # Sort by severity then component
    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    sorted_items = sorted(
        by_component.values(), key=lambda x: (severity_order.get(x[3], 2), x[0], x[1])
    )

    for comp, exc_name, trigger, severity in sorted_items:
        # Truncate long triggers
        display_trigger = trigger[:60] + "..." if len(trigger) > 60 else trigger
        lines.append(f"| `{comp}` | `{exc_name}` | {display_trigger} | {severity} |")

    lines.append("")
    lines.append(
        "> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    root = find_project_root()
    print(f"[error_taxonomy] Project root: {root}")

    files = resolve_patterns(root, SCAN_PATTERNS)
    print(f"[error_taxonomy] Scanning {len(files)} files...")

    all_findings: list[tuple[str, str, str, str, int]] = []

    for fpath in files:
        rel = os.path.relpath(fpath, root).replace(os.sep, "/")

        try:
            source = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"[error_taxonomy] Skip {rel}: {e}")
            continue

        # AST-based raises and except handlers
        try:
            tree = ast.parse(source)
            finder = ExceptionFinder(source, rel)
            finder.visit(tree)
            for exc, trigger, severity, line in finder.findings:
                all_findings.append((rel, exc, trigger, severity, line))
        except SyntaxError as e:
            print(f"[error_taxonomy] Syntax error in {rel}: {e}")

        # Docstring :raises:
        for exc, trigger, severity, line in extract_docstring_raises(source, rel):
            all_findings.append((rel, exc, trigger, severity, line))

        # TECH DEBT comments
        for exc, trigger, severity, line in extract_tech_debt_comments(source, rel):
            all_findings.append((rel, exc, trigger, severity, line))

    # Remove duplicates (same file, same exception)
    seen = set()
    deduped = []
    for item in all_findings:
        key = (item[0], item[1])  # path, exc only — ignore trigger for dedup
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    print(f"[error_taxonomy] Found {len(deduped)} unique findings")

    # Build and save
    md = build_taxonomy(deduped)
    out_path = root / "dev" / "ERROR_TAXONOMY.md"
    out_path.write_text(md, encoding="utf-8")

    print(f"[error_taxonomy] Written: {out_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
