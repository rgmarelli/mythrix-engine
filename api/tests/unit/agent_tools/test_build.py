"""Unit tests for `build_tools` itself — the composition of the tool set and
its split by reachability (ADR-015)."""

from conftest import FakeChatClient

from mythrix.agent.tools import build_tools
from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings

_MODEL_TOOLS = {
    "list_semiotic_systems",
    "list_traditions",
    "list_signs",
    "get_sign",
    "query_sign",
    "fetch_segments",
    "summarize_passage",
}
_NODE_TOOLS = {"read_region", "augment_passage", "consolidate_augmentations"}


def test_build_tools_returns_exactly_the_seven_read_only_model_tools(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    assert set(tools) == _MODEL_TOOLS | _NODE_TOOLS


def test_region_reading_and_its_generation_steps_are_unreachable_from_the_model(
    stores: Stores, settings: Settings
) -> None:
    """FR-AU-11 as a structural property: the orchestration model is bound to
    `model_tools` alone, so these three are absent from its tool schema — it
    cannot augment regions on its own initiative."""
    toolset = build_tools(stores, settings, FakeChatClient())

    assert {t.name for t in toolset.model_tools} == _MODEL_TOOLS
    assert {t.name for t in toolset.node_tools} == _NODE_TOOLS


def test_all_exposes_both_halves_for_a_deterministic_nodes_lookup(stores: Stores, settings: Settings) -> None:
    toolset = build_tools(stores, settings, FakeChatClient())

    assert {t.name for t in toolset.all} == _MODEL_TOOLS | _NODE_TOOLS
