# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

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
    citation_max_retries: int = 0,
):  # noqa: ANN201
    """`compile_agent_graph` with the tool-set split and the augmentation
    bounds filled in — the arguments only `api/dependencies.py` really
    supplies. A test that cares about any of them passes it explicitly.

    `citation_max_retries` defaults to `0`, not `api/dependencies.py`'s
    production default — at `0` the citation-check node's behavior collapses
    to exactly the pre-ADR-023 "invalid marker -> immediate fallback", so
    every existing test that scripts one invalid-marker `AIMessage` and
    asserts the fallback keeps working unchanged, with `ScriptedLLM` called
    the same number of times it always was. Only a test that means to
    exercise the retry loop itself passes a higher value."""
    return compile_agent_graph(
        llm,
        ToolSet(model_tools=tools, node_tools=node_tools or []),
        augment_max_regions=max_regions,
        augment_consolidation_group_size=consolidation_group_size,
        citation_max_retries=citation_max_retries,
    )
