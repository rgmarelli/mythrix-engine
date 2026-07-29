"""The build's declared command vocabulary and instruction execution bindings
(specs/interfaces/agent-capabilities.md, ADR-011).

This module is the single place either is stated. Command names are imported
from the modules that implement them rather than restated, so the registry
cannot drift from the behavior it describes.

The `method`/`body`/`result` vocabularies are closed on purpose: a binding
selects among this API's own read endpoints, it does not describe an arbitrary
request. Every method in the vocabulary is safe and idempotent, so no
declaration expressible here can cause a write (FR-CAP-16)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from mythrix.agent.commands.adhoc import CONFIRM_COMMAND, QUERY_COMMAND
from mythrix.agent.commands.discover import DISCOVER_COMMAND, DISCOVER_CONFIRM_COMMAND
from mythrix.agent.commands.summarize import SUMMARIZE_COMMAND

CLEAR_COMMAND = "/clear"

SafeMethod = Literal["GET", "QUERY"]
BodyMode = Literal["payload"]
ResultKind = Literal["regions"]
InstructionType = Literal["confirm_query", "execute_query", "confirm_discovery"]


class CommandSpec(BaseModel):
    name: str
    args: str | None
    summary: str
    handled_by: Literal["server", "client"]
    listed: bool


class InstructionBinding(BaseModel):
    """How one instruction type is executed (FR-CAP-08). `path` is a
    same-origin absolute path; consumers reject anything else."""

    method: SafeMethod
    path: str
    body: BodyMode
    result: ResultKind


class InstructionSpec(BaseModel):
    type: InstructionType
    binding: InstructionBinding | None


class AgentCapabilities(BaseModel):
    commands: list[CommandSpec]
    instructions: list[InstructionSpec]


AGENT_CAPABILITIES = AgentCapabilities(
    commands=[
        CommandSpec(
            name=CLEAR_COMMAND,
            args=None,
            summary="Clear this thread and start a new session",
            # No backend code implements `/clear` — the consumer does
            # (agent.md FR-AG-22). Declaring it here states the product's
            # vocabulary; `handled_by` states where it lives.
            handled_by="client",
            listed=True,
        ),
        CommandSpec(
            name=SUMMARIZE_COMMAND,
            args=None,
            summary="Summarize the passage selected in the viewer",
            handled_by="server",
            listed=True,
        ),
        CommandSpec(
            name=QUERY_COMMAND,
            args="term[:exact|:filter], …",
            summary="Search the corpus on your own terms, with no sign selected",
            handled_by="server",
            listed=True,
        ),
        CommandSpec(
            name=CONFIRM_COMMAND,
            args="<id>",
            summary="Run a parsed ad-hoc query",
            handled_by="server",
            listed=False,
        ),
        CommandSpec(
            name=DISCOVER_COMMAND,
            args='"what to look for", term[:exact|:filter], …',
            summary="Search the corpus on your own terms, read every result against a question, and consolidate",
            handled_by="server",
            listed=True,
        ),
        CommandSpec(
            name=DISCOVER_CONFIRM_COMMAND,
            args="<id>",
            summary="Run a parsed discovery",
            handled_by="server",
            listed=False,
        ),
    ],
    instructions=[
        InstructionSpec(type="confirm_query", binding=None),
        # Like `confirm_query`: no binding, so a consumer renders an affordance
        # that sends the confirmation command rather than issuing a request
        # (FR-CAP-07, FR-DS-31). A declared type with no binding and an
        # undeclared type are deliberately different things (FR-CAP-13) —
        # emitting this without declaring it here would surface as an error.
        InstructionSpec(type="confirm_discovery", binding=None),
        InstructionSpec(
            type="execute_query",
            binding=InstructionBinding(
                method="QUERY",
                path="/api/query/adhoc",
                body="payload",
                result="regions",
            ),
        ),
    ],
)
