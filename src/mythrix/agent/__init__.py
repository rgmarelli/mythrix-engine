"""The Mythrix conversational operator (`specs/agent-operator`): a LangGraph
tool-calling loop over Mythrix's existing, read-only operations. Ships as its
own `mythrix-agent` console script, self-contained from the `mythrix` CLI
(`cli/main.py`) and `core/` (beyond `core/graph/store.py::list_semiotic_systems`,
a deliberate, general-purpose addition — see plan.md)."""
