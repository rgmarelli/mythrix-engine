# TODO

Known-open items across the project — not a task backlog (see
`specs/symbol-interpretation-core/tasks.md` for that), but a place to collect
things that were deliberately deferred, found but not fixed, or flagged as
"revisit later" during development. Each entry says where it comes from and
why it's not resolved yet.

## Retrieval quality (`core/retrieval/pipeline.py`)

- **No `key:` label on attribute queries — inconsistent effect, not resolved.**
  Dropping the `key:` prefix (e.g. searching bare `laughter` instead of
  `foundation: laughter`) measurably helped in some cases and hurt in others,
  with no clean universal rule found — see the empirical numbers in
  `pipeline.py`'s module docstring. Cut anyway because "search the bare
  value" was the simpler, more predictable default to start from. Revisit
  whether some lighter-weight semantic signal could recover the cases a bare
  label would have helped without reintroducing the cases it hurt — worth
  checking specifically against the Hebrew letter data (`meaning` vs
  `foundation` vs `constellation`/`planet` currently look identical to
  retrieval once the label's gone, despite being conceptually distinct kinds
  of fact). *(`pipeline.py` TODO(retrieval-semantics), line ~41)*

- **A `corresponds_to` target's bare name is disabled as its own query.**
  E.g. a tarot card's Hebrew-letter correspondence no longer searches
  `"Qoph"` alone — a bare proper noun scored *higher* than a precise fact
  like `laughter` purely because it sits closer to generic vocabulary in the
  embedding space, nothing to do with relevance, and this will recur for any
  symbol system's names, not just Hebrew letters. Disabled universally
  (not domain-special-cased) rather than fixed properly. The name genuinely
  is a useful, specific search target in the right corpus — e.g. Psalm 119's
  stanzas are each headed by a Hebrew letter name, and a corpus that was
  itself Kabbalistic (the Sepher Yetzirah, the Bahir) would discuss these
  names constantly and meaningfully. Revisit as a corpus-aware or
  per-relationship-type decision, not a blanket on/off switch, once there's a
  concrete case that needs it. *(`pipeline.py` TODO(retrieval-semantics), line ~52)*

- **Reciprocal Rank Fusion (`_RRF_K = 60`) is untuned.** Switched from raw
  cosine-score merging to RRF because raw scores aren't comparable across
  differently-distributed queries (a real case: bare `"hebrew_letter Qoph"`
  scored higher than bare `"laughter"` even at the same query length). RRF
  fixed that specific unfairness but introduced a different trade-off: a
  fact that appears strongly in exactly *one* query can lose to a fact that
  appears moderately in *several* queries. ~~Concrete example still open: for
  The Sun (→ Qoph → `foundation: laughter`), Genesis 21 ranks #4 within the
  `laughter` query alone (RRF contribution 0.0156) but the 6th-place cutoff
  needs 0.0164 — a margin of ~0.0008~~ **Superseded by a Phase 11 finding:**
  verifying concept-pair convergence (T39) against the real corpus with the
  currently-pulled `nomic-embed-text` found Genesis 21:5-6 does not appear at
  all in any of The Sun's concepts' top-30 matching pools anymore, even
  though `laughter`, `child`, and `100` all correctly converge with each
  other on *other* Genesis passages (Genesis 20, adjacent to 21, among them).
  The number above is therefore stale relative to whatever model version or
  chunking produced it — not reproduced, not actively investigated further,
  since T39's test was rewritten to assert the convergence *mechanism* (real
  pairs form, backed by real passages) rather than that specific verse. Worth
  revisiting if someone wants to chase why 21:5-6 dropped out of the pool —
  candidates include an Ollama `nomic-embed-text` version change, or the
  document loader's chunk boundaries shifting.

- **Every symbol is now represented by short, atomic queries only** — no
  combined descriptive-identity query (canonical name + display name +
  summary). This was a deliberate trade-off to make queries comparable in
  length/score-distribution across symbols, but it means a symbol's prose
  `summary` is no longer searched *at all* during retrieval (still shown to
  the LLM in the synthesis prompt, just not used to find passages). If a
  future case shows a summary's phrasing was carrying real signal no
  keyword/attribute captures, this trade-off should be revisited — possibly
  by splitting the summary into per-sentence/per-clause atomic queries
  instead of dropping it outright.

## Reference dataset / data model

- ~~**`spec.md`'s own worked example is invalid against the real schema.**~~
  **Fixed (2026-07-19).** The "Structured-data authoring format" section
  showed `properties: [{key: alphabet_position, value: 15}, ...]` with a
  bare integer `value`, but `PropertyEntry.value` (`symbol_schema.py`) is a
  strict `str` — pydantic rejects a bare int at validation time (confirmed
  directly against the loader before fixing, not just read from the model).
  Every real YAML file in `data/` already used quoted string values, so the
  example (in both `spec.md` and `plan.md`, which duplicates it) was quoted
  to match rather than changing the model — no code/loader behavior changed.

- **Cross-tradition interpretive blending is unaddressed** (not silently
  solved). Retrieval searches the full corpus unscoped by tradition (FR7),
  which is correct for reading an independent document through a symbol's
  established meaning — but if a second *interpretive* tradition's own
  commentary is ever added for a domain that already has one (e.g. Crowley's
  Thoth-deck writing alongside Waite's Rider-Waite), an unscoped query could
  surface both traditions' passages side by side without distinguishing
  them. No mechanism exists yet to tell "an independent corpus, safe to
  search unscoped" apart from "a second competing interpretive tradition,
  needs explicit scoping." Must be resolved (e.g. a flag on `Tradition`
  distinguishing interpretive traditions from open corpora, or reviving the
  dropped `--include-related-traditions` CLI idea) before a second
  interpretive tradition's documents are ever added. *(`plan.md` Risks)*

- **Citation-id correctness ≠ content faithfulness.** The citation validator
  (`synthesis/citations.py`) proves a `[G#]`/`[S#]` marker refers to real
  context, not that the LLM's paraphrase around it is actually accurate. A
  future entailment/faithfulness check (e.g. an NLI model or a second LLM
  pass) is natural v2 work, explicitly out of v1 scope. *(`plan.md` Risks)*

- **`Citations valid: yes` is vacuously true when zero citations are used —
  dormant, not fixed.** The validator only checks that markers *present* are
  real — a narrative with no `[G#]`/`[S#]` markers at all still reports
  "valid." Flagged during a real query where the model's narrative never
  cited anything. As of Phase 11 (FR29) the `query` path produces no
  narrative to validate at all, so this doesn't currently surface anywhere —
  but the underlying ambiguity is still unresolved in `synthesis/citations.py`
  and will resurface the moment the planned agent loop starts generating text
  worth validating. Needs a decision on desired semantics first (e.g. a
  distinct "no citations used" signal, separate from "invalid marker
  present") before that happens.

## Synthesis / output structure

- ~~**Per-concept summary → general summary.**~~ **Implemented (T26–T33), then
  reversed (Phase 11).** The two-level trail landed exactly as designed and
  worked structurally — but a real run against the reference dataset showed
  the generated prose was the least useful part of the output: the general
  summary restated the concept summaries without adding a reading of the
  card, and a concept summary once concluded there was "no direct connection"
  between the very passages it had correctly found and the symbol being
  queried. FR25 is retired; FR24's per-concept retrieval survives as the
  foundation for concept-pair convergence below. See `spec.md`'s FR25 note
  and `plan.md`'s "Concept-pair convergence" section.

- **Concept-pair convergence (FR27, FR28) — implemented (T34–T39), replacing
  the synthesized narrative above.** When two independently-derived concepts
  retrieve the same passage, that convergence is now surfaced as its own
  result — additively, alongside each concept's own group, never instead of
  it. Ranked by the geometric mean of the pair's semantic component scores
  (see `pipeline.py`'s module docstring for why geometric, not arithmetic).
  Open items this introduces:
  - **Pair-group count is unbounded and grows quadratically.** No cap exists
    on how many pair groups a query can produce (`N` concepts → up to
    `N*(N-1)/2` groups); mitigated only by strongest-first ordering and
    `min_score`. See `plan.md`'s Risks.
  - **The `_RRF_K`/per-query `top_k` tuning question above is now compounded
    by `retrieval_match_pool_size`** (default 30) — a third knob affecting how
    many lopsided, low-signal pairs get generated. Not yet measured against
    the full reference dataset at scale.

- **The query path invokes no generation model (FR29).** `--facts-only` and
  `--strict` are removed — every query is facts-only in shape now, so there
  was nothing left for those flags to distinguish. `synthesis/chain.py`,
  `prompts.py`, and `citations.py` are trimmed to a minimal Ollama chat
  client, marker rendering, and single-level citation validation,
  respectively — kept, not deleted, because they're exactly what the planned
  conversational agent loop (`spec.md`'s non-goal on NL request parsing) will
  need. Nothing currently calls them.

- **Per-passage `[meaning / sentiment]` line — proposed, explicitly deferred
  again.** Raised alongside concept-pair convergence: a per-passage prompt
  like "analyze the sentiment of this text where the core concept is
  [symbol]." Deliberately **not** built in Phase 11 — it would reintroduce a
  generation call exactly where FR29 just removed one, and the project has no
  running agent-loop surface yet for it to belong to. Revisit once the
  conversational agent layer exists; no design work done (no proposed model,
  no scope for what "sentiment" means for interpretive/symbolic text).

## Verification

- **T25/T39's full-corpus acceptance tests are removed, not just unrun
  (2026-07-19).** Both `tests/integration/test_query_end_to_end.py` and
  `tests/integration/test_query_concept_scoped_synthesis.py` re-ingested the
  complete ~1700-chunk Douay-Rheims Bible into a fresh store on every
  invocation, purely to get a local Ollama embedding model in the loop —
  40+ minutes per run. Judged not worth maintaining as routine coverage, so
  both files are deleted rather than left as an ever-growing "still not run"
  item. T39's convergence finding and T33's crowding-out fix remain valid as
  one-time historical results recorded on those tasks in `tasks.md`; T25's
  real-Ollama run for The Tower specifically was never completed and has no
  automated path left to close it out. `test_synthesis_chain_ollama.py`
  (a single small `invoke()` call) is unaffected and still runs under
  `uv run pytest tests/integration -m requires_ollama -q`.

## Possible future retrieval strategies

Noted per the user's framing ("en el futuro podemos tener distintas
estrategias") — not committed to, just recorded as options if the current
per-fact/RRF approach needs revisiting:

- ~~Per-attribute LLM-free re-ranking of a larger candidate pool (retrieve top
  30-50 per query instead of top 6, then apply a cheaper secondary filter
  before the final cut).~~ **Partially realized (Phase 11).** A deeper pool
  (`retrieval_match_pool_size`, default 30) is now retrieved per concept — but
  for concept-pair intersection-finding (FR27), not for re-ranking a
  concept's own displayed results, which still cut to `top_k`. The general
  re-ranking idea (widen a concept's *own* top-k using the deeper pool, not
  just cross-concept pairs) remains open.
- A pluggable retrieval-strategy interface, so `build_query_texts`'s
  decomposition (per-fact, no identity, no bare relationship names) becomes
  one strategy among several rather than the only option — deliberately not
  built now (no second concrete strategy exists yet to justify the
  abstraction).
- Corpus-aware toggling of the disabled relationship-target-name query (see
  above) based on whether the ingested corpus itself is about the same
  symbol system (e.g. auto-enable for a Sepher Yetzirah/Bahir corpus,
  leave disabled for a general text like the Bible).
