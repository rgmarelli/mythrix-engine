# ADR-025 — A dedicated fact-checking model tags grounding, replacing self-citation and in-graph retry

- **Status**: Accepted
- **Date**: 2026-08-04
- **Extends**: [ADR-006](adr-006-conversational-agent-orchestration-boundary.md), [ADR-022](adr-022-tool-owned-opaque-grounding-ids.md)
- **Supersedes**: [ADR-023](adr-023-in-graph-citation-retry.md)
- **Realized by**: [agent.md](../interfaces/agent.md) FR-AG-06

## Context

ADR-023 asked the same model that composes the conversational answer to also
cite it correctly, inline, on the first attempt — and gave it up to
`citation_max_retries` corrective chances when it didn't. Two further fixes
landed on top of that mechanism in the days after it shipped (`b2aedbe`,
`b5ebe7c`): real-model retries against `qwen3:1.7b` kept finding new ways to
satisfy the regex check without genuinely re-grounding the claim — collapsing
the answer to a bare id list, or pasting a named-bad marker onto unrelated
prose once the pushback revealed it. Each fix chased a specific failure mode
of the same underlying design rather than the design itself: a small local
model asked to *compose* an answer and *correctly cite it inline* in one pass
is being asked to do two different jobs at once, and the second one degrades
whenever it has to compete with the first for the model's limited attention
and instruction-following budget.

Separately, `docs/agent-graph.md` and `turn_service.py` make explicit
something the self-citation design never surfaced: `[G#]`/`[S#]` markers
have never been shown to the user. `strip_markers` removes them
unconditionally before a reply is delivered (only `/augment`'s `[R#]`
region markers survive, for a structurally different reason — they identify
a viewer-scoped region, not a tool-result item). The entire mechanism has
always been an internal grounding *check*, not a citation *feature* — which
means the fix does not need to preserve inline citation authorship as a
model responsibility at all; it only needs to preserve the check.

An earlier draft of this decision (superseded within this same ADR, before
it was ever committed — see "Revision" below) tried to preserve that
check by having the fact-checker echo the primary model's full answer back
with grounding tags inserted inline, verifying in code that stripping the
tags reproduced the original text. Six distinct real-`qwen3:1.7b` failure
shapes were found hardening that design (an appended closing remark, a
deleted-and-replaced clause, a duplicated/reordered clause, markdown/list
reformatting, and a whole evidence-block echo), each fixed in turn without
the failure rate reaching zero. The common cause: **the task asked the model
to reproduce text it wasn't supposed to touch**, and reproduction has a
non-zero failure rate on a small local model regardless of how the prompt
is worded. The design below removes that task rather than continuing to
harden it.

## Decision

Citation grounding for the conversational turn moves from the primary
model's own output to a **second, dedicated fact-checking model call**,
made after the primary model's final answer (no further tool calls):

- The primary model (`agent_node`, `SYSTEM_PROMPT`) is told nothing about
  grounding ids anymore. It answers freely; composing the answer is its only
  job.
- A new node, `fact_check_node` (`agent/graph/nodes/fact_check.py`), replaces
  `validate_citations_node` on the `agent -- final answer -->` edge. It
  builds this turn's evidence — `source`/`locator`/`text` for every citable
  item `get_sign`/`query_sign`/`fetch_segments` returned this turn, read via
  a widened `agent/citation_grounding.py` — and sends it, alongside the
  primary model's answer split into numbered sentences
  (`agent/fact_check.py::split_sentences`, done deterministically in code),
  to a separate model call (`agent/fact_check.py::run_fact_check`) over the
  same narrow, tool-less `ChatClient` every other generative tool uses
  (ADR-006's boundary applies unchanged: the fact-checker orchestrates
  nothing and calls no tool).
- **The fact-checker never receives or returns any of the answer's own
  text.** It is given only the numbered sentences and the evidence, and
  returns a compact JSON classification keyed by sentence index —
  `{"results": [{"index": 0, "supported": true, "citations": ["G4f9a2c"]}, ...]}`
  — omitting a sentence entirely when it states no factual claim. There is
  nothing to reword, truncate, reorder, or echo, because the model never has
  custody of the text it would need to reproduce. `fact_check_node` parses
  this into `SentenceVerdict`s and validates the response's *structure*
  (well-formed JSON, an `index` in range, a boolean `supported`) rather than
  comparing reproduced text against the original — the guarantee that the
  displayed answer is untouched is now structural (the model's output is
  never the answer's text at all), not a check the model could get wrong.
- There is no retry and no rejection. Every failure mode — the fact-check
  model unreachable, its response unparseable, or an answer with no
  sentences to classify — falls back to the **original, untouched answer**,
  not a citation-failure message. Grounding was never a reason to withhold a
  reply under this design; a failed *classification* pass is not a grounding
  failure.
- A `grounding_score` (`agent/fact_check.py::grounding_score`) is computed in
  code from the parsed verdicts — never self-reported by the model, and
  never from the model's own top-level `verified` field, which nothing
  reads. A verdict counts as supported only when `supported=true` *and* at
  least one of its citations is an id this turn's evidence actually has;
  `supported=true` with no valid citation counts as unsupported, since the
  boolean alone is not trusted. The score is appended to the reply as a
  plain-text footer (`\n---\nfacts checked: NN%`). This is the one part of
  the mechanism that is user-visible, by deliberate choice: individual
  citations stay exactly as internal as they always were (they never reach
  the displayed reply at all now, tagged or otherwise), but the aggregate
  signal is surfaced.
- The fact-checking core (`agent/fact_check.py::run_fact_check`,
  `agent/citation_grounding.py`'s evidence extraction) takes plain
  types — `list[Evidence]`, `tuple[str, ...]` — with no dependency on
  `AgentState`, LangGraph, or `ToolMessage`. Only the thin
  `ToolMessage`-parsing layer (`evidence_from_tool_messages`) and the graph
  node itself know about the conversational path's specific plumbing.
  `/summarize` and `/augment` are explicitly out of scope for this decision
  (their citation risk profiles and generation shapes differ, same reasoning
  ADR-023 already gave for leaving `/augment` alone) but can adopt the same
  core later by building their own evidence list from the dicts they already
  hold.
- The fact-check model call sets Ollama's `format="json"` (`api/dependencies.py`),
  constraining decoding to syntactically valid JSON at the daemon level —
  belt-and-suspenders with the code-side parser, which still validates the
  *schema* of a well-formed-but-wrong-shaped response.

## Consequences

- The primary model's prompt gets strictly smaller and simpler — one fewer
  instruction competing for a small local model's attention while it
  composes an answer.
- The reproduction-drift failure class (six distinct shapes found hardening
  the superseded tag-and-reproduce draft) is removed by construction, not
  mitigated: the fact-checker's task has no step in which it holds or
  returns the answer's own text, so there is nothing left for it to
  mishandle that way. What remains is a schema-validity failure mode
  (malformed/unparseable JSON, an out-of-range index) — a different, smaller
  problem, defended by `format="json"` plus code-side parsing rather than a
  text-comparison check.
- Grounding no longer gates whether a reply is shown. This is a deliberate
  trade against ADR-023's design (which would hide an uncorrectable reply
  behind `CITATION_FAILURE_MESSAGE`): a plausible answer with a low
  `grounding_score` is now shown to the user, with the score as a visible
  signal, rather than replaced with a generic apology. `CITATION_FAILURE_MESSAGE`
  is not removed — it remains the correct behavior for `/augment` and the
  conversational path's redundant backstop in `turn_service.py`, both
  unaffected by this decision — but `fact_check_node` itself never produces
  it.
- One more full model call is added to every conversational turn that called
  a citable tool, on top of the primary model's own call(s). This is a real
  latency/cost trade against ADR-023's retry loop, which only cost extra
  calls on an invalid reply; a fixed second pass is paid on every turn with
  evidence to check, whether or not the first answer needed correction. The
  call's own output budget is small (a short JSON classification, not the
  full answer echoed back), which keeps this pass cheaper than the
  reproduce-and-tag design it replaces.
- `Settings.citation_max_retries` is removed; a new `Settings.fact_check_model`
  (falling back to `agent_model`, then `generation_model` — the same pattern
  `agent_model` itself already establishes) lets an operator point the
  fact-checker at a different local model than the conversational agent,
  without requiring one.
- The `[G#]`/`[S#]`/`[C#]`/`[R#]` marker vocabulary `agent/citations.py` and
  ADR-022 established is unchanged by this decision — no `[UNSUPPORTED]`
  marker is added, since the fact-checker never writes into the answer's
  text at all.

## Alternatives considered

- **Have the fact-checker tag the answer inline, verified by reproducing the
  original text.** This was this ADR's original decision, replaced by the
  design above before ever being committed (see "Revision" below) — kept
  here as the alternative it now is, not deleted, since the failure record
  behind rejecting it is exactly what justifies not returning to it.
- **Retry the primary model on an ungrounded claim, as ADR-023 did, but
  driven by the fact-checker's semantic judgment instead of a marker
  regex.** Rejected — as directed: the point of this design is to stop
  treating grounding as a reason to regenerate or withhold the answer at
  all, not to swap the retry loop's judge.
- **Show the fact-checker's citations to the user.** Rejected for this pass
  — matches the existing, already-internal-only behavior of `[G#]`/`[S#]`
  markers; a user-facing citation UI (akin to `[R#]`'s region links) is a
  separate, larger feature with its own frontend scope, not assumed here.
  Only the aggregate score is surfaced, as a plain-text footer requiring no
  API or frontend change.

## Revision (2026-08-05)

The original decision above (structured JSON output rejected in favor of a
tag-and-reproduce design verified by a no-reword text comparison) was
revised, before ever being committed, to the sentence-indexed JSON
classification design now documented above — directed after six real-model
failure shapes were found hardening the reproduce-and-tag mechanism (see
Context). Since this ADR had not yet landed, the revision is made in place
per the normal editing rule for an in-flight decision, rather than as a
separate superseding ADR.
