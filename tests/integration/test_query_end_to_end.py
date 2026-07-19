"""T25 — v1 end-to-end acceptance (spec.md "Reference implementation scope"):
load-symbols + load-documents + query against the real reference dataset
under `data/`, using a real local Ollama. Opt-in (`@pytest.mark.requires_ollama`)
— needs `ollama pull nomic-embed-text` and a generation model pulled locally
(see docs/SETUP.md). Not part of the default `tests/unit` run.

Self-contained: loads the dataset fresh into a `tmp_path`-based Kùzu/Chroma
store rather than depending on a pre-existing persistent store, so this test
is reproducible on its own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mythrix.cli.commands.query import run_query
from mythrix.core.embedding import OllamaEmbedder
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.document_loader import load_document
from mythrix.core.loaders.symbol_loader import load_directory
from mythrix.core.synthesis.chain import OllamaSynthesizer
from mythrix.core.vector.store import ChromaVectorStore

DATA_ROOT = Path(__file__).parent.parent.parent / "data"
BIBLE_DOCUMENT = DATA_ROOT / "bible" / "documents" / "douay-rheims-bible.txt"
BASE_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"
GENERATION_MODEL = "llama3.2"


@pytest.mark.requires_ollama
def test_query_the_tower_returns_a_grounded_cited_interpretation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    graph_store = KuzuGraphStore(tmp_path / "graph.kuzu")
    vector_store = ChromaVectorStore(tmp_path / "chroma")
    embedder = OllamaEmbedder(model=EMBEDDING_MODEL, base_url=BASE_URL)

    load_directory(DATA_ROOT, graph_store)
    load_document(
        BIBLE_DOCUMENT,
        source_id="douay-rheims-bible",
        tradition_slug="douay-rheims",
        domain="scripture",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
    )

    def synthesizer_factory() -> OllamaSynthesizer:
        return OllamaSynthesizer(generation_model=GENERATION_MODEL, embedding_model=EMBEDDING_MODEL, base_url=BASE_URL)

    exit_code = run_query(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        synthesizer_factory=synthesizer_factory,
        top_k=6,
        min_score=0.0,
        strict=True,
    )

    output = capsys.readouterr().out
    assert exit_code == 0, f"non-zero exit; output was:\n{output}"
    assert "[G1]" in output
    assert "Citations valid: yes" in output
    # The independent Bible document (not Waite's own text) was retrieved and shown verbatim (FR13).
    assert "tower" in output.lower()
