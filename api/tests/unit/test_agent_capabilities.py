# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `agent/capabilities.py`. The registry's whole purpose is that
it cannot drift from the behavior it describes, so these tests check it against
the code that implements each command and instruction — not against a second
copy of the same literals."""

from langchain_core.messages import HumanMessage

from mythrix.agent.capabilities import AGENT_CAPABILITIES, CLEAR_COMMAND
from mythrix.agent.commands import resolve_command
from mythrix.agent.commands.adhoc import CONFIRM_COMMAND, QUERY_COMMAND
from mythrix.agent.commands.augment import AUGMENT_COMMAND, AUGMENT_CONFIRM_COMMAND
from mythrix.agent.commands.summarize import SUMMARIZE_COMMAND
from mythrix.agent.graph.builder import route_input

_COMMANDS = {command.name: command for command in AGENT_CAPABILITIES.commands}
_BINDINGS = {instruction.type: instruction.binding for instruction in AGENT_CAPABILITIES.instructions}


def test_every_server_command_is_one_the_backend_actually_recognizes() -> None:
    """The drift a type checker cannot catch: a command declared `server` that
    no backend code handles would be sent as an ordinary message and answered
    by the model as if it were prose."""
    for name, command in _COMMANDS.items():
        if command.handled_by != "server":
            continue
        recognized = resolve_command(name) is not None
        assert recognized, f"{name} is declared server-handled but no backend path recognizes it"


def test_clear_is_the_only_client_handled_command() -> None:
    client_commands = [name for name, command in _COMMANDS.items() if command.handled_by == "client"]
    assert client_commands == [CLEAR_COMMAND]


def test_declared_commands_cover_every_command_the_backend_implements() -> None:
    assert {
        QUERY_COMMAND,
        CONFIRM_COMMAND,
        SUMMARIZE_COMMAND,
        AUGMENT_COMMAND,
        AUGMENT_CONFIRM_COMMAND,
    } <= set(_COMMANDS)


def test_the_confirmation_commands_are_unlisted() -> None:
    """A consumer emits one from a confirmation affordance, or the user copies
    it out of the plan reply; offering either in a command palette would invite
    typing an id by hand."""
    assert _COMMANDS[CONFIRM_COMMAND].listed is False
    assert _COMMANDS[QUERY_COMMAND].listed is True
    assert _COMMANDS[AUGMENT_CONFIRM_COMMAND].listed is False
    assert _COMMANDS[AUGMENT_COMMAND].listed is True


def test_every_declared_instruction_type_is_one_the_graph_can_emit() -> None:
    assert set(_BINDINGS) == {"confirm_query", "execute_query", "confirm_augment", "augment_region"}
    assert route_input({"messages": [HumanMessage(content=f"{QUERY_COMMAND} laughter")]}) == "parse_query"
    assert route_input({"messages": [HumanMessage(content=f"{CONFIRM_COMMAND} 7f3a1c9e")]}) == "execute_query"
    assert route_input({"messages": [HumanMessage(content=f"{AUGMENT_COMMAND} where is joy")]}) == "plan_augment"


def test_the_unbound_instructions_declare_an_explicit_none() -> None:
    """None of these triggers a request: the confirmations send a chat
    command (FR-CAP-07, FR-AU-32), and `augment_region` carries a result
    rather than asking for one (FR-AU-26). Modeling that as an explicit
    `None` is what lets a consumer tell it apart from a type it simply does
    not know (FR-CAP-13) — the difference between handling it and reporting
    an error."""
    assert _BINDINGS["confirm_query"] is None
    assert _BINDINGS["confirm_augment"] is None
    assert _BINDINGS["augment_region"] is None


def test_execute_query_binds_to_a_safe_method_and_a_same_origin_path() -> None:
    binding = _BINDINGS["execute_query"]
    assert binding is not None
    assert binding.method == "QUERY"
    assert binding.path.startswith("/api/")
    assert binding.body == "payload"
    assert binding.result == "regions"


def test_no_binding_can_name_an_unsafe_method() -> None:
    """FR-CAP-16 as a property of the vocabulary rather than of the current
    declarations: POST is absent from the `method` type, so a state-changing
    binding is unrepresentable."""
    for binding in _BINDINGS.values():
        if binding is not None:
            assert binding.method in ("GET", "QUERY")
