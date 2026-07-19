"""Unit tests for T22's `run_load_documents`, called directly (no Typer
machinery, no Ollama needed — dry-run needs no embedder at all, and the real
ingest path is given a fake one)."""

import json
from pathlib import Path

import pytest

from mythrix.cli.commands.load_documents import run_load_documents
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Source, Tradition
from mythrix.core.vector.store import ChromaVectorStore


class FakeEmbedder:
    model_name = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.0] for text in texts]


@pytest.fixture
def graph_store(tmp_path: Path) -> KuzuGraphStore:
    store = KuzuGraphStore(tmp_path / "graph.kuzu")
    store.upsert_tradition(Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot"))
    store.upsert_source(Source(id="waite", title="The Pictorial Key to the Tarot", author="A. E. Waite"))
    return store


@pytest.fixture
def vector_store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def test_dry_run_reports_new_without_writing(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = tmp_path / "excerpt.txt"
    doc.write_text("The Tower depicts sudden upheaval.", encoding="utf-8")

    exit_code = run_load_documents(
        doc,
        source_id="waite",
        tradition_slug="rider-waite",
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
    assert payload["status"] == "new"


def test_real_ingest_writes_chunks_then_dry_run_reports_unchanged(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = tmp_path / "excerpt.txt"
    doc.write_text("The Tower depicts sudden upheaval.", encoding="utf-8")

    exit_code = run_load_documents(
        doc,
        source_id="waite",
        tradition_slug="rider-waite",
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
        doc,
        source_id="waite",
        tradition_slug="rider-waite",
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
    assert payload["status"] == "unchanged"


def test_unknown_tradition_reports_error(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = tmp_path / "excerpt.txt"
    doc.write_text("Some text.", encoding="utf-8")

    exit_code = run_load_documents(
        doc,
        source_id="waite",
        tradition_slug="nonexistent",
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
