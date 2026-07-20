# Query Viewer Facet/Fragment Redesign — Tasks

## Backend

- [x] T1: Add `FragmentMatch`, `Fragment`, `SourceFacet`, `InterpretantFacet`, `Facets`, `FragmentQueryResult` to `core/models.py`.
- [x] T2: Extract `RetrievalPipeline._search_deep_pools` from `iter_candidates`; confirm `iter_candidates`/`retrieve` behavior is unchanged.
- [x] T3: Add `RetrievalPipeline.retrieve_fragments` (`_build_fragment`/`_build_facets` helpers as needed).
- [x] T4: Add `core/query_service.py::query_fragments`; remove `stream_query`.
- [x] T5: Replace `GET /api/query` in `api/routes.py` with the single-JSON `FragmentQueryResult` endpoint; remove SSE plumbing; fix `api/errors.py` docstring.
- [x] T6: Update `tests/unit/test_retrieval_pipeline.py` with `retrieve_fragments` coverage (N-way convergence, eligibility cutoff, per-match `min_score`, `exact_value` matches, facet counts).
- [x] T7: Update `tests/unit/test_query_service.py` (`query_fragments` replacing `stream_query` tests).
- [x] T8: Update `tests/unit/test_api.py` (`/api/query` plain-JSON tests replacing SSE tests).
- [x] T9: `pytest tests/unit/test_retrieval_pipeline.py tests/unit/test_query_service.py tests/unit/test_api.py` green.

## Frontend

- [x] T10: Rewrite `web/src/api/types.ts`.
- [x] T11: Rewrite `web/src/api/client.ts` (`fetchQuery` replacing `streamQuery`).
- [x] T12: Remove `GraphFactsPanel.tsx`, `ConceptCandidatesSection.tsx`, `PairCandidatesSection.tsx`, `PassageCard.tsx`, `PassageDetailPanel.tsx`.
- [x] T13: Add `FacetRow.tsx`.
- [x] T14: Add `HotspotCard.tsx`, `HotspotList.tsx`.
- [x] T15: Add `FragmentDetailPanel.tsx`.
- [x] T16: Rewrite `App.tsx`.
- [x] T17: Add new classes to `index.css`.

## Verification

- [x] T18: `cd web && npx tsc -b && npx vite build`.
- [x] T19: Run `mythrix query --json` against a real store; confirm CLI output unaffected.
- [x] T20: Manual UI walkthrough: submit query, toggle each facet independently and together, confirm convergence badges are stable under filtering, select/prev/next fragments at both list boundaries, copy-ref, generate AI summary.

## Follow-up: convergence count excludes exact-value matches

Root cause of misleadingly broad convergence badges (e.g. a fragment showing 8 matched Interpretants): an exact-value/filter-directive match (e.g. a gematria value matched via literal `"hundred"` containment) counted toward convergence identically to a real semantic match, even though it carries no similarity score and can fire on any chunk containing a common word.

- [x] T21: Add `Fragment.convergence_count: int` to `core/models.py`.
- [x] T22: `RetrievalPipeline._build_fragment` computes `convergence_count` (matches where `exact_value` is `False`); `retrieve_fragments` sorts by `(convergence_count, max match score)` instead of `(len(matches), ...)`.
- [x] T23: Update `tests/unit/test_retrieval_pipeline.py`/`tests/unit/test_api.py` for `convergence_count`.
- [x] T24: Update frontend (`types.ts`, `HotspotCard.tsx`, `FragmentDetailPanel.tsx`, `App.tsx`) to use `convergence_count` for the badge and for ranking, keeping `matches` (all of them, including exact-value) shown in the fragment detail chip row.
- [x] T25: `pytest`/`ruff`/`tsc -b`/`vite build` green; verify live that an exact-value-only match no longer inflates a fragment's badge count.
