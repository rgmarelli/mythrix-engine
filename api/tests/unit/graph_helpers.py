# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Helpers shared by the unit tests that compile a real agent graph."""

from mythrix.agent.graph import compile_agent_graph
from mythrix.agent.tools import ToolSet
from mythrix.core.chat import ChatClient

AUGMENT_MAX_REGIONS = 8
AUGMENT_CONSOLIDATION_GROUP_SIZE = 8


class PassthroughChatClient:
    """A `fact_check_chat_client` default for tests that don't care about
    fact-checking (most of them): its response is not valid JSON, so
    `run_fact_check`'s parser (ADR-025) returns `None` and the node falls
    back to its no-op path — the scripted reply a test asserts on passes
    through completely unchanged, with no footer appended."""

    generation_model = "fake-fact-check-model"

    def invoke(self, prompt: str) -> str:
        return "<fact-check not exercised by this test>"


def compile_graph(
    llm,  # noqa: ANN001
    tools: list,
    *,
    node_tools: list | None = None,
    max_regions: int = AUGMENT_MAX_REGIONS,
    consolidation_group_size: int = AUGMENT_CONSOLIDATION_GROUP_SIZE,
    fact_check_chat_client: ChatClient | None = None,
):  # noqa: ANN201
    """`compile_agent_graph` with the tool-set split and the augmentation
    bounds filled in — the arguments only `api/dependencies.py` really
    supplies. A test that cares about any of them passes it explicitly.

    `fact_check_chat_client` defaults to `PassthroughChatClient()`, not a
    real fact-checking model — every existing test that scripts a final
    `AIMessage` and asserts on its content keeps working unchanged, since
    the fact-check node's default behavior is a no-op pass-through. Only a
    test that means to exercise fact-checking itself passes a fake that
    inserts tags."""
    return compile_agent_graph(
        llm,
        ToolSet(model_tools=tools, node_tools=node_tools or []),
        augment_max_regions=max_regions,
        augment_consolidation_group_size=consolidation_group_size,
        fact_check_chat_client=fact_check_chat_client or PassthroughChatClient(),
    )
