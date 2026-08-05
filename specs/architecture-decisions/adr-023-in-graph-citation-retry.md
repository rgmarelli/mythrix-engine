# ADR-023 — In-graph citation retry replaces the one-shot post-hoc reject

- **Status**: Superseded by [ADR-025](adr-025-post-hoc-fact-checker-replaces-self-citation.md)
- **Date**: 2026-08-03
- **Extends**: [ADR-006](adr-006-conversational-agent-orchestration-boundary.md), [ADR-022](adr-022-tool-owned-opaque-grounding-ids.md)
- **Realized by**: [agent.md](../interfaces/agent.md) FR-AG-06

## Context

Citation validation has always run as a single post-hoc gate after the model's tool-calling loop has already ended: the final reply's grounding markers are checked against this turn's tool results, and any invalid marker discards the *entire* reply in favor of one generic apology. The model never sees that check fail and never gets a chance to correct it — a wrong marker and a wrong answer are handled identically.

Real-model testing showed this reject-only handling is a poor fit for the actual failure mode: across many turns, the model never once fabricated a grounding id — the opaque, independently-generated ids ADR-022 introduced held up completely — but it frequently *formatted* a real one wrong (prose instead of brackets, or an invented citation notation of its own). This is a recoverable mistake, not a grounding failure, and a model shown exactly which marker was wrong is far better positioned to fix it than one asked to redo an entire answer with no feedback.

## Decision

Citation validation for the model-driven conversational turn moves from a post-hoc check into a new deterministic graph node, `validate_citations_node`, reached whenever the agent produces a reply with no further tool calls:

- Valid reply (or a turn where only listing tools were called, which carry no citations to validate): no-op, the turn ends exactly as before.
- Invalid reply, retries remaining (bounded by a small configured budget, default 2): a corrective message naming the specific invalid marker(s) is appended, and the graph routes back to the agent for another generation attempt.
- Invalid reply, retries exhausted: the same failure message the old post-hoc check used is substituted as the final reply.

A new turn-scoped state field fixes where in the conversation this turn began, so the node can reliably find "this turn's tool messages" across zero or more retry loops — a naive "scan back to the most recent user message" would find its own pushback instead of the turn's real boundary once a retry has happened.

The post-hoc check itself is **not removed**. It remains the sole citation gate for `/augment`'s reply (a distinct, position-based marker space, out of scope here) and continues to run, now redundantly, as a final backstop on the conversational path too — a reply that reaches it from the new node is expected to already be valid or already be the fallback message, so in practice it should never trip there, but removing it would require a stronger guarantee about the node's coverage of every path through the graph than this change establishes.

## Consequences

- A model that gets a citation format wrong gets a bounded number of chances to fix it, with concrete feedback naming what was wrong, before the turn falls back to the generic apology — strictly better than an immediate, uninformative reject for the large class of failures that are formatting mistakes rather than fabrication.
- The retry budget is a new small, tunable setting, independent of the tool-call iteration budget — a turn's total step count can now be tool-call iterations *and* citation retries combined, still bounded by the same outer recursion limit, so a pathological turn cannot loop unboundedly even if both budgets are set generously.
- `validate_citations_node` only sits on the agent-driven conversational path. `/augment` is unaffected by design — its citation risk profile and generation shape (a single hierarchical consolidation call, not a conversational loop) differ enough that folding it into the same retry mechanism is a separate decision, not assumed here.
- A pushback is delivered as a message appended to conversation state, the first time this codebase has injected a message into persisted turn history that did not originate from the real user or a tool. It is scoped to the graph's internal retry loop only — a pushback/retry cycle that ends in a valid reply leaves no trace of the attempt in what session history carries forward, exactly as a discarded intermediate reply already didn't under the old scheme.

## Alternatives considered

- **Leave the one-shot post-hoc reject as-is.** Rejected — this decision's entire motivation: real-model testing showed most invalid-marker cases are recoverable formatting mistakes, and discarding a correct-but-mis-cited answer wholesale is a worse outcome for the user than giving the model one clear chance to fix it.
- **Validate and retry inside the agent node itself, rather than a separate node.** Rejected — mixes model-invocation concerns with citation-integrity concerns in one function, and the codebase's existing precedent for a deterministic post-generation check is its own node rather than inline logic in the node that calls the model.
- **Extend the retry mechanism to `/augment`'s consolidation reply too.** Rejected for this pass — that path is a deterministic multi-step pipeline (read region → augment → consolidate), not the conversational tool-calling loop; giving it a comparable self-correction path is a materially different, separately-scoped change.
