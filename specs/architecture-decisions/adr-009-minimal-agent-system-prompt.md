# ADR-009 — Minimal system prompt for the local tool-calling agent

- **Status**: Accepted
- **Date**: 2026-07-27
- **Realized by**: [prompts.py](../../api/src/mythrix/agent/prompts.py); [agent.md](../interfaces/agent.md) FR-AG-06, FR-AG-23–FR-AG-26, FR-AG-28–FR-AG-32; [ADR-006](adr-006-conversational-agent-orchestration-boundary.md)

## Context

ADR-006 commits the agent to a **local-only Ollama model**, not a hosted
frontier model. That choice has a direct consequence for prompt design: a
small local model has far less spare instruction-following capacity than a
commercial model, and every additional rule in the system prompt competes
with tool-call selection and argument formatting for that capacity.

The original system prompt encoded the full `agent.md` behavioral spec
directly as prose: the sign/tradition/interpretant domain model, verbose
tool-selection rules, an exhaustive enumeration of how a user might refer to
the active hotspot, a "report all items but don't re-quote them" rule, a
`[G#]`/`[S#]` citation-marker scheme with its own numbering rules, and a
"working notes" mechanism that asked the model to end replies with a fenced
`` ```agent-notes `` block for the agent's own later reference. It also told the
model to reply in **plain prose only — no markdown** ("no `**bold**`, no
`#` headings, no `-`/`*` bullet lists ... markdown syntax would show up as
literal stray characters"), because at the time the chat UI rendered
assistant replies as plain text.

That last rule directly contradicted the working-notes rule two paragraphs
later, which required emitting a fenced code block — markdown syntax — for
every reply worth remembering. A small local model asked to never produce
markdown and also to reliably produce a markdown fence in the same
response does not resolve the contradiction gracefully; observed behavior
was the model derailing mid-turn into loose prose (e.g. narrating "Fetch
segments from source..." as text) instead of emitting a clean tool call,
which the LangGraph tool-call parser then failed to recognize. The other
rules compounded the same problem at a smaller scale: each one is
reasonable in isolation, but stacked together in a single system prompt
they left less of the model's limited attention on the one thing that
determines whether the turn works at all — picking the right tool and
formatting its arguments.

## Decision

Keep the agent's system prompt (`prompts.py::SYSTEM_PROMPT`) intentionally
short, and resolve behavioral requirements at the layer that actually owns
them rather than by adding another prompt rule:

- The prompt states only what changes model *behavior*: which tool to use
  for which purpose, the "Active hotspot" → immediate `fetch_segments` rule,
  a stop condition against re-fetching adjacent segments, the no-fabrication
  rule, and the `[G#]`/`[S#]` grounding-marker convention. It does not
  restate the domain model (semiotic systems/signs/traditions) — the tool
  results themselves carry that structure.
- Formatting constraints imposed for the UI's benefit, not the model's
  correctness, are enforced by the UI instead of the prompt. Markdown was
  the concrete case: rather than banning markdown in the prompt to keep a
  plain-text renderer happy, the chat panel now renders assistant markdown
  (FR-AG-23–FR-AG-25) and the backend stops stripping it (FR-AG-26), so the
  prompt no longer needs a formatting rule — or a contradiction — at all.
- Mechanisms that ask the model to maintain state across turns in its own
  reply text (the `agent-notes` fenced block) were removed rather than kept
  and reworded. Cross-turn state the agent needs (which sign/tradition/hotspot
  is active) is already tracked deterministically in `AgentContext`
  (`context.py`, backfilled from tool results, never from model prose); a
  free-text note the model must remember to emit correctly every turn was
  redundant with that and an extra way for a small model's output to
  degrade.
- Citation/grounding rules stay, but as a short convention (`[G#]`/`[S#]`,
  numbered in result order) rather than a multi-paragraph explanation of the
  "report all items without re-quoting them" nuance — the nuance is real,
  but it is enforced in code (`turn_service.py`'s marker validation against
  `core/synthesis/citations.py`) rather than depended on from prose alone.

## Consequences

- The prompt asks the model to do one job in a turn — choose and call a
  tool, or answer from what tools already returned — instead of
  simultaneously satisfying a domain-model recap, a formatting ban, a
  citation scheme, and a note-taking convention. This is a direct trade
  against ADR-006's "small local models may mis-select or mis-format tool
  calls" acknowledged risk: less prompt content the model must hold at once
  is the lever this ADR uses in addition to the stronger-local-model
  override ADR-006 already allows.
- Requirements that used to live only in prose now live where they are
  actually enforced: markdown handling in the UI (FR-AG-23–FR-AG-26) and
  citation-marker correctness in `citations.py`, validated in
  `turn_service.py` rather than trusted from the prompt alone. A prompt rule
  with no code backing it is advisory only; moving enforcement to code where
  possible makes the guarantee hold even when the model doesn't follow the
  prompt precisely.
- No general mechanism replaces `agent-notes`. If a future feature needs the
  agent to persist something across turns that `AgentContext`'s fixed fields
  don't cover, that is a new, explicitly-scoped field on `AgentContext`
  (deterministic, code-set), not a free-text convention asked of the model.
- The prompt will grow again as new tools or behaviors are added. The
  guardrail this ADR establishes is not "the prompt must stay under N
  lines" but "a new rule belongs in the prompt only if it changes what the
  model decides, not what the surrounding code already guarantees or could
  guarantee instead."

## Alternatives considered

- **Keep the exhaustive prompt and fix only the markdown contradiction.**
  Rejected — the contradiction was the sharpest symptom, but the underlying
  problem was total instruction load on a small model, not one bad rule;
  trimming only the one line would have left the same class of failure
  available to recur with the next rule added.
- **Keep formatting rules in the prompt and drop the working-notes
  requirement instead of also moving markdown to the UI.** Rejected —
  banning markdown in the prompt was solving a UI limitation with a model
  constraint. Once the UI could render markdown, the prompt rule had no
  remaining purpose, so removing it (rather than just decontradicting it)
  was strictly better.
- **A larger/cloud model for tool-calling instead of trimming the prompt.**
  Rejected — ADR-006 already fixes the agent to a local Ollama model; that
  boundary is not reopened here.
