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
matches the concept. See `_fact_queries`. Because that filter is a *hard*
Chroma `where_document` constraint, every hit it returns provably contains the
number — which is what lets the number appear as a first-class member of a
concept pair (FR28, see "Concept-pair convergence" below).

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

**Concept-scoped retrieval (FR24).** Results are grouped by concept — every
`_Query` derived from the same atomic value (its plain form plus, if present,
its exact-value-filtered variant; see `_fact_queries`) shares that value as
its `text`, which doubles as the concept's grouping key. Each concept's hits
are Reciprocal-Rank-Fused *only against that concept's own queries* and kept
up to `top_k` **per concept**, never merged into one shared pool across
concepts. This is a deliberate fix, not a tuning tweak: a card with a precise
numeric fact can generate many more queries than one without (see the module
docstring above), and merging everything into one shared final cutoff let a
handful of low-signal concepts (e.g. `naked child`, `white horse`) crowd out
a high-signal one (`laughter`, ranked #1 within its own query) purely by
outnumbering it — confirmed against the real `~/.mythrix` store for The Sun.
Concept-scoping means every concept gets its own retrieval budget instead of
competing for a shared one.

**Exact-number filters now apply globally, not just within the group they
came from (`build_query_texts`).** Originally a recognized numeric value
(e.g. Qoph's gematria, `numeric_value: 100`) only filtered concepts in its
*own* `_fact_queries` group — Qoph's own `meaning`/`foundation`/`constellation`
concepts got the "hundred" filter, but The Sun's own keywords (`naked`,
`child`, ...) never did, even though a real passage can combine a concept
from one part of the graph with a number from a completely different part
(Genesis 21: a *child* born when his father was *a hundred* years old).
Confirmed empirically before changing this: querying `child` + the `hundred`
filter (combining a keyword that had never gotten this filter with a number
from an unrelated relationship) ranked the Genesis 21 passage at #3 and the
Genesis 17 passage (a second, independent laughter-at-a-hundred-years-old
account, "Abraham fell upon his face, and laughed... shall a son be born to
him that is a hundred years old?") at #25 — the best combined ranking for
*both* passages found across every query shape tried, better than any single
concept alone. So every recognized number anywhere in a query's `GraphFacts`
(the symbol's own attributes, and every `corresponds_to` target's facts) is
now collected once (`_collect_numbers`) and applied as an additional
filtered variant to *every* concept's plain query, regardless of which group
originated the number — still additive, never replacing the plain query, per
the boost-not-hard-filter principle above.

**Concept-pair convergence (FR27, FR28).** Per-concept grouping above discards
the single most useful thing retrieval knows: when two independently-derived
concepts retrieve the *same* passage, that convergence is itself the finding.
Under concept-scoping alone, Genesis 21:5 — a child born to a hundred-year-old
father, named "laughter" — is merely an ordinary member of the `child` list and
of the `laughter` list, with nothing recording that it was one passage all
along. `RetrievalPipeline.retrieve` therefore also emits one
`ConceptPairCandidates` per co-occurring concept pair, *alongside* (never
instead of) the per-concept groups. Because the groups are additive, a strong
single-concept match cannot lose to a convergent one — it still stands in its
own group — so no ranking rule has to adjudicate between the two.

Two details carry the design. First, pairs are detected against a pool deeper
than the one displayed (`match_pool_size` vs `top_k`): intersecting only the
displayed candidates would miss a passage ranked #1 for one concept and #9 for
another, which is exactly the lopsided-but-real convergence worth surfacing.
Second, a pair's combined score is the *geometric* mean of its semantic
components, clamped at zero (`_combined_score`) — convergence is conjunctive,
not additive, and only a geometric mean distinguishes a passage scoring
(0.57, 0.53) from one scoring (0.90, 0.20), which share both a sum and a mean
despite only the first genuinely sitting at the intersection. That distinction
is *created* by the deep pool: at display depth alone, anything appearing in
two lists was decent at both, so lopsided pairs were rare and the formula
wouldn't have mattered. An exact numeric value contributes membership but no
score (FR28) — it arrives via a hard text filter, so its match is a guarantee
rather than a magnitude, and scoring it as 1.0 would let every number-bearing
pair dominate the output.

Scores are comparable only *within* a pair group, where every candidate is
scored by the same two queries so any per-query bias is constant across the
rows being compared. They are not comparable across groups — see plan.md's
Risks, and this module's own history above on why raw cross-query score
comparison was abandoned for RRF in the first place.
"""

from __future__ import annotations

import itertools
import math
from typing import NamedTuple

from mythrix.core.embedding import Embedder
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import (
    Attribute,
    ConceptCandidates,
    ConceptMatchScore,
    ConceptPairCandidates,
    GraphFacts,
    MergedCandidate,
    RelationshipFact,
    RetrievalContext,
    RetrievedPassage,
    Source,
    Tradition,
)
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


class _Number(NamedTuple):
    """A recognized exact numeric value in two forms: `value` as the curator
    authored it ("100"), which is what a researcher recognizes and what appears
    as a pair member (FR28), and `word` as it must be searched ("hundred"),
    since the corpus spells numbers out. Kept together because the search form
    alone is not presentable and the authored form alone is not searchable."""

    value: str
    word: str


class _Query(NamedTuple):
    """One retrieval query: the text to embed, and an optional exact value to
    combine with it as a literal-text filter — see this module's docstring on
    when a query gets one.

    `number` carries the whole `_Number` rather than just the search word so a
    hit can be attributed back to the authored value (FR28). Every hit from a
    query bearing one provably contains that number: `document_contains` is a
    hard `where_document` constraint, not a boost."""

    text: str
    number: _Number | None = None

    @property
    def document_contains(self) -> str | None:
        return self.number.word if self.number else None


class RetrievalPipeline:
    def __init__(
        self,
        *,
        graph_store: KuzuGraphStore,
        vector_store: ChromaVectorStore,
        embedder: Embedder,
        top_k: int = 6,
        match_pool_size: int = 30,
        merge_top_k: int = 6,
        min_score: float = 0.0,
    ) -> None:
        self._graph_store = graph_store
        self._vector_store = vector_store
        self._embedder = embedder
        self._top_k = top_k
        self._match_pool_size = match_pool_size
        self._merge_top_k = merge_top_k
        self._min_score = min_score

    def retrieve(self, graph_facts: GraphFacts) -> RetrievalContext:
        """Deterministic Kùzu-then-Chroma retrieval (FR9): `graph_facts` must
        already be the result of `KuzuGraphStore.get_interpretation` — this
        method never touches Kùzu's query surface itself, only the resulting
        facts, plus `KuzuGraphStore.get_source`/`get_tradition` to hydrate hits.

        Runs one similarity search per query from `build_query_texts` (one
        per individual atomic concept, some carrying an exact-value text
        filter — see this module's docstring), grouped by concept (FR24)
        rather than merged into one shared pool: within a concept, hits are
        combined by Reciprocal Rank Fusion (each chunk's fused score is the
        sum of `1 / (_RRF_K + rank)`, 1-based rank within that specific
        query's own results, across every query *of that same concept* that
        surfaced it — never across a different concept's queries, which this
        module's docstring explains isn't a fair comparison and is exactly
        the crowding-out this grouping exists to prevent).

        Each concept's fused ranking is searched to `match_pool_size` depth
        but only its top `top_k` is *displayed* (FR24 unchanged) — the extra
        depth exists purely to detect concept-pair convergence (FR27) below
        the displayed cutoff, e.g. a passage ranked #1 for one concept and #9
        for another. A chunk's displayed score is its best (lowest-distance)
        individual match, for `min_score` filtering and for what a researcher
        actually sees.

        Concept pairs (FR27, FR28) are then built from every concept's full
        deep pool: two semantic concepts sharing a chunk, or a semantic
        concept sharing a chunk with a recognized exact value (proven via
        that value's `document_contains` filter, not similarity). Each pair's
        candidates are ranked by `_combined_score` and cut to `merge_top_k`.
        """
        self._lookup_cache: dict[tuple[str, str], tuple[Source, Tradition]] = {}

        queries = build_query_texts(graph_facts)
        query_embeddings = self._embedder.embed([query.text for query in queries])

        queries_by_concept: dict[str, list[tuple[_Query, list[float]]]] = {}
        for query, embedding in zip(queries, query_embeddings, strict=True):
            queries_by_concept.setdefault(query.text, []).append((query, embedding))

        concept_candidates = []
        deep_hits_by_concept: dict[str, dict[str, VectorHit]] = {}
        number_chunk_ids: dict[str, set[str]] = {}

        for concept, concept_queries in queries_by_concept.items():
            best_hit_by_chunk_id: dict[str, VectorHit] = {}
            rrf_score_by_chunk_id: dict[str, float] = {}
            for query, embedding in concept_queries:
                hits = self._vector_store.similarity_search(
                    embedding, top_k=self._match_pool_size, document_contains=query.document_contains
                )
                if query.number is not None:
                    number_chunk_ids.setdefault(query.number.value, set()).update(hit.chunk_id for hit in hits)
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
            deep_chunk_ids = ranked_chunk_ids[: self._match_pool_size]
            deep_hits_by_concept[concept] = {chunk_id: best_hit_by_chunk_id[chunk_id] for chunk_id in deep_chunk_ids}

            display_hits = [best_hit_by_chunk_id[chunk_id] for chunk_id in deep_chunk_ids[: self._top_k]]
            passages = tuple(self._hydrate(hit) for hit in display_hits if _similarity_score(hit) >= self._min_score)
            if passages:
                concept_candidates.append(ConceptCandidates(concept=concept, passages=passages))

        pair_candidates = self._build_pair_candidates(deep_hits_by_concept, number_chunk_ids)

        return RetrievalContext(
            graph_facts=graph_facts,
            concept_candidates=tuple(concept_candidates),
            pair_candidates=pair_candidates,
        )

    def _build_pair_candidates(
        self,
        deep_hits_by_concept: dict[str, dict[str, VectorHit]],
        number_chunk_ids: dict[str, set[str]],
    ) -> tuple[ConceptPairCandidates, ...]:
        """One `ConceptPairCandidates` per co-occurring pair (FR27): every
        unordered pair of semantic concepts sharing a chunk in their deep
        pools, plus every semantic concept paired with every recognized exact
        value it shares a chunk with (FR28). A pair of two exact values is
        never emitted — an exact value carries no score of its own (it's a
        guarantee of containment, not a similarity judgment), so there is
        nothing to rank such a pair by. Groups are sorted strongest-first by
        their own top candidate; see this module's docstring and plan.md's
        Risks on why that ordering is a display heuristic, not a claim that
        one group's score is commensurable with another's."""
        concepts = sorted(deep_hits_by_concept)
        groups: list[ConceptPairCandidates] = []

        for concept_a, concept_b in itertools.combinations(concepts, 2):
            pool_a, pool_b = deep_hits_by_concept[concept_a], deep_hits_by_concept[concept_b]
            candidates = []
            for chunk_id in set(pool_a) & set(pool_b):
                score_a, score_b = _similarity_score(pool_a[chunk_id]), _similarity_score(pool_b[chunk_id])
                combined = _combined_score((score_a, score_b))
                if combined < self._min_score:
                    continue
                candidates.append(
                    MergedCandidate(
                        passage=self._hydrate(pool_a[chunk_id]),
                        matches=(
                            ConceptMatchScore(concept=concept_a, score=score_a),
                            ConceptMatchScore(concept=concept_b, score=score_b),
                        ),
                        combined_score=combined,
                    )
                )
            self._append_group(groups, (concept_a, concept_b), candidates)

        for concept, number_value in itertools.product(concepts, sorted(number_chunk_ids)):
            pool = deep_hits_by_concept[concept]
            candidates = []
            for chunk_id in set(pool) & number_chunk_ids[number_value]:
                score = _similarity_score(pool[chunk_id])
                if score < self._min_score:
                    continue
                candidates.append(
                    MergedCandidate(
                        passage=self._hydrate(pool[chunk_id]),
                        matches=(
                            ConceptMatchScore(concept=concept, score=score),
                            ConceptMatchScore(concept=number_value, score=0.0, exact_value=True),
                        ),
                        combined_score=score,
                    )
                )
            self._append_group(groups, (concept, number_value), candidates)

        groups.sort(key=lambda group: group.candidates[0].combined_score, reverse=True)
        return tuple(groups)

    def _append_group(
        self, groups: list[ConceptPairCandidates], concepts: tuple[str, str], candidates: list[MergedCandidate]
    ) -> None:
        if not candidates:
            return
        candidates.sort(key=lambda candidate: candidate.combined_score, reverse=True)
        groups.append(ConceptPairCandidates(concepts=concepts, candidates=tuple(candidates[: self._merge_top_k])))

    def _hydrate(self, hit: VectorHit) -> RetrievedPassage:
        source, tradition = self._source_and_tradition(hit)
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

    def _source_and_tradition(self, hit: VectorHit) -> tuple[Source, Tradition]:
        """Caches `KuzuGraphStore` lookups per `retrieve()` call — the same
        chunk can be hydrated once for its own concept's display list and
        again while building a pair candidate, and a passage's source/
        tradition never varies by which concept or query surfaced it (only
        its similarity score does, which this method does not cache)."""
        key = (hit.source_id, hit.tradition_slug)
        cached = self._lookup_cache.get(key)
        if cached is None:
            cached = (self._graph_store.get_source(hit.source_id), self._graph_store.get_tradition(hit.tradition_slug))
            self._lookup_cache[key] = cached
        return cached


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


def _number_for(value: str) -> _Number | None:
    """The recognized `_Number` for an integer-valued attribute (e.g. "100" ->
    `_Number("100", "hundred")`), if it's one this project's data actually
    uses — `None` for anything else (not a number, or a number outside
    `_NUMBER_WORDS`), so an unrecognized value just falls back to being
    searched as plain text in `_fact_queries` rather than silently dropped."""
    try:
        word = _NUMBER_WORDS.get(int(value))
    except ValueError:
        return None
    return _Number(value=value, word=word) if word else None


def _extract_concepts(attributes: tuple[Attribute, ...]) -> list[str]:
    """Every retrievable attribute's value, decomposed to one atomic concept
    per value (`_atomic_values`), no `key:` label (see this module's docstring
    TODO on why that's cut without a settled replacement) — a recognized exact
    numeric value (`value_type: integer`) is excluded here, since it's handled
    separately as a global filter (`_collect_numbers`), not as a concept of
    its own."""
    concepts: list[str] = []
    for attribute in attributes:
        if not _is_retrievable(attribute):
            continue
        if attribute.value_type == "integer" and _number_for(attribute.value):
            continue
        concepts.extend(_atomic_values(attribute.value))
    return concepts


def _collect_numbers(attribute_groups: list[tuple[Attribute, ...]]) -> list[_Number]:
    """Every recognized exact numeric value (`value_type: integer`) found
    anywhere across `attribute_groups` — the symbol's own interpretation
    attributes, and every `corresponds_to` target's properties/semantic facts
    — converted to a `_Number` and deduplicated by word form, order-preserved
    by first appearance. Collected globally rather than per-group (see this
    module's docstring): a real passage can combine a concept from one part
    of the graph with a number from an entirely different part, so the filter
    these become (`_fact_queries`) applies to *every* concept, not just the
    ones that happen to share a group with the number. The value form (e.g.
    "100") is kept alongside the word form ("hundred") so it can surface as
    a pair member in its own right (FR28) rather than being discarded once
    the search text is derived."""
    numbers: list[_Number] = []
    seen_words: set[str] = set()
    for attributes in attribute_groups:
        for attribute in attributes:
            if not _is_retrievable(attribute) or attribute.value_type != "integer":
                continue
            number = _number_for(attribute.value)
            if number and number.word not in seen_words:
                seen_words.add(number.word)
                numbers.append(number)
    return numbers


def _fact_queries(attributes: tuple[Attribute, ...], numbers: list[_Number]) -> list[_Query]:
    """This group's atomic concepts (`_extract_concepts`), each as a plain
    query, plus — for every number recognized *anywhere* in the current
    `GraphFacts` (`numbers`, global, not just this group's own) — one
    additional filtered variant per concept, combined with that number as a
    literal-text filter.

    Deliberately a boost, not a hard requirement: an earlier version made a
    numeric fact *replace* its group's concept queries with filtered-only
    versions, which silently returns zero results for any card where no
    single passage happens to combine the number and the concept — killing
    real candidates is worse than an occasional missed boost. Now every
    concept is always searched plainly (nothing is ever lost), and each
    filtered variant only adds an *additional* independent ranking that
    rewards a passage combining both signals — via Reciprocal Rank Fusion
    (`RetrievalPipeline.retrieve`), a passage matching both ranks higher than
    one matching only the concept, without excluding the latter. A group with
    no concepts of its own contributes no queries here — a lone number with
    nothing to filter is handled once, globally, by `build_query_texts`."""
    concepts = _extract_concepts(attributes)
    queries = [_Query(text=concept) for concept in concepts]
    for number in numbers:
        queries += [_Query(text=concept, number=number) for concept in concepts]
    return queries


def _relationship_query_texts(relationship: RelationshipFact, numbers: list[_Number]) -> list[_Query]:
    """One query per *individual atomic concept* about a `corresponds_to`
    target — its own symbol-level properties (e.g. gematria value, meaning)
    and its own interpretation-level attributes across every tradition it's
    interpreted under (`target_semantic_facts`, e.g. its Sepher Yetzirah
    `foundation`). Both are already hydrated by
    `KuzuGraphStore._get_symbol_relationships`, so this needs no extra graph
    fetch here.

    Deliberately does *not* query the target's bare name (e.g. "Qoph") on its
    own — see this module's docstring TODO on why that's disabled for now."""
    target = relationship.target_symbol
    return _fact_queries(target.properties + relationship.target_semantic_facts, numbers)


def build_query_texts(graph_facts: GraphFacts) -> list[_Query]:
    """One query per individual atomic concept reachable from the queried
    symbol (FR8): one per atomic concept in each attribute of the symbol's
    own interpretation, then for each `corresponds_to` relationship (FR3,
    FR19), one per individual atomic concept about the target — see this
    module's docstring for why keeping every concept this isolated matters,
    for why there's no combined descriptive-identity query (the symbol's own
    canonical name/display name/summary aren't searched at all), and for why
    every recognized number anywhere in `graph_facts` becomes a filtered
    variant of *every* concept, not just the ones in its own group.
    `RetrievalPipeline.retrieve` embeds and searches every one, then merges
    the results by rank (RRF), not raw score, within each concept."""
    symbol, interpretation = graph_facts.symbol, graph_facts.interpretation
    attribute_groups = [interpretation.attributes]
    attribute_groups += [
        relationship.target_symbol.properties + relationship.target_semantic_facts
        for relationship in symbol.relationships
    ]
    numbers = _collect_numbers(attribute_groups)

    queries = _fact_queries(interpretation.attributes, numbers)
    for relationship in symbol.relationships:
        queries += _relationship_query_texts(relationship, numbers)

    if not queries:
        # No concept anywhere to attach a number filter to (e.g. a symbol whose
        # only fact is a bare numeric value) — search each number's word form on
        # its own rather than silently dropping it (a filter with nothing to
        # filter isn't useful, but the word itself may still be meaningful
        # search text). Not tagged with `number=`: there's no concept for it to
        # pair against, so it can't participate in FR27/FR28 convergence anyway.
        queries += [_Query(text=number.word) for number in numbers]

    return [query for query in queries if query.text]


def _similarity_score(hit: VectorHit) -> float:
    """`ChromaVectorStore` is configured for cosine distance (`[0, 2]`, 0 =
    identical) — `1 - distance` gives a similarity score where higher is
    better, matching `Settings.retrieval_min_score`'s "keep at or above this"
    semantics."""
    return 1.0 - hit.distance


def _combined_score(scores: tuple[float, ...]) -> float:
    """Geometric mean of a concept pair's semantic component scores, clamped
    at zero per component before multiplying (FR27). `_similarity_score` is
    `1 - cosine_distance`, which spans `[-1, 1]`, not `[0, 1]` — a negative
    component would otherwise make the root complex, and a passage
    anti-correlated with one member of a pair has no conjunctive strength to
    reward anyway.

    Geometric rather than arithmetic because convergence is conjunctive, not
    additive: a passage scoring `(0.90, 0.20)` and one scoring `(0.57, 0.53)`
    share an identical sum and mean, yet only the second genuinely sits at
    the intersection of both concepts — the first is a strong match on one
    concept that merely reached the other's deep matching pool. The
    geometric mean tells them apart (`0.42` vs `0.55`); see this module's
    docstring and `ConceptPairCandidates` for the full argument."""
    clamped = tuple(max(0.0, score) for score in scores)
    return math.prod(clamped) ** (1.0 / len(clamped))
