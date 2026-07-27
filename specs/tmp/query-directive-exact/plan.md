# Plan: `exact` query directive

Implements `spec.md` (FR-EX-01–06). Extends the existing `"filter"`/`"skip"` directive mechanism (ADR-002, ADR-007) rather than introducing a new architectural boundary — no new ADR needed.

## Core mechanism (`api/src/mythrix/core/retrieval/pipeline.py`)

- `_FilterToken` (`:88-96`): add `kind: Literal["filter", "exact"]`.
- `_filter_token_for` (`:478-485`): recognize `"filter"` and `"exact"`. For `"exact"`, `as_token = interpretant.query.as_token or interpretant.value` (FR-EX-02); tag the token with the matching `kind`.
- `_extract_concepts` (`:496-509`): exclude an interpretant from the unrestricted plain concept list when its directive is `"filter"` **or** `"exact"` (new `_is_exact_directive` helper) — an `"exact"` interpretant's only query is the self-filtered one below (FR-EX-01). (Superseded an earlier version of this plan that kept `"exact"` in the plain list alongside its filtered variant; live testing showed the redundant unfiltered query was exactly the gap letting a low-similarity literal match get crowded out of its own concept pool — see plan note below.)
- `_collect_filter_tokens` (`:512-530`): unchanged in spirit — keep collecting only `kind == "filter"` tokens; this remains the global, every-concept-paired pool (FR-RT-09).
- New `_self_filtered_queries(interpretants)`: for each interpretant whose own directive is `"exact"`, emit one `_Query(text=atomic_value, filter_token=own_token)` per atomic value in its own value — self-paired, never cross-joined (FR-EX-02/03). This is now the *only* query such an interpretant contributes.
- `_fact_queries` (`:533-545`): append `_self_filtered_queries(interpretants)`.
- `_search_deep_pools` (`:183-258`): `filter_token_chunk_ids` is keyed by `_FilterToken.value` with no kind info today. Add a parallel `token_kind_by_value: dict[str, str]` built from `query.filter_token` alongside it.
- `retrieve_regions` (`:298-307`): replace hardcoded `Match(..., kind="exact", ...)` with `Match(..., kind=token_kind_by_value.get(filter_value, "filter"), ...)` (FR-EX-04/05).
- `_build_pair_candidates` (`:363-420`): restrict the `itertools.product(concepts, sorted(filter_token_chunk_ids))` cross-join to `kind == "filter"` values only (FR-EX-03).
- `retrieve_regions`'s per-region dedup (`best_match_by_interpretant`) stays keyed by `interpretant` alone, **not** `(interpretant, kind)` — an earlier iteration of this plan keyed it by `(interpretant, kind)` so an `"exact"`-directive interpretant's `"concept"` and `"exact"` matches could coexist on the same segment, but live testing showed that surfaces as two confusing pills for one value (`"100 · 0.63"` and `"100 · exact"`) and inflates the facet count. Keeping the single-key dedup means a real score always wins over a same-value literal-filter match, and the literal-filter match only surfaces on its own when no concept match for that value survives in the region at all (FR-EX-06).

**Removing `"exact"`'s unrestricted plain query (revision after live testing).** The original plan kept an `"exact"`-directive interpretant's value in the plain concept list *alongside* its self-filtered variant (two queries, RRF-fused into one pool). Live testing against `qof.yaml`'s `"100"`/`hundred` interpretant surfaced two problems this caused: (1) the unfiltered query's hits (semantically similar but not literally containing the token) could crowd the literally-matching chunk out of the concept's own `match_pool_size`-capped pool, so the real hit only survived via the separate, unbounded `filter_token_chunk_ids` path and displayed as a scoreless `kind="exact"` pill instead of a real score; (2) this contradicted the feature's actual intent — an exhaustive, always-literal search ("devolveme todos los vectores que tengan exactamente este token"), not a semantic query merely nudged by a filter. Excluding `"exact"` from `_extract_concepts` (FR-EX-01, revised) removes the unfiltered query entirely: the self-filtered query becomes the interpretant's *only* query, so its concept pool is 100% literal matches, and a hit found there naturally carries a real similarity score via the ordinary `"concept"` loop in `retrieve_regions` — the `kind="exact"`/score-0.0 path now only fires for the pre-existing edge case where `match_pool_size` trims a chunk out of even that single-query pool (same class of edge case `"filter"` already has).

## Models (`api/src/mythrix/core/models.py`)

- `QueryDirective` (`:99-112`) and `Interpretant` (`:115-124`) docstrings: document `"exact"`.
- `Match.kind` (`:426`): `Literal["concept", "exact"]` → `Literal["concept", "exact", "filter"]`.
- `ConceptMatchScore` (`:294-309`): no field change.

## Loader (`api/src/mythrix/core/loaders/sign_schema.py`)

- `QueryDirectiveEntry` (`:118-126`): no field change (`directive: str`, `as_token: str = ""` already fit); docstring update only.

## Frontend (`web/src`)

- `api/types.ts` (`:67, :99, :151, :187`): widen `'concept' | 'exact'` → `'concept' | 'exact' | 'filter'`.
- `HotspotCard.tsx:21`, `HotspotDetailPanel.tsx:208`, `AgentChatPanel.tsx:65`: generalize `kind === 'exact' ? 'exact' : score.toFixed(2)` → `kind === 'concept' ? score.toFixed(2) : kind`.

## Spec doc (`specs/retrieval/retrieval.md`)

- Add FR-RT items mirroring FR-EX-01–05 (next available numbers) so the retrieval functional spec stays the single source of truth for retrieval behavior; `query-directive-exact` spec is the origin/rationale, retrieval.md gets the durable requirement text.

## Tests

- `api/tests/unit/test_retrieval_pipeline.py`: new coverage for FR-EX-01–04; update the two existing `retrieve_regions` tests asserting `kind == "exact"` on `"filter"`-directive fixtures to `kind == "filter"` (FR-EX-05).
- `api/tests/unit/test_models.py`: `Match.kind` literal accepts `"filter"`.

## Verification

- `ruff check . && ruff format --check .`
- `pytest api/tests/unit/test_retrieval_pipeline.py api/tests/unit/test_models.py -q`
- Manual: `mythrix query --sign ... --tradition ... --json` against a fixture with both an `"exact"`-directive interpretant (no `as_token`) and an existing `"filter"`-directive interpretant; confirm `kind: "exact"` vs `kind: "filter"` in the output.
- Frontend dev server: confirm chips read "filter"/"exact" per the above.
