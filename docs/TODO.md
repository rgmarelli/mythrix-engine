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
  appears moderately in *several* queries. Concrete example still open: for
  The Sun (→ Qoph → `foundation: laughter`), Genesis 21 ranks #4 within the
  `laughter` query alone (RRF contribution 0.0156) but the 6th-place cutoff
  needs 0.0164 — a margin of ~0.0008, likely closeable by raising the
  per-query `top_k` (more candidates enter the fused pool) or lowering
  `_RRF_K` (steeper rank decay, rewards strong single hits more). Not tuned
  because the marginal gain was judged not worth chasing one example further
  without seeing how the current settings behave across other cards first.

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

- **`spec.md`'s own worked example is invalid against the real schema.**
  The "Structured-data authoring format" section shows
  `properties: [{key: alphabet_position, value: 15}, ...]` with a bare
  integer `value`, but `PropertyEntry.value` (`symbol_schema.py`) is a
  strict `str` — pydantic rejects a bare int at validation time (verified
  directly against the loader, not just read from the model). Every real
  YAML file in `data/` already uses quoted string values
  (`value: "15"`), so this only affects the spec's own illustrative example,
  not real data. Fix either the model (accept int/float and coerce) or the
  spec's example (quote the value) — flagged, not yet decided which.

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

- **`Citations valid: yes` is vacuously true when zero citations are used.**
  The validator only checks that markers *present* are real — a narrative
  with no `[G#]`/`[S#]` markers at all still reports "valid." Flagged during
  a real query where the model's narrative never cited anything; not fixed,
  since changing what counts as "valid" would change `--strict`'s exit-code
  behavior and needs a decision on desired semantics first (e.g. a distinct
  "no citations used" signal, separate from "invalid marker present").

## Synthesis / output structure (future)

- **Per-concept summary → general summary → sentiment analysis, instead of one
  flat merged passage list.** Today `RetrievalPipeline.retrieve()` merges every
  query's hits (14 for a card with a numeric fact, after the boost fix below)
  into one shared pool and cuts to a single final `top_k`. Verified this has a
  real cost: for The Sun, the Genesis 21 passage (Isaac born, "a hundred years
  old", "God hath made a laughter for me") ranked #1 within its own
  `laughter`+`"hundred"`-filtered query, but was cut from the merged result at
  `top_k=8` — it only survived once `top_k` was raised to 15 — because 14
  queries (several low-signal, e.g. `naked child`, `white horse`) now compete
  for one small shared budget of final slots. Proposed restructuring instead
  of raising `top_k` as a blunt fix: candidates per concept (already boosted
  by the exact-number filter) → one summary per concept → one general summary
  rolling those up → a sentiment-analysis pass over the general summary. Each
  concept gets its own retrieval+summary budget instead of competing for a
  shared cutoff, which also reads more naturally as the explainable trail the
  project is meant to produce ("references to `white horse` are these 3, my
  summary of them is X; references to `laughter` are these, my summary is Y;
  general summary: Z"). Trade-off: multiplies LLM calls from 1 per query to
  N concepts + 1 (general) + 1 (sentiment), and citation validation
  (`synthesis/citations.py`) needs to hold at two levels — a concept summary
  citing only its own real passages, and the general summary citing only real
  concept summaries — to keep the "every conclusion traceable" guarantee
  intact. This is an architecture change plus a genuinely new capability
  (sentiment analysis isn't in `spec.md` at all today), not a bugfix — per
  this repo's SDD process, needs `spec.md`/`plan.md` updates before
  implementation, not an ad-hoc addition to the current pipeline.

## Verification

- **T25 (end-to-end v1 acceptance) is still unchecked in `tasks.md`.**
  `tests/integration/test_query_end_to_end.py` (`@pytest.mark.requires_ollama`)
  exists and collects cleanly but has not been run and confirmed passing —
  extensive manual retrieval diagnostics happened this session (direct
  Python scripts against the real store), but not the actual integration
  test or a plain `mythrix query` CLI run confirmed end-to-end. Run
  `uv run pytest tests/integration -m requires_ollama -q` to close this out;
  it's the last item blocking "Definition of done for v1" in `tasks.md`.

## Possible future retrieval strategies

Noted per the user's framing ("en el futuro podemos tener distintas
estrategias") — not committed to, just recorded as options if the current
per-fact/RRF approach needs revisiting:

- Per-attribute LLM-free re-ranking of a larger candidate pool (retrieve top
  30-50 per query instead of top 6, then apply a cheaper secondary filter
  before the final cut).
- A pluggable retrieval-strategy interface, so `build_query_texts`'s
  decomposition (per-fact, no identity, no bare relationship names) becomes
  one strategy among several rather than the only option — deliberately not
  built now (no second concrete strategy exists yet to justify the
  abstraction).
- Corpus-aware toggling of the disabled relationship-target-name query (see
  above) based on whether the ingested corpus itself is about the same
  symbol system (e.g. auto-enable for a Sepher Yetzirah/Bahir corpus,
  leave disabled for a general text like the Bible).
