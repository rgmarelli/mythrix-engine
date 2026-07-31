# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `run_preview_segments`, called directly (no Typer
machinery, no graph/vector store, no Ollama) — the whole point of
`preview-segments` is that it needs none of those."""

import json
from pathlib import Path

import pytest

from mythrix.cli.commands.preview_segments import run_preview_segments


def _write_corpus_source(directory: Path, *, id_: str = "en_drb", text: str = "The Tower depicts upheaval.") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "doc.yaml").write_text(
        f'source:\n  id: "{id_}"\n  domain: scripture\n  title: "The Holy Bible"\n  author: "Various"\n',
        encoding="utf-8",
    )
    (directory / "doc.txt").write_text(text, encoding="utf-8")


def test_preview_prints_each_segments_locator(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus_source(corpus)

    exit_code = run_preview_segments(corpus, as_json=False)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "'en_drb': 1 segment" in out
    assert "[0]" in out


def test_preview_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus_source(corpus)

    exit_code = run_preview_segments(corpus, as_json=True)

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"] == [
        {
            "source_id": "en_drb",
            "segments": [{"ordinal": 0, "locator": "", "section": ""}],
        }
    ]


def test_preview_no_corpus_sources_found_reports_cleanly(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_preview_segments(tmp_path, as_json=False)

    assert exit_code == 0
    assert "No corpus sources found." in capsys.readouterr().out


def test_preview_duplicate_source_id_reports_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_corpus_source(tmp_path / "a", id_="dup")
    _write_corpus_source(tmp_path / "b", id_="dup")

    exit_code = run_preview_segments(tmp_path, as_json=False)

    assert exit_code == 1
    assert "Error" in capsys.readouterr().err
