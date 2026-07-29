# ADR-015 — A deterministic command may run ad-hoc retrieval server-side and read its results, over a node-only tool set

- **Status**: Accepted
- **Date**: 2026-07-28
- **Realized by**: [discovery.md](../interfaces/discovery.md) FR-DS-01–FR-DS-30

## Context

[ADR-010](adr-010-agnostic-adhoc-interpretant-query.md) admitted one scoped exception to [corpus.md](../retrieval/corpus.md) FR-CO-03 ("query text is never raw, unvalidated user input"): a deterministically-parsed term list may become query text, because the parse is exhaustive and the confirmation gate is code rather than model compliance. It kept that exception narrow in two further ways. The retrieval is *executed by the consumer*, not the backend: the agent emits an `execute_query` instruction and the frontend calls `/api/query/adhoc` itself. And the results never come back to the agent at all — [agnostic-query.md](../interfaces/agnostic-query.md)'s non-goals state that the agent "cannot discuss, refer back to, or answer questions about a query run through this path."

Both of those hold for `/query`, whose product purpose is to put regions in the viewer. Neither can hold for the capability this ADR exists to enable: reading every retrieved region against a question and reporting what recurs across them. That work is by definition backend work — the passages must reach the generation model, and the model's readings must be consolidated before anything is returned. A client-executed hand-off cannot express it, and "the agent never sees ad-hoc results" is precisely what has to change.

The obvious way to change it is also the wrong one: add an ad-hoc retrieval tool to the agent's bound tool set and let the orchestration model call it. That would delete ADR-010's guarantee wholesale. The model would then be able to compose query text from anything in the conversation, run retrieval on its own initiative, and narrate the results — the exact three properties ADR-010 was written to prevent, given up to serve one command.

There is a second, quieter pressure. [ADR-012](adr-012-deterministic-command-nodes-bypass-tool-selection.md) established that a deterministic node fabricates the `AIMessage(tool_calls=…)`/`ToolMessage` pair a model-driven call would have produced, "so conversation history, the tool trace, and citation-marker accounting stay unchanged in shape." With `/summarize` that is two pairs. A run that analyzes eight regions performs one retrieval, eight passage fetches and nine generation calls; fabricating all of it appends on the order of thirty-six messages, eight of them carrying full passages, into a thread that the *next* ordinary turn replays into a 8192-token context (`generation_num_ctx`). One run would evict the rest of the conversation. ADR-012's rule was written for a two-call sequence and does not survive contact with a fan-out.

## Decision

**A command handled by a deterministic node may execute ad-hoc retrieval within its own turn and give the results to the generation model, provided the retrieval is unreachable from the orchestration model.**

Concretely:

- **The tool set splits by reachability.** `build_tools` returns a `ToolSet` with two lists. `model_tools` is bound to the orchestration model and is what `ToolNode` executes; `node_tools` is reachable only by name lookup from a deterministic node. Ad-hoc retrieval and the analysis/consolidation generation steps live in `node_tools`. The orchestration model has no binding for them, so ADR-010's guarantee is not weakened by prompt instruction but by vocabulary: the model still cannot run or narrate an ad-hoc query of its own accord, because the operation does not exist in its tool schema.
- **The amendment to ADR-010 is exactly this wide.** Ad-hoc retrieval may run server-side inside a turn whose entire operation sequence is fixed in code, and its results may be read by the generation model. Every other property ADR-010 established is unchanged: the term list is still the only user text that becomes query text, the confirmation gate is still id-based and still code, and the pipeline, match floor and ranking are still the ones every other query runs.
- **A deterministic node may fan out N generation calls in one turn, bounded by its own configuration.** `agent_max_tool_iterations` (FR-AG-12) bounds the *orchestration model's* tool loop, which such a turn never enters; it is not a budget for work the backend decided to do. A fan-out therefore carries an explicit bound of its own (`discover_max_regions`), and the count of generation calls is arithmetic in that bound rather than a function of model behavior.
- **A node may record less in conversation history than it did work.** ADR-012's fabricate-every-pair rule is narrowed to: fabricate the pairs that citation-marker accounting needs, which is the retrieval step alone. The per-region fetches and analyses are observable in the process log, not in the thread. A tool result that a node fabricates into history is rendered without passage text when the node re-reads that text by structural coordinate anyway.

## Consequences

- `agnostic-query.md`'s non-goal — the agent cannot discuss or answer questions about an ad-hoc query — remains literally true for the agent's model-driven path, which is the path it was written about. It is no longer true of the backend as a whole. The distinction is now carried by the `model_tools`/`node_tools` split rather than by the absence of a tool.
- The tool set is no longer a flat list, so `compile_agent_graph` takes a `ToolSet` and `api/dependencies.py` binds only `model_tools`. "Read-only is a structural property of this list" (FR-AG-04) becomes a property of both lists; neither contains a write operation.
- Conversation history after a run is small and lossy by design: the user's command, the retrieval call and its region list, and the report. A later turn in the thread can refer back to the report — which contains every finding — but not to the raw passages, which were never in the thread. Reconstructing a run's full trace is a log operation.
- The per-turn cost of a run is bounded but large: N+1 sequential generation calls block one HTTP request. There is no timeout anywhere in this codebase, so a hung daemon hangs the request; a run is the most likely way to meet that pre-existing gap.
- Citation markers gain a fourth kind. `[R#]` is validated like `[G#]`/`[S#]` but, unlike them, is **retained** in the delivered reply, because it is what lets a consolidated claim be traced to the section that supports it. Validation and stripping stop being the same predicate.
- A future command needing the same shape — retrieve, read each hit, consolidate — has a named precedent covering both the retrieval exception and the history reduction, rather than re-deriving either.

## Alternatives considered

- **Bind an ad-hoc retrieval tool to the orchestration model.** Rejected — it hands the model the ability to compose query text from arbitrary conversation and to run retrieval unprompted, discarding ADR-010's guarantee entirely to serve one command that does not need the model to make the decision at all.
- **Emit an `execute_query` instruction and have the consumer run the retrieval, then send the regions back in a second request.** Rejected — it makes the frontend a participant in an analysis pipeline, requires a new instruction type and result kind for the return leg, and turns one gated flow into three round trips. The retrieval is not being run to display something; it is an intermediate step of backend work.
- **Fabricate the full tool trace into history, per ADR-012 unamended.** Rejected — an eight-region run would push roughly thirty-six messages including eight full passages into an 8192-token context, degrading every subsequent turn in the thread. Fidelity to a trace-shape convention is not worth poisoning the conversation it was meant to document.
- **Reuse `summarize_passage` for the per-region reading rather than adding a node-only analysis tool.** Rejected — a passage read against a user's own question needs a prompt that names the question and instructs answering from the passage alone; giving that prompt to `summarize_passage` would change what a shipped `/summarize` returns (FR-AG-35). The two share the generation-call seam (`_generated`) and nothing else.
- **Analyze regions concurrently.** Rejected for now — it would cut wall time roughly linearly, but the interleaved progress log is the only visibility this version has (FR-DS-19), and wall time is not yet the binding constraint.
