# Spec: Hierarchical consolidation for `/augment`

## Problem

A run of `/augment-confirm` produces one augmentation per region, then consolidates all of them into a single synthesized answer with one generation-model invocation. That invocation is given every augmentation's full text in one prompt. As the number of augmented regions grows, the quality of the resulting consolidation degrades — the run's answer stops reliably describing what recurs and diverges across the augmentations.

## Goals

- A run's consolidation quality does not degrade as the number of augmented regions grows.
- The number of generation-model invocations a run performs remains deterministic, bounded, and known before the run starts.
- Every `[R#]` citation marker delivered in a run's terminal reply names a region this run actually augmented, regardless of how many consolidation steps produced the reply.

## Non-goals

- Changing what an individual region's augmentation contains or how it is produced (FR-AU-17–FR-AU-19 are unaffected).
- Changing `augment_max_regions` or the bound it enforces on the number of regions a run reads.
- Making the orchestration model a participant in consolidation. Consolidation remains fully deterministic (ADR-015).
- Running consolidation concurrently. Consolidation, like augmentation, remains sequential within a run.

## Functional requirements

- FR-1: Once every augmented region's reading has been produced, the run's augmentations are consolidated into a single answer to the run's focus through one or more generation-model invocations, never more than one prompt's worth of augmentations per invocation.
- FR-2: The maximum number of augmentations (or prior consolidation results) one invocation may be given is a fixed, configured bound.
- FR-3: When the number of a run's augmentations does not exceed that bound, the run performs exactly one consolidation invocation, given the augmentations directly — the same behavior as before this change.
- FR-4: When the number of a run's augmentations exceeds that bound, they are grouped into batches no larger than the bound; each batch is consolidated by one invocation; if more than one batch's worth of results remain, those results are themselves grouped and consolidated again; this repeats until exactly one result remains, which is the run's answer.
- FR-5: An invocation above the first level is given only prior consolidation results, never raw region passage text and never the individual augmentations directly.
- FR-6: A region's `[R#]` marker is assigned once, when its augmentation is produced, and is never reassigned, renumbered, or replaced by a later consolidation step. Every consolidation invocation above the first level is instructed to preserve, unchanged, every such marker present in what it is given, and to introduce no marker of its own.
- FR-7: The run's terminal reply carries only `[R#]` markers naming regions this run augmented, regardless of how many consolidation levels produced the reply — the existing citation-validation guarantee (FR-AU-31) holds unchanged.
- FR-8: The total number of generation-model invocations a run performs is deterministic given the number of augmented regions and the configured bound, and is known once augmentation completes, before consolidation begins.
- FR-9: The plan a user is shown before confirming a run states how many consolidation invocations the run will perform, as a plain count.
- FR-10: As each consolidation invocation other than the run's final one completes, the run reports progress before continuing, the same way an individual region's completion is already reported. The run's final consolidation invocation is not separately reported, since its result is the terminal reply itself.
