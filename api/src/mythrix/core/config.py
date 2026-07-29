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

    `retrieval_match_pool_size` is how deep each concept's own Reciprocal-Rank-Fused
    pool goes before region rollup (FR-RK-01). Kept large so a segment ranking #1
    for one interpretant and #90 for another still contributes both matches to the
    region they share — trimming earlier would discard exactly the convergence
    ranking exists to reward (ADR-004). The cost is extra Chroma searches only;
    query embeddings are computed once regardless and no generation model is
    involved (FR-RT-10). Default of `100` calibrated per ADR-008, not derived from
    a formula — re-sweep if the embedding model or corpus scale changes materially.

    `generation_model`/`generation_num_ctx` are read by the conversational agent
    layer only; nothing on the query path reads them (FR-RT-10). `generation_model`
    has no hardcoded default since installed Ollama models vary by machine — code
    that needs it must fail with an actionable `ModelUnavailableError` rather than
    silently falling back to a guess. `generation_num_ctx` exists because Ollama
    silently defaults to a 2048-token context window and truncates from the *start*
    of the prompt (dropping system instructions and earliest context first) if left
    unset.

    `retrieval_min_score` is the absolute match floor a concept's raw similarity
    must clear (ADR-004, FR-RT-14). Default of `0.6` calibrated per ADR-008: match
    scores have no natural gap between "real" and "noise", so an explicit floor
    above the noise band favors precision over recall — override per-request via
    `/api/query`'s `min_score` param if this default doesn't suit a particular
    corpus.

    `signs_data_path` is where `POST /api/reload-signs` reads from when the
    request omits a path — the same directory the local dev workflow already
    passes to `mythrix load-signs` by hand.

    `region_window_size` (FR-RK-02) is how many
    consecutive segment ordinals of one source a region rollup can chain
    together — a region can still span further end-to-end when matches occur
    in a close-packed chain (see `retrieval.pipeline._cluster_ordinals`).

    `region_min_interpretants` (FR-RK-03) is the minimum count of distinct
    *concept* interpretants a region must carry to be eligible. Defaults to
    `1` — an isolated strong match is a valid, rankable region on its own
    (ADR-004); convergence raises rank, it is never required to appear at
    all.

    `agent_model`/`agent_max_tool_iterations` are read only by the in-app
    agent chat panel (`specs/interfaces/agent.md`, `mythrix.api`), never by the
    `query` path. `agent_model` falls back to `generation_model` when unset;
    `agent_max_tool_iterations` bounds how many tool calls one conversational
    turn may make before it ends rather than looping (FR-AG-12).

    `discover_max_regions` (FR-DS-13) bounds how many retrieved regions one
    corpus-discovery run reads, and so bounds its generation calls at N+1.
    `agent_max_tool_iterations` does not apply: it governs the orchestration
    model's own tool loop, which a deterministic run never enters (ADR-015).
    Kept small because the calls are sequential and block the turn.
    """

    model_config = SettingsConfigDict(env_prefix="MYTHRIX_", env_file=".env", extra="ignore")

    kuzu_db_path: Path = Path(".mythrix/graph.kuzu")
    chroma_persist_dir: Path = Path(".mythrix/chroma")
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    generation_model: str | None = None
    retrieval_match_pool_size: int = 100
    retrieval_min_score: float = 0.6
    generation_num_ctx: int = 8192
    signs_data_path: Path = Path("data/semiotic_systems")
    region_window_size: int = 3
    region_min_interpretants: int = 1
    agent_model: str | None = None
    agent_max_tool_iterations: int = 8
    discover_max_regions: int = 8
