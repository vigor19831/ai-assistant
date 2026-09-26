"""web_grab wrapper tests: the Pop-OS guard (drift #216)."""
from __future__ import annotations

import types


def test_web_grab_short_output_skipped(monkeypatch, tmp_path) -> None:
    """Near-empty extraction never writes a file to raw_documents."""
    import scripts.web_grab as wg

    monkeypatch.setattr(wg, "RAW_DIR", tmp_path)
    fake = types.SimpleNamespace(returncode=0, stdout="short", stderr="")
    monkeypatch.setattr(wg.subprocess, "run", lambda *a, **k: fake)
    assert wg._grab("https://example.com") is None
    assert not list(tmp_path.glob("*.md"))


def test_web_grab_ok_writes_file(monkeypatch, tmp_path) -> None:
    """A real extraction lands as .md in raw_documents."""
    import scripts.web_grab as wg

    monkeypatch.setattr(wg, "RAW_DIR", tmp_path)
    md = "# Test Page\n\n" + ("Body text. " * 20)
    fake = types.SimpleNamespace(returncode=0, stdout=md, stderr="")
    monkeypatch.setattr(wg.subprocess, "run", lambda *a, **k: fake)
    result = wg._grab("https://example.com")
    assert result is not None
    assert result.suffix == ".md"
    assert "Test-Page" in result.name or result.exists()
