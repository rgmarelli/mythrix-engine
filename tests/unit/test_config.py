"""Unit tests for core.config.Settings: defaults, env-var override, and kwarg precedence."""

import pytest

from mythrix.core.config import Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.embedding_model == "nomic-embed-text"
    assert settings.generation_model is None
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.retrieval_top_k == 6
    assert settings.retrieval_match_pool_size == 30
    assert settings.merge_top_k == 6
    assert settings.retrieval_min_score == 0.0
    assert settings.generation_num_ctx == 8192


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYTHRIX_EMBEDDING_MODEL", "custom-embedder")
    monkeypatch.setenv("MYTHRIX_RETRIEVAL_TOP_K", "10")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.embedding_model == "custom-embedder"
    assert settings.retrieval_top_k == 10


def test_constructor_kwarg_takes_precedence_over_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYTHRIX_EMBEDDING_MODEL", "from-env")

    settings = Settings(embedding_model="from-kwarg", _env_file=None)  # type: ignore[call-arg]

    assert settings.embedding_model == "from-kwarg"


def test_generation_model_can_be_set_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYTHRIX_GENERATION_MODEL", "llama3.1")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.generation_model == "llama3.1"


def test_generation_num_ctx_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYTHRIX_GENERATION_NUM_CTX", "16384")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.generation_num_ctx == 16384


def test_match_pool_size_and_merge_top_k_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYTHRIX_RETRIEVAL_MATCH_POOL_SIZE", "50")
    monkeypatch.setenv("MYTHRIX_MERGE_TOP_K", "10")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.retrieval_match_pool_size == 50
    assert settings.merge_top_k == 10
