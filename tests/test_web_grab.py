"""web_grab wrapper tests: the Pop-OS guard, the Downloads barrier."""
from __future__ import annotations

import sys
import types

import pytest


def test_web_grab_short_output_skipped(monkeypatch, tmp_path) -> None:
    """Near-empty extraction never writes a file to Downloads."""
    import scripts.web_grab as wg

    monkeypatch.setattr(wg, "DOWNLOAD_DIR", tmp_path)
    fake = types.SimpleNamespace(returncode=0, stdout="short", stderr="")
    monkeypatch.setattr(wg.subprocess, "run", lambda *a, **k: fake)
    assert wg._grab("https://example.com") is None
    assert not list(tmp_path.glob("*.md"))


def test_web_grab_ok_writes_file(monkeypatch, tmp_path) -> None:
    """A real extraction lands as .md in Downloads."""
    import scripts.web_grab as wg

    monkeypatch.setattr(wg, "DOWNLOAD_DIR", tmp_path)
    md = "# Test Page\n\n" + ("Body text. " * 20)
    fake = types.SimpleNamespace(returncode=0, stdout=md, stderr="")
    monkeypatch.setattr(wg.subprocess, "run", lambda *a, **k: fake)
    result = wg._grab("https://example.com")
    assert result is not None
    assert result.suffix == ".md"
    assert result.parent == tmp_path


def test_web_grab_no_args_is_loud(monkeypatch, tmp_path) -> None:
    """No url and no --batch: argparse error (exit 2), nothing written."""
    import scripts.web_grab as wg

    monkeypatch.setattr(wg, "DOWNLOAD_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["web_grab.py"])
    with pytest.raises(SystemExit) as excinfo:
        wg.main()
    assert excinfo.value.code == 2
    assert not list(tmp_path.glob("*.md"))


def test_web_grab_batch_without_url(monkeypatch, tmp_path) -> None:
    """--batch alone works: the Usage line in the docstring is honest."""
    import scripts.web_grab as wg

    queue = tmp_path / "queue.txt"
    queue.write_text("https://example.com\n# comment\n\n", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(wg, "DOWNLOAD_DIR", out)
    md = "# Batch Page\n\n" + ("Body text. " * 20)
    fake = types.SimpleNamespace(returncode=0, stdout=md, stderr="")
    monkeypatch.setattr(wg.subprocess, "run", lambda *a, **k: fake)
    monkeypatch.setattr(sys, "argv", ["web_grab.py", "--batch", str(queue)])
    assert wg.main() == 0
    assert len(list(out.glob("*.md"))) == 1
