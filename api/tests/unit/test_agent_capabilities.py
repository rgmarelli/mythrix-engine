"""Unit tests for `agent/capabilities.py`. The registry's whole purpose is that
it cannot drift from the behavior it describes, so these tests check it against
the code that implements each command and instruction — not against a second
copy of the same literals."""

from langchain_core.messages import HumanMessage

from mythrix.agent.adhoc_query import CONFIRM_COMMAND, QUERY_COMMAND, is_adhoc_command
from mythrix.agent.capabilities import AGENT_CAPABILITIES, CLEAR_COMMAND
from mythrix.agent.graph import route_input
from mythrix.agent.summarize_command import SUMMARIZE_COMMAND
from mythrix.agent.summarize_command import command_of as summarize_command_of

_COMMANDS = {command.name: command for command in AGENT_CAPABILITIES.commands}
_BINDINGS = {instruction.type: instruction.binding for instruction in AGENT_CAPABILITIES.instructions}


def test_every_server_command_is_one_the_backend_actually_recognizes() -> None:
    """The drift a type checker cannot catch: a command declared `server` that
    no backend code handles would be sent as an ordinary message and answered
    by the model as if it were prose."""
    for name, command in _COMMANDS.items():
        if command.handled_by != "server":
            continue
        recognized = is_adhoc_command(name) or summarize_command_of(name) is not None
        assert recognized, f"{name} is declared server-handled but no backend path recognizes it"


def test_clear_is_the_only_client_handled_command() -> None:
    client_commands = [name for name, command in _COMMANDS.items() if command.handled_by == "client"]
    assert client_commands == [CLEAR_COMMAND]


def test_declared_commands_cover_every_command_the_backend_implements() -> None:
    assert {QUERY_COMMAND, CONFIRM_COMMAND, SUMMARIZE_COMMAND} <= set(_COMMANDS)


def test_the_confirmation_command_is_unlisted() -> None:
    """A consumer emits it from a `confirm_query` affordance; offering it in a
    command palette would invite typing an id by hand."""
    assert _COMMANDS[CONFIRM_COMMAND].listed is False
    assert _COMMANDS[QUERY_COMMAND].listed is True


def test_every_declared_instruction_type_is_one_the_graph_can_emit() -> None:
    assert set(_BINDINGS) == {"confirm_query", "execute_query"}
    assert route_input({"messages": [HumanMessage(content=f"{QUERY_COMMAND} laughter")]}) == "parse_query"
    assert route_input({"messages": [HumanMessage(content=f"{CONFIRM_COMMAND} 7f3a1c9e")]}) == "execute_query"


def test_confirm_query_declares_no_binding() -> None:
    """It triggers no request — the affordance sends a chat command
    (FR-CAP-07). Modeling that as an explicit `None` is what lets a consumer
    tell it apart from a type it simply does not know."""
    assert _BINDINGS["confirm_query"] is None


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
