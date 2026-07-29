# ADR-016 — Consolidate a run's augmentations hierarchically, bounded by a configured group size, rather than in one flat invocation

- **Status**: Accepted
- **Date**: 2026-07-29
- **Realized by**: [augmentation.md](../interfaces/augmentation.md) FR-AU-20, FR-AU-21 (revised), FR-AU-39–FR-AU-41
- **Narrows**: [ADR-015](adr-015-deterministic-augmentation-over-viewer-regions.md)'s "exactly one further generation-model invocation" / "exactly N+1... never more" clauses

## Context

[ADR-015](adr-015-deterministic-augmentation-over-viewer-regions.md) established that a run reads N regions, produces N augmentations, and consolidates them with exactly one further generation-model invocation given every augmentation's full text in a single prompt. That invocation's quality does not hold as N grows: `docs/TODO.md` records that raising `augment_max_regions` to 50 "produces bad consolidation," with 20 tested as accurate. The single call is being asked to hold and synthesize an increasing number of independent readings at once, against a fixed `generation_num_ctx`; degraded synthesis quality, not merely truncation, is the observed failure.

The complication specific to this codebase is that each augmentation carries a citation marker (`[R#]`, FR-AU-30) the consolidation cites, and the run's terminal reply is validated against those exact markers regardless of how the consolidation was produced (FR-AU-31). Any restructuring of the consolidation step has to keep every marker traceable to the region it names, however many generation calls produce the final text.

## Decision

**A run's augmentations are consolidated hierarchically: grouped into batches of at most a configured size, consolidated batch by batch, and — if more than one batch's worth of results remain — consolidated again, until exactly one result remains.**

Concretely:

- **`augment_consolidation_group_size`** (`core/config.py`) bounds how many augmentations, or prior consolidation results, one consolidation invocation may be given, at every level. A run whose augmentations do not exceed it performs exactly one consolidation invocation, given the augmentations directly — unchanged from ADR-015's original behavior.
- **Two node-only tools, split by what they are given, not one overloaded.** `consolidate_augmentations` is used only for the first level: raw, individually `[R#]`-labeled augmentation texts, and its prompt cites from that label vocabulary — unchanged from ADR-015. A new `rollup_augmentations` tool is used for every level above it: already-synthesized summaries that each already embed `[R#]` markers from a lower level, with no label of their own. Its prompt's one load-bearing instruction is the opposite of the leaf prompt's: carry every marker already present forward verbatim, and invent none. Overloading a single tool for both shapes was rejected — see Alternatives.
- **A marker is assigned once, at the first consolidation level, and never reassigned.** Every invocation above that level is given no vocabulary to invent a marker from, only an instruction to preserve what it is given unchanged. The run's terminal reply is validated exactly as before (FR-AU-31), against the same run's leaf-level region record, regardless of how many levels produced the text carrying the markers that survive into it.
- **The total invocation count is `N + C`, deterministic and known before consolidation begins**, where `C` is arithmetic in `N` and `augment_consolidation_group_size` (FR-AU-21) — never a function of model behavior, matching ADR-015's original arithmetic-bound property, just with a formula that is no longer always `1`. The plan a user is shown before confirming states this count as a plain number, never "up to," consistent with how the region counts are already stated exactly.
- **Progress streams for the reduce phase, mirroring FR-AU-23's precedent.** As each consolidation invocation other than a run's last completes, a chat message reports progress; no instruction accompanies it, since a batch's result addresses no single region. The final invocation is not separately announced, since its result is the terminal reply itself.

## Consequences

- Total generation calls become `N + C(N, group_size)` rather than `N+1`. For `N` at or below the group size this is identical to ADR-015's original behavior; larger `N` now means a longer chain of sequential calls held on one open connection — the same unmitigated "no timeout anywhere" risk ADR-015 already named, now larger for large runs.
- Two prompts (`render_consolidation_prompt`, `render_rollup_prompt`) and two tools now have to be kept in sync with the marker-preservation invariant, rather than one prompt and one tool.
- `augment_consolidation_group_size` becomes a second context-budget dial alongside `generation_num_ctx`: raising `augment_max_regions` well past the ~20–50 range that previously degraded consolidation quality no longer requires touching consolidation itself, only wall time.
- Everything else ADR-015 decided — the node-only tool split's reachability property, region identity as the sole consumer-supplied trust surface, per-region streaming, the narrowed history-recording rule (`_record_messages`), sequential (non-concurrent) execution — is unchanged and not restated here.

## Alternatives considered

- **Overload `consolidate_augmentations` for both the leaf level and the rollup level.** Rejected — its prompt's citation contract depends on every input having exactly one label that is the call's citation vocabulary. Feeding it multi-marker summaries either forces a synthetic per-group label the citation validator's `[G#]/[S#]/[C#]/[R#]` pattern does not recognize (surviving as inert, confusing literal text), or invites the model to treat a whole summary as one new claim and drop the markers embedded in it — breaking the marker-preservation invariant this decision exists to hold.
- **Raise `generation_num_ctx` instead of restructuring consolidation.** Rejected — the TODO's own empirical finding is about answer *quality* degrading as more independent readings are asked to be synthesized at once, not merely about fitting a prompt inside a context window. A larger window does not make one call better at synthesizing fifty independent readings.
- **A deterministic, non-LLM merge above the leaf level (e.g., concatenation).** Rejected — it relocates the flat-dump problem one level up and produces disjointed prose instead of a further synthesis, which is the actual complaint the TODO records, not just token overflow.
- **Consolidate groups concurrently.** Rejected for the same reason ADR-015 rejected concurrent per-region augmentation: the ordered progress stream is what keeps a long run legible, and wall time is not yet the binding constraint.
