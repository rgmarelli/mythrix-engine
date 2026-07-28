# ADR-010 — A scoped, deterministically-gated exception for ad-hoc, graph-independent interpretant queries

- **Status**: Proposed
- **Date**: 2026-07-27
- **Realized by**: [agnostic-query.md](../interfaces/agnostic-query.md) (new); [agent.md](../interfaces/agent.md) non-goals (amended)

## Context

Mythrix's evidentiary chain rests on FR-CO-03 ([corpus.md](../retrieval/corpus.md)): retrieval
query text is built entirely from retrieved `GraphFacts` — a curator-authored
interpretant's `value` — "never raw, unvalidated user input." The conversational
agent (ADR-006) is bounded the same way: its LLM may converse and select tools,
but never decides what a retrieval result *is*, and [agent.md](../interfaces/agent.md)'s
non-goals explicitly state the agent "does not parse free text into retrieval
query text."

Users want a capability neither of these paths supports: searching the corpus
directly on an arbitrary, user-typed list of terms — e.g. `/query laughter,
child, hundred:exact, pisces:filter` — with no Sign or Tradition named at all.
This reuses the same directive vocabulary curated interpretants already carry
(`QueryDirective.directive: "exact"|"filter"`, FR-RT-09/15/17–19), just
authored by the user instead of a curator. No existing entry point can satisfy
this: `query_regions`/`RetrievalPipeline.retrieve` and the CLI's `query` command
all require a `GraphFacts` resolved from a real `Sign`+`Manifestation` in the
graph store; none accepts bare text.

Granting that capability raises a second, separate question: **what enforces
the boundary?** Two candidates exist. The model can parse the term list, present
it, and be instructed by the system prompt to call an execution tool only after
the user agrees — or the whole exchange can be handled deterministically, in
code, with the model uninvolved. FR-AG-32 and [ADR-009](adr-009-minimal-agent-system-prompt.md)
already settle this class of question in general terms ("where enforcement in
code is possible, that takes precedence over relying on the model to follow a
prompt instruction"), and both halves of this exchange are fully
deterministic: the command syntax is fixed, and the confirmation is a
yes/no whose only failure mode that matters — executing a query the user never
approved — is precisely what this ADR is meant to bound.

## Decision

Introduce a second, explicitly separate query path — an ad-hoc/agnostic
query — permitted to build query text from raw user-typed terms, bounded by
four constraints:

1. **A fully separate entry point.** A new service function
   (`execute_adhoc_query`) and endpoint (`POST /api/query/adhoc`) carry this
   capability; neither `query_regions`, the CLI `query` command, nor the graph
   store's `get_manifestation` are touched. FR-CO-03 continues to hold,
   unmodified, for every existing graph-native path — this is an addition
   alongside it, not a relaxation of it.
2. **Retrieval/ranking code itself is untouched.** Ad-hoc terms are turned into
   ordinary `Interpretant` objects (using the same `QueryDirective` vocabulary)
   on a synthetic, sentinel `GraphFacts`, then fed into the same
   `RetrievalPipeline` every graph-native query already uses. Matching, match
   floors, specificity weighting, and region rollup all run exactly as they do
   today — FR-RT-03 ("no model participates in deciding what a result *is*")
   holds without change, since nothing about *how* a term is matched changes,
   only *where the term's text came from*.
3. **The generation model is not part of this path at all.** The `/query`
   command and its confirmation are recognized and handled by dedicated
   deterministic steps in the agent's state machine, ahead of the model's
   tool-calling loop. Parsing the term list, restating it back to the user,
   validating the confirmation, and emitting the resulting instruction are all
   code. The agent's tool set gains no tool, and the system prompt gains no
   rule — nothing about this feature depends on model compliance, so ADR-009
   and FR-AG-28/32 are satisfied by construction rather than by wording.
4. **Confirmation is structurally gated, not interpreted.** Parsing a `/query`
   command mints a pending ad-hoc query held in server-side session state under
   a backend-generated id, and emits a `confirm_query` instruction naming that
   id. Execution happens only when a later turn presents that exact id back via
   an explicit confirmation command; the terms executed come from the stored
   pending record, never from the confirming message. No message is ever
   inspected for affirmative intent, by whitelist or by model — an unmatched id
   simply does not execute.

Execution itself remains a hand-off: the confirmed turn emits a
transport-agnostic `execute_query` instruction (`{"type": ..., "payload":
...}`) carrying no HTTP method or path, and performs no retrieval inside the
agent turn. Every result this path can produce is unambiguously marked
non-graph-native (sentinel `sign`/`tradition` identifiers on the synthetic
`GraphFacts`, e.g. `sign="adhoc"`), so it can never be confused with curated
Sign Graph content downstream.

## Consequences

- FR-CO-03 remains true as a general rule; this ADR documents one narrow,
  explicitly-scoped exception to it, not a relaxation.
- The agent's "does not parse free text into retrieval query text" non-goal
  survives almost intact: no *free text* is parsed and no *model* parsing
  occurs anywhere. What is excepted is narrower than the capability itself —
  a deterministic parser turns one structured command's operands into query
  text. The agent's conversational layer is unchanged.
- No change to any existing tool, the CLI, or the graph-native
  retrieval/ranking code — every FR-RT-07–20 requirement applies to the ad-hoc
  path with zero new matching/ranking logic. The agent's tool set stays exactly
  as FR-AG-03 defines it.
- Confirmation is now a code-level guarantee rather than a trust assumption:
  there is no sequence of model behavior that can execute an ad-hoc query the
  user did not confirm, because the model is never consulted. The cost is
  rigidity — a user who replies "yes" instead of sending the confirmation
  command is not understood, and must send the command. This trade is
  deliberate: a false negative costs one retry, a false positive is the failure
  this ADR exists to prevent.
- Because these turns bypass the model entirely, they contribute nothing to the
  conversation history and cannot influence any later reply. The corollary is
  that the agent has no awareness of an ad-hoc query the user ran — it cannot
  discuss or refer back to one. Acceptable, since results are rendered by the
  instruction's consumer, never narrated by the agent.
- The restating reply names the confirmation command in plain text, so the
  whole flow is completable — and testable — with no consumer that understands
  instructions at all. A frontend that does understand `confirm_query` renders
  it as an affordance that sends the very same command; the two paths share one
  implementation rather than diverging.
- This ADR licenses only the backend/agent-side half of the feature. Actually
  calling `POST /api/query/adhoc` from the browser and rendering its results
  is deliberately out of scope here and deferred to a later increment.

## Alternatives considered

- **Extend `query_regions`/the CLI `query` command to accept raw text
  directly.** Rejected — this would blur FR-CO-03's guarantee on the
  *graph-native* path itself, rather than keeping the exception contained to a
  path that is structurally impossible to reach except through an explicit,
  confirmed command.
- **Let the model parse the term list and call an execution tool, with the
  system prompt forbidding it from doing so before the user confirms.**
  Rejected under FR-AG-32/ADR-009: the parse is entirely deterministic, so it
  belongs in code; and a prompt rule cannot actually prevent the model from
  calling the tool in the same turn it presents the list — it can only ask.
  This alternative also spends a tool slot and a prompt rule on a flow that
  needs neither.
- **Interpret the confirming turn's language** (an affirmative whitelist such
  as "yes"/"ok"/"go ahead", or a model classification of intent). Rejected —
  both admit false positives, which is exactly the failure this ADR bounds,
  and a whitelist additionally fails on ordinary phrasings it does not contain.
  An id-carrying command has neither problem.
- **Let the confirmed turn run retrieval and narrate cited results inline**
  (the way `query_sign` does today). Considered, rejected for this increment:
  it would require new citation-marker handling for a result shape the
  corpus-grounding invariant wasn't built around, and would run retrieval
  inside the agent turn for a path this ADR wants kept structurally distinct.
  Returning a descriptor for a consumer to act on keeps the agent
  transport-agnostic and avoids extending the citation-validation surface.
