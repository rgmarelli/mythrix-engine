"""Helpers shared by the unit tests that compile a real agent graph."""

from mythrix.agent.graph import compile_agent_graph
from mythrix.agent.tools import ToolSet

AUGMENT_MAX_REGIONS = 8


def compile_graph(llm, tools: list, *, node_tools: list | None = None):  # noqa: ANN001, ANN201
    """`compile_agent_graph` with the tool-set split and the discovery bound
    filled in — the two arguments only `api/dependencies.py` really supplies.
    A test that cares about either passes it explicitly."""
    return compile_agent_graph(
        llm,
        ToolSet(model_tools=tools, node_tools=node_tools or []),
        augment_max_regions=AUGMENT_MAX_REGIONS,
    )
