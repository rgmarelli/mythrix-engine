# Tasks: `exact` query directive

- [x] 1. `models.py`: widen `Match.kind` to `Literal["concept", "exact", "filter"]`; update `QueryDirective`/`Interpretant` docstrings to describe `"exact"`.
- [x] 2. `sign_schema.py`: update `QueryDirectiveEntry` docstring to mention `"exact"` and its default-to-value `as_token`.
- [x] 3. `pipeline.py`: add `kind` to `_FilterToken`; update `_filter_token_for` to recognize `"exact"` (default-to-value `as_token`, tag `kind`).
- [x] 4. `pipeline.py`: update `_extract_concepts` to exclude only `"filter"`-directive interpretants, not `"exact"`.
- [x] 5. `pipeline.py`: add `_self_filtered_queries`; wire into `_fact_queries`.
- [x] 6. `pipeline.py`: thread `kind` through `_search_deep_pools` (`token_kind_by_value`); use it in `retrieve_regions`'s `Match(kind=...)` construction.
- [x] 7. `pipeline.py`: restrict `_build_pair_candidates`'s cross-join to `kind == "filter"` tokens.
- [x] 8. `pipeline.py`: update module docstring and any other `"filter"`-only prose that now needs to mention `"exact"`. Also found and fixed a real bug surfaced by this work: `retrieve_regions`'s per-region dedup keyed the best match by `interpretant` alone, so an `"exact"`-directive interpretant's own `"exact"` match was always discarded in favor of its `"concept"` match on the same segment. Now keyed by `(interpretant, kind)`.
- [x] 9. `specs/retrieval/retrieval.md`: add FR-RT-17–19 for the `"exact"` directive.
- [x] 10. Tests: updated the two `retrieve_regions` tests asserting `kind == "exact"` on `"filter"` fixtures to `kind == "filter"`; added tests for FR-EX-01–04 (plain+self-filtered query construction, default `as_token`, `as_token` override, no synthetic cross-concept pairing, `kind == "exact"` labeling) plus a `Match.kind == "filter"` model test.
- [x] 11. `web/src/api/types.ts`: widened the four `kind` literal sites to include `'filter'`.
- [x] 12. `HotspotCard.tsx`, `HotspotDetailPanel.tsx`, `AgentChatPanel.tsx`: generalized the score/label ternary.
- [x] 13. `ruff check`/`ruff format --check` clean on all changed files; full `pytest` suite (349 tests) passes; `tsc -b` and `oxlint` clean on the web changes.
- [ ] 14. Manual verification per `plan.md` (CLI JSON output + web dev server chip labels) — not run: the local `.mythrix` store doesn't have this corpus loaded, and loading it (`mythrix load-signs`/`load-documents`) would modify persisted local state, so left for the user to run if wanted. Pipeline-level behavior is otherwise covered end-to-end by the unit tests in task 10.
