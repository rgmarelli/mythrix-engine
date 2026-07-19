"""`RetrievalPipeline`: turns deterministic graph facts into grounding document
passages (plan.md "Chroma vector store design", FR7/FR8/FR13).

Similarity-search query text is built entirely from already-retrieved
`GraphFacts` (attribute values) — never from raw user input (FR8) — as *many*
separate queries, one per individual atomic concept, never grouped into a
combined string: one query per atomic concept in each of the symbol's own
attributes/keywords, and for every `corresponds_to` relationship (FR3, FR19),
one per atomic concept about the target. A value that lists several distinct
concepts separated by commas (e.g. a Hebrew letter's `meaning`, "Monkey, eye
of the needle") is split further still, one query per concept — those aren't
one idea, they're several sharing a key, and one ("eye of the needle" — an
impossible-thing-made-possible image, echoing a child born to hundred-year-old
parents) can be exactly the useful part while another ("Monkey") contributes
nothing. No `key:` label is included (see the TODO below on why that's
deliberately unresolved rather than reasoned out), and there's no combined
descriptive-identity query either: a symbol's own canonical name/display
name/summary are no longer searched at all, only its individual attribute
values, so every symbol is represented by comparably short, atomic queries
rather than some being diluted by a long paragraph others don't have.

An exact numeric value (`value_type: integer`, e.g. a Hebrew letter's
gematria) is a special case, handled differently from every other concept:
semantic similarity can't distinguish "this passage happens to mention some
number" from "this passage mentions exactly this number" — a real case found
`numeric_value: 100` (bare, embedded as text) surfacing a passage about
measuring units ("the ephi and the bate") with no thematic connection to
anything, purely because it also contains numbers. So a recognized numeric
value is converted to its English word form (`_NUMBER_WORDS`) and used as a
literal-text filter (`document_contains`, `ChromaVectorStore.similarity_search`)
— but as a *second, additional* query alongside each plain concept query, not
a replacement for it. An earlier version made the filtered version replace
the plain one, which silently returns zero results for any card where no
single passage happens to combine the exact number and the concept — for
most symbols, most of the time, since that's a fairly specific coincidence.
Killing real candidates that way is worse than an occasional missed boost, so
now every concept is always searched plainly too; the filtered variant is
purely additive, a second independent ranking that rewards (via Reciprocal
Rank Fusion) a passage combining both signals without excluding one that only
matches the concept. See `_fact_queries`.

A real query (The Sun, corresponding to the Hebrew letter Qoph) drove every
round of this design, in order: embedding "laughter" (Qoph's Sepher Yetzirah
foundation) completely alone ranked the one Bible passage it should surface at
#4 of ~1600 chunks; grouped with Qoph's *other* facts (one query per
relationship, not yet per fact) it only reached #57; labelled with its own key
("foundation: laughter" instead of bare "laughter") it dropped to #30;
averaged into one ~30-word query combining everything the card and the letter
both carry, it dropped past #100. Isolating every concept this far (see
`build_query_texts`) got "laughter" back to #4 *within its own search* — but
it still didn't survive the final merge, because that merge compared raw
cosine scores across differently-distributed queries: "hebrew_letter Qoph" (a
bare proper name) scored *higher* across the board than "laughter" purely
because "Qoph" sits closer to generic ceremonial/priestly vocabulary in the
embedding space, nothing to do with relevance. Reciprocal Rank Fusion
(`RetrievalPipeline.retrieve`) and disabling the bare target-name query
(`_relationship_query_texts`) fixed that. The exact-number filter above is the
newest fix, for a different failure mode found afterward: `numeric_value: 100`
surfacing thematically unrelated passages that merely contained other numbers.

TODO(retrieval-semantics): dropping the `key:` label measurably helped in some
cases above and hurt in others — there was no clean universal rule, just a
per-fact empirical trade-off, and the label was cut anyway because "search the
bare value" was the simpler, more predictable default to start from. Revisit
whether some lighter-weight semantic signal could recover the cases a bare
label would have helped, without reintroducing the cases it hurt — worth
checking specifically against the Hebrew letter data (`meaning` vs
`foundation` vs `constellation`/`planet` currently look identical to
retrieval once the label's gone, despite being conceptually distinct kinds of
fact).

TODO(retrieval-semantics): a `corresponds_to` target's bare name (e.g. "Qoph")
is disabled as its own query for now, for every relationship regardless of
domain — not special-cased to Hebrew letters specifically, since the same
failure mode (a bare proper noun scoring high for generic reasons unrelated to
meaning) will recur for any symbol system's names, not just this one. But the
name genuinely is a useful, specific search target in the right corpus — e.g.
Psalm 119's stanzas are each headed by a Hebrew letter name, and a corpus that
was itself Kabbalistic (the Sepher Yetzirah, the Bahir) would discuss these
names constantly and meaningfully. Revisit as a corpus-aware or
per-relationship-type decision, not a blanket on/off switch, once there's a
concrete case that needs it.

Retrieval searches the full document corpus by default (FR7) — an independent,
uploaded document (e.g. a scriptural text) is meant to be read *through* the
graph's established symbolism, not excluded just because it carries a different
tradition tag; see plan.md's Risks for what this deliberately does not yet solve
(blending competing *interpretive* traditions, should a second one ever be
added). Each hit is hydrated into a `RetrievedPassage` carrying the full
verbatim chunk text plus its `Source`/`Tradition`, so the CLI can render a
References section without re-reading the original document file (FR13).
"""

from __future__ import annotations

from typing import NamedTuple

from mythrix.core.embedding import Embedder
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Attribute, GraphFacts, RelationshipFact, RetrievalContext, RetrievedPassage
from mythrix.core.vector.store import ChromaVectorStore, VectorHit

# Damping constant for Reciprocal Rank Fusion (Cormack et al., 2009) — large
# enough that a result's contribution depends mostly on how high it ranked
# *within* its own query, not on how many queries happened to surface it or
# how that query's raw score distribution compares to another's.
_RRF_K = 60

# English word forms for the integer values this project's data actually
# uses (Hebrew letter gematria: the 22 letters' values are 1-10, 20-90, then
# 100/200/300/400) — not a general-purpose number-to-words converter, just
# enough to turn a recognized exact value into literal search text. See this
# module's docstring on why an exact value needs this instead of being
# embedded as a normal concept query.
_NUMBER_WORDS: dict[int, str] = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    20: "twenty",
    30: "thirty",
    40: "forty",
    50: "fifty",
    60: "sixty",
    70: "seventy",
    80: "eighty",
    90: "ninety",
    100: "hundred",
    200: "two hundred",
    300: "three hundred",
    400: "four hundred",
}


class _Query(NamedTuple):
    """One retrieval query: the text to embed, and an optional literal-text
    filter (`ChromaVectorStore.similarity_search`'s `document_contains`) to
    combine with it — see this module's docstring on when a query gets one."""

    text: str
    document_contains: str | None = None


class RetrievalPipeline:
    def __init__(
        self,
        *,
        graph_store: KuzuGraphStore,
        vector_store: ChromaVectorStore,
        embedder: Embedder,
        top_k: int = 6,
        min_score: float = 0.0,
    ) -> None:
        self._graph_store = graph_store
        self._vector_store = vector_store
        self._embedder = embedder
        self._top_k = top_k
        self._min_score = min_score

    def retrieve(self, graph_facts: GraphFacts) -> RetrievalContext:
        """Deterministic Kùzu-then-Chroma retrieval (FR9): `graph_facts` must
        already be the result of `KuzuGraphStore.get_interpretation` — this
        method never touches Kùzu's query surface itself, only the resulting
        facts, plus `KuzuGraphStore.get_source`/`get_tradition` to hydrate hits.

        Runs one similarity search per query from `build_query_texts` (one
        per individual atomic concept, some carrying an exact-value text
        filter — see this module's docstring), rather than a single combined
        query. Hits are merged by Reciprocal Rank Fusion: each chunk's fused
        score is the sum of `1 / (_RRF_K + rank)` (1-based rank within that
        specific query's own results) across every query that surfaced it —
        not by comparing raw cosine scores across queries, which this
        module's docstring explains isn't a fair comparison. The chunk's
        *displayed* score is still its best (lowest-distance) individual
        match, for `min_score` filtering and for what a researcher actually
        sees.
        """
        queries = build_query_texts(graph_facts)
        query_embeddings = self._embedder.embed([query.text for query in queries])

        best_hit_by_chunk_id: dict[str, VectorHit] = {}
        rrf_score_by_chunk_id: dict[str, float] = {}
        for query, embedding in zip(queries, query_embeddings, strict=True):
            hits = self._vector_store.similarity_search(
                embedding, top_k=self._top_k, document_contains=query.document_contains
            )
            for rank, hit in enumerate(hits, start=1):
                existing = best_hit_by_chunk_id.get(hit.chunk_id)
                if existing is None or hit.distance < existing.distance:
                    best_hit_by_chunk_id[hit.chunk_id] = hit
                rrf_score_by_chunk_id[hit.chunk_id] = rrf_score_by_chunk_id.get(hit.chunk_id, 0.0) + 1.0 / (
                    _RRF_K + rank
                )

        ranked_chunk_ids = sorted(
            rrf_score_by_chunk_id, key=lambda chunk_id: rrf_score_by_chunk_id[chunk_id], reverse=True
        )
        ranked_hits = [best_hit_by_chunk_id[chunk_id] for chunk_id in ranked_chunk_ids[: self._top_k]]
        passages = tuple(self._hydrate(hit) for hit in ranked_hits if _similarity_score(hit) >= self._min_score)
        return RetrievalContext(graph_facts=graph_facts, passages=passages)

    def _hydrate(self, hit: VectorHit) -> RetrievedPassage:
        source = self._graph_store.get_source(hit.source_id)
        tradition = self._graph_store.get_tradition(hit.tradition_slug)
        return RetrievedPassage(
            chunk_id=hit.chunk_id,
            source=source,
            tradition=tradition,
            text=hit.text,
            locator=hit.locator,
            score=_similarity_score(hit),
            chunk_index=hit.chunk_index,
            char_start=hit.char_start,
            char_end=hit.char_end,
            embedding_model=hit.embedding_model,
        )


def _is_retrievable(attribute: Attribute) -> bool:
    """Whether curator-declared data should feed retrieval query construction
    (FR8) — a call the curator makes per-fact in the YAML (`Attribute.retrievable`),
    not something this module infers from a key name or value type. Both were
    tried here and were wrong: hardcoding the key `"number"` baked a domain
    assumption (tarot cards have deck positions) into supposedly domain-agnostic
    retrieval code, and before that, excluding every `value_type: integer` fact
    wrongly dropped a Hebrew letter's gematria value — real symbolic content in
    Kabbalah, not an identifier, despite also being a number. `retrievable` is
    data, so no code change is needed the next time a new domain's numbers turn
    out to matter (or not)."""
    return attribute.retrievable


def _atomic_values(value: str) -> list[str]:
    """A comma-separated value (e.g. a Hebrew letter's `meaning`, "Monkey, eye
    of the needle") lists several distinct concepts sharing one curator-chosen
    key, not a single unified phrase — split it so each concept is searched
    entirely on its own. A value with no comma is already atomic and comes
    back as a one-item list; see this module's docstring for the concrete
    case this exists for."""
    return [part.strip() for part in value.split(",") if part.strip()]


def _number_word(value: str) -> str | None:
    """The English word form of an integer-valued attribute (e.g. "100" ->
    "hundred"), if it's one this project's data actually uses — `None` for
    anything else (not a number, or a number outside `_NUMBER_WORDS`), so an
    unrecognized value just falls back to being searched as plain text in
    `_fact_queries` rather than silently dropped."""
    try:
        return _NUMBER_WORDS.get(int(value))
    except ValueError:
        return None


def _fact_queries(attributes: tuple[Attribute, ...]) -> list[_Query]:
    """Every retrievable attribute's value, decomposed to one query per atomic
    concept (`_atomic_values`), no `key:` label (see this module's docstring
    TODO on why that's cut without a settled replacement) — plus, when this
    group has a recognized exact numeric value (`value_type: integer`, e.g. a
    Hebrew letter's gematria), one *additional* filtered variant of every
    concept query, combined with the number as a literal-text filter.

    Deliberately a boost, not a hard requirement: an earlier version made the
    numeric fact *replace* its group's concept queries with filtered-only
    versions, which silently returns zero results for any card where no
    single passage happens to combine the number and the concept — killing
    real candidates is worse than an occasional missed boost. Now every
    concept is always searched plainly (nothing is ever lost), and the
    filtered variant only adds a *second* independent ranking that rewards a
    passage combining both signals — via Reciprocal Rank Fusion
    (`RetrievalPipeline.retrieve`), a passage matching both ranks higher than
    one matching only the concept, without excluding the latter. If there's a
    numeric value but no other concepts in this group, it's searched as plain
    text on its own — a filter with nothing to filter isn't useful."""
    number_word: str | None = None
    concepts: list[str] = []
    for attribute in attributes:
        if not _is_retrievable(attribute):
            continue
        if attribute.value_type == "integer":
            word = _number_word(attribute.value)
            if word:
                number_word = number_word or word
                continue
        concepts.extend(_atomic_values(attribute.value))

    if not concepts:
        return [_Query(text=number_word)] if number_word else []

    queries = [_Query(text=concept) for concept in concepts]
    if number_word:
        queries += [_Query(text=concept, document_contains=number_word) for concept in concepts]
    return queries


def _relationship_query_texts(relationship: RelationshipFact) -> list[_Query]:
    """One query per *individual atomic concept* about a `corresponds_to`
    target — its own symbol-level properties (e.g. gematria value, meaning)
    and its own interpretation-level attributes across every tradition it's
    interpreted under (`target_semantic_facts`, e.g. its Sepher Yetzirah
    `foundation`), combined into one `_fact_queries` group so a numeric value
    living in `properties` still gets applied as a filter to concepts living
    in `target_semantic_facts`, and vice versa. Both are already hydrated by
    `KuzuGraphStore._get_symbol_relationships`, so this needs no extra graph
    fetch here.

    Deliberately does *not* query the target's bare name (e.g. "Qoph") on its
    own — see this module's docstring TODO on why that's disabled for now."""
    target = relationship.target_symbol
    return _fact_queries(target.properties + relationship.target_semantic_facts)


def build_query_texts(graph_facts: GraphFacts) -> list[_Query]:
    """One query per individual atomic concept reachable from the queried
    symbol (FR8): one per atomic concept in each attribute of the symbol's
    own interpretation, then for each `corresponds_to` relationship (FR3,
    FR19), one per individual atomic concept about the target — see this
    module's docstring for why keeping every concept this isolated matters,
    for why there's no combined descriptive-identity query (the symbol's own
    canonical name/display name/summary aren't searched at all), and for
    when a query carries an exact-value text filter instead of being a plain
    concept. `RetrievalPipeline.retrieve` embeds and searches every one, then
    merges the results by rank (RRF), not raw score."""
    symbol, interpretation = graph_facts.symbol, graph_facts.interpretation
    queries = _fact_queries(interpretation.attributes)
    for relationship in symbol.relationships:
        queries += _relationship_query_texts(relationship)
    return [query for query in queries if query.text]


def _similarity_score(hit: VectorHit) -> float:
    """`ChromaVectorStore` is configured for cosine distance (`[0, 2]`, 0 =
    identical) — `1 - distance` gives a similarity score where higher is
    better, matching `Settings.retrieval_min_score`'s "keep at or above this"
    semantics."""
    return 1.0 - hit.distance
