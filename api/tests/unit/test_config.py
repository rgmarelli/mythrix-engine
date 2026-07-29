# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for core.config.Settings: defaults, env-var override, and kwarg precedence."""

import pytest

from mythrix.core.config import Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.embedding_model == "nomic-embed-text"
    assert settings.generation_model is None
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.retrieval_match_pool_size == 100
    assert settings.retrieval_min_score == 0.6
    assert settings.generation_num_ctx == 8192
    assert settings.region_window_size == 3
    assert settings.region_min_interpretants == 1
    assert settings.augment_max_regions == 1000
    assert settings.augment_consolidation_group_size == 8


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYTHRIX_EMBEDDING_MODEL", "custom-embedder")
    monkeypatch.setenv("MYTHRIX_RETRIEVAL_MIN_SCORE", "0.75")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.embedding_model == "custom-embedder"
    assert settings.retrieval_min_score == 0.75


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


def test_match_pool_size_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYTHRIX_RETRIEVAL_MATCH_POOL_SIZE", "50")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.retrieval_match_pool_size == 50


def test_augment_max_regions_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYTHRIX_AUGMENT_MAX_REGIONS", "3")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.augment_max_regions == 3


def test_augment_consolidation_group_size_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYTHRIX_AUGMENT_CONSOLIDATION_GROUP_SIZE", "3")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.augment_consolidation_group_size == 3


def test_augment_consolidation_group_size_rejects_values_below_two() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 2"):
        Settings(augment_consolidation_group_size=1, _env_file=None)  # type: ignore[call-arg]


def test_region_window_size_and_min_interpretants_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYTHRIX_REGION_WINDOW_SIZE", "5")
    monkeypatch.setenv("MYTHRIX_REGION_MIN_INTERPRETANTS", "2")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.region_window_size == 5
    assert settings.region_min_interpretants == 2
