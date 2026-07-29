# Region Augmentation

A confirmation-gated chat command that reads every region the consumer is
currently displaying ([web-viewer.md](web-viewer.md)) against a free-text
focus, delivers each reading as it is produced, and consolidates the readings
into one cited answer, consolidated hierarchically when there are more than
one batch's worth of them
([ADR-016](../architecture-decisions/adr-016-hierarchical-map-reduce-augmentation-consolidation.md)).
Served by the [Conversational Agent](agent.md)'s chat panel and handled
entirely in code, without the orchestration model's tool selection
([ADR-015](../architecture-decisions/adr-015-deterministic-augmentation-over-viewer-regions.md)).

## Vocabulary

- **focus**: The free-text analysis instruction an augmentation command carries.
  It is applied to every augmented region and answered across all of them.
- **visible regions**: The ordered list of region identities the consumer is
  displaying when a turn is sent.
- **augmentation**: One region's generated reading, produced by applying the
  focus to that region's verbatim passage.
- **consolidation**: The single generated answer to the focus across every
  augmentation in a run.
- **run**: One confirmed augmentation: N augmentations and one consolidation.
- **turn event**: One unit of a turn's response — a chat message, an
  instruction, or the turn's terminal result.

## Problem

Mythrix can retrieve ranked regions for a set of interpretants, narrow them by
facet and by search text, and summarize one selected region. It cannot read the
result set a user is looking at and report what those regions have in common.

The user has already expressed what they want examined: they ran a query, chose
a source facet, chose an interpretant, and typed into the search box. Requiring
them to re-specify that scope as a second, differently-shaped query in order to
analyse it discards the selection they already made and can return a different
set of regions than the one on screen.

A reading of many regions also takes long enough that a response delivered only
on completion leaves the user with no indication of progress, and places every
per-region reading in a single block of text rather than beside the region it
describes.

## Goals

- One command that answers a free-text question across exactly the regions the
  consumer is displaying, in the order it displays them.
- Per-region results delivered as they are produced, each identifying the region
  it belongs to.
- A consolidation whose every claim points at a region that supports it,
  verified in code.
- Every step decided in code, so a fan-out of N generation calls is bounded by
  configuration rather than by a model's choices.
- No new retrieval, no new persistence.

## Non-Goals

- Retrieving regions. A run reads only what the consumer supplies.
- Interpretant terms, directives, or any query syntax in the command.
- Extending a region's passage beyond its own span.
- Cancelling a run in flight, or any defined behavior for a selection change or
  tab switch while a run is executing.
- Resuming or replaying a run whose stream was interrupted.
- Concurrent region augmentation. Regions are augmented one at a time.
- Structured (JSON) augmentations, or any cross-region aggregation computed in
  code rather than generated.
- Editing, regenerating, or dismissing a single region's augmentation.
- Retaining an augmentation across a change of query result.
- Persisting a run, its augmentations, or a pending augmentation beyond the
  browser session.

## Functional Requirements

### The command

- FR-AU-01: The system offers an `/augment` command taking one input: the
  free-text focus, being everything in the message after the command name.
- FR-AU-02: The focus is free text. It is never parsed for terms, directives, or
  delimiters, and never becomes query text.
- FR-AU-03: An `/augment` command supplying an empty focus is rejected with a
  message naming the accepted syntax, without invoking the generation model.
- FR-AU-04: An `/augment` command sent when the consumer is displaying no
  regions is rejected saying so, without invoking the generation model.

### Confirmation

- FR-AU-05: `/augment` does not run. It records the focus and the visible
  regions in session state under a backend-generated id, and replies with a plan
  restating the focus, the number of regions a run will augment, and the literal
  command that runs it. The plan turn also emits a confirmation instruction
  (FR-AU-28); the command is stated in the reply text regardless, so the flow is
  completable with no consumer that interprets instructions.
- FR-AU-06: The plan turn invokes no generation model and reads no passage.
- FR-AU-07: An `/augment-confirm` command naming the outstanding id runs the
  augmentation it names. An id that does not match the outstanding one, or a
  confirmation with no outstanding augmentation, is refused and runs nothing —
  confirmation is gated by the id, never by affirmative language. A refused
  confirmation leaves the outstanding augmentation in place.
- FR-AU-08: At most one augmentation is outstanding per session. A new
  `/augment` replaces any outstanding one, and an `/augment` that is rejected
  drops it. A confirmed augmentation is cleared. A thread reset clears it.
- FR-AU-09: A run augments the region list recorded when the augmentation was
  planned, not the list the consumer is displaying when the confirmation is
  sent.

### Dispatch

- FR-AU-10: Both commands are handled deterministically: which operations run —
  read each region's passage, augment each passage, consolidate — and in what
  order is decided in code, not by the orchestration model's tool selection. The
  orchestration model is not invoked at any point in either turn.
- FR-AU-11: The region-reading, augmentation, and consolidation operations are
  not selectable by the orchestration model. They are absent from the tool set
  bound to it, so they exist only on the deterministic augmentation path.

### Regions

- FR-AU-12: Each turn carries the consumer's visible regions as an ordered list
  of region identities, separate from the turn's context object. The list
  reflects whatever filtering and ordering the consumer applies to its display;
  the system reproduces none of that filtering or ordering itself.
- FR-AU-13: The regions augmented, and the order they are augmented and labelled
  in, are exactly the supplied list, truncated from its start. No model
  participates in selecting, dropping, or re-ordering a region.
- FR-AU-14: The number of regions a run augments is configurable and bounded by
  default. The plan and the reply each state how many regions were supplied and
  how many were augmented.
- FR-AU-15: Every attribute of an augmented region other than its identity — its
  source, its human-readable locator, and its passage — is derived by the system
  from that identity alone, against its own stores. No displayed value supplied
  by the consumer is used.
- FR-AU-16: A supplied identity that is not a well-formed region identity, or
  that names a source or ordinal range the stores do not hold, is skipped: it is
  not augmented, costs no generation invocation, and appears in no result. When
  no supplied region can be read, the turn ends saying so, without invoking the
  generation model.

### Passage

- FR-AU-17: An augmented region's passage is its full contiguous ordinal range,
  read verbatim by structural coordinate
  ([context-expansion.md](../retrieval/context-expansion.md) FR-CE-02,
  FR-CE-11). Every segment whose ordinal lies
  within the range is included, whether or not it carried a match, so the
  passage reads as one gap-free sequence.
- FR-AU-18: A passage extends no further than the region's own span. No segment
  before the range's start or after its end is included.

### Generation

- FR-AU-19: Each augmented region produces one augmentation from exactly one
  generation-model invocation, given that region's passage, its source and
  locator, and the run's focus. The invocation is instructed to use the
  reference only to know what passage it is reading, not to draw on outside
  knowledge of it, and to answer from the passage alone — saying so when the
  passage does not bear on the focus.
- FR-AU-20: After every augmentation is produced, the augmentations are
  consolidated into a single answer to the focus, naming what recurs across
  them and where it does not, through a bounded, hierarchical sequence of
  generation-model invocations rather than always exactly one: the
  augmentations are grouped into batches of at most a configured size; each
  batch is consolidated by one invocation, given that batch's augmentations
  and their region labels only, never raw passage text; if more than one
  batch's worth of results remain, those results are themselves grouped and
  consolidated again, given only prior results, never raw passage text or the
  individual augmentations directly; this repeats until exactly one result
  remains, which is the run's answer. When the number of a run's augmentations
  does not exceed the configured batch size, this collapses to exactly one
  invocation given the augmentations directly.
- FR-AU-21: A run invokes the generation model N + C times for N augmented
  regions, where C is the number of consolidation invocations FR-AU-20
  performs — deterministic from N and the configured batch size, never a
  function of model behavior, and equal to 1 whenever N does not exceed that
  size. The fan-out is bounded by FR-AU-14 and FR-AU-40, not by the per-turn
  tool-call bound, which governs the model's own tool loop and is not reached.

### Delivery

- FR-AU-22: A turn's response is a sequence of turn events, ending in exactly one
  terminal event carrying the turn's context, reply text, instructions, and
  thread-reset flag. A turn that produces no intermediate events consists of the
  terminal event alone.
- FR-AU-23: A run emits, as each region completes and before the run finishes, a
  chat message naming the region augmented and an instruction carrying that
  region's identity, label, and augmentation. Events are emitted in the order
  the regions are augmented.
- FR-AU-24: The run's terminal reply text is the consolidation and the count
  statement of FR-AU-14. It does not restate the individual augmentations.
- FR-AU-25: A failure arising after a turn's first event is delivered is reported
  within the event sequence, not as a transport-level error.

### Display

- FR-AU-26: A consumer holds each augmentation against the region it names, for
  as long as that region is displayed. Augmentations accumulate as their
  instructions arrive; a region augmented by a later run replaces its earlier
  augmentation.
- FR-AU-27: A region with an augmentation is marked as such in the result list,
  distinguishably from one without, without displaying the augmentation itself.
- FR-AU-28: Opening a region that has an augmentation displays it, attributed as
  generated analysis and visually distinct from the region's verbatim source
  text, positioned so it cannot be mistaken for part of that text.
- FR-AU-29: Augmentations are discarded when the query result they were produced
  against is replaced. They are scoped to one workspace tab and are never shared
  between tabs.

### Grounding

- FR-AU-30: Each augmented region carries a region marker `[R1]`, `[R2]`, …
  numbered by its 1-based position in the supplied list, so a region that was
  skipped leaves a gap rather than shifting the ones after it. The consolidation
  cites the regions supporting each claim by marker, and each region's marker
  accompanies its augmentation.
- FR-AU-31: A marker in a model-authored reply that names no region this run
  augmented fails the turn, as for the existing graph-fact and segment markers
  ([agent.md](agent.md) FR-AG-06, [retrieval.md](../retrieval/retrieval.md)
  FR-RT-04).
  A reply composed entirely by the system, with no model-authored text in it, is
  not subject to this validation. An augmentation carries no markers of its own:
  marker-shaped text a generation model emits into one is removed before it is
  delivered.

### Registration and history

- FR-AU-32: The plan turn emits one confirmation instruction carrying the
  augmentation's id, its focus, the number of regions, and the confirmation
  command verbatim. Both this type and the per-region instruction type of
  FR-AU-23 are declared with no binding: they trigger no request and are handled
  by the consumer itself ([agent-capabilities.md](agent-capabilities.md)
  FR-CAP-07). A rejected `/augment` emits no instruction.
- FR-AU-33: Both commands are declared in the capabilities document like every
  other command ([agent-capabilities.md](agent-capabilities.md) FR-CAP-02,
  FR-CAP-04). `/augment` is listed to users; `/augment-confirm` is not.
- FR-AU-34: Both turns are recorded in conversation history like any other turn,
  and the stored user message is the literal text the user sent, so later turns
  in the thread can refer back to the consolidation.
- FR-AU-35: A run's history entry consists of the user's literal command, a
  record of the regions augmented, and the terminal reply. The per-region
  passage reads and augmentations are not recorded in conversation history.
- FR-AU-36: The record of augmented regions carries each region's identity,
  source, human-readable locator and label, and carries no passage text.
- FR-AU-37: Every step of a run is logged at INFO: the focus; the count supplied
  and the count augmented; each region's index, label, source and locator as its
  augmentation starts, and its elapsed time as it completes; each consolidation
  invocation and the run's total invocation count; and the run's total elapsed
  time.
- FR-AU-38: Neither command changes the session's semiotic system, sign,
  tradition, or active hotspot.
- FR-AU-39: A region's marker is assigned once, when its augmentation is
  produced (FR-AU-30), and is never reassigned, renumbered, or replaced by a
  later consolidation invocation. Every invocation above the first
  consolidation level is given no marker vocabulary of its own and is
  instructed to carry forward, unchanged, whatever markers already appear in
  what it is given. The run's terminal reply carries only markers naming
  regions this run augmented (FR-AU-31), regardless of how many consolidation
  levels produced it.
- FR-AU-40: The number of augmentations or prior consolidation results one
  consolidation invocation may be given is configurable and bounded by
  default, uniformly at every level (FR-AU-20).
- FR-AU-41: As each consolidation invocation other than a run's final one
  completes, a chat message reports progress, before the run continues. No
  instruction accompanies it, since a batch's result is not attached to one
  region. The run's final consolidation invocation is not separately
  announced, since its result is the terminal reply itself.
