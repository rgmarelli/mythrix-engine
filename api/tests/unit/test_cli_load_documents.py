# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for T22's `run_load_documents`, called directly (no Typer
machinery, no Ollama needed — dry-run needs no embedder at all, and the real
ingest path is given a fake one). Auto-discovers corpus sources under a
directory; no `--tradition`/`--source-slug` (FR-CO-01)."""

import json
from pathlib import Path

import pytest

from mythrix.cli.commands.load_documents import run_load_documents
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.vector.store import ChromaVectorStore


class FakeEmbedder:
    model_name = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.0] for text in texts]


@pytest.fixture
def graph_store(tmp_path: Path) -> KuzuGraphStore:
    return KuzuGraphStore(tmp_path / "graph.kuzu")


@pytest.fixture
def vector_store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def _write_corpus_source(
    directory: Path, *, id_: str = "en_drb", text: str = "The Tower depicts sudden upheaval."
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "doc.yaml").write_text(
        f'source:\n  id: "{id_}"\n  domain: scripture\n  citation_label: "Label"\n'
        '  title: "The Holy Bible"\n  author: "Various"\n',
        encoding="utf-8",
    )
    (directory / "doc.txt").write_text(text, encoding="utf-8")


def test_dry_run_reports_new_without_writing(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus_source(corpus)

    exit_code = run_load_documents(
        corpus,
        graph_store=graph_store,
        vector_store=None,
        embedder=None,
        chunk_size=650,
        chunk_overlap=100,
        dry_run=True,
        as_json=True,
    )

    assert exit_code == 0
    assert vector_store.count() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"] == [{"source_id": "en_drb", "status": "new", "detail": "would ingest for the first time"}]


def test_real_ingest_writes_chunks_then_dry_run_reports_unchanged(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus_source(corpus)

    exit_code = run_load_documents(
        corpus,
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        chunk_size=650,
        chunk_overlap=100,
        dry_run=False,
        as_json=False,
    )
    assert exit_code == 0
    assert vector_store.count() == 1
    assert "Ingested" in capsys.readouterr().out

    dry_run_exit_code = run_load_documents(
        corpus,
        graph_store=graph_store,
        vector_store=None,
        embedder=None,
        chunk_size=650,
        chunk_overlap=100,
        dry_run=True,
        as_json=True,
    )
    assert dry_run_exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["status"] == "unchanged"


def test_duplicate_source_id_reports_error(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_corpus_source(tmp_path / "a", id_="dup")
    _write_corpus_source(tmp_path / "b", id_="dup")

    exit_code = run_load_documents(
        tmp_path,
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        chunk_size=650,
        chunk_overlap=100,
        dry_run=False,
        as_json=False,
    )

    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_no_corpus_sources_found_reports_cleanly(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run_load_documents(
        tmp_path,
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        chunk_size=650,
        chunk_overlap=100,
        dry_run=False,
        as_json=False,
    )

    assert exit_code == 0
    assert "No corpus sources found." in capsys.readouterr().out
