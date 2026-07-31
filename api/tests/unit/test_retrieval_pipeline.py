# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for RetrievalPipeline: multi-query text construction from graph
facts only — one query per *individual atomic concept*, no identity query and
no `type:` label (one per interpretant value — split further on commas, since a
value can list several distinct concepts under one type — then per
intersemiotic interpretant one per atomic concept about the target's own
`target_interpretants`, but not the target's bare name, disabled for now),
never grouping concepts into a combined query, see pipeline.py's docstring for
why — plus corpus-wide retrieval with no tradition to scope by (FR-CO-02),
merged per concept via Reciprocal Rank Fusion *within* that concept's own
queries only, never across a different concept's queries (ADR-007), and rollup
of the surviving matches into ranked regions (ADR-013, FR-RK-01–FR-RK-10),
attributed to an independent corpus source (FR-CO-02: e.g. Genesis,
discoverable when querying a tarot sign, carrying no interpretive tradition of
its own). Uses a fake vector store/embedder — no Ollama needed."""

import logging
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import (
    GraphFacts,
    Interpretant,
    IntersemioticInterpretant,
    Manifestation,
    Property,
    QueryDirective,
    Segment,
    Sign,
    Source,
    Tradition,
)
from mythrix.core.retrieval.pipeline import (
    RetrievalPipeline,
    build_query_texts,
    collect_exact_tokens,
    parse_region_id,
    region_id_of,
    region_locator,
)
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
    def __init__(
        self, hits: list[VectorHit], *, document_matches_by_term: dict[str, list[VectorHit]] | None = None
    ) -> None:
        self._hits = hits
        self._document_matches_by_term = document_matches_by_term or {}
        self.last_call: dict | None = None
        self.document_matches_calls: list[str] = []

    def similarity_search(self, query_embedding, *, top_k=6, document_contains=None):  # noqa: ANN001, ANN201
        self.last_call = {
            "query_embedding": query_embedding,
            "top_k": top_k,
            "document_contains": document_contains,
        }
        return self._hits

    def document_matches(self, term: str) -> list[VectorHit]:
        self.document_matches_calls.append(term)
        return self._document_matches_by_term.get(term, [])


class DocumentFrequencyVectorStore(FakeVectorStore):
    """`FakeVectorStore` plus `count()`/`document_frequency()`, for tests of
    the specificity-weight helper and region rollup, which need a corpus size
    and per-term literal document frequency (FR-RK-04/FR-RK-06)
    that plain `FakeVectorStore` has no use for."""

    def __init__(
        self,
        hits: list[VectorHit],
        *,
        corpus_size: int,
        document_frequencies: dict[str, int],
        document_matches_by_term: dict[str, list[VectorHit]] | None = None,
    ) -> None:
        super().__init__(hits, document_matches_by_term=document_matches_by_term)
        self._corpus_size = corpus_size
        self._document_frequencies = document_frequencies

    def count(self) -> int:
        return self._corpus_size

    def document_frequency(self, term: str) -> int:
        return self._document_frequencies.get(term, 0)


class SequencedVectorStore:
    """Returns a different, pre-scripted set of hits on each successive call —
    for tests exercising multi-query retrieval, where `FakeVectorStore`'s single
    fixed response for every call isn't enough to tell searches apart.

    `corpus_size`/`document_frequencies` back `count()`/`document_frequency()`
    for tests of the specificity-weighted region path, which plain
    multi-query tests have no use for and so leave at their harmless
    defaults."""

    def __init__(
        self,
        hits_per_call: list[list[VectorHit]],
        *,
        corpus_size: int = 1,
        document_frequencies: dict[str, int] | None = None,
        document_matches_by_term: dict[str, list[VectorHit]] | None = None,
    ) -> None:
        self._hits_per_call = iter(hits_per_call)
        self.call_count = 0
        self.document_contains_per_call: list[str | None] = []
        self._corpus_size = corpus_size
        self._document_frequencies = document_frequencies or {}
        self._document_matches_by_term = document_matches_by_term or {}
        self.document_matches_calls: list[str] = []

    def similarity_search(self, query_embedding, *, top_k=6, document_contains=None):  # noqa: ANN001, ANN201
        self.call_count += 1
        self.document_contains_per_call.append(document_contains)
        return next(self._hits_per_call)

    def document_matches(self, term: str) -> list[VectorHit]:
        self.document_matches_calls.append(term)
        return self._document_matches_by_term.get(term, [])

    def count(self) -> int:
        return self._corpus_size

    def document_frequency(self, term: str) -> int:
        return self._document_frequencies.get(term, 0)


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
    # Every filtered variant carries the number's authored value too (FR-RT-09),
    # not just its search token — this is what lets "100" surface as a pair
    # member later, rather than being discarded once the search text is derived.
    filtered_queries = [q for q in query_texts if q.filter_token is not None]
    assert all(q.filter_token.value == "100" for q in filtered_queries)
    assert "Qoph" not in texts
    assert not any("Qoph" in t for t in texts)
    assert "100" not in texts  # the raw digit form is never searched as embeddable text
    assert not any("simple" in t for t in texts)  # Qoph's own properties never feed query text either


def test_query_texts_skip_directive_produces_no_query_at_all() -> None:
    """FR-RT-11: an interpretant carrying `query.directive: "skip"` contributes no
    query of any kind — neither a plain concept query nor a filter token —
    unlike `"filter"`, which still contributes the filtered variant."""
    manifestation_with_skip = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (
                Interpretant(id="interp-element", type="element", value="Fire"),
                Interpretant(
                    id="interp-skipped",
                    type="meaning",
                    value="eye of the needle",
                    query=QueryDirective(directive="skip"),
                ),
            )
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation_with_skip)

    query_texts = build_query_texts(graph_facts)

    assert query_texts == [("Fire", None)]
    assert not any("needle" in q.text for q in query_texts)


def test_query_texts_exact_directive_contributes_no_embeddable_query_at_all() -> None:
    """FR-EX-01: unlike an ordinary concept or a `"filter"`-directive token,
    an `"exact"`-directive interpretant is never embedded or ANN-searched —
    it contributes nothing to `build_query_texts` at all. It is matched
    entirely by `collect_exact_tokens`'s exhaustive document scan instead."""
    manifestation_with_exact = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (
                Interpretant(
                    id="interp-numeric-value",
                    type="numeric_value",
                    value="2",
                    query=QueryDirective(directive="exact"),
                ),
            )
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation_with_exact)

    query_texts = build_query_texts(graph_facts)

    assert query_texts == []


def test_region_id_round_trips_through_parse_region_id() -> None:
    assert parse_region_id(region_id_of("ecclesiasticus-vulgate", 0, 3)) == ("ecclesiasticus-vulgate", 0, 3)


def test_parse_region_id_rejects_a_missing_separator() -> None:
    with pytest.raises(ValueError, match="missing '::'"):
        parse_region_id("waite-0-1")


def test_parse_region_id_rejects_a_non_numeric_range() -> None:
    with pytest.raises(ValueError, match="non-numeric ordinal range"):
        parse_region_id("waite::first-last")


def test_collect_exact_tokens_defaults_as_token_to_value() -> None:
    """FR-EX-02: with no `as_token` given, an `"exact"`-directive token
    searches the interpretant's own value directly."""
    manifestation_with_exact = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (
                Interpretant(
                    id="interp-numeric-value",
                    type="numeric_value",
                    value="2",
                    query=QueryDirective(directive="exact"),
                ),
            )
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation_with_exact)

    (token,) = collect_exact_tokens(graph_facts)

    assert token.value == "2"
    assert token.as_token == "2"
    assert token.kind == "exact"


def test_collect_exact_tokens_honors_an_explicit_as_token() -> None:
    """FR-EX-02: an `"exact"`-directive interpretant's `as_token`, when
    given, is used as the literal search form instead of `value` — e.g. a
    numeral whose corpus surface form is spelled out."""
    manifestation_with_exact = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (
                Interpretant(
                    id="interp-numeric-value",
                    type="numeric_value",
                    value="100",
                    query=QueryDirective(directive="exact", as_token="hundred"),
                ),
            )
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation_with_exact)

    (token,) = collect_exact_tokens(graph_facts)

    assert token.value == "100"
    assert token.as_token == "hundred"


def test_collect_exact_tokens_never_touches_an_unrelated_concepts_query() -> None:
    """FR-EX-03: unlike a `"filter"`-directive token, which is collected
    globally and paired with every concept in the sign (see the gematria
    tests above), an `"exact"`-directive token never becomes part of any
    concept's query at all — `build_query_texts` for an unrelated concept in
    the same sign carries no trace of it."""
    manifestation_with_exact = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (
                Interpretant(id="interp-element", type="element", value="Fire"),
                Interpretant(
                    id="interp-numeric-value",
                    type="numeric_value",
                    value="2",
                    query=QueryDirective(directive="exact"),
                ),
            )
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation_with_exact)

    query_texts = build_query_texts(graph_facts)

    assert [q.text for q in query_texts] == ["Fire"]
    assert query_texts[0].filter_token is None
    (token,) = collect_exact_tokens(graph_facts)
    assert token.value == "2"


def test_retrieval_searches_the_full_corpus_with_no_scoping_filter(graph_store: KuzuGraphStore) -> None:
    """FR-CO-02: retrieval is never scoped by tradition — there is no tradition
    parameter left on `similarity_search` to pass one through. `match_pool_size`
    is what reaches `similarity_search`."""
    embedder = FakeEmbedder()
    vector_store = FakeVectorStore(hits=[])
    pipeline = RetrievalPipeline(
        graph_store=graph_store, vector_store=vector_store, embedder=embedder, match_pool_size=3
    )

    pipeline.retrieve_regions(GRAPH_FACTS)

    assert embedder.embedded_texts == [q.text for q in build_query_texts(GRAPH_FACTS)]
    assert vector_store.last_call == {
        "query_embedding": [1.0, 0.0],
        "top_k": 3,
        "document_contains": None,
    }


def test_a_region_is_attributed_to_an_independent_corpus_source(graph_store: KuzuGraphStore) -> None:
    """The concrete scenario FR-CO-02 exists for: a query about a tarot sign
    surfacing a passage from an independent corpus document, which carries no
    tradition of its own at all."""
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
    vector_store = DocumentFrequencyVectorStore(hits=[hit], corpus_size=100, document_frequencies={"Fire": 10})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(GRAPH_FACTS)

    (region,) = result.regions
    assert region.source.title == "The Holy Bible, Douay-Rheims, Complete"
    assert region.source.citation_label == "Douay-Rheims"
    assert "tower" in region.segments[0].text.lower()
    assert [match.interpretant for match in region.matches] == ["Fire"]
    assert region.matches[0].score == pytest.approx(0.7)


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
    and isolation *between* concepts (FR-RT-07)."""
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


def _make_hit(chunk_id: str, distance: float, ordinal: int = 0) -> VectorHit:
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
        ordinal=ordinal,
    )


def test_matching_never_fuses_across_different_concepts(graph_store: KuzuGraphStore) -> None:
    """Two concepts ("Fire", the sign's own interpretant; "Fish", the
    intersemiotic target's meaning) must never be merged into one shared pool
    (ADR-007) — each is searched on its own and contributes its own `Match`,
    even though the old flat-merge design would have combined them into a
    single ranked list."""
    graph_facts = _intersemiotic_graph_facts()
    hit_fire = _make_hit("waite-pictorial-key::fire-hit", distance=0.2, ordinal=0)
    hit_fish = _make_hit("waite-pictorial-key::fish-hit", distance=0.3, ordinal=1)
    vector_store = SequencedVectorStore(
        [[hit_fire], [hit_fish]], corpus_size=100, document_frequencies={"Fire": 10, "Fish": 10}
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    assert vector_store.call_count == 2
    (region,) = result.regions
    by_interpretant = {match.interpretant: match.segment_ordinal for match in region.matches}
    assert by_interpretant == {"Fire": 0, "Fish": 1}


def test_reciprocal_rank_fusion_decides_which_hits_survive_one_concepts_pool(
    graph_store: KuzuGraphStore,
) -> None:
    """*Within* one concept (the gematria pair: "Fish" plain + "Fish"+hundred
    filtered), Reciprocal Rank Fusion can rank a chunk found by both of that
    concept's queries above one found by only one of them, even when the
    latter's individual best distance is better — the whole point of ranking
    by rank rather than comparing raw scores (ADR-007). With the pool trimmed
    to one entry, the fused winner is the hit that reaches region rollup at
    all. This is unrelated to, and must not be confused with, fusion *across*
    concepts, which never happens (see the sibling 'never fuses across
    different concepts' test)."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    hit_x = _make_hit("waite-pictorial-key::X", distance=0.05, ordinal=7)  # best raw match, only in one query
    hit_y = _make_hit("waite-pictorial-key::Y", distance=0.5, ordinal=1)
    hit_y_filtered = _make_hit("waite-pictorial-key::Y", distance=0.4, ordinal=1)  # found by both Fish queries
    # 4 calls now that the gematria filter is global (Fire also gets a filtered variant):
    # Fire(None), Fire(hundred), Fish(None), Fish(hundred).
    vector_store = SequencedVectorStore(
        [[], [], [hit_x, hit_y], [hit_y_filtered]], corpus_size=100, document_frequencies={"Fish": 10}
    )
    pipeline = RetrievalPipeline(
        graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder(), match_pool_size=1
    )

    result = pipeline.retrieve_regions(graph_facts)

    (region,) = result.regions
    assert [segment.ordinal for segment in region.segments] == [1]
    # Y's match score is still its own best (lowest-distance) individual match.
    assert region.matches[0].score == pytest.approx(0.6)


def test_a_chunk_matched_by_two_queries_of_one_concept_keeps_its_best_score(
    graph_store: KuzuGraphStore,
) -> None:
    """The same segment can legitimately match both of one concept's queries
    (its plain form and its gematria-filtered variant) — it must contribute
    one `Match`, carrying its best (lowest-distance) score, not one per
    matching query."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    weaker_match = _make_hit("waite-pictorial-key::0", distance=0.6)
    stronger_match = _make_hit("waite-pictorial-key::0", distance=0.3)
    # 4 calls now that the gematria filter is global: Fire(None), Fire(hundred), Fish(None), Fish(hundred).
    vector_store = SequencedVectorStore(
        [[], [], [weaker_match], [stronger_match]], corpus_size=100, document_frequencies={"Fish": 10}
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    (region,) = result.regions
    fish_matches = [match for match in region.matches if match.interpretant == "Fish"]
    assert len(fish_matches) == 1
    assert fish_matches[0].score == pytest.approx(0.7)


def test_every_concepts_own_best_match_survives_even_when_globally_outranked(
    graph_store: KuzuGraphStore,
) -> None:
    """The concrete regression concept-scoped matching fixes: a well-supported
    concept's own best segment must survive even when several *other*
    concepts' hits would all individually outscore it on raw distance. The
    real case: for The Sun, 'laughter' (Qoph's Sepher Yetzirah foundation)
    ranked #1 within its own query, but lost a shared cutoff to unrelated,
    lower-signal concepts like 'naked child'/'white horse'/'red standard' that
    simply had better raw scores. Reproduced directly here: 'laughter' has the
    *worst* raw distance of the four concepts below, and still contributes its
    own match — there is no shared budget for it to be crowded out of."""
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
        [_make_hit("naked-child-hit", distance=0.1, ordinal=0)],
        [_make_hit("white-horse-hit", distance=0.15, ordinal=1)],
        [_make_hit("red-standard-hit", distance=0.2, ordinal=2)],
        [_make_hit("laughter-hit", distance=0.9, ordinal=3)],  # worst raw match of the four
    ]
    vector_store = SequencedVectorStore(hits_per_call, corpus_size=100, document_frequencies={})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    (region,) = result.regions
    assert {match.interpretant for match in region.matches} == {
        "naked child",
        "white horse",
        "red standard",
        "laughter",
    }
    laughter = next(match for match in region.matches if match.interpretant == "laughter")
    assert laughter.segment_ordinal == 3


def test_the_gematria_filter_reaches_the_vector_store_globally(graph_store: KuzuGraphStore) -> None:
    """End-to-end: an intersemiotic target's gematria value reaches the vector
    store as an actual `document_contains` filter *globally* — not just on
    its own sibling concept ("Fish"), but also on the sign's own unrelated
    "Fire" interpretant — never replacing any plain (unfiltered) search, just
    adding to every one of them (see pipeline.py's module docstring on why a
    hard filter would silently kill results for most cards, and on why the
    filter is global rather than scoped to the group the number came from)."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    vector_store = SequencedVectorStore(
        [[_make_hit("waite-pictorial-key::0", distance=0.1)], [], [], []],
        corpus_size=100,
        document_frequencies={"Fire": 10},
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    pipeline.retrieve_regions(graph_facts)

    # Query 1 ("Fire" plain) carries no filter; query 2 ("Fire" + gematria)
    # carries the filter too, even though "Fire" has nothing to do with Qoph
    # or gematria — the filter is global. Query 3 ("Fish" plain) carries
    # none; query 4 ("Fish" + gematria) carries it as an additional, not
    # replacing, search.
    assert vector_store.document_contains_per_call == [None, "hundred", None, "hundred"]


def test_an_exact_directive_value_is_never_embedded(graph_store: KuzuGraphStore) -> None:
    """FR-EX-01/FR-EX-03: an `"exact"`-directive interpretant's value never
    becomes an ANN query — it is found only through the separate, non-ANN
    `document_matches` scan, even when that scan and another concept's query
    surface the same chunk."""
    manifestation = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (
                Interpretant(id="interp-element", type="element", value="Fire"),
                Interpretant(
                    id="interp-numeric-value",
                    type="numeric_value",
                    value="2",
                    query=QueryDirective(directive="exact"),
                ),
            )
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation)
    shared_hit = _make_hit("shared", distance=0.2)
    vector_store = SequencedVectorStore(
        [[shared_hit]],
        corpus_size=100,
        document_frequencies={"Fire": 10, "2": 5},
        document_matches_by_term={"2": [shared_hit]},
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    assert vector_store.call_count == 1
    assert vector_store.document_matches_calls == ["2"]
    (region,) = result.regions
    assert {match.interpretant: match.kind for match in region.matches} == {"Fire": "concept", "2": "exact"}


# --- Specificity weighting (FR-RK-04–FR-RK-06) ---


def test_specificity_weight_is_strictly_higher_for_a_rarer_surface_form(graph_store: KuzuGraphStore) -> None:
    vector_store = DocumentFrequencyVectorStore(
        hits=[], corpus_size=200, document_frequencies={"laughter": 11, "hundred": 130}
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    rare_weight = pipeline._specificity_weight("laughter")
    common_weight = pipeline._specificity_weight("hundred")

    assert rare_weight > common_weight


def test_specificity_weight_handles_a_surface_form_absent_from_the_corpus(graph_store: KuzuGraphStore) -> None:
    """A surface form with `df == 0` must not divide by zero or raise on
    `log(0)` — floored at `df = 1`, the maximally rare finite case."""
    vector_store = DocumentFrequencyVectorStore(hits=[], corpus_size=200, document_frequencies={})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    weight = pipeline._specificity_weight("monkey")

    assert weight == pytest.approx(math.log(200))


# --- Region-centric retrieval (FR-RK-01–FR-RK-10) ---


def _make_segment_hit(
    chunk_id: str, *, ordinal: int, locator: str, distance: float, text: str | None = None
) -> VectorHit:
    return VectorHit(
        chunk_id=chunk_id,
        source_id="waite-pictorial-key",
        domain="tarot",
        text=text or f"Segment text for {chunk_id}.",
        chunk_index=ordinal,
        char_start=0,
        char_end=10,
        embedding_model="fake-embed",
        distance=distance,
        ordinal=ordinal,
        locator=locator,
        section="",
    )


def test_retrieve_regions_rolls_up_adjacent_ordinals_into_one_region(graph_store: KuzuGraphStore) -> None:
    """FR-RK-01/FR-RK-02: interpretant matches on adjacent segments of one source roll
    up into a single region, with the right `convergence_count`."""
    graph_facts = _intersemiotic_graph_facts()
    hit_fire = _make_segment_hit("waite-pictorial-key::100", ordinal=100, locator="Genesis 21:5", distance=0.3)
    hit_fish = _make_segment_hit("waite-pictorial-key::101", ordinal=101, locator="Genesis 21:6", distance=0.35)
    vector_store = SequencedVectorStore(
        [[hit_fire], [hit_fish]], corpus_size=200, document_frequencies={"Fire": 10, "Fish": 10}
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.convergence_count == 2
    assert {s.ordinal for s in region.segments} == {100, 101}
    assert {m.interpretant for m in region.matches} == {"Fire", "Fish"}


def test_retrieve_regions_each_match_anchors_to_its_own_segment(graph_store: KuzuGraphStore) -> None:
    """FR-RK-09: a match's `segment_ordinal` points at the specific segment it
    hit, not just the region as a whole."""
    graph_facts = _intersemiotic_graph_facts()
    hit_fire = _make_segment_hit("waite-pictorial-key::517", ordinal=517, locator="Genesis 21:5", distance=0.3)
    hit_fish = _make_segment_hit("waite-pictorial-key::518", ordinal=518, locator="Genesis 21:6", distance=0.35)
    vector_store = SequencedVectorStore([[hit_fire], [hit_fish]], corpus_size=200, document_frequencies={})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    region = result.regions[0]
    matches_by_interpretant = {m.interpretant: m for m in region.matches}
    assert matches_by_interpretant["Fire"].segment_ordinal == 517
    assert matches_by_interpretant["Fish"].segment_ordinal == 518


def test_retrieve_regions_deduplicates_a_segment_shared_by_two_interpretants(graph_store: KuzuGraphStore) -> None:
    graph_facts = _intersemiotic_graph_facts()
    hit_fire = _make_segment_hit("waite-pictorial-key::9", ordinal=9, locator="Genesis 21:6", distance=0.2)
    hit_fish = _make_segment_hit("waite-pictorial-key::9", ordinal=9, locator="Genesis 21:6", distance=0.25)
    vector_store = SequencedVectorStore([[hit_fire], [hit_fish]], corpus_size=200, document_frequencies={})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    region = result.regions[0]
    assert len(region.segments) == 1
    assert len(region.matches) == 2


def test_retrieve_regions_same_interpretant_matching_two_segments_keeps_only_its_best(
    graph_store: KuzuGraphStore,
) -> None:
    """FR-RK-01/FR-RK-05: within one region, an interpretant that matched more than
    one of its own segments keeps only its single best match — summing every
    per-segment occurrence would let a passage repeating one concept across
    many adjacent segments (e.g. a genealogy chapter repeating a number)
    inflate its score by simple repetition, the list-like-passage failure
    mode ADR-004 already rejected."""
    graph_facts = _intersemiotic_graph_facts()
    weaker_hit = _make_segment_hit("waite-pictorial-key::100", ordinal=100, locator="Genesis 21:5", distance=0.3)
    stronger_hit = _make_segment_hit("waite-pictorial-key::101", ordinal=101, locator="Genesis 21:6", distance=0.1)
    vector_store = SequencedVectorStore([[weaker_hit, stronger_hit], []], corpus_size=200, document_frequencies={})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    assert len(result.regions) == 1
    region = result.regions[0]
    fire_matches = [m for m in region.matches if m.interpretant == "Fire"]
    assert len(fire_matches) == 1
    assert fire_matches[0].segment_ordinal == 101
    assert fire_matches[0].score == pytest.approx(0.9)


def test_retrieve_regions_non_contiguous_ordinals_do_not_merge(graph_store: KuzuGraphStore) -> None:
    graph_facts = _intersemiotic_graph_facts()
    hit_fire = _make_segment_hit("waite-pictorial-key::1", ordinal=1, locator="Genesis 1:1", distance=0.2)
    hit_fish = _make_segment_hit("waite-pictorial-key::500", ordinal=500, locator="Genesis 40:1", distance=0.2)
    vector_store = SequencedVectorStore([[hit_fire], [hit_fish]], corpus_size=200, document_frequencies={})
    pipeline = RetrievalPipeline(
        graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder(), region_window_size=3
    )

    result = pipeline.retrieve_regions(graph_facts)

    assert len(result.regions) == 2


def test_retrieve_regions_isolated_single_interpretant_region_survives(graph_store: KuzuGraphStore) -> None:
    """FR-RK-03: with the default `region_min_interpretants=1`, a region matched
    by exactly one interpretant is eligible and rankable (the corrected
    model — isolated matches are first-class, not filtered out)."""
    graph_facts = _intersemiotic_graph_facts()
    hit_fire = _make_segment_hit("waite-pictorial-key::83", ordinal=83, locator="§83", distance=0.238)
    vector_store = SequencedVectorStore([[hit_fire], []], corpus_size=200, document_frequencies={})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    assert len(result.regions) == 1
    assert result.regions[0].convergence_count == 1


def test_retrieve_regions_below_min_interpretants_is_excluded(graph_store: KuzuGraphStore) -> None:
    graph_facts = _intersemiotic_graph_facts()
    hit_fire = _make_segment_hit("waite-pictorial-key::83", ordinal=83, locator="§83", distance=0.238)
    vector_store = SequencedVectorStore([[hit_fire], []], corpus_size=200, document_frequencies={})
    pipeline = RetrievalPipeline(
        graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder(), region_min_interpretants=2
    )

    result = pipeline.retrieve_regions(graph_facts)

    assert result.regions == ()


def test_retrieve_regions_below_floor_is_excluded(graph_store: KuzuGraphStore) -> None:
    graph_facts = _intersemiotic_graph_facts()
    weak_hit = _make_segment_hit("waite-pictorial-key::1", ordinal=1, locator="Genesis 1:1", distance=1.9)
    vector_store = SequencedVectorStore([[weak_hit], []], corpus_size=200, document_frequencies={})
    pipeline = RetrievalPipeline(
        graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder(), min_score=0.5
    )

    result = pipeline.retrieve_regions(graph_facts)

    assert result.regions == ()


def test_retrieve_regions_rare_interpretant_outweighs_a_ubiquitous_one_of_equal_strength(
    graph_store: KuzuGraphStore,
) -> None:
    """FR-RK-04–FR-RK-06: a rare surface form's higher specificity weight lets a
    two-real-interpretant region outrank a comparable single, and a rare
    interpretant outweighs a ubiquitous one at equal raw similarity."""
    graph_facts = _intersemiotic_graph_facts()
    rare_hit = _make_segment_hit("waite-pictorial-key::1", ordinal=1, locator="Genesis 1:1", distance=0.3)
    common_hit = _make_segment_hit("waite-pictorial-key::500", ordinal=500, locator="Genesis 40:1", distance=0.3)
    vector_store = SequencedVectorStore(
        [[rare_hit], [common_hit]], corpus_size=200, document_frequencies={"Fire": 2, "Fish": 100}
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    by_ordinal = {r.segments[0].ordinal: r.score for r in result.regions}
    assert by_ordinal[1] > by_ordinal[500]  # "Fire" (df=2) outweighs "Fish" (df=100) at equal similarity


def test_retrieve_regions_exact_match_scores_by_fixed_presence_strength(graph_store: KuzuGraphStore) -> None:
    """FR-RK-05: a literal-containment match contributes a fixed presence
    strength to the region score, not a computed similarity — but it does
    count toward `convergence_count` like any other matching interpretant
    (FR-RK-03). Reached via a `"filter"`-directive interpretant, so it is
    labeled `kind == "filter"` (FR-EX-05), not `"exact"` (reserved for a
    `query.directive: "exact"` interpretant)."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    hit = _make_segment_hit("waite-pictorial-key::1", ordinal=1, locator="Genesis 21:5", distance=0.3)
    # 4 calls: Fire(None), Fire(hundred), Fish(None), Fish(hundred) — hit only
    # returned by Fish's filtered query, so membership is via the token filter.
    vector_store = SequencedVectorStore(
        [[], [], [], [hit]], corpus_size=200, document_frequencies={"Fish": 10, "hundred": 10}
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    region = result.regions[0]
    assert len(region.matches) == 2  # "Fish" (concept) + "100" (filter)
    assert region.convergence_count == 2
    filter_match = next(m for m in region.matches if m.kind == "filter")
    assert filter_match.interpretant == "100"
    assert filter_match.exact_value is True


def test_retrieve_regions_lone_filter_directive_match_is_not_eligible(graph_store: KuzuGraphStore) -> None:
    """ADR-017/FR-RT-20: unlike an `"exact"`-directive match, a `"filter"`-
    directive match with no `"concept"` match converging in the same region
    does not make that region eligible on its own. Here "Fish"'s own
    similarity falls below the default floor, so the only surviving match at
    this segment is the filter-token one ("100") — and now no region
    survives at all, unlike an isolated `"exact"`-directive match reached the
    same way (`test_retrieve_regions_lone_exact_directive_match_is_eligible_on_its_own`)."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    weak_hit = _make_segment_hit("waite-pictorial-key::1", ordinal=1, locator="Genesis 21:5", distance=1.9)
    # 4 calls: Fire(None), Fire(hundred), Fish(None), Fish(hundred) — hit only
    # returned by Fish's filtered query, and its similarity (1 - 1.9 = -0.9)
    # falls below the default floor, so "Fish" contributes no concept match.
    vector_store = SequencedVectorStore(
        [[], [], [], [weak_hit]], corpus_size=200, document_frequencies={"Fish": 10, "hundred": 10}
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    assert result.regions == ()


def test_retrieve_regions_filter_plus_exact_is_eligible_without_a_concept(graph_store: KuzuGraphStore) -> None:
    """ADR-017: a region reached by a `"filter"` match together with an
    `"exact"` match — no `"concept"` match anywhere in it — remains eligible:
    the `"exact"` match satisfies FR-RT-20 on its own, and the `"filter"`
    match still contributes its fixed strength to the score and
    `convergence_count`, exactly as before this decision."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    graph_facts = graph_facts.model_copy(
        update={
            "manifestation": graph_facts.manifestation.model_copy(
                update={
                    "interpretants": (
                        Interpretant(
                            id="interp-numeric-value-exact",
                            type="numeric_value",
                            value="2",
                            query=QueryDirective(directive="exact"),
                        ),
                    )
                }
            )
        }
    )
    weak_hit = _make_segment_hit("waite-pictorial-key::1", ordinal=1, locator="Genesis 21:5", distance=1.9)
    exact_hit = _make_segment_hit("waite-pictorial-key::1", ordinal=1, locator="Genesis 21:5", distance=1.9)
    # Only "Fish" remains a concept (the manifestation's own interpretant is
    # now the exact directive, contributing no embeddable query): 2 calls,
    # Fish(None) -> [], Fish(hundred) -> [weak_hit], its similarity below the
    # floor so "Fish" contributes no concept match either.
    vector_store = SequencedVectorStore(
        [[], [weak_hit]],
        corpus_size=200,
        document_frequencies={"Fish": 10, "hundred": 10},
        document_matches_by_term={"2": [exact_hit]},
    )
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    assert len(result.regions) == 1
    region = result.regions[0]
    assert {m.kind for m in region.matches} == {"filter", "exact"}
    assert region.convergence_count == 2


def test_retrieve_regions_exact_directive_reports_membership_only_no_score(
    graph_store: KuzuGraphStore,
) -> None:
    """FR-EX-01/04: an `"exact"`-directive interpretant's match is
    membership-only (`kind == "exact"`, `score == 0.0`) — it is never
    embedded, so it never competes with a `"concept"` match for the same
    value. Its segment is still fully hydrated (locator, text) purely from
    `document_matches`'s exhaustive scan, with no ANN query or embedding
    involved for it at all."""
    manifestation = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (
                Interpretant(id="interp-element", type="element", value="Fire"),
                Interpretant(
                    id="interp-numeric-value",
                    type="numeric_value",
                    value="2",
                    query=QueryDirective(directive="exact"),
                ),
            )
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation)
    hit = _make_segment_hit("waite-pictorial-key::1", ordinal=1, locator="Genesis 1:1", distance=0.3)
    # 1 ANN call: Fire(plain) lands on the same segment "2"'s document scan
    # finds, so both matches merge into one eligible region.
    vector_store = SequencedVectorStore([[hit]], document_matches_by_term={"2": [hit]})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    region = result.regions[0]
    assert region.segments[0].locator == "Genesis 1:1"
    assert len(region.matches) == 2  # "Fire" (concept) + "2" (exact)
    assert region.convergence_count == 2
    two_match = next(m for m in region.matches if m.interpretant == "2")
    assert two_match.kind == "exact"
    assert two_match.score == 0.0
    assert two_match.exact_value is True
    assert vector_store.document_matches_calls == ["2"]


def test_retrieve_regions_lone_exact_directive_match_is_eligible_on_its_own(
    graph_store: KuzuGraphStore,
) -> None:
    """FR-RK-03: a region matched by exactly one interpretant is eligible and
    rankable regardless of kind — an `"exact"`-directive value with no
    nearby concept match at all still forms its own region. This is the
    whole point of `"exact"`: every literal occurrence of the token
    surfaces, not only the ones sitting next to a semantic match."""
    manifestation = THE_TOWER_MANIFESTATION.model_copy(
        update={
            "interpretants": (
                Interpretant(
                    id="interp-numeric-value",
                    type="numeric_value",
                    value="2",
                    query=QueryDirective(directive="exact"),
                ),
            )
        }
    )
    graph_facts = GraphFacts(sign=THE_TOWER, manifestation=manifestation)
    hit = _make_segment_hit("waite-pictorial-key::1", ordinal=1, locator="Genesis 1:1", distance=0.3)
    vector_store = SequencedVectorStore([], document_matches_by_term={"2": [hit]})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.convergence_count == 1
    (match,) = region.matches
    assert match.interpretant == "2"
    assert match.kind == "exact"
    assert match.score == 0.0


def test_retrieve_regions_anchors_an_exact_match_that_never_survives_a_concepts_own_deep_pool(
    graph_store: KuzuGraphStore,
) -> None:
    """An exact-token hit can be squeezed out of every *concept's* own RRF-
    ranked pool (`match_pool_size`) by chunks that rank in both that
    concept's plain and filtered queries, while still being a genuine,
    provable containment match from the filtered query's raw results — the
    real case found in Genesis: "hundred" at 21:5 never ranks highly enough
    for "child" alone to survive that concept's own pool, but the token
    match is still real and must still anchor its segment into a region,
    pulling it in alongside a neighboring genuine concept match (21:6's
    "laughter")."""
    graph_facts = _gematria_intersemiotic_graph_facts()
    concept_hit = _make_segment_hit("waite-pictorial-key::100", ordinal=100, locator="Genesis 21:6", distance=0.2)
    exact_only_hit = _make_segment_hit("waite-pictorial-key::99", ordinal=99, locator="Genesis 21:5", distance=0.9)
    # Fish plain ranks `concept_hit` #1; Fish filtered ranks `concept_hit` #1
    # again (so its RRF score, summed across both queries, wins the
    # `match_pool_size=1` cutoff) and `exact_only_hit` #2 (squeezed out of
    # the deep pool, but still a real filtered-query hit).
    vector_store = SequencedVectorStore(
        [[], [], [concept_hit], [concept_hit, exact_only_hit]],
        corpus_size=200,
        document_frequencies={},
    )
    pipeline = RetrievalPipeline(
        graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder(), match_pool_size=1
    )

    result = pipeline.retrieve_regions(graph_facts)

    assert len(result.regions) == 1
    region = result.regions[0]
    assert {s.ordinal for s in region.segments} == {99, 100}
    filter_match = next(m for m in region.matches if m.kind == "filter")
    assert filter_match.segment_ordinal == 99
    assert filter_match.score == 0.0


def test_retrieve_regions_facets_count_eligible_regions(graph_store: KuzuGraphStore) -> None:
    graph_facts = _intersemiotic_graph_facts()
    hit_fire = _make_segment_hit("waite-pictorial-key::9", ordinal=9, locator="Genesis 21:6", distance=0.2)
    hit_fish = _make_segment_hit("waite-pictorial-key::9", ordinal=9, locator="Genesis 21:6", distance=0.25)
    vector_store = SequencedVectorStore([[hit_fire], [hit_fish]], corpus_size=200, document_frequencies={})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    result = pipeline.retrieve_regions(graph_facts)

    assert result.facets.sources[0].id == "waite-pictorial-key"
    assert result.facets.sources[0].count == 1
    interpretant_counts = {f.value: f.count for f in result.facets.interpretants}
    assert interpretant_counts == {"Fire": 1, "Fish": 1}


# --- Query/filter-token logging (FR-QEL-07, FR-QEL-08) ---


def test_search_deep_pools_logs_each_concepts_plain_and_filtered_query_variants(
    graph_store: KuzuGraphStore, caplog: pytest.LogCaptureFixture
) -> None:
    graph_facts = _gematria_intersemiotic_graph_facts()
    fish_hit = _make_hit("waite-pictorial-key::0", distance=0.2)
    # 4 calls: Fire(None), Fire(hundred), Fish(None), Fish(hundred).
    vector_store = SequencedVectorStore([[], [], [fish_hit], []], corpus_size=100, document_frequencies={"Fish": 10})
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    with caplog.at_level(logging.INFO, logger="mythrix.core.retrieval.pipeline"):
        pipeline.retrieve_regions(graph_facts)

    messages = [record.getMessage() for record in caplog.records]
    fish_lines = [m for m in messages if "concept='Fish'" in m]
    assert len(fish_lines) == 1
    assert "'Fish'" in fish_lines[0]
    assert "'Fish+filter:hundred'" in fish_lines[0]
    assert "hits_above_floor=1" in fish_lines[0]


def test_search_deep_pools_logs_a_filter_token_with_zero_matching_chunks(
    graph_store: KuzuGraphStore, caplog: pytest.LogCaptureFixture
) -> None:
    graph_facts = _gematria_intersemiotic_graph_facts()
    # 4 calls: Fire(None), Fire(hundred), Fish(None), Fish(hundred) — none match.
    vector_store = SequencedVectorStore([[], [], [], []])
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    with caplog.at_level(logging.INFO, logger="mythrix.core.retrieval.pipeline"):
        pipeline.retrieve_regions(graph_facts)

    messages = [record.getMessage() for record in caplog.records]
    assert any("filter_token='100'" in m and "as_token='hundred'" in m and "hits=0" in m for m in messages)


def _segment(ordinal: int, locator: str) -> Segment:
    return Segment(ordinal=ordinal, locator=locator, text="…", section="")


def test_region_locator_reuses_a_single_segments_own_locator() -> None:
    assert region_locator((_segment(1, "Genesis 21:5"),)) == "Genesis 21:5"


def test_region_locator_merges_a_shared_prefix_into_a_range() -> None:
    """The label a multi-segment region is cited by (FR-RT-05) — the two
    locators collapse to one reference rather than reading as two."""
    segments = (_segment(1, "Genesis 21:5"), _segment(2, "Genesis 21:6"), _segment(3, "Genesis 21:8"))

    assert region_locator(segments) == "Genesis 21:5–8"


def test_region_locator_joins_both_locators_in_full_when_no_prefix_is_shared() -> None:
    """A region spanning a chapter boundary cannot be written as one
    `chapter:verse` range without naming a verse in the wrong chapter."""
    segments = (_segment(1, "Genesis 21:8"), _segment(2, "Genesis 22:1"))

    assert region_locator(segments) == "Genesis 21:8–Genesis 22:1"


def test_region_locator_reuses_the_shared_locator_when_first_and_last_are_identical() -> None:
    """A `chapter_section` source with no subsection layer gives every
    paragraph in a chapter the same locator, so a region confined to one
    chapter must not read as that locator joined with itself."""
    label = "9. CHAPTER IX. MYTHOLOGY (_continued_)."
    segments = (_segment(1, label), _segment(2, label), _segment(3, label))

    assert region_locator(segments) == label


def test_region_locator_merges_bahir_style_numbered_sections_into_a_grouped_range() -> None:
    """A multi-segment Bahir region must produce `"§§83–90"`, not a crude
    `"§83–§90"` concatenation of two already-correct single-point
    locators."""
    segments = (_segment(1, "§83"), _segment(2, "§90"))

    assert region_locator(segments) == "§§83–90"


def _chapter_section_segment(
    ordinal: int,
    *,
    chapter_ordinal: int,
    chapter_title: str,
    subsection_ordinal: int = 0,
    subsection_title: str = "",
) -> Segment:
    return Segment(
        ordinal=ordinal,
        locator="",
        text="…",
        section=f"{chapter_ordinal}. {chapter_title}",
        chapter_ordinal=chapter_ordinal,
        chapter_title=chapter_title,
        subsection_ordinal=subsection_ordinal,
        subsection_title=subsection_title,
    )


def test_region_locator_formats_a_single_chapter_section_segment() -> None:
    segments = (
        _chapter_section_segment(
            1,
            chapter_ordinal=7,
            chapter_title="Isis, the Virgin of the World",
            subsection_ordinal=19,
            subsection_title="THE THREE SUNS",
        ),
    )

    assert region_locator(segments) == "Ch. 7: Isis, the Virgin of the World — §19: The Three Suns"


def test_region_locator_groups_a_chapter_section_region_spanning_two_subsections() -> None:
    segments = (
        _chapter_section_segment(
            1,
            chapter_ordinal=7,
            chapter_title="Isis, the Virgin of the World",
            subsection_ordinal=19,
            subsection_title="THE THREE SUNS",
        ),
        _chapter_section_segment(
            2,
            chapter_ordinal=7,
            chapter_title="Isis, the Virgin of the World",
            subsection_ordinal=20,
            subsection_title="THE CELESTIAL INHABITANTS OF THE SUN",
        ),
    )

    assert region_locator(segments) == (
        "Ch. 7: Isis, the Virgin of the World — §§19–20: The Three Suns–The Celestial Inhabitants of the Sun"
    )
