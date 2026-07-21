"""Runtime configuration for the Mythrix core library.

Precedence (highest to lowest): explicit constructor kwargs (how the CLI applies
per-invocation flag overrides, e.g. `Settings(embedding_model=...)`) > environment
variables (`MYTHRIX_*` prefix) > a local `.env` file > the defaults below. This
ordering is pydantic-settings' native behavior, not custom logic.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Local-only runtime configuration: storage locations and Ollama model selection.

    `retrieval_top_k` is how many candidates each concept *displays* (FR24 — a
    per-concept budget, not a shared one).

    `retrieval_match_pool_size` is how deep each concept's pool goes when detecting
    which passages two concepts both retrieved (FR27), independent of what's
    displayed. Deliberately much larger than `retrieval_top_k`: intersecting only
    the displayed candidates would miss the case the feature exists for — a passage
    ranking #1 for one concept and #9 for another is a real convergence, and it
    never appears in the second concept's displayed list. The cost is extra Chroma
    searches only; query embeddings are computed once regardless and no generation
    model is involved (FR29). It also directly controls how many low-value lopsided
    pairs get produced, so it is the knob to reach for if output grows unwieldy —
    see plan.md's Risks on pair-group count.

    `merge_top_k` caps candidates *within* one concept-pair group, the pair-side
    analogue of `retrieval_top_k`.

    `generation_model`/`generation_num_ctx` are retained for the planned
    conversational agent layer; nothing on the query path reads them (FR29).
    `generation_model` has no hardcoded default since installed Ollama models vary
    by machine — code that needs it must fail with an actionable
    `ModelUnavailableError` rather than silently falling back to a guess.
    `generation_num_ctx` exists because Ollama silently defaults to a 2048-token
    context window and truncates from the *start* of the prompt (dropping system
    instructions and earliest context first) if left unset — confirmed empirically:
    a real ~6979-token prompt was cut to `prompt_eval_count: 2050` at the default,
    which read as the model hallucinating when it had simply never seen most of its
    own supplied context.

    `retrieval_min_score` defaults to `0.45`, not `0.0` — confirmed empirically
    against a real query (The Sun/Rider-Waite, `nomic-embed-text`, 1621-chunk
    corpus): the distribution of match scores across all retrieved fragments is a
    smooth, single-humped curve from ~0.36 to ~0.55 with no natural gap between
    "real" and "noise" matches, mean/median both ~0.44. At `0.0`, every candidate
    within `retrieval_match_pool_size` counts toward convergence regardless of how
    weak its score is, which let a long, topically broad chunk (Deuteronomy 33, an
    imagery-dense passage) register as converging on 8 of 10 interpretants at once
    — none of them individually strong (each below or barely at that interpretant's
    own weakest top-6 corpus-wide score). `0.45` sits at the observed median; on the
    same query it cut that chunk's convergence from 8 interpretants to 3 (the ones
    with genuinely above-median scores) and the total eligible-fragment count from
    44 to 25, without a principled "correct" cutoff existing in the data — override
    per-request via `/api/query`'s `min_score` param or `mythrix query --min-score`
    if this default doesn't suit a particular corpus.

    `symbols_data_path` is where `POST /api/reload-symbols` reads from when the
    request omits a path — the same directory the local dev workflow already
    passes to `mythrix load-symbols` by hand.
    """

    model_config = SettingsConfigDict(env_prefix="MYTHRIX_", env_file=".env", extra="ignore")

    kuzu_db_path: Path = Path(".mythrix/graph.kuzu")
    chroma_persist_dir: Path = Path(".mythrix/chroma")
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    generation_model: str | None = None
    retrieval_top_k: int = 6
    retrieval_match_pool_size: int = 30
    merge_top_k: int = 6
    retrieval_min_score: float = 0.45
    generation_num_ctx: int = 8192
    symbols_data_path: Path = Path("data/semiotic_systems")
