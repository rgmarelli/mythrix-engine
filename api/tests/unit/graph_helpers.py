"""Helpers shared by the unit tests that compile a real agent graph."""

from mythrix.agent.graph import compile_agent_graph
from mythrix.agent.tools import ToolSet

AUGMENT_MAX_REGIONS = 8
AUGMENT_CONSOLIDATION_GROUP_SIZE = 8


def compile_graph(
    llm,  # noqa: ANN001
    tools: list,
    *,
    node_tools: list | None = None,
    max_regions: int = AUGMENT_MAX_REGIONS,
    consolidation_group_size: int = AUGMENT_CONSOLIDATION_GROUP_SIZE,
):  # noqa: ANN201
    """`compile_agent_graph` with the tool-set split and the augmentation
    bounds filled in — the arguments only `api/dependencies.py` really
    supplies. A test that cares about any of them passes it explicitly."""
    return compile_agent_graph(
        llm,
        ToolSet(model_tools=tools, node_tools=node_tools or []),
        augment_max_regions=max_regions,
        augment_consolidation_group_size=consolidation_group_size,
    )
