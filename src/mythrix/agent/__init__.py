"""The Mythrix conversational operator (`specs/interfaces/agent.md`): a LangGraph
tool-calling loop over Mythrix's existing, read-only operations. Powers the
in-app agent chat panel via `mythrix.api`, self-contained from the `mythrix`
CLI (`cli/main.py`) and `core/` (beyond `core/graph/store.py::list_semiotic_systems`,
a deliberate, general-purpose addition — see plan.md)."""
