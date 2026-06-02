#!/usr/bin/env python3
'''Pre-commit checks — lightweight regex scanner.'''

import re
import sys
from pathlib import Path

R, Y, G, RST = '[31m', '[33m', '[32m', '[0m'


# Production directories to scan (relative to src/ai_assistant/)
_PROD_DIRS = ('adapters', 'features', 'core', 'api', 'pipeline')


def _find_src_root() -> Path:
    '''Find src/ai_assistant relative to script location.'''
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    src = project_root / 'src' / 'ai_assistant'
    if src.exists():
        return src
    cwd_src = Path.cwd() / 'src' / 'ai_assistant'
    if cwd_src.exists():
        return cwd_src
    raise FileNotFoundError(f'src/ai_assistant not found in {project_root} or {Path.cwd()}')


def _clean_line(line: str) -> str:
    '''Remove string literals and inline comments to reduce false positives.

    Handles single-line strings only. Multi-line strings are NOT cleaned.
    '''
    # Single-quoted strings (non-greedy, single line)
    line = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", line)
    # Double-quoted strings (non-greedy, single line)
    line = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', line)
    # Inline comments
    if '#' in line:
        line = line.split('#', 1)[0]
    return line


def _scan_file(
    path: Path,
    pattern: re.Pattern,
    rule: str,
    warn_only: bool = False,
) -> list[tuple[Path, int, str, bool]]:
    '''Scan single file for pattern.'''
    found: list[tuple[Path, int, str, bool]] = []
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except (OSError, UnicodeDecodeError) as e:
        print(f'{Y}{path}:READ_ERROR:{e}{RST}')
        return found

    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if pattern.search(_clean_line(line)):
            found.append((path, n, rule, warn_only))
    return found


def main() -> int:
    src = _find_src_root()
    issues: list[tuple[Path, int, str, bool]] = []

    # 1. hasattr / isinstance in production code (tests exempt)
    # AI_RULES: NEVER use hasattr/isinstance to bypass port contracts
    for subdir in _PROD_DIRS:
        sub = src / subdir
        if not sub.exists():
            continue
        for p in sub.rglob('*.py'):
            if 'test' in p.name or 'conftest' in p.name:
                continue
            issues.extend(_scan_file(p, re.compile(r'hasattr\('), 'no-hasattr-in-production', warn_only=False))
            issues.extend(_scan_file(p, re.compile(r'isinstance\('), 'no-isinstance-in-production', warn_only=False))

    # 2. **kwargs in production code
    # AI_RULES: NEVER Add **kwargs to pass data that belongs in PipelineData
    for subdir in _PROD_DIRS:
        sub = src / subdir
        if not sub.exists():
            continue
        for p in sub.rglob('*.py'):
            if 'test' in p.name or 'conftest' in p.name:
                continue
            # llm.py excluded — sampling params are open-ended by design
            if subdir == 'core' and 'ports' in str(p) and p.name == 'llm.py':
                continue
            issues.extend(_scan_file(p, re.compile(r'\*\*kwargs'), 'no-kwargs-in-production'))

    # 3. cross-feature imports (absolute + relative)
    feat_root = src / 'features'
    if feat_root.exists():
        for feat in feat_root.iterdir():
            if not feat.is_dir():
                continue
            for p in feat.rglob('*.py'):
                if 'test' in p.name or 'conftest' in p.name:
                    continue
                try:
                    text = p.read_text(encoding='utf-8', errors='replace')
                except (OSError, UnicodeDecodeError):
                    continue
                for n, line in enumerate(text.splitlines(), 1):
                    if line.strip().startswith('#'):
                        continue
                    clean = _clean_line(line)
                    # Absolute: from ai_assistant.features.chat import ...
                    m = re.search(
                        r'(?:from|import)\s+ai_assistant\.features\.([a-z_]+)',
                        clean,
                    )
                    if m and m.group(1) != feat.name:
                        issues.append((p, n, 'no-cross-feature-imports', False))
                    # Relative: from ..chat import ...  or  from ...chat import ...
                    m_rel = re.search(
                        r'from\s+\.{2,}([a-z_]+)',
                        clean,
                    )
                    if m_rel and m_rel.group(1) != feat.name:
                        issues.append((p, n, 'no-cross-feature-imports', False))

    # 4. PipelineData mutation in production code
    _mut_pat = re.compile(
        r'\bdata\.'
        r'(context\s*=|'
        r'chunks\s*=|'
        r'response\s*=|'
        r'metadata\s*=|'
        r'metadata\s*\[.*\]\s*=|'
        r'metadata\.update\s*\(|'
        r'metadata\.setdefault\s*\(|'
        r'errors\.(append|extend)\s*\(|'
        r'errors\s*\+=)'
    )
    for subdir in _PROD_DIRS:
        sub = src / subdir
        if not sub.exists():
            continue
        for p in sub.rglob('*.py'):
            if 'test' in p.name or 'conftest' in p.name:
                continue
            issues.extend(_scan_file(p, _mut_pat, 'no-direct-pipeline-mutation'))

    # 5. print / pprint / logging.basicConfig in production code
    _prod_pat = re.compile(r'\b(print|pprint)\s*\(|logging\.basicConfig\s*\(')
    for subdir in _PROD_DIRS:
        sub = src / subdir
        if not sub.exists():
            continue
        for p in sub.rglob('*.py'):
            if 'test' in p.name or 'conftest' in p.name:
                continue
            issues.extend(_scan_file(p, _prod_pat, 'no-print-in-production'))

    # Output
    for p, n, rule, w in issues:
        print(f'{Y if w else R}{p}:{n}:{rule}{RST}')

    if any(not w for _, _, _, w in issues):
        print(f'{R}BLOCKED{RST}')
        return 1
    if any(w for _, _, _, w in issues):
        print(f'{Y}WARNING{RST}')
    print(f'{G}OK{RST}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
