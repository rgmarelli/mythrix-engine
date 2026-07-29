# Corpus Discovery

A confirmation-gated chat command that runs one ad-hoc interpretant query
([agnostic-query.md](agnostic-query.md)), reads every retrieved region
([ranking.md](../retrieval/ranking.md)) against a free-text analysis focus, and
consolidates the readings into one cited answer. Served by the
[Conversational Agent](agent.md)'s chat panel and handled entirely in code,
without the orchestration model's tool selection
([ADR-015](../architecture-decisions/adr-015-deterministic-analysis-over-adhoc-retrieval.md)).

## Vocabulary

- **focus**: The free-text analysis instruction a discovery command carries. It
  is applied to every analyzed region and answered across all of them. It never
  becomes query text.
- **terms**: The interpretant list a discovery command carries, in the syntax
  `/query` accepts. It becomes query text and nothing else.
- **finding**: One region's generated reading, produced by applying the focus to
  that region's verbatim passage.
- **consolidation**: The single generated answer to the focus across every
  finding in a run.
- **report**: The turn's complete reply — the consolidation followed by one
  labeled section per analyzed region.
- **run**: One confirmed discovery: a retrieval, N findings, and one
  consolidation.

## Problem

Mythrix can retrieve ranked regions for a set of interpretants, and it can
summarize one selected region. It cannot read the regions a query returned and
report what they have in common. A user exploring an idea across the corpus —
"where does the corpus treat this, and what recurs when it does" — has no path
that does not involve opening each hotspot by hand.

The two existing paths each stop short. `/query` renders its regions in the
viewer and the agent never sees them
([agnostic-query.md](agnostic-query.md) Non-goals). `/summarize` reads one
region, chosen by the user's own selection ([agent.md](agent.md) FR-AG-33).

## Goals

- One command that carries both an analysis focus and a term list, and that
  answers the focus across the whole result of querying those terms.
- Every step decided in code, so a fan-out of N generation calls is bounded by
  configuration rather than by a model's choices.
- A traceable answer: every claim in the consolidation points at the region that
  supports it, verified in code.
- No new transport, no new frontend surface, no persistence.

## Non-Goals

- Streaming, incremental delivery, or in-response progress. A run's progress is
  observable in the process log only (FR-DS-19).
- Cancelling a run in flight, or any defined behavior for a hotspot change or
  tab switch while a run is executing.
- Retrieving from a selected sign's interpretants rather than from the command's
  own terms. The retrieval scope is always the term list.
- Any new result kind, instruction binding, panel, or rendering surface. The one
  instruction type this adds carries no binding and triggers no request
  (FR-DS-31); the report is markdown through the existing path (FR-AG-23).
- Concurrent region analysis. Regions are analyzed one at a time.
- Structured (JSON) findings, or any cross-region aggregation computed in code
  rather than generated.
- Reporting an exact retrieved-region count before a run is confirmed
  (FR-DS-06).
- Persisting a run, its report, or a pending discovery beyond the browser
  session (FR-AG-20 is unchanged).

## Functional Requirements

### The command

- FR-DS-01: The system offers a `/discover` command taking two inputs in one
  message: a double-quoted analysis focus, followed by a comma-separated
  interpretant term list. The term list uses the same syntax and the same
  `:exact`/`:filter` directive vocabulary as `/query`
  ([agnostic-query.md](agnostic-query.md) FR-AQ-02, FR-AQ-03).
- FR-DS-02: A `/discover` command that supplies no quoted focus, an unterminated
  quote, an empty focus, or no terms is rejected with a message naming the
  accepted syntax, without invoking the generation model or retrieving anything.
- FR-DS-03: The focus is free text. It may contain commas, colons and directive
  suffixes without being parsed as a term, because it is delimited by its
  quotes.
- FR-DS-04: The terms are the run's query text. The focus, the conversation
  history, and the session's context are never query text — no text other than
  the deterministically parsed term list reaches retrieval
  ([corpus.md](../retrieval/corpus.md) FR-CO-03).

### Confirmation

- FR-DS-05: `/discover` does not run. It parses its two inputs, holds them in
  session state under a backend-generated id, and replies with a plan restating
  the parsed focus, the parsed terms with their directives, the maximum number
  of regions a run will read, and the literal command that runs it. The plan
  turn also emits a confirmation instruction (FR-DS-31); the command is stated
  in the reply text regardless, so the flow is completable with no consumer that
  interprets instructions.
- FR-DS-06: The plan turn retrieves nothing and invokes no generation model. It
  states the analysis bound, not how many regions the query would match.
- FR-DS-07: A `/discover-confirm` command naming the outstanding id runs the
  discovery it names. An id that does not match the outstanding one, or a
  confirmation with no outstanding discovery, is refused and runs nothing —
  confirmation is gated by the id, never by affirmative language
  ([ADR-010](../architecture-decisions/adr-010-agnostic-adhoc-interpretant-query.md)).
  A refused confirmation leaves the outstanding discovery in place.
- FR-DS-08: At most one discovery is outstanding per session. A new `/discover`
  replaces any outstanding one, and a `/discover` that fails to parse drops it.
  A confirmed discovery is cleared. A thread reset clears it.

### Dispatch

- FR-DS-09: Both commands are handled deterministically: which operations run —
  retrieve, fetch each region's passage, analyze each passage, consolidate — and
  in what order is decided in code, not by the orchestration model's tool
  selection. The orchestration model is not invoked at any point in either turn
  ([ADR-012](../architecture-decisions/adr-012-deterministic-command-nodes-bypass-tool-selection.md)).
- FR-DS-10: The ad-hoc retrieval, per-region analysis, and consolidation
  operations are not selectable by the orchestration model. They are absent from
  the tool set bound to it, so they exist only on the deterministic discovery
  path and the agent can still neither run nor narrate an ad-hoc query of its
  own accord.

### Retrieval

- FR-DS-11: The retrieval step is the existing ad-hoc interpretant query,
  unchanged: terms become ordinary interpretants on a synthetic sign and
  tradition and run through the same pipeline, match floor and ranking as every
  other query (FR-AQ-15–FR-AQ-17). It executes within the turn; a run emits no
  instruction and hands nothing to a consumer to execute.
- FR-DS-12: The regions read, and the order they are read and reported in, are
  exactly what retrieval returned, truncated from the top of the ranking. No
  model participates in selecting, dropping, re-ordering or re-scoring a region
  ([retrieval.md](../retrieval/retrieval.md) FR-RT-03).
- FR-DS-13: The number of regions a run reads is configurable and bounded by
  default. The report states how many regions matched and how many were read.
- FR-DS-14: When retrieval returns no region above the match floor, the turn
  ends saying so, without invoking the generation model.

### Analysis

- FR-DS-15: Each analyzed region's passage is its full contiguous ordinal range,
  internal gaps included, retrieved verbatim by structural coordinates — never
  the matched-only subset the region itself carries
  ([context-expansion.md](../retrieval/context-expansion.md) FR-CE-02,
  FR-CE-11).
- FR-DS-16: Each analyzed region produces one finding from exactly one
  generation-model invocation, given that region's passage, the run's focus, and
  the run's terms. The invocation is instructed to answer from the passage alone
  and to say so when the passage does not bear on the focus. A region whose
  passage cannot be retrieved is not analyzed, costs no invocation, and appears
  in no section of the report. When no region can be retrieved, the turn ends
  saying so, without invoking the generation model.
- FR-DS-17: After every finding is produced, exactly one further
  generation-model invocation consolidates them into a single answer to the
  focus, naming what recurs across the findings and where it does not. It is
  given the findings and their region labels only — never raw passage text.
- FR-DS-18: A run invokes the generation model exactly N+1 times for N analyzed
  regions, and never more. The fan-out is bounded by FR-DS-13, not by the
  per-turn tool-call bound (FR-AG-12), which governs the model's own tool loop
  and is not reached.

### Report and grounding

- FR-DS-19: Every step of a run is logged at INFO: the parsed focus and terms;
  the count matched and the count read; each region's index, label, source and
  locator as its analysis starts, and its elapsed time as it completes; the
  consolidation; and the run's total elapsed time (FR-AG-27).
- FR-DS-20: The report is composed by the backend: the consolidation first, then
  one section per analyzed region carrying its label, its source, its
  human-readable locator, its rank and score, and its finding.
- FR-DS-21: Each analyzed region carries a region marker `[R1]`, `[R2]`, …
  numbered by its 1-based position in the retrieval ranking, so a region that
  was not analyzed leaves a gap rather than shifting the ones after it. The
  consolidation cites the regions supporting each claim by marker.
- FR-DS-22: A marker in a model-authored reply that names no item from this
  turn's tool results fails the turn, for region markers exactly as for the
  existing graph-fact and segment markers (FR-AG-06, FR-RT-04).
- FR-DS-23: Region markers are retained in the reply text delivered to the
  consumer, so a consolidated claim can be traced to the section that supports
  it. Graph-fact and segment markers continue to be stripped after validation.
- FR-DS-24: A reply composed entirely by the backend, with no model-authored
  text in it, is not subject to citation validation — a marker-shaped sequence
  in a user-supplied focus, term or id cannot fail such a turn. A report is not
  such a reply: it carries generated text and is validated.
- FR-DS-25: A finding carries no citation markers. Marker-shaped text a
  generation model emits into a finding is removed before the finding enters the
  report — the analysis invocation is given no marker vocabulary, so such text
  names nothing. The consolidation's region markers are the report's only
  markers.

### Registration and history

- FR-DS-26: Both commands are declared in the capabilities document like every
  other command ([agent-capabilities.md](agent-capabilities.md) FR-CAP-02,
  FR-CAP-04). `/discover` is listed to users; `/discover-confirm` is not.
- FR-DS-27: Both turns are recorded in conversation history like any other turn,
  and the stored user message is the literal text the user sent — not a
  rewritten or fabricated instruction — so later turns in the thread can refer
  back to the report (cf. FR-AG-36).
- FR-DS-28: A run's history entry consists of the user's literal command, the
  retrieval step's tool call and result, and the report. The per-region passage
  fetches and analyses are not recorded in conversation history — a run's tool
  trace is observable in the log (FR-DS-19), not in the thread the next turn
  carries.
- FR-DS-29: The retrieval step's tool result carries each read region's
  identity, source, human-readable locator, rank and score, and carries no
  passage text. Passage text reaches a run only through the per-region
  structural-coordinate fetch (FR-DS-15).
- FR-DS-30: Neither command changes the session's semiotic system, sign,
  tradition, or active hotspot.
- FR-DS-31: The plan turn emits one `confirm_discovery` instruction carrying the
  discovery's id, its parsed focus, its parsed terms, and the confirmation
  command verbatim. The type is declared with no binding: it triggers no request
  and is handled by the consumer itself ([agent-capabilities.md](agent-capabilities.md)
  FR-CAP-07). A consumer's affordance runs the discovery by sending the
  identical command string a human would type, so the affordance and the typed
  command are one path rather than two (cf. FR-AQ-07, FR-WEB-21). A `/discover`
  that fails to parse emits no instruction.
