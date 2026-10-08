"""CLI: scripted demo runs end-to-end and prints the plan + trail."""

from __future__ import annotations

from taste_concierge.cli import main


def test_demo_runs_and_prints_plan(capsys):
    rc = main(["--demo"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OFFLINE" in out
    assert "Blade Runner 2049" in out
    assert "Ippudo Westside" in out
    assert "=== QLOO API TRAIL ===" in out
    assert "/v2/insights" in out


def test_demo_labels_fixture_source(capsys):
    main(["--demo"])
    out = capsys.readouterr().out
    assert "[fixture]" in out


def test_interactive_eof_exits_cleanly(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(EOFError))
    rc = main(["--offline"])
    assert rc == 0
    assert "OFFLINE" in capsys.readouterr().out
