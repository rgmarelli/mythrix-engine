"""Unit tests for RetrievalPipeline (T15, restructured T26): multi-query text
construction from graph facts only — one query per *individual atomic
concept*, no identity query and no `type:` label (one per interpretant value —
split further on commas, since a value can list several distinct concepts
under one type — then per intersemiotic interpretant one per atomic concept
about the target's own `target_interpretants`, but not the target's bare
name, disabled for now), never grouping concepts into a combined query, see
pipeline.py's docstring for why — plus corpus-wide retrieval with no
tradition to scope by (FR7), grouped and merged per concept (FR24) via
Reciprocal Rank Fusion *within* that concept's own queries only, never
across a different concept's queries (see pipeline.py's docstring for the
real crowding-out case that motivated this), and hydration of raw vector
hits into full RetrievedPassages from an independent corpus source (FR7:
e.g. Genesis, discoverable when querying a tarot sign, carrying no
interpretive tradition of its own). Uses a fake vector store/embedder — no
Ollama needed."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import (
    ConceptCandidates,
    ConceptPairCandidates,
    GraphFacts,
    Interpretant,
    IntersemioticInterpretant,
    Manifestation,
    Property,
    QueryDirective,
    RetrievalContext,
    Sign,
    Source,
    Tradition,
)
from mythrix.core.retrieval.pipeline import RetrievalPipeline, _combined_score, build_query_texts
from mythrix.core.vector.store import VectorHit

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
THE_TOWER = Sign(
    id="the-tower",
    slug="the-tower",
    canonical_name="The Tower",
    sign_type="major-arcana",
    semiotic_system="tarot",
)
THE_TOWER_MANIFESTATION = Manifestation(
    id="the-tower::rider-waite",
    sign_id="the-tower",
    tradition=RIDER_WAITE,
    display_name="The Tower",
    denotation="Sudden upheaval; the collapse of false structures.",
    interpretants=(Interpretant(id="interp-element", type="element", value="Fire"),),
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)
GRAPH_FACTS = GraphFacts(sign=THE_TOWER, manifestation=THE_TOWER_MANIFESTATION)


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

    def similarity_search(self, query_embedding, *, top_k=6, document_contains=None):  # noqa: ANN001, ANN201
        self.last_call = {
            "query_embedding": query_embedding,
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

    def similarity_search(self, query_embedding, *, top_k=6, document_contains=None):  # noqa: ANN001, ANN201
        self.call_count += 1
        self.document_contains_per_call.append(document_contains)
        return next(self._hits_per_call)


@pytest.fixture
def graph_store(tmp_path: Path) -> KuzuGraphStore:
    store = KuzuGraphStore(tmp_path / "graph.kuzu")
    store.upsert_tradition(RIDER_WAITE)
    store.upsert_source(
        Source(id="waite-pictorial-key", domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite")
    )
    return store


def test_query_texts_have_no_identity_query_only_one_per_interpretant_value() -> None:
    """No combined name+denotation query — a sign's canonical name, display
    name, and denotation are never searched at all, only its individual
    interpretant values, so every sign is represented by comparably short,
    atomic queries instead of some being diluted by a long paragraph others
    don't have (pipeline.py's module docstring)."""
    query_texts = build_query_texts(GRAPH_FACTS)

    assert query_texts == [("Fire", None)]
    assert not any("Tower" in q.text or "upheaval" in q.text for q in query_texts)


def test_manifestation_properties_never_feed_query_text() -> None:
    """A card's ordinal position in its deck isn't descriptive of what the
    sign means — including it would inject an arbitrary numeral into the
    similarity search, diluting it with content unrelated to meaning.
    Properties are structurally excluded from query-text construction — there
    is no per-fact flag to set, `build_query_texts` simply never reads
    `Manifestation.properties`/`Sign.properties` at all."""
    manifestation_with_property = THE_TOWER_MANIFESTATION.model_copy(
        update={"properties": (Property(id="prop-number", key="number", value="16"),)}
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation_with_property)

    query_texts = build_query_texts(graph_facts)

    assert query_texts == [("Fire", None)]
    assert not any("16" in q.text for q in query_texts)


def test_query_texts_convert_a_lone_gematria_interpretant_to_its_authored_token_with_no_filter() -> None:
    """Unlike a card's `number`, a Hebrew letter's `numeric_value` (gematria)
    is real symbolic content in Kabbalah — gematria is literally the
    technique of connecting concepts by matching numeric value — so a curator
    marks it with `query: {directive: filter, as_token: ...}`. But an exact
    value isn't a fuzzy meaning an embedding matches well on its own
    (pipeline.py's module docstring):
    with no other concept in this group to attach it to as a filter, it's
    searched plainly in its authored token form ("100" -> "hundred")."""
    manifestation_with_gematria = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (
                Interpretant(
                    id="interp-numeric-value",
                    type="numeric_value",
                    value="100",
                    query=QueryDirective(directive="filter", as_token="hundred"),
                ),
            )
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation_with_gematria)

    query_texts = build_query_texts(graph_facts)

    assert query_texts == [("hundred", None)]


def test_query_texts_split_a_comma_separated_value_into_one_query_per_concept() -> None:
    """A value like a Hebrew letter's `meaning`, "Monkey, eye of the needle",
    lists two unrelated concepts sharing one type — not one phrase. Each must
    become its own query, since one ("eye of the needle") can be exactly the
    useful signal while the other ("Monkey") contributes nothing, and bundled
    together neither would compete cleanly against anything."""
    manifestation_with_list_meaning = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (Interpretant(id="interp-meaning", type="meaning", value="Monkey, eye of the needle"),)
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation_with_list_meaning)

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
    plainly (nothing lost), *plus* a filtered variant combined with the
    number as a literal-text filter (`document_contains`) — a passage
    combining both signals ranks higher via RRF, without excluding a passage
    that only matches the concept. The filter is global (not scoped to the
    group the number came from): Qoph's gematria filters its own
    `target_interpretants` concepts (Monkey, eye of the needle, laughter,
    Pisces) *and* the sign's own unrelated "Fire" interpretant — a real
    passage can combine a concept from one part of the graph with a number
    from a completely different part (e.g. Genesis 21: a child born when his
    father was a hundred years old). The target's bare name ("Qoph") is
    deliberately NOT queried on its own — see the module docstring TODO on
    why. Qoph's own `properties` never feed this at all — only
    `target_interpretants` does (the properties-asymmetry fix)."""
    qoph = Sign(
        id="qoph",
        slug="qoph",
        canonical_name="Qoph",
        sign_type="hebrew-letter",
        semiotic_system="hebrew_alef_bet",
        properties=(Property(id="qoph-letter-type", key="letter_type", value="simple"),),
    )
    marelli = Tradition(id="marelli", slug="marelli", name="marelli", domain="kabbalah")
    the_sun = THE_TOWER.model_copy(
        update={
            "canonical_name": "The Sun",
            "intersemiotic_interpretants": (
                IntersemioticInterpretant(
                    relationship="hebrew_letter",
                    target_sign=qoph,
                    according_to=marelli,
                    target_interpretants=(
                        Interpretant(
                            id="qoph-numeric-value",
                            type="numeric_value",
                            value="100",
                            query=QueryDirective(directive="filter", as_token="hundred"),
                        ),
                        Interpretant(id="qoph-meaning", type="meaning", value="Monkey, eye of the needle"),
                        Interpretant(id="qoph-foundation", type="foundation", value="laughter"),
                        Interpretant(id="qoph-constellation", type="constellation", value="Pisces"),
                    ),
                ),
            ),
        }
    )
    graph_facts = GraphFacts(sign=the_sun, manifestation=THE_TOWER_MANIFESTATION)

    query_texts = build_query_texts(graph_facts)

    texts = [q.text for q in query_texts]
    document_contains = [q.document_contains for q in query_texts]
    assert texts == [
        "Fire",
        "Fire",
        "Monkey",
        "eye of the needle",
        "laughter",
        "Pisces",
        "Monkey",
        "eye of the needle",
        "laughter",
        "Pisces",
    ]
    assert document_contains == [
        None,
        "hundred",
        None,
        None,
        None,
        None,
        "hundred",
        "hundred",
        "hundred",
        "hundred",
    ]
    # Every filtered variant carries the number's authored value too (FR28),
    # not just its search token — this is what lets "100" surface as a pair
    # member later, rather than being discarded once the search text is derived.
    filtered_queries = [q for q in query_texts if q.filter_token is not None]
    assert all(q.filter_token.value == "100" for q in filtered_queries)
    assert "Qoph" not in texts
    assert not any("Qoph" in t for t in texts)
    assert "100" not in texts  # the raw digit form is never searched as embeddable text
    assert not any("simple" in t for t in texts)  # Qoph's own properties never feed query text either


def test_retrieve_searches_the_full_corpus_with_no_scoping_filter(graph_store: KuzuGraphStore) -> None:
    """FR7: retrieval is never scoped by tradition — there is no tradition
    parameter left on `similarity_search` to pass one through."""
    embedder = FakeEmbedder()
    vector_store = FakeVectorStore(hits=[])
    # match_pool_size, not top_k, is what reaches `similarity_search` (FR27 —
    # pair convergence is detected against a pool deeper than what's displayed).
    pipeline = RetrievalPipeline(
        graph_store=graph_store, vector_store=vector_store, embedder=embedder, top_k=3, match_pool_size=3
    )

    pipeline.retrieve(GRAPH_FACTS)

    assert embedder.embedded_texts == [q.text for q in build_query_texts(GRAPH_FACTS)]
    assert vector_store.last_call == {
        "query_embedding": [1.0, 0.0],
        "top_k": 3,
        "document_contains": None,
    }


def test_retrieve_hydrates_a_hit_from_an_independent_corpus_source(graph_store: KuzuGraphStore) -> None:
    """The concrete scenario FR7 exists for: a query about a tarot sign
    surfacing a passage from an independent corpus document, which carries no
    tradition of its own at all (FR7)."""
    graph_store.upsert_source(
        Source(
            id="douay-rheims-bible",
            domain="scripture",
            citation_label="Douay-Rheims",
            title="The Holy Bible, Douay-Rheims, Complete",
            author="Various",
        )
    )
    hit = VectorHit(
        chunk_id="douay-rheims-bible::0",
        source_id="douay-rheims-bible",
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

    assert len(context.all_passages) == 1
    passage = context.all_passages[0]
    assert passage.source.title == "The Holy Bible, Douay-Rheims, Complete"
    assert passage.source.citation_label == "Douay-Rheims"
    assert "tower" in passage.text.lower()


def test_retrieve_hydrates_hits_into_full_retrieved_passages(graph_store: KuzuGraphStore) -> None:
    hit = VectorHit(
        chunk_id="waite-pictorial-key::0",
        source_id="waite-pictorial-key",
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
    assert len(context.concept_candidates) == 1
    assert context.concept_candidates[0].concept == "Fire"
    assert len(context.all_passages) == 1
    passage = context.all_passages[0]
    assert passage.text == "The Tower represents sudden and unavoidable upheaval."
    assert passage.source.title == "The Pictorial Key to the Tarot"
    assert passage.chunk_index == 0
    assert passage.char_start == 100
    assert passage.char_end == 155
    assert passage.score == pytest.approx(0.8)


def test_retrieve_filters_out_hits_below_min_score(graph_store: KuzuGraphStore) -> None:
    low_score_hit = VectorHit(
        chunk_id="waite-pictorial-key::1",
        source_id="waite-pictorial-key",
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

    assert context.concept_candidates == ()
    assert context.all_passages == ()


def _intersemiotic_graph_facts() -> GraphFacts:
    """A sign with exactly two query facets under the current (no identity,
    no relationship-name) scheme: one interpretant of the sign's own
    manifestation, and one interpretant on its intersemiotic-interpretant
    target — i.e. the minimal case that still exercises multi-query search:
    one query from the sign's own side, one from the target's side."""
    qoph = Sign(
        id="qoph", slug="qoph", canonical_name="Qoph", sign_type="hebrew-letter", semiotic_system="hebrew_alef_bet"
    )
    marelli = Tradition(id="marelli", slug="marelli", name="marelli", domain="kabbalah")
    the_sun = THE_TOWER.model_copy(
        update={
            "canonical_name": "The Sun",
            "intersemiotic_interpretants": (
                IntersemioticInterpretant(
                    relationship="hebrew_letter",
                    target_sign=qoph,
                    according_to=marelli,
                    target_interpretants=(Interpretant(id="qoph-meaning", type="meaning", value="Fish"),),
                ),
            ),
        }
    )
    manifestation_with_one_interpretant = THE_TOWER_MANIFESTATION.model_copy(
        update={"interpretants": (Interpretant(id="interp-element", type="element", value="Fire"),)}
    )
    return GraphFacts(sign=the_sun, manifestation=manifestation_with_one_interpretant)


def _gematria_intersemiotic_graph_facts() -> GraphFacts:
    """Like `_intersemiotic_graph_facts`, but the target also carries a
    gematria value — so the sign's own "Fire" interpretant is one concept
    with a single query, while the target's "Fish" meaning is a *second*,
    separate concept with two queries (plain + "hundred"-filtered). Used to
    test Reciprocal Rank Fusion and top_k truncation *within* one concept,
    and isolation *between* concepts (FR24)."""
    qoph = Sign(
        id="qoph", slug="qoph", canonical_name="Qoph", sign_type="hebrew-letter", semiotic_system="hebrew_alef_bet"
    )
    marelli = Tradition(id="marelli", slug="marelli", name="marelli", domain="kabbalah")
    the_sun = THE_TOWER.model_copy(
        update={
            "canonical_name": "The Sun",
            "intersemiotic_interpretants": (
                IntersemioticInterpretant(
                    relationship="hebrew_letter",
                    target_sign=qoph,
                    according_to=marelli,
                    target_interpretants=(
                        Interpretant(
                            id="qoph-numeric-value",
                            type="numeric_value",
                            value="100",
                            query=QueryDirective(directive="filter", as_token="hundred"),
                        ),
                        Interpretant(id="qoph-meaning", type="meaning", value="Fish"),
                    ),
                ),
            ),
        }
    )
    manifestation_with_one_interpretant = THE_TOWER_MANIFESTATION.model_copy(
        update={"interpretants": (Interpretant(id="interp-element", type="element", value="Fire"),)}
    )
    return GraphFacts(sign=the_sun, manifestation=manifestation_with_one_interpretant)


def _make_hit(chunk_id: str, distance: float) -> VectorHit:
    return VectorHit(
        chunk_id=chunk_id,
        source_id="waite-pictorial-key",
        domain="tarot",
        text=f"Passage for {chunk_id}.",
        chunk_index=0,
        char_start=0,
        char_end=10,
        embedding_model="fake-embed",
        distance=distance,
    )


def test_retrieve_never_fuses_across_different_concepts(graph_store: KuzuGraphStore) -> None:
    """Two concepts ("Fire", the sign's own interpretant; "Fish", the
    intersemiotic target's meaning) must never be merged into one shared pool
    (FR24) — each comes back as its own separate `ConceptCandidates`, even
    though the old flat-merge design would have combined them into a single
    ranked list."""
    graph_facts = _intersemiotic_graph_facts()
    hit_fire = _make_hit("waite-pictorial-key::fire-hit", distance=0.2)
    hit_fish = _make_hit("waite-pictorial-key::fish-hit", distance=0.3)
    vector_store = SequencedVectorStore([[hit_fire], [hit_fish]])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    context = pipeline.retrieve(graph_facts)

    assert vector_store.call_count == 2
    by_concept = {c.concept: [p.chunk_id for p in c.passages] for c in context.concept_candidates}
    assert by_concept == {
        "Fire": ["waite-pictorial-key::fire-hit"],
        "Fish": ["waite-pictorial-key::fish-hit"],
    }


def test_retrieve_fuses_multiple_queries_of_the_same_concept_by_reciprocal_rank(
    graph_store: KuzuGraphStore,
) -> None:
    """*Within* one concept (the gematria pair: "Fish" plain + "Fish"+hundred
    filtered), Reciprocal Rank Fusion can still rank a chunk found by both of
    that concept's queries above one found by only one of them, even when the
    latter's individual best distance is better — the whole point of ranking
    by rank rather than comparing raw scores (pipeline.py's module
    docstring). This is unrelated to, and must not be confused with, fusion
    *across* concepts, which no longer happens at all (see the sibling
    'never fuses across different concepts' test)."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    hit_x = _make_hit("waite-pictorial-key::X", distance=0.05)  # best raw match, but only in one query
    hit_y = _make_hit("waite-pictorial-key::Y", distance=0.5)
    hit_y_filtered = _make_hit("waite-pictorial-key::Y", distance=0.4)  # Y found by both of Fish's queries
    # 4 calls now that the gematria filter is global (Fire also gets a filtered variant):
    # Fire(None), Fire(hundred), Fish(None), Fish(hundred).
    vector_store = SequencedVectorStore([[], [], [hit_x, hit_y], [hit_y_filtered]])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    context = pipeline.retrieve(graph_facts)

    fish = next(c for c in context.concept_candidates if c.concept == "Fish")
    assert [p.chunk_id for p in fish.passages] == ["waite-pictorial-key::Y", "waite-pictorial-key::X"]
    # Y's displayed score is still its own best (lowest-distance) individual match.
    assert fish.passages[0].score == pytest.approx(0.6)


def test_retrieve_deduplicates_a_chunk_matched_by_multiple_queries_of_the_same_concept(
    graph_store: KuzuGraphStore,
) -> None:
    """The same passage can legitimately match both of one concept's queries
    (its plain form and its gematria-filtered variant) — it must appear once
    in that concept's results, with its best (lowest-distance) displayed
    score, not once per matching query."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    weaker_match = _make_hit("waite-pictorial-key::0", distance=0.6)
    stronger_match = _make_hit("waite-pictorial-key::0", distance=0.3)
    # 4 calls now that the gematria filter is global: Fire(None), Fire(hundred), Fish(None), Fish(hundred).
    vector_store = SequencedVectorStore([[], [], [weaker_match], [stronger_match]])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    context = pipeline.retrieve(graph_facts)

    fish = next(c for c in context.concept_candidates if c.concept == "Fish")
    assert len(fish.passages) == 1
    assert fish.passages[0].score == pytest.approx(0.7)


def test_retrieve_truncates_each_concepts_own_hits_to_top_k(graph_store: KuzuGraphStore) -> None:
    """`top_k` caps each concept's *own* candidates independently (FR24) — not
    one shared budget split across every concept in the query. Chunk 2
    appears in both of "Fish"'s queries (rank 2 in the first, rank 1 in the
    second), giving it the highest fused score within that concept; chunk 0
    (rank 1 in one query only) comes next; chunk 3 (rank 2 in one query only)
    is excluded by the `top_k=2` cap — all entirely within the "Fish"
    concept, unaffected by "Fire" (which returns nothing here)."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    plain_hits = [
        _make_hit("waite-pictorial-key::0", distance=0.1),
        _make_hit("waite-pictorial-key::2", distance=0.2),
    ]
    filtered_hits = [
        _make_hit("waite-pictorial-key::2", distance=0.1),
        _make_hit("waite-pictorial-key::3", distance=0.9),
    ]
    # 4 calls now that the gematria filter is global: Fire(None), Fire(hundred), Fish(None), Fish(hundred).
    vector_store = SequencedVectorStore([[], [], plain_hits, filtered_hits])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder(), top_k=2)

    context = pipeline.retrieve(graph_facts)

    fish = next(c for c in context.concept_candidates if c.concept == "Fish")
    assert len(fish.passages) == 2
    assert [p.chunk_id for p in fish.passages] == ["waite-pictorial-key::2", "waite-pictorial-key::0"]


def test_retrieve_keeps_every_concepts_own_top_hit_even_when_globally_outranked(
    graph_store: KuzuGraphStore,
) -> None:
    """The concrete regression this restructuring fixes (plan.md's
    "Concept-scoped synthesis"): a well-supported concept's own best passage
    must survive even when several *other* concepts' hits would all
    individually outscore it on raw distance. The real case: for The Sun,
    'laughter' (Qoph's Sepher Yetzirah foundation) ranked #1 within its own
    query, but lost the old shared `top_k` cutoff to unrelated, lower-signal
    concepts like 'naked child'/'white horse'/'red standard' that simply had
    better raw scores. Reproduced directly here: 'laughter' has the *worst*
    raw distance of the four concepts below — under the old flat-merge design
    with `top_k=1`, it would have been the only one excluded. Each concept
    now gets its own `top_k` budget, so it survives regardless of how many
    other concepts exist alongside it."""
    manifestation = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (
                Interpretant(id="interp-1", type="concept", value="naked child"),
                Interpretant(id="interp-2", type="concept", value="white horse"),
                Interpretant(id="interp-3", type="concept", value="red standard"),
                Interpretant(id="interp-4", type="foundation", value="laughter"),
            )
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation)
    hits_per_call = [
        [_make_hit("naked-child-hit", distance=0.1)],
        [_make_hit("white-horse-hit", distance=0.15)],
        [_make_hit("red-standard-hit", distance=0.2)],
        [_make_hit("laughter-hit", distance=0.9)],  # worst raw match of the four
    ]
    vector_store = SequencedVectorStore(hits_per_call)
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder(), top_k=1)

    context = pipeline.retrieve(graph_facts)

    concepts_with_a_passage = {c.concept for c in context.concept_candidates}
    assert concepts_with_a_passage == {"naked child", "white horse", "red standard", "laughter"}
    laughter = next(c for c in context.concept_candidates if c.concept == "laughter")
    assert [p.chunk_id for p in laughter.passages] == ["laughter-hit"]


def test_retrieve_passes_the_gematria_filter_through_to_the_vector_store(graph_store: KuzuGraphStore) -> None:
    """End-to-end: an intersemiotic target's gematria value reaches the vector
    store as an actual `document_contains` filter *globally* — not just on
    its own sibling concept ("Fish"), but also on the sign's own unrelated
    "Fire" interpretant — never replacing any plain (unfiltered) search, just
    adding to every one of them (see pipeline.py's module docstring on why a
    hard filter would silently kill results for most cards, and on why the
    filter is global rather than scoped to the group the number came from)."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    vector_store = SequencedVectorStore([[_make_hit("waite-pictorial-key::0", distance=0.1)], [], [], []])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    pipeline.retrieve(graph_facts)

    # Query 1 ("Fire" plain) carries no filter; query 2 ("Fire" + gematria)
    # carries the filter too, even though "Fire" has nothing to do with Qoph
    # or gematria — the filter is global. Query 3 ("Fish" plain) carries
    # none; query 4 ("Fish" + gematria) carries it as an additional, not
    # replacing, search.
    assert vector_store.document_contains_per_call == [None, "hundred", None, "hundred"]


# --- Concept-pair convergence (FR27, FR28) ---


def test_pair_candidates_emitted_for_a_chunk_shared_by_two_concepts(graph_store: KuzuGraphStore) -> None:
    """FR27: a passage retrieved by two different concepts is surfaced as an
    additional `ConceptPairCandidates` group, *alongside* — never instead of
    — each concept's own group. Additive, not a restructuring: a strong
    single-concept match never has to compete with a convergent one."""
    graph_facts = _intersemiotic_graph_facts()
    shared_hit_for_fire = _make_hit("shared", distance=0.2)
    shared_hit_for_fish = _make_hit("shared", distance=0.3)
    vector_store = SequencedVectorStore([[shared_hit_for_fire], [shared_hit_for_fish]])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    context = pipeline.retrieve(graph_facts)

    assert {c.concept for c in context.concept_candidates} == {"Fire", "Fish"}
    assert len(context.pair_candidates) == 1
    pair = context.pair_candidates[0]
    assert set(pair.concepts) == {"Fire", "Fish"}
    assert len(pair.candidates) == 1
    assert pair.candidates[0].passage.chunk_id == "shared"
    assert {m.concept for m in pair.candidates[0].matches} == {"Fire", "Fish"}


def test_iter_candidates_yields_concept_candidates_before_pair_candidates(graph_store: KuzuGraphStore) -> None:
    """`iter_candidates` is the incremental form `retrieve()` collects in
    full — every concept's `ConceptCandidates` comes out before any
    `ConceptPairCandidates`, and collecting the whole generator reproduces
    exactly what `retrieve()` returns."""
    graph_facts = _intersemiotic_graph_facts()
    shared_hit_for_fire = _make_hit("shared", distance=0.2)
    shared_hit_for_fish = _make_hit("shared", distance=0.3)
    vector_store = SequencedVectorStore([[shared_hit_for_fire], [shared_hit_for_fish]])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    items = list(pipeline.iter_candidates(graph_facts))

    kinds = [type(item) for item in items]
    assert kinds.count(ConceptCandidates) == 2
    assert kinds.count(ConceptPairCandidates) == 1
    assert kinds.index(ConceptPairCandidates) > kinds.index(ConceptCandidates)

    reconstructed = RetrievalContext(
        graph_facts=graph_facts,
        concept_candidates=tuple(i for i in items if isinstance(i, ConceptCandidates)),
        pair_candidates=tuple(i for i in items if isinstance(i, ConceptPairCandidates)),
    )
    vector_store_2 = SequencedVectorStore([[shared_hit_for_fire], [shared_hit_for_fish]])
    pipeline_2 = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store_2, embedder=FakeEmbedder())
    assert reconstructed == pipeline_2.retrieve(graph_facts)


def test_no_pair_candidates_when_no_chunk_is_shared(graph_store: KuzuGraphStore) -> None:
    """A passage retrieved by only one concept produces no pair group at all
    — convergence is only surfaced when it genuinely occurs."""
    graph_facts = _intersemiotic_graph_facts()
    vector_store = SequencedVectorStore(
        [[_make_hit("fire-only", distance=0.2)], [_make_hit("fish-only", distance=0.2)]]
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    context = pipeline.retrieve(graph_facts)

    assert context.pair_candidates == ()


def test_pair_candidates_found_even_when_below_one_concepts_displayed_top_k(graph_store: KuzuGraphStore) -> None:
    """The motivating case for searching a deeper pool than what's displayed
    (FR27): a passage ranked #1 for one concept but only #9 for another is a
    real convergence, yet it never enters the second concept's *displayed*
    top-6 list. Pairs must be detected against `match_pool_size`, not
    `top_k`, or this case is invisible."""
    graph_facts = _intersemiotic_graph_facts()
    converge_hit_for_fire = _make_hit("converge", distance=0.1)  # rank 1 for "Fire"
    fish_hits = [_make_hit(f"fish-filler-{i}", distance=0.05 + i * 0.01) for i in range(8)]
    fish_hits.append(_make_hit("converge", distance=0.5))  # ranked 9th for "Fish"
    vector_store = SequencedVectorStore([[converge_hit_for_fire], fish_hits])
    pipeline = RetrievalPipeline(
        graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder(), top_k=6, match_pool_size=30
    )

    context = pipeline.retrieve(graph_facts)

    fish = next(c for c in context.concept_candidates if c.concept == "Fish")
    assert "converge" not in [p.chunk_id for p in fish.passages]  # absent from Fish's displayed top 6
    assert len(context.pair_candidates) == 1
    assert context.pair_candidates[0].candidates[0].passage.chunk_id == "converge"


def test_exact_value_pairs_with_the_concept_sharing_its_chunk(graph_store: KuzuGraphStore) -> None:
    """FR28: a recognized exact value (Qoph's gematria, "100"/"hundred") pairs
    with whichever concept shares a chunk with it, scored by that concept's
    own similarity alone — the value itself carries no score, only a
    guarantee of containment, since it arrived via `document_contains` (a
    hard filter) rather than embedding similarity."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    fish_and_hundred_hit = _make_hit("fish-and-hundred", distance=0.3)
    # 4 calls: Fire(None), Fire(hundred), Fish(None), Fish(hundred) — the hit
    # is only returned by Fish's *filtered* query, proving membership comes
    # from the filter, not from the plain concept search.
    vector_store = SequencedVectorStore([[], [], [], [fish_and_hundred_hit]])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    context = pipeline.retrieve(graph_facts)

    assert len(context.pair_candidates) == 1
    pair = context.pair_candidates[0]
    assert set(pair.concepts) == {"Fish", "100"}
    candidate = pair.candidates[0]
    assert candidate.combined_score == pytest.approx(0.7)  # Fish's own score alone, per FR28
    matches_by_concept = {m.concept: m for m in candidate.matches}
    assert matches_by_concept["100"].exact_value is True
    assert matches_by_concept["100"].score == 0.0
    assert matches_by_concept["Fish"].exact_value is False
    assert matches_by_concept["Fish"].score == pytest.approx(0.7)


def test_combined_score_ranks_a_balanced_pair_above_a_lopsided_one_with_the_same_sum() -> None:
    """Sum and arithmetic mean can't tell these apart: (0.90+0.20) ==
    (0.57+0.53) == 1.10, and both average to 0.55. But only the second
    genuinely sits at the intersection of both concepts — the first is a
    strong match on one concept that merely reached the other's deep
    matching pool. The geometric mean is what distinguishes them (see this
    module's docstring and `pipeline.py`'s)."""
    lopsided = _combined_score((0.90, 0.20))
    balanced = _combined_score((0.57, 0.53))

    assert balanced > lopsided


def test_combined_score_clamps_negative_components_instead_of_raising() -> None:
    """`_similarity_score` is `1 - cosine_distance`, spanning [-1, 1] — a
    negative component must not raise a math-domain error on the square
    root, and contributes no conjunctive strength."""
    assert _combined_score((-0.4, 0.6)) == pytest.approx(0.0)
    assert _combined_score((-0.4, -0.6)) == pytest.approx(0.0)
