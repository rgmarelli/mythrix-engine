"""Unit tests for RetrievalPipeline (T15): multi-query text construction from
graph facts only — one query per *individual atomic concept*, no identity
query and no `key:` label (one per attribute value — split further on
commas, since a value can list several distinct concepts under one key —
then per corresponds_to relationship one per atomic concept about the
target, but not the target's bare name, disabled for now), never grouping
concepts into a combined query, see pipeline.py's docstring for why — plus
corpus-wide (not tradition-scoped) retrieval merged via Reciprocal Rank
Fusion (by each hit's rank within its own query, not by comparing raw scores
across different queries — see pipeline.py's docstring for the real case
that motivated this), and hydration of raw vector hits into full
RetrievedPassages — including hits from a *different* tradition than the one
queried, which is the whole point of FR7's revised scoping (an independent
document like Genesis should be discoverable when querying a tarot symbol,
not excluded for carrying a different tradition tag). Uses a fake vector
store/embedder — no Ollama needed."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Attribute, GraphFacts, Interpretation, RelationshipFact, Source, Symbol, Tradition
from mythrix.core.retrieval.pipeline import RetrievalPipeline, build_query_texts
from mythrix.core.vector.store import VectorHit

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
THE_TOWER = Symbol(id="the-tower", slug="the-tower", canonical_name="The Tower", symbol_type="major-arcana")
THE_TOWER_INTERPRETATION = Interpretation(
    id="the-tower::rider-waite",
    symbol_id="the-tower",
    tradition=RIDER_WAITE,
    display_name="The Tower",
    summary="Sudden upheaval; the collapse of false structures.",
    attributes=(Attribute(id="attr-element", key="element", value="Fire"),),
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)
GRAPH_FACTS = GraphFacts(symbol=THE_TOWER, interpretation=THE_TOWER_INTERPRETATION)


class FakeEmbedder:
    model_name = "fake-embed"

    def __init__(self) -> None:
        self.embedded_texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded_texts.extend(texts)
        return [[1.0, 0.0] for _ in texts]


class FakeVectorStore:
    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits
        self.last_call: dict | None = None

    def similarity_search(self, query_embedding, *, tradition_slug=None, top_k=6, document_contains=None):  # noqa: ANN001, ANN201
        self.last_call = {
            "query_embedding": query_embedding,
            "tradition_slug": tradition_slug,
            "top_k": top_k,
            "document_contains": document_contains,
        }
        return self._hits


class SequencedVectorStore:
    """Returns a different, pre-scripted set of hits on each successive call —
    for tests exercising multi-query retrieval, where `FakeVectorStore`'s single
    fixed response for every call isn't enough to tell searches apart."""

    def __init__(self, hits_per_call: list[list[VectorHit]]) -> None:
        self._hits_per_call = iter(hits_per_call)
        self.call_count = 0
        self.document_contains_per_call: list[str | None] = []

    def similarity_search(self, query_embedding, *, tradition_slug=None, top_k=6, document_contains=None):  # noqa: ANN001, ANN201
        self.call_count += 1
        self.document_contains_per_call.append(document_contains)
        return next(self._hits_per_call)


@pytest.fixture
def graph_store(tmp_path: Path) -> KuzuGraphStore:
    store = KuzuGraphStore(tmp_path / "graph.kuzu")
    store.upsert_tradition(RIDER_WAITE)
    store.upsert_source(Source(id="waite-pictorial-key", title="The Pictorial Key to the Tarot", author="A. E. Waite"))
    return store


def test_query_texts_have_no_identity_query_only_one_per_attribute_value() -> None:
    """No combined name+summary query — a symbol's canonical name, display
    name, and summary are never searched at all, only its individual
    attribute values, so every symbol is represented by comparably short,
    atomic queries instead of some being diluted by a long paragraph others
    don't have (pipeline.py's module docstring)."""
    query_texts = build_query_texts(GRAPH_FACTS)

    assert query_texts == [("Fire", None)]
    assert not any("Tower" in q.text or "upheaval" in q.text for q in query_texts)


def test_query_texts_exclude_only_attributes_marked_not_retrievable() -> None:
    """A card's ordinal position in its deck isn't descriptive of what the
    symbol means — including it would inject an arbitrary numeral into the
    similarity search, diluting it with content unrelated to meaning. Only
    an attribute explicitly marked `retrievable: false` is excluded — being
    numeric isn't itself disqualifying (see the sibling test: a Hebrew
    letter's gematria `numeric_value` is numeric too, but is real symbolic
    content and must stay included by default)."""
    numbered_interpretation = THE_TOWER_INTERPRETATION.model_copy(
        update={
            "attributes": (
                Attribute(id="attr-element", key="element", value="Fire"),
                Attribute(id="attr-number", key="number", value="16", value_type="integer", retrievable=False),
            )
        }
    )
    graph_facts = GraphFacts(symbol=THE_TOWER, interpretation=numbered_interpretation)

    query_texts = build_query_texts(graph_facts)

    assert query_texts == [("Fire", None)]


def test_query_texts_convert_a_lone_gematria_value_to_its_word_form_with_no_filter() -> None:
    """Unlike a card's `number`, a Hebrew letter's `numeric_value` (gematria)
    is real symbolic content in Kabbalah — gematria is literally the
    technique of connecting concepts by matching numeric value — so it must
    stay included by default (`retrievable` defaults to `True`) despite also
    being `value_type: integer`. But an exact value isn't a fuzzy meaning an
    embedding matches well on its own (pipeline.py's module docstring): with
    no other concept in this group to attach it to as a filter, it's
    searched as plain text in its English word form ("100" -> "hundred")."""
    interpretation_with_gematria = THE_TOWER_INTERPRETATION.model_copy(
        update={
            "attributes": (Attribute(id="attr-numeric-value", key="numeric_value", value="100", value_type="integer"),)
        }
    )
    graph_facts = GraphFacts(symbol=THE_TOWER, interpretation=interpretation_with_gematria)

    query_texts = build_query_texts(graph_facts)

    assert query_texts == [("hundred", None)]


def test_query_texts_split_a_comma_separated_value_into_one_query_per_concept() -> None:
    """A value like a Hebrew letter's `meaning`, "Monkey, eye of the needle",
    lists two unrelated concepts sharing one key — not one phrase. Each must
    become its own query, since one ("eye of the needle") can be exactly the
    useful signal while the other ("Monkey") contributes nothing, and bundled
    together neither would compete cleanly against anything."""
    interpretation_with_list_meaning = THE_TOWER_INTERPRETATION.model_copy(
        update={"attributes": (Attribute(id="attr-meaning", key="meaning", value="Monkey, eye of the needle"),)}
    )
    graph_facts = GraphFacts(symbol=THE_TOWER, interpretation=interpretation_with_list_meaning)

    query_texts = build_query_texts(graph_facts)

    texts = [q.text for q in query_texts]
    assert "Monkey" in texts
    assert "eye of the needle" in texts
    assert not any("Monkey" in t and "needle" in t for t in texts)  # never bundled back together


def test_query_texts_add_a_gematria_filtered_variant_without_dropping_the_plain_concept() -> None:
    """A Hebrew letter's gematria value doesn't replace its group's concept
    queries with filtered-only versions — that would silently return zero
    results for any card where no single passage happens to combine the
    number and the concept (a real case surfaced a passage about measuring
    units, "the ephi and the bate", for bare `100`, but that's a different
    problem than losing results entirely). Instead every concept is searched
    plainly (nothing lost), *plus* a second, filtered variant combined with
    the number as a literal-text filter (`document_contains`) — a passage
    combining both signals ranks higher via RRF, without excluding a passage
    that only matches the concept. Numbers living in `properties` and
    concepts living in `target_semantic_facts` still combine, since both are
    folded into one `_fact_queries` group. The target's bare name ("Qoph") is
    deliberately NOT queried on its own — see the module docstring TODO on
    why."""
    qoph = Symbol(
        id="qoph",
        slug="qoph",
        canonical_name="Qoph",
        symbol_type="hebrew-letter",
        properties=(
            Attribute(id="qoph-numeric-value", key="numeric_value", value="100", value_type="integer"),
            Attribute(id="qoph-meaning", key="meaning", value="Monkey, eye of the needle"),
        ),
    )
    marelli = Tradition(id="marelli", slug="marelli", name="marelli", domain="kabbalah")
    the_sun = THE_TOWER.model_copy(
        update={
            "canonical_name": "The Sun",
            "relationships": (
                RelationshipFact(
                    relationship_type="hebrew_letter",
                    target_symbol=qoph,
                    according_to_tradition=marelli,
                    target_semantic_facts=(
                        Attribute(id="qoph-foundation", key="foundation", value="laughter"),
                        Attribute(id="qoph-constellation", key="constellation", value="Pisces"),
                    ),
                ),
            ),
        }
    )
    graph_facts = GraphFacts(symbol=the_sun, interpretation=THE_TOWER_INTERPRETATION)

    query_texts = build_query_texts(graph_facts)

    assert query_texts == [
        ("Fire", None),
        ("Monkey", None),
        ("eye of the needle", None),
        ("laughter", None),
        ("Pisces", None),
        ("Monkey", "hundred"),
        ("eye of the needle", "hundred"),
        ("laughter", "hundred"),
        ("Pisces", "hundred"),
    ]
    texts = [q.text for q in query_texts]
    assert "Qoph" not in texts
    assert not any("Qoph" in t for t in texts)
    assert "100" not in texts  # the raw digit form is never searched as text


def test_retrieve_searches_the_full_corpus_without_a_tradition_filter(graph_store: KuzuGraphStore) -> None:
    """FR7 (revised): retrieval is not scoped to the queried interpretation's
    own tradition — an independent document may carry any tradition tag."""
    embedder = FakeEmbedder()
    vector_store = FakeVectorStore(hits=[])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=embedder, top_k=3)

    pipeline.retrieve(GRAPH_FACTS)

    assert embedder.embedded_texts == [q.text for q in build_query_texts(GRAPH_FACTS)]
    assert vector_store.last_call == {
        "query_embedding": [1.0, 0.0],
        "tradition_slug": None,
        "top_k": 3,
        "document_contains": None,
    }


def test_retrieve_hydrates_a_hit_from_a_different_tradition(graph_store: KuzuGraphStore) -> None:
    """The concrete scenario FR7 was revised for: a query about a tarot symbol
    (tradition `rider-waite`) surfacing a passage from an independent corpus
    tagged under an entirely different tradition (`douay-rheims`)."""
    bible_tradition = Tradition(id="douay-rheims", slug="douay-rheims", name="Douay-Rheims Bible", domain="scripture")
    graph_store.upsert_tradition(bible_tradition)
    graph_store.upsert_source(
        Source(id="douay-rheims-bible", title="The Holy Bible, Douay-Rheims, Complete", author="Various")
    )
    hit = VectorHit(
        chunk_id="douay-rheims-bible::0",
        source_id="douay-rheims-bible",
        tradition_slug="douay-rheims",
        domain="scripture",
        text="And they said: Come, let us make a city and a tower, the top whereof may reach to heaven.",
        chunk_index=0,
        char_start=0,
        char_end=89,
        embedding_model="fake-embed",
        distance=0.3,
    )
    pipeline = RetrievalPipeline(
        graph_store=graph_store, vector_store=FakeVectorStore(hits=[hit]), embedder=FakeEmbedder()
    )

    context = pipeline.retrieve(GRAPH_FACTS)

    assert len(context.passages) == 1
    passage = context.passages[0]
    assert passage.tradition.slug == "douay-rheims"
    assert passage.source.title == "The Holy Bible, Douay-Rheims, Complete"
    assert "tower" in passage.text.lower()


def test_retrieve_hydrates_hits_into_full_retrieved_passages(graph_store: KuzuGraphStore) -> None:
    hit = VectorHit(
        chunk_id="waite-pictorial-key::0",
        source_id="waite-pictorial-key",
        tradition_slug="rider-waite",
        domain="tarot",
        text="The Tower represents sudden and unavoidable upheaval.",
        chunk_index=0,
        char_start=100,
        char_end=155,
        embedding_model="fake-embed",
        distance=0.2,
    )
    pipeline = RetrievalPipeline(
        graph_store=graph_store, vector_store=FakeVectorStore(hits=[hit]), embedder=FakeEmbedder()
    )

    context = pipeline.retrieve(GRAPH_FACTS)

    assert context.graph_facts == GRAPH_FACTS
    assert len(context.passages) == 1
    passage = context.passages[0]
    assert passage.text == "The Tower represents sudden and unavoidable upheaval."
    assert passage.source.title == "The Pictorial Key to the Tarot"
    assert passage.tradition.slug == "rider-waite"
    assert passage.chunk_index == 0
    assert passage.char_start == 100
    assert passage.char_end == 155
    assert passage.score == pytest.approx(0.8)


def test_retrieve_filters_out_hits_below_min_score(graph_store: KuzuGraphStore) -> None:
    low_score_hit = VectorHit(
        chunk_id="waite-pictorial-key::1",
        source_id="waite-pictorial-key",
        tradition_slug="rider-waite",
        domain="tarot",
        text="Unrelated passage.",
        chunk_index=1,
        char_start=0,
        char_end=19,
        embedding_model="fake-embed",
        distance=1.9,
    )
    pipeline = RetrievalPipeline(
        graph_store=graph_store,
        vector_store=FakeVectorStore(hits=[low_score_hit]),
        embedder=FakeEmbedder(),
        min_score=0.5,
    )

    context = pipeline.retrieve(GRAPH_FACTS)

    assert context.passages == ()


def _relationship_graph_facts() -> GraphFacts:
    """A symbol with exactly two query facets under the current (no identity,
    no relationship-name) scheme: one attribute of the symbol's own
    interpretation, and one property on its corresponds_to target — i.e. the
    minimal case that still exercises multi-query search: one query from the
    symbol's own side, one from the relationship's target."""
    qoph = Symbol(
        id="qoph",
        slug="qoph",
        canonical_name="Qoph",
        symbol_type="hebrew-letter",
        properties=(Attribute(id="qoph-meaning", key="meaning", value="Fish"),),
    )
    marelli = Tradition(id="marelli", slug="marelli", name="marelli", domain="kabbalah")
    the_sun = THE_TOWER.model_copy(
        update={
            "canonical_name": "The Sun",
            "relationships": (
                RelationshipFact(relationship_type="hebrew_letter", target_symbol=qoph, according_to_tradition=marelli),
            ),
        }
    )
    interpretation_with_one_attribute = THE_TOWER_INTERPRETATION.model_copy(
        update={"attributes": (Attribute(id="attr-element", key="element", value="Fire"),)}
    )
    return GraphFacts(symbol=the_sun, interpretation=interpretation_with_one_attribute)


def _make_hit(chunk_id: str, distance: float) -> VectorHit:
    return VectorHit(
        chunk_id=chunk_id,
        source_id="waite-pictorial-key",
        tradition_slug="rider-waite",
        domain="tarot",
        text=f"Passage for {chunk_id}.",
        chunk_index=0,
        char_start=0,
        char_end=10,
        embedding_model="fake-embed",
        distance=distance,
    )


def test_retrieve_runs_one_search_per_query_and_ranks_by_reciprocal_rank_fusion(
    graph_store: KuzuGraphStore,
) -> None:
    """A symbol with a `corresponds_to` relationship has two query facets
    (its own, plus one for the relationship) — retrieve must search both,
    not just the last one. Ranking is by Reciprocal Rank Fusion, not raw
    score: chunk B appears in *both* queries (rank 2 in the first, rank 1 in
    the second) and so out-ranks chunk A, which appears in only one query
    (rank 1) despite A's best individual distance being better than either
    of B's — the whole point of switching away from comparing raw scores
    across different queries (pipeline.py's module docstring)."""
    graph_facts = _relationship_graph_facts()
    hit_a = _make_hit("waite-pictorial-key::A", distance=0.1)
    hit_b_weak = _make_hit("waite-pictorial-key::B", distance=0.9)
    hit_b_strong = _make_hit("waite-pictorial-key::B", distance=0.05)
    vector_store = SequencedVectorStore([[hit_a, hit_b_weak], [hit_b_strong]])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    context = pipeline.retrieve(graph_facts)

    assert vector_store.call_count == 2
    assert [p.chunk_id for p in context.passages] == ["waite-pictorial-key::B", "waite-pictorial-key::A"]
    # The displayed score is still each chunk's own best (lowest-distance) match.
    assert context.passages[0].score == pytest.approx(0.95)
    assert context.passages[1].score == pytest.approx(0.9)


def test_retrieve_deduplicates_a_chunk_matched_by_multiple_queries_keeping_its_best_score(
    graph_store: KuzuGraphStore,
) -> None:
    """The same passage can legitimately match more than one query facet —
    it must appear once in the results, with its best (lowest-distance)
    displayed score, not once per matching query."""
    graph_facts = _relationship_graph_facts()
    weaker_match = _make_hit("waite-pictorial-key::0", distance=0.6)
    stronger_match = _make_hit("waite-pictorial-key::0", distance=0.3)
    vector_store = SequencedVectorStore([[weaker_match], [stronger_match]])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    context = pipeline.retrieve(graph_facts)

    assert len(context.passages) == 1
    assert context.passages[0].score == pytest.approx(0.7)


def test_retrieve_truncates_merged_hits_to_top_k(graph_store: KuzuGraphStore) -> None:
    """Merging results across multiple queries can produce more candidates
    than `top_k` — the final result must still be capped, keeping the
    highest fused (RRF) scores. Chunk 2 appears in both queries (rank 2 in
    the first, rank 1 in the second), giving it the highest fused score of
    the three distinct chunks; chunk 0 (rank 1 in one query only) comes
    next; chunk 3 (rank 2 in one query only) is excluded by the `top_k=2`
    cap."""
    graph_facts = _relationship_graph_facts()
    query1_hits = [
        _make_hit("waite-pictorial-key::0", distance=0.1),
        _make_hit("waite-pictorial-key::2", distance=0.2),
    ]
    query2_hits = [
        _make_hit("waite-pictorial-key::2", distance=0.1),
        _make_hit("waite-pictorial-key::3", distance=0.9),
    ]
    vector_store = SequencedVectorStore([query1_hits, query2_hits])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder(), top_k=2)

    context = pipeline.retrieve(graph_facts)

    assert len(context.passages) == 2
    assert [p.chunk_id for p in context.passages] == ["waite-pictorial-key::2", "waite-pictorial-key::0"]


def test_retrieve_passes_the_gematria_filter_through_to_the_vector_store(graph_store: KuzuGraphStore) -> None:
    """End-to-end: a relationship target's gematria value reaches the vector
    store as an actual `document_contains` filter on an *additional* search
    for its sibling concept — not replacing the plain (unfiltered) search for
    that same concept, just adding to it (see pipeline.py's module docstring
    on why a hard filter would silently kill results for most cards)."""
    qoph = Symbol(
        id="qoph",
        slug="qoph",
        canonical_name="Qoph",
        symbol_type="hebrew-letter",
        properties=(
            Attribute(id="qoph-numeric-value", key="numeric_value", value="100", value_type="integer"),
            Attribute(id="qoph-meaning", key="meaning", value="Fish"),
        ),
    )
    marelli = Tradition(id="marelli", slug="marelli", name="marelli", domain="kabbalah")
    the_sun = THE_TOWER.model_copy(
        update={
            "canonical_name": "The Sun",
            "relationships": (
                RelationshipFact(relationship_type="hebrew_letter", target_symbol=qoph, according_to_tradition=marelli),
            ),
        }
    )
    interpretation_with_one_attribute = THE_TOWER_INTERPRETATION.model_copy(
        update={"attributes": (Attribute(id="attr-element", key="element", value="Fire"),)}
    )
    graph_facts = GraphFacts(symbol=the_sun, interpretation=interpretation_with_one_attribute)
    vector_store = SequencedVectorStore([[_make_hit("waite-pictorial-key::0", distance=0.1)], [], []])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    pipeline.retrieve(graph_facts)

    # Query 1 ("Fire", the symbol's own attribute) carries no filter; query 2
    # ("Fish" plain) also carries none; query 3 ("Fish" + gematria) carries
    # the target's gematria filter as an additional, not replacing, search.
    assert vector_store.document_contains_per_call == [None, None, "hundred"]
