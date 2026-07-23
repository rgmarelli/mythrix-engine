# ADR 0006 — Conversational agent orchestrates; retrieval stays deterministic and cited

- **Status**: Accepted
- **Date**: 2026-07-21
- **Realized by**: `specs/agent-operator/spec.md` FR1–FR11; `specs/spec.md` FR11, FR12, FR29 and the "conversational agent layer" Non-goal

## Context

Mythrix's core promise is an **auditable evidence chain**: a query returns ranked,
cited graph facts and source passages, and no model decides what a result *is*
(master FR11). The query path invokes no generation model at all (FR29); the only
generated text in the system is the single-turn, on-demand passage summary
(FR54), and even that carries citation markers validated in code (FR12). The
master spec explicitly anticipates a future "conversational agent layer (a
console/chat interface driving an agent loop)" and requires that v1's design not
preclude it — while insisting the same code-driven-retrieval and
validated-citation guarantees apply to that layer too.

Building that agent layer forces a decision about where a generation model is
allowed to act. A naïve chat agent would let the LLM read the corpus, decide what
is relevant, and narrate an interpretation directly — exactly the free-form
generation this project was built to avoid. The tension is real: an agent is
useful precisely *because* an LLM plans and converses, yet the engine's value
depends on the LLM never being the thing that determines symbolic evidence.

## Decision

A generation model may **orchestrate** Mythrix but may not **retrieve or
interpret**. Concretely:

- The agent's LLM does two things only: hold the conversation, and select which
  **tool** to call. It never reads the corpus directly and never decides what a
  retrieval result is.
- The agent operates exclusively through a fixed set of **read-only tools**, each
  a thin wrapper over an existing (or a small new read-only) access function: list
  semiotic systems, list traditions, list symbols (discovery, scoped by semiotic
  system), get symbol (a sign's graph facts), query symbol (the existing region
  query), fetch segments (coordinate lookup), and summarize passage (the existing
  single-turn summary). No tool writes to, mutates, or reloads a store — read-only
  is a structural property of the tool set, not a runtime guard.
- The retrieval a tool triggers is **unchanged and embedding-only** (FR29): the
  agent changes *who calls* the query path and *how results are presented*, not
  what the query path does. Ranking, convergence, floors, and facets are
  untouched.
- The only generative steps remain the two that already existed: the agent's own
  conversational text, and the explicit summarize tool (which reuses
  `synthesis/prompts.py` and stays subject to `synthesis/citations.py`
  validation, per FR12). The agent must ground every factual claim in a tool
  result and carry through the citation the tool returned; it invents no symbols
  or interpretations.
- The agent runs on a **local Ollama model only**. No hosted/cloud model — the
  local-only stance (master Goals) is preserved end to end.

The first surface for this layer is a CLI (`mythrix agent`); a web endpoint and
chat panel are deferred, but the same boundary governs them when they ship.

## Consequences

- The auditable evidence chain survives the addition of conversation. Anything
  the agent asserts about symbols or passages traces to a tool result and its
  citation; the parts a user must trust as *generated* are confined to the
  agent's phrasing and the clearly-labelled summary, both already validated
  surfaces.
- Retrieval quality is entirely inherited from the existing query path — the
  agent cannot make retrieval better or worse, only easier to drive. Improving
  results still means improving interpretants and the pipeline, not prompting.
- Read-only-by-construction means the agent can never corrupt the stores.
  Ingestion and reload stay human-invoked (`load-symbols` / `load-documents` /
  `reload-symbols`), keeping single-writer Kùzu assumptions intact.
- Small local models may mis-select or mis-format tool calls; this degrades the
  agent's *convenience*, not the engine's retrieval correctness, and is bounded
  by the system prompt, structured tool returns, and a configurable stronger
  local model. A per-turn tool-call bound prevents runaway loops.
- Prompting alone is not sufficient to guarantee FR6 (no fabrication) against a
  small local model — observed directly: after `get_symbol` returned only a
  tradition list (`needs_tradition`, no interpretive content), a model
  sometimes composed a plausible-sounding but entirely invented denotation
  instead of asking, and this was sampling-dependent, not reliably reproduced.
  Where a tool's result is fully self-describing and composing a reply is pure
  formatting rather than synthesis, the decision this ADR establishes is
  applied at the code level, not left to the prompt: the generation model is
  bypassed entirely for that turn (`specs/agent-operator/spec.md` FR7,
  `graph.py`'s `clarify_tradition_node`). This is deliberately narrow — most
  tool results still require the model to compose a reply — but establishes
  the pattern for any future case where a tool result is complete enough that
  a deterministic reply is possible.
- Because tools wrap existing functions, the same tool layer is reusable by the
  future `/api/agent` endpoint with no change to the boundary.

## Alternatives considered

- **Free-form RAG chat: let the LLM read the corpus and narrate.** Rejected —
  it discards the code-driven-retrieval and validated-citation guarantees (FR11,
  FR12) that are the reason the project exists; the LLM would become the arbiter
  of evidence.
- **Give the agent mutating tools (ingest / reload) too.** Rejected for v1 —
  writes belong to deliberate human-invoked ingestion; an agent that reloads the
  graph mid-session risks partial-write reads and violates the single-writer
  assumption. Deferred to a later, explicitly-guarded phase.
- **Cloud generation model for stronger tool-calling.** Rejected — breaks the
  local-only stance and sends corpus/interpretant text off the machine. A
  stronger *local* model (via the `agent_model` override) is the sanctioned lever.
- **Extend `OllamaChatClient` with tool-binding instead of a separate agent chat
  construction.** An implementation choice, not a boundary one; the plan keeps
  the narrow summarize client unchanged and builds a tool-capable client for the
  agent node, sharing only the error-mapping helper.
