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

    `generation_model` has no hardcoded default since installed Ollama models vary by
    machine — code that needs it (the synthesis chain) must fail with an actionable
    `ModelUnavailableError` rather than silently falling back to a guess.
    """

    model_config = SettingsConfigDict(env_prefix="MYTHRIX_", env_file=".env", extra="ignore")

    kuzu_db_path: Path = Path(".mythrix/graph.kuzu")
    chroma_persist_dir: Path = Path(".mythrix/chroma")
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    generation_model: str | None = None
    retrieval_top_k: int = 6
    retrieval_min_score: float = 0.0
