"""Backup script — copies non-rebuildable data out of the project.

Backs up (everything else is rebuildable or versioned):
- config.yaml          the live config: language tables, paths, models
- data/raw_documents/  the corpus — the source of truth
- storage db           chat history — permanent-loss data

Skips on purpose: indices (derived, rebuilt by reindex), code and
docs (git is their backup).

The target folder is owner data in config.yaml (backup.target_dir);
each run creates a timestamped subfolder, old backups are NEVER
deleted automatically. Every copy is verified after writing (file
count, byte count, SQLite integrity_check, YAML re-parse); any
mismatch exits 1. Run via run_scripts or directly:
python scripts/backup.py
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import yaml

from ai_assistant.core.config import AppConfig, load_config

_ROOT = Path(__file__).resolve().parent.parent


def _resolve(path_str: str) -> Path:
    """Absolute passes through; relative anchors to the project root."""
    path = Path(path_str)
    return path if path.is_absolute() else _ROOT / path


def _tree_stats(path: Path) -> tuple[int, int]:
    """Return (file_count, total_bytes) under path."""
    files = [f for f in path.rglob("*") if f.is_file()]
    return len(files), sum(f.stat().st_size for f in files)


def _backup_db(src: Path, dst: Path) -> None:
    """Consistent snapshot of a (possibly live) SQLite db.

    The backup API, not a file copy: the server may hold the db open
    in WAL mode while this runs — a raw copy can be torn.
    """
    source = sqlite3.connect(f"{src.as_uri()}?mode=ro", uri=True)
    target = sqlite3.connect(str(dst))
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()


def _db_integrity(db: Path) -> str:
    """Run PRAGMA integrity_check on a copy; 'ok' means consistent."""
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "no result"
    finally:
        conn.close()


def main() -> int:
    config_path = _resolve(os.getenv("AI_CONFIG_PATH", "config.yaml"))
    if not config_path.exists():
        print(f"FAIL: config not found: {config_path}")
        return 1

    cfg: AppConfig = load_config(config_path)

    if cfg.backup is None:
        print("FAIL: backup section is missing. Add to config.yaml:")
        print()
        print("backup:")
        print('    target_dir: "/path/outside/the/project"')
        return 1

    target_root = _resolve(cfg.backup.target_dir)
    if target_root == _ROOT or _ROOT in target_root.parents:
        print(f"FAIL: target_dir {target_root} is inside the project")
        print("folder — a disk failure takes the backup with it.")
        print("Point it outside the project, ideally to another disk.")
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = target_root / f"backup_{timestamp}"
    try:
        backup_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        print(f"FAIL: cannot create {backup_dir}: {exc}")
        return 1

    raw_docs = _ROOT / "data" / "raw_documents"
    db_path = _resolve(cfg.storage.db_path)
    ok = True
    # Skipped assets must reach the manifest: "result: OK" alone hid
    # a backup without the corpus (the source of truth).
    skipped: list[str] = []

    # 1. The config itself
    config_copy = backup_dir / config_path.name
    shutil.copy2(config_path, config_copy)
    parsed = yaml.safe_load(config_copy.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        print("FAIL: the config copy does not parse as YAML")
        ok = False
    else:
        print(f"OK   config: {config_copy.name} re-parses")

    # 2. The corpus
    if raw_docs.exists():
        shutil.copytree(raw_docs, backup_dir / "raw_documents")
        src_files, src_bytes = _tree_stats(raw_docs)
        dst_files, dst_bytes = _tree_stats(backup_dir / "raw_documents")
        if (dst_files, dst_bytes) != (src_files, src_bytes):
            print(
                f"FAIL: raw_documents mismatch: "
                f"{dst_files}/{src_files} files, {dst_bytes}/{src_bytes} bytes"
            )
            ok = False
        else:
            print(f"OK   raw_documents: {dst_files} files, {dst_bytes} bytes")
    else:
        print(f"WARN raw_documents not found ({raw_docs}) — skipped")
        skipped.append("raw_documents")

    # 3. Chat history
    if db_path.exists():
        db_copy = backup_dir / db_path.name
        _backup_db(db_path, db_copy)
        integrity = _db_integrity(db_copy)
        if integrity != "ok":
            print(f"FAIL: storage copy integrity_check: {integrity}")
            ok = False
        else:
            print(f"OK   storage: {db_copy.name} integrity ok")
    else:
        print(f"WARN storage db not found ({db_path}) — skipped")
        skipped.append("storage")

    manifest = backup_dir / "manifest.txt"
    manifest.write_text(
        f"backup: {timestamp}\n"
        f"source_root: {_ROOT}\n"
        f"config: {config_path}\n"
        f"raw_documents: {raw_docs}\n"
        f"storage_db: {db_path}\n"
        f"result: {'OK' if ok else 'FAILED'}\n"
        f"skipped: {', '.join(skipped) if skipped else 'none'}\n",
        encoding="utf-8",
    )

    print(f"backup at: {backup_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
