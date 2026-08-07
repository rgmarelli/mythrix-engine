# ADR-012 — Deterministic commands bypass model tool-selection when the tool sequence is fully determined by context

- **Status**: Accepted
- **Date**: 2026-07-28
- **Realized by**: [agent.md](../interfaces/agent.md) FR-AG-33–FR-AG-36

## Context

[ADR-006](adr-006-conversational-agent-orchestration-boundary.md) drew the boundary that the generation model may orchestrate (hold the conversation, select tools) but never retrieve or interpret. [ADR-010](adr-010-agnostic-adhoc-interpretant-query.md) went one step further for `/query`/`/query-confirm`: for those two commands, the model is not even trusted to orchestrate — parsing, confirmation, and instruction-building are handled by dedicated LangGraph nodes the model never reaches, because the entire sequence is deterministic and a false-positive execution is the one failure ADR-010 exists to prevent.

`/summarize` was left out of that increment because, unlike `/query`, it *wants* a generation model — a summary is inherently generated text, not a parse. It shipped instead as a pre-graph string rewrite in `turn_service.py`: the literal `/summarize` message is replaced with a natural-language directive ("Use the summarize_passage tool to summarize the active passage (X)...") and handed to the ordinary model-driven agent loop, trusting the model to call `fetch_segments` then `summarize_passage`, in that order, with the right arguments.

That trust is unnecessary. Given the active hotspot's `region_id`, every argument either tool needs is already known: `fetch_segments`'s `source_id`/`start_ordinal`/`end_ordinal` are encoded in `region_id` itself (`{source_id}::{start}-{end}`, `retrieval/pipeline.py`), and `summarize_passage`'s `concepts` come from the command's trailing focus text or the session's current interpretant — never from the model's own judgment. The only step that is genuinely generative is the summary text itself, which `summarize_passage` already produces via one `ChatClient.invoke` call. Routing the *decision* to call these two tools, in this order, through a small local model's tool-selection reasoning buys nothing and risks exactly the failure modes ADR-006 already documents observing (skipped or misordered calls, small-model unreliability) for a sequence that has no branching to reason about.

This generalizes past ADR-010's specific concern (confirmation-gating a side-effecting command) to a broader one: **whenever a command's tool sequence is fully determined by the turn's own context — no branch the model could meaningfully decide — that sequence belongs in code, and the model is invoked only for the step(s), if any, that are genuinely generative.**

## Decision

A chat command whose tool sequence is fully determined by the message text and the session's context object is handled by a dedicated LangGraph node reached directly from `route_input` (`agent/graph.py`), never by the model's own tool-selection loop:

- The node calls the same tool implementations the model would otherwise select (looked up by name from the graph's existing bound `tools` list, not reimplemented) directly, with arguments computed in code from the command text and context — no `ChatOllama.invoke` call decides whether or how to call them.
- Each such call still produces the same `AIMessage(tool_calls=...)`/`ToolMessage` pair shape a model-driven call would, so conversation history, the tool trace (FR-AG-10), and citation-marker accounting stay unchanged in shape — only *who decided to call the tool* changes, not what the call looks like afterward.
- Where a step is genuinely generative (there is no way to produce the content without a model — e.g., the summary text itself), the model is still invoked, but only for that content, and the node uses the tool's own result as the reply directly rather than routing it through a second, free-composing model call to phrase a reply — mirroring `clarify_node`'s existing precedent (ADR-006) that a reply which is pure formatting of an already-complete result does not need the model either.
- `AgentState` may carry additional structured, backend-resolved fields (beyond the existing flattened `context_summary` string) when a deterministic node needs to branch on them — e.g. the active hotspot's `region_id`. This does not change what the *model* sees; `context_summary` remains the model's only view of context, per FR-AG-29's "no duplicated state" concern applying to the model, not to code.

This is not a blanket rule that every command must avoid the model — a command whose correct handling genuinely depends on open-ended judgment (most ordinary conversation) is unaffected and continues to run through `agent`/`tools`. The test is narrow: no branch left for the model to get right or wrong.

## Consequences

- `/summarize` moves fully into the graph (`agent/graph.py`), joining `/query`/`/query-confirm`, and the pre-graph rewrite hack in `turn_service.py` is removed. As a side effect, the stored `HumanMessage` in session history is now always the user's literal command text, fixing the defect the agnostic-query plan flagged (the rewrite previously overwrote it with the fabricated directive).
- Reliability for `/summarize` no longer depends on the local model correctly choosing to call `fetch_segments` before `summarize_passage`, or choosing to call them at all — the one thing a small local model was observed to be unreliable about (ADR-006's Consequences).
- The generation model is still invoked exactly once per `/summarize` turn (inside `summarize_passage`), preserving the "explicit summarize tool" as the system's only other generative step besides ordinary conversation (ADR-006, FR-AG-09) — this ADR changes *who decides to invoke it*, not how many models or which one.
- `AgentState` gaining fields specific to one command's node is an accepted, bounded form of coupling — the alternative (parsing everything needed back out of `context_summary`'s rendered text) is strictly worse and was rejected for `/query`'s `pending_query` for the same reason.
- Future commands with a fully determined tool sequence (none currently planned) have a named precedent to follow rather than re-deriving the "should this go through the model?" judgment call from first principles each time.

## Alternatives considered

- **Leave `/summarize` as a pre-graph model-driven rewrite.** Rejected — this is the status quo this ADR replaces; it leaves tool-call reliability to the model for a sequence that has no actual decision in it, and it carries the session-history defect noted above.
- **Give the deterministic node direct access to `Stores`/`ChatClient` instead of reusing the bound `tools` list.** Rejected — it would duplicate `agent/tools.py`'s error-mapping (`MythrixError` → `{"error": ...}`) and require threading two more constructor arguments through `compile_agent_graph`/`build_agent_graph` for no benefit; the tools are already available, already tested, and already the single place that wrapping logic lives.
- **Keep tool selection model-driven but add stronger system-prompt rules ordering `fetch_segments` before `summarize_passage`.** Rejected under FR-AG-32/ADR-009: enforceable in code, so it belongs in code, not in a prompt the model can still fail to follow.
