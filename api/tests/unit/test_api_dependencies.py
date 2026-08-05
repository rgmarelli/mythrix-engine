# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `api/dependencies.py::get_agent_graph` — the one place the
agent's two model roles are derived (FR-03, FR-04, FR-05). A fake chat model
stands in for `create_chat_model`, so no Ollama daemon is involved and the
number of constructions is directly observable."""

from types import SimpleNamespace

import pytest

from mythrix.api import dependencies
from mythrix.core.bootstrap import Stores


class FakeBinding:
    """Stands in for the `RunnableBinding` `ChatOllama.bind_tools` returns —
    keeps a reference to the model it bound."""

    def __init__(self, bound: object, tools: list, kwargs: dict) -> None:
        self.bound = bound
        self.tools = tools
        self.kwargs = kwargs

    def invoke(self, messages: list):  # noqa: ANN201 - never called; the graph is not run here
        raise AssertionError("the compiled graph is not invoked in this test")


class FakeChatModel:
    """The `ChatOllama` surface `get_agent_graph` touches. `model_copy` mirrors
    pydantic's: a new instance carrying updated generation fields, sharing the
    original's already-validated client."""

    def __init__(self, model: str, client: object | None = None, **options) -> None:  # noqa: ANN003
        self.model = model
        self.client = client if client is not None else object()
        self.options = options
        self.bindings: list[FakeBinding] = []
        self.copies: list[FakeChatModel] = []

    def model_copy(self, *, update: dict) -> "FakeChatModel":
        copy = FakeChatModel(self.model, client=self.client, **{**self.options, **update})
        self.copies.append(copy)
        return copy

    def bind_tools(self, tools: list, **kwargs) -> FakeBinding:  # noqa: ANN003
        binding = FakeBinding(self, tools, kwargs)
        self.bindings.append(binding)
        return binding


@pytest.fixture
def request_stub(tmp_path) -> SimpleNamespace:  # noqa: ANN001 - pytest tmp_path
    from mythrix.core.graph.store import KuzuGraphStore
    from mythrix.core.vector.store import ChromaVectorStore

    class FakeEmbedder:
        model_name = "fake-embed"

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

    stores = Stores(
        graph_store=KuzuGraphStore(tmp_path / "graph.kuzu"),
        vector_store=ChromaVectorStore(tmp_path / "chroma"),
        embedder=FakeEmbedder(),
    )
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(stores=stores, agent_graph=None)))


@pytest.fixture
def created_models(monkeypatch: pytest.MonkeyPatch) -> list[FakeChatModel]:
    created: list[FakeChatModel] = []

    def fake_create_chat_model(*, model: str, base_url: str, num_ctx: int) -> FakeChatModel:
        created.append(FakeChatModel(model))
        return created[-1]

    monkeypatch.setattr(dependencies, "create_chat_model", fake_create_chat_model)
    monkeypatch.setenv("MYTHRIX_GENERATION_MODEL", "qwen3:1.7b")
    return created


def test_one_chat_model_is_constructed_per_process(
    request_stub: SimpleNamespace, created_models: list[FakeChatModel]
) -> None:
    """FR-03: both roles come from a single construction, so the daemon is
    validated once rather than once per role."""
    dependencies.get_agent_graph(request_stub)

    assert len(created_models) == 1


def test_the_summarize_client_and_the_agent_model_share_one_validated_client(
    request_stub: SimpleNamespace, created_models: list[FakeChatModel]
) -> None:
    """FR-04: the agent's model is a derived copy of the same instance the
    narrow `ChatClient` wraps, reusing its already-validated client — not a
    second construction."""
    dependencies.get_agent_graph(request_stub)

    llm = created_models[0]
    agent_llm, fact_check_llm = llm.copies
    assert agent_llm.client is llm.client
    assert fact_check_llm.client is llm.client
    (binding,) = agent_llm.bindings
    assert binding.bound is agent_llm


def test_the_agent_output_budget_is_scoped_to_the_agents_own_model(
    request_stub: SimpleNamespace, created_models: list[FakeChatModel]
) -> None:
    """FR-05: the per-role parameter is set on the derived copy, so it is
    carried as a generation option rather than as a bound keyword — and the
    summarize client, which shares the original, is unaffected."""
    dependencies.get_agent_graph(request_stub)

    llm = created_models[0]
    agent_llm, fact_check_llm = llm.copies
    assert agent_llm.options["num_predict"] == dependencies._AGENT_NUM_PREDICT
    assert fact_check_llm.options["num_predict"] == dependencies._FACT_CHECK_NUM_PREDICT
    assert "num_predict" not in llm.options
    assert agent_llm.bindings[0].kwargs == {}


def test_the_fact_check_role_shares_the_agent_model_when_unconfigured(
    request_stub: SimpleNamespace, created_models: list[FakeChatModel]
) -> None:
    """ADR-025: with no distinct `fact_check_model` set, the fact-check role
    is a second derived copy of the same validated connection — not a
    second daemon construction (`create_chat_model` is called once, per
    `test_one_chat_model_is_constructed_per_process`)."""
    dependencies.get_agent_graph(request_stub)

    llm = created_models[0]
    _, fact_check_llm = llm.copies
    assert fact_check_llm.model == llm.model
    assert len(created_models) == 1


def test_a_distinct_fact_check_model_gets_its_own_construction(
    request_stub: SimpleNamespace, created_models: list[FakeChatModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-025: when `fact_check_model` names a model different from the
    agent's own, it is validated separately rather than derived — the
    fake `create_chat_model` is called twice, once per distinct model."""
    monkeypatch.setenv("MYTHRIX_FACT_CHECK_MODEL", "a-different-model")

    dependencies.get_agent_graph(request_stub)

    assert [m.model for m in created_models] == ["qwen3:1.7b", "a-different-model"]
    agent_llm, *_ = created_models[0].copies
    assert agent_llm.options["num_predict"] == dependencies._AGENT_NUM_PREDICT
    # One copy: the `reasoning=False` derive applied to every fact-check role
    # (see `test_the_fact_check_role_disables_thinking_mode`) regardless of
    # whether the role shares the agent's model or is its own construction.
    (fact_check_llm,) = created_models[1].copies
    assert fact_check_llm.options["reasoning"] is False


def test_the_fact_check_role_disables_thinking_mode(
    request_stub: SimpleNamespace, created_models: list[FakeChatModel]
) -> None:
    """ADR-025: qwen3's default "thinking" pass made this narrow tagging-only
    call slower and less likely to obey the additive-only instruction, so the
    fact-check role always gets `reasoning=False` — the last derive applied,
    after the num_predict override above it."""
    dependencies.get_agent_graph(request_stub)

    llm = created_models[0]
    _, fact_check_llm = llm.copies
    (final_fact_check_llm,) = fact_check_llm.copies
    assert final_fact_check_llm.options["reasoning"] is False


def test_the_fact_check_role_does_not_pin_temperature(
    request_stub: SimpleNamespace, created_models: list[FakeChatModel]
) -> None:
    """A first attempt pinned `temperature=0.0`, reasoning the fact-check
    role's job is a mechanical copy-and-tag pass rather than a generative
    one — but real-world use kept hitting the exact same non-compliant
    completion on the exact same input every time. Greedy (temperature 0)
    decoding does not sample around a bad completion, it reproduces it
    deterministically forever, so the role is left at the shared default
    instead — nonzero temperature at least gives repeated turns a chance to
    land on a compliant one."""
    dependencies.get_agent_graph(request_stub)

    llm = created_models[0]
    _, fact_check_llm = llm.copies
    (final_fact_check_llm,) = fact_check_llm.copies
    assert "temperature" not in final_fact_check_llm.options


def test_the_graph_is_built_once_and_cached(request_stub: SimpleNamespace, created_models: list[FakeChatModel]) -> None:
    first = dependencies.get_agent_graph(request_stub)
    second = dependencies.get_agent_graph(request_stub)

    assert first is second
    assert len(created_models) == 1
