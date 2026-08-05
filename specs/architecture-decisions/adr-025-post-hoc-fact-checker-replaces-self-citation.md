# ADR-025 — A dedicated fact-checking model tags grounding, replacing self-citation and in-graph retry

- **Status**: Accepted
- **Date**: 2026-08-04
- **Extends**: [ADR-006](adr-006-conversational-agent-orchestration-boundary.md), [ADR-022](adr-022-tool-owned-opaque-grounding-ids.md)
- **Supersedes**: [ADR-023](adr-023-in-graph-citation-retry.md)
- **Realized by**: [agent.md](../interfaces/agent.md) FR-AG-06

## Context

ADR-023 asked the same model that composes the conversational answer to also
cite it correctly, inline, on the first attempt, retrying on an invalid
marker. Real-model testing against `qwen3:1.7b` found the model could satisfy
the citation check without genuinely re-grounding the claim — a small local
model asked to *compose* an answer and *correctly cite it inline* in one pass
is being asked to do two jobs at once, and the second degrades whenever it
competes with the first for the model's limited attention.

Separately, `[G#]`/`[S#]` markers have never been shown to the user —
`strip_markers` removes them unconditionally before a reply is delivered.
The mechanism has always been an internal grounding *check*, not a citation
*feature*, so the fix does not need to preserve inline citation authorship as
a model responsibility — only the check.

An earlier design considered here had the fact-checker echo the answer back
with grounding tags inserted inline, verified by confirming that stripping
the tags reproduced the original text byte-for-byte. Real-model testing
found several distinct ways a small model could fail to reproduce text
faithfully while editing it. The common cause: reproduction of text the
model isn't supposed to touch has a non-zero failure rate on a small local
model regardless of prompting. The design below removes that task rather
than continuing to harden it.

## Decision

Citation grounding for the conversational turn moves from the primary
model's own output to a **second, dedicated fact-checking model call**, made
after the primary model's final answer (no further tool calls):

- The primary model is told nothing about grounding ids anymore. It answers
  freely; composing the answer is its only job.
- A new graph node, `fact_check_node`, replaces the retry node on the
  `agent -- final answer -->` edge. It builds this turn's evidence from the
  citable items this turn's tools returned, and sends it — alongside the
  answer split into numbered sentences, done deterministically in code — to
  a separate model call over the same narrow, tool-less client every other
  generative call uses (ADR-006's boundary applies unchanged).
- **The fact-checker never receives or returns the answer's own text.** It
  is given only the numbered sentences and the evidence, and returns a
  compact per-sentence classification: supported or not, and if supported,
  which evidence id(s). There is nothing for it to reword, truncate,
  reorder, or echo, because it never has custody of the text it would need
  to reproduce — the guarantee that the displayed answer is untouched is
  structural, not a check the model could get wrong.
- There is no retry and no rejection. Every failure mode — the call
  unreachable, its response unparseable, or an answer with no sentences to
  classify — falls back to the original, untouched answer, never a
  citation-failure message. A failed *classification* pass is not a
  grounding failure.
- A grounding score is computed in code from the parsed verdicts — never
  self-reported by the model. A verdict counts as supported only when the
  model marked it so *and* cites an id that actually exists in this turn's
  evidence. The score is appended to the reply as a plain-text footer; this
  is the one part of the mechanism that is user-visible, by deliberate
  choice — individual citations stay internal, but the aggregate signal is
  surfaced.
- The fact-checking core takes plain types, with no dependency on graph
  state — only the thin parsing layer between tool messages and evidence
  knows about the conversational path's plumbing. `/summarize` and
  `/augment` are out of scope for this decision (their citation risk
  profiles and generation shapes differ) but can build their own evidence
  list onto the same core later.

## Consequences

- The primary model's prompt gets strictly smaller and simpler — one fewer
  instruction competing for a small local model's attention while it
  composes an answer.
- The reproduction-drift failure class found hardening the tag-and-reproduce
  draft is removed by construction, not mitigated: the fact-checker's task
  has no step in which it holds or returns the answer's own text. What
  remains is a schema-validity failure mode, a smaller problem, defended by
  constrained JSON decoding plus code-side parsing rather than a
  text-comparison check.
- Grounding no longer gates whether a reply is shown. This is a deliberate
  trade against ADR-023's design, which would hide an uncorrectable reply
  behind a rejection message: a plausible answer with a low grounding score
  is now shown to the user, with the score as a visible signal, rather than
  replaced with a generic apology. That message is not removed — it remains
  correct for `/augment` and as the conversational path's redundant
  backstop — but `fact_check_node` itself never produces it.
- One more full model call is added to every conversational turn that
  called a citable tool, on top of the primary model's own call(s). This is
  a real latency/cost trade against ADR-023's retry loop, which only cost
  extra calls on an invalid reply; a fixed second pass is now paid on every
  turn with evidence to check. The call's own output budget is small — a
  short classification, not the full answer echoed back — which keeps this
  pass cheaper than the reproduce-and-tag design it replaces.
- `Settings.citation_max_retries` is removed; a new `Settings.fact_check_model`
  (falling back to `agent_model`, then `generation_model`) lets an operator
  point the fact-checker at a different local model than the conversational
  agent, without requiring one.
- The `[G#]`/`[S#]`/`[C#]`/`[R#]` marker vocabulary ADR-022 established is
  unchanged — no new marker is added, since the fact-checker never writes
  into the answer's text at all.

## Alternatives considered

- **Tag the answer inline, verified by reproducing the original text.** This
  was the original approach for this decision; rejected once real-model
  testing showed reproduction itself has a non-zero failure rate on a small
  local model (see Context).
- **Retry the primary model on an ungrounded claim, driven by the
  fact-checker's judgment instead of a marker regex.** Rejected — the point
  of this design is to stop treating grounding as a reason to regenerate or
  withhold the answer at all, not to swap the retry loop's judge.
- **Show the fact-checker's citations to the user.** Rejected for this pass
  — matches the existing, already-internal-only behavior of `[G#]`/`[S#]`
  markers; a user-facing citation UI is a separate, larger feature not
  assumed here.
