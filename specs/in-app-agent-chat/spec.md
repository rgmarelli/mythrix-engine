# In-App Agent Chat — spec

## Purpose

A conversational chat panel, docked into the web viewer, grounded in the
currently active hotspot. It replaces the one-shot "Generate AI summary" button
with a conversational surface: the user can ask about the hotspot in natural
language, and the agent answers using Mythrix's existing retrieval tools —
never inventing symbols, interpretants, or passages.

## Scope: v0 vs v1

- **v0** (this spec's implementation target): conversational chat grounded in
  the active hotspot. Summarization is folded into the agent as an ordinary
  chat capability; the standalone "Generate AI summary" button is removed. The
  agent answers questions and cites grounding passages/interpretants; it does
  not change any filter or navigate the UI.
- **v1** (explicitly deferred, not precluded by v0's design): the agent can
  return an instruction for the UI to execute — e.g. "show me hotspots with the
  Monkey interpretant" changes the interpretant facet, or "next hotspot" and
  the agent asks the client to navigate. v1 requires new tools beyond v0's set
  (see Functional requirements (v1) below) and is out of scope for this
  implementation pass.

Anywhere this spec or the reference mockup shows the agent changing a filter
or navigating the hotspot list, that is a v1 capability shown for continuity of
design, not something v0 implements.

## Relationship to existing architecture

- Master `specs/spec.md` already defines a conversational agent layer
  (`mythrix-agent`, FR58-70) — a tool-calling loop over a fixed, read-only tool
  set, running on a local generation model only, grounding every claim in a
  tool result (FR63) with citation validation available for it (FR12).
  **ADR 0006** settled the orchestration boundary for that layer: *a generation
  model may orchestrate but never retrieve or interpret directly*, and it runs
  on a **local model only** — a hosted/cloud model was explicitly considered
  and rejected. ADR 0006 also names this exact feature: *"a web endpoint and
  chat panel are deferred, but the same boundary governs them when they ship."*
  This spec is that web endpoint and chat panel — it inherits ADR 0006's
  boundary unchanged, and introduces no exception to it.
- This spec is deliberately silent on which generation model or vendor backs
  the agent — that is an implementation choice for `plan.md`, not a spec-level
  concern. It commits only to what ADR 0006 already requires: local, not
  hosted/cloud.
- This spec stays standalone (its own `spec.md`/`plan.md`/`tasks.md`) through
  implementation and is folded into master `specs/spec.md` on completion —
  same pattern as `agent-operator` and `hotspot-context-expansion` before it.
  Folding in will need to update master `spec.md`'s Non-goal *"A conversational
  or chat-style web UI"* (currently still true) once v0 ships; that update is
  not made now.

## Vocabulary

Reuses master `spec.md`'s existing terms without redefinition: `agent`, `tool`,
`turn`, `session`, `tool trace`, `hotspot`/`region`, `matched segment`. One new
term:

- **thread**: the portion of a session's history scoped to one active hotspot.
  Selecting a different hotspot starts a new thread; it never merges with or
  extends a prior thread.

## Placement & states

- **Docked, floating** — fixed bottom-right, 392×540px, overlays the existing
  layout. Does not reflow the hotspot list or filter bar.
- **Collapse** — header has a collapse control. Collapsing preserves the
  thread; re-opening restores it unchanged.
- No separate "launcher" screen — open/collapsed are the only two states.

## Architecture (where things run)

- The agent lives **entirely in the Mythrix backend**, in the same process
  that already serves search/query results. The browser only ever sends the
  user's message and its **current UI selection**, as-is, each turn — it never
  calls a generation model itself, never executes a query itself, and is never
  responsible for detecting a thread boundary or clearing any part of context.
  The backend holds the previous turn's context, compares it against what just
  arrived, and — if a thread-reset condition is met (Thread behavior, below) —
  clears `agent_notes` itself **before** invoking the agent loop for that turn.
- Every turn's response has three parts: the **updated context** (Context
  object, below); the **text to show** — the reply plus any structured cards
  it grounds (verse citation, interpretant chips), all tool-grounded per FR10;
  and **instructions to execute** — zero or more UI actions the browser should
  apply (e.g. select a different sign, change a facet, navigate to another
  hotspot). v0 always returns zero instructions; v1 (FR16) is exactly the case
  where this list becomes non-empty. The shape is the same across v0/v1 — v0
  just never populates the third part.
- Backend turn loop (conceptually — the concrete mechanism is a plan.md
  decision): the backend passes the conversation to its configured local
  generation model; when the model needs data, it calls one of the agent's
  existing registered tools; the backend executes that tool through Mythrix's
  **existing** service functions — the same functions `query_regions` /
  `fetch_source_segments` / graph-store lookups that the Query button, hotspot
  navigation, and the existing `mythrix-agent` CLI already use. No second code
  path to the same data is introduced.
- v0 introduces **no new tools**. It reuses the seven read-only tools already
  defined for `mythrix-agent` (list semiotic systems, list traditions, list
  symbols, get symbol, query symbol, fetch segments, summarize passage) —
  including `summarize passage`, which is how "make a summary" now reaches the
  same generation call the removed button used to trigger directly.
- Every structured card shown in the thread (verse citation, interpretant
  chips) is populated by the backend **directly from the tool result(s) that
  grounded that turn** — never parsed or inferred from the model's free-text
  reply. The model's prose is conversational framing around already-validated
  structured data; it is never the source of truth for a citation or a chip.
  (v1's interface receipt follows the same rule: built from the actual diff
  applied, never from what the model said it would do.)

## Context object

The context object is the agent's structured working memory — distinct from
the raw per-turn message history the generation model already sees. Unlike
`mythrix-agent`'s own REPL, where that transcript is unbounded for the life of
the process, here it resets along with the rest of the thread whenever the
thread resets (see Thread behavior) — a thread never merges with or extends a
prior thread's transcript either, matching Vocabulary's definition of thread.
Context holds the compact facts the agent needs across turns without
re-deriving them; it is also what the context strip renders. It has two
scopes:

- **Session-scoped** (persist across hotspot changes, until explicitly
  changed): `semiotic_system`, `sign`, `tradition`, and the currently applied
  facet selection / min-score override, if any — these describe the current
  *query*, not any one hotspot.
- **Thread-scoped** (reset whenever the thread resets — see Thread behavior):
  the active hotspot's **structural reference** — a source id plus ordinal
  range, exactly what a region's existing `region_id` already encodes
  (`f"{source_id}::{start_ordinal}-{end_ordinal}"`, `core/retrieval/pipeline.py`,
  so no new identifier scheme is needed) — and `agent_notes`: free-form notes
  the agent writes for its own later reference within the thread (e.g.
  "already summarized this passage"). `agent_notes` carries no numeric cap; it
  is bounded structurally by the thread's own lifetime — it is cleared, not
  carried over, when the thread resets (see Thread behavior).

The context **never carries passage or segment text**. If the agent needs
verbatim text — to answer a question or to summarize — it retrieves it itself
via `fetch_segments`/`query_symbol`, exactly as `mythrix-agent`'s tools already
do. The browser only ever hands over *where* to look, never *what's there*.

Fields fill in independently, not all at once — either side can set one:
the UI's picker/hotspot selection sets any of them directly; the agent sets
one when it resolves an entity from a chat message alone (e.g. "tell me about
the Sun" sets `sign` with `semiotic_system`/`tradition` left unset).

**Clarification, not guessing.** Two distinct situations, neither resolved by
the agent inventing a value:

- **Ambiguous** — a field is unset and more than one value is plausible (a
  sign name exists in more than one semiotic system, or a sign has
  manifestations in more than one tradition — master FR62/FR64's existing
  case, widened here to any field capable of the same ambiguity). The tool
  call attempted names its own candidates in its result, exactly as
  `get_symbol`'s existing `needs_tradition` payload already does; the
  clarifying question is composed **directly from that result, with no
  generation-model call** — the same deterministic bypass master FR64
  established for tradition specifically because prompting alone isn't
  reliable enough to guarantee no fabrication (ADR 0006's Consequences), now
  generalized to every field, not only tradition.
- **Not yet determined** — a field is unset because nothing has been
  selected or searched yet (no hotspot chosen yet, so no `region`), not
  because candidates are competing. There is nothing to disambiguate; if the
  attempted tool call actually needs that field, the agent says so plainly
  (e.g. "pick a hotspot first") instead of offering a choice among options
  that don't exist.

Once the user's answer resolves a field, it is written into context at its
proper scope (FR4) and the original request is retried on the next turn using
the conversation history already in play — no separate retry mechanism is
needed.

The backend returns the updated (or confirmed-unchanged) context alongside its
reply each turn. In v0, an agent-resolved field updates only the chat panel's
own context strip — never the top filter bar, and it never fires a hotspot
query on its own. Actually driving the filter bar or the query remains v1's
"instruction the UI executes" (FR16).

## Thread behavior

- The thread is **scoped to the active hotspot** (see Vocabulary). Navigating
  to a new hotspot (e.g. "next hotspot →") resets the thread and shows a thin
  `— now reading {reference} —` divider; it does not silently clear.
- Changing a **session-scoped** context field via chat (a new `sign` or
  `tradition`) resets the thread the same way an explicit hotspot change does
  — an old hotspot reference no longer belongs to the newly-selected sign/
  tradition.
- A thread reset clears `agent_notes` and the raw message history the
  generation model sees, starting the new thread's transcript empty;
  session-scoped fields are unaffected.
- **The backend detects the reset, not the browser.** The browser always
  sends its current UI selection as-is; it never pre-clears or diffs context
  before sending. The backend compares the incoming selection against the
  context it stored from the previous turn and performs the reset itself,
  before the agent loop runs — the same "single source of truth" reasoning as
  FR10's structured cards: state that matters is owned and computed
  server-side, never trusted from what the client last rendered.
- The context strip (below the header, gold background) always shows the
  current hotspot reference and its interpretants — the anchor for whatever
  the user asks next.

## Message types in the thread

| Type | When | Visual | Scope |
|---|---|---|---|
| User bubble | user input | dark, right-aligned | v0 |
| AI bubble | conversational reply | violet-wash, left-aligned, agent mark | v0 |
| Verse citation | agent quotes the grounding passage | serif card, gold left border | v0 |
| Interpretant chips | agent references scored interpretants | small mono pills under an AI bubble | v0 |
| Reset divider | hotspot changed | thin rule + mono label | v0 |
| Interface receipt | agent changed a filter | green card, `field → value` chips, only after the real change is applied | **v1** |

## Composer

Single input + send button. No shortcut pills — all actions go through
natural language.

## Logo / agent mark

"Convergence" mark: four short strokes pointing inward to a center dot,
representing N interpretants converging on one hotspot (matches existing
product copy: "interpretants converging in each hotspot"). Used at 22–28px
in the header and per-message avatar. Pulses (opacity/scale on the center
dot) while the agent is waiting on a backend response — no spin.

## Design tokens

Scoped to the `.agent-dock` subtree only — the rest of the app keeps its own
existing token set (`web/src/index.css`, e.g. `--accent: #7c3aed`). The two are
not reconciled into one palette in v0.

```
--paper       #FAFAF8   page background
--panel       #FFFFFF   card/panel surface
--ink         #1B1523   primary text
--ink-soft    #4A4453   secondary text
--muted       #8A8394   tertiary / labels
--line        #E7E3DC   borders
--line-soft   #EFECE6   inner dividers
--violet      #6D28D9   agent / primary accent
--violet-deep #4C1D95   hover states
--violet-wash #F2EEFB   AI bubble fill
--gold        #C79A3E   citation / context accent
--gold-wash   #FAF3E4   context strip fill
```
Type: **Fraunces** (headings, citations), **Inter** (UI, body), **IBM Plex
Mono** (scores, references, receipts — anything that reads as data).

## Functional requirements (v0)

- FR1: A single chat panel is docked bottom-right of the web viewer, in the
  states described under Placement & states; it never reflows the existing
  filter bar or hotspot list.
- FR2: The panel is grounded in the currently active hotspot; the context
  strip displays that hotspot's structural reference and its matched
  interpretants at all times.
- FR3: Selecting a different hotspot starts a new thread (FR/Vocabulary
  "thread"): the prior thread's messages are replaced by a reset divider
  naming the new hotspot; threads are never merged or extended across
  hotspots. Changing a session-scoped context field via chat (a new `sign` or
  `tradition`) triggers the same reset. A thread reset clears `agent_notes`
  and the raw message history the generation model sees; it never affects
  session-scoped context fields. The **backend** detects the reset condition,
  by comparing the incoming turn's UI selection against the context it stored
  from the previous turn, and clears `agent_notes` and the message history
  before invoking the agent loop — the browser never pre-clears or diffs
  context itself.
- FR4: Each user turn is sent with the context object — session-scoped
  (`semiotic_system`, `sign`, `tradition`, facet/min-score selection) and
  thread-scoped (active hotspot's structural reference, `agent_notes`)
  fields, as defined under Context object; the browser always sends its
  current UI selection as-is; the backend returns an updated or
  confirmed-unchanged context alongside its reply.
- FR5: Context fields fill in independently, from either the UI or the
  agent.
- FR6: Whenever an attempted tool call needs a field that is still unset,
  the agent distinguishes **ambiguous** (more than one value is plausible —
  the tool call names its own candidates, and the clarifying question is
  composed directly from that result, with no generation-model call, the
  general form of master FR62/FR64) from **not yet determined** (nothing has
  been selected or searched yet — the agent says so plainly, with no set of
  candidates to offer). Neither case ends with the agent guessing a value.
  See Context object's "Clarification, not guessing."
- FR7: The browser never sends passage or segment text as part of a chat
  turn; any verbatim text the agent needs is retrieved by the backend's own
  tool calls, never inlined by the client.
- FR8: The agent answers exclusively through its existing registered
  read-only tools; it never calls retrieval, ranking, or store-access
  functions directly, consistent with ADR 0006's orchestration boundary.
- FR9: v0 introduces no new tools. Summarization becomes reachable through
  ordinary chat requests (e.g. "summarize this") via the existing
  `summarize passage` tool; the standalone "Generate AI summary" button and
  its handler are removed from the hotspot detail panel.
- FR10: Every structured card in the thread (verse citation, interpretant
  chips) is populated by the backend directly from the tool result(s) that
  grounded the turn — never parsed or inferred from the model's free-text
  reply.
- FR11: Outgoing agent text (conversational replies and summaries) is
  validated against the tool results that grounded it before being shown,
  using the existing citation-validation machinery (`core/synthesis/
  citations.py`) — this is already required by master FR12/FR63 for "the
  agent layer" and has not yet been wired into any agent surface; this spec
  requires it be wired in for chat.
- FR12: A tool failure (unreachable model, unknown sign/tradition, etc.) is
  shown as a distinct message within the thread without ending the session;
  the user can continue the conversation (mirrors master FR68).
- FR13: A single turn cannot invoke tools indefinitely; on reaching the
  bound, the turn ends with a clear in-thread message rather than looping
  (mirrors master FR69).
- FR14: Thread/session history and context are retained only for the life of
  the browser session; none of it is persisted across a backend process
  restart (mirrors the existing agent's non-goal on cross-restart
  persistence).
- FR15: The agent runs on a local generation model only; no hosted/cloud
  model is introduced (ADR 0006).

## Functional requirements (v1, deferred)

- FR16: The agent may additionally return a UI instruction (e.g. change a
  facet, change min score, navigate to another hotspot); the browser applies
  it through its own existing state-setting code, never a second path to the
  same behavior. The resulting "interface updated" receipt is built from the
  actual diff the backend applied, never from what the model said it would
  do. This requires new tools beyond v0's set (e.g. one to change facets/
  min-score, one to navigate hotspots) and is not implemented in v0; v0's
  context-object and tool-boundary design (FR4, FR8) must not preclude
  adding it later.

## Non-goals

- New tools beyond the seven that already exist for `mythrix-agent` — no
  facet-setting, min-score-setting, or hotspot-navigation tool ships in v0
  (deferred to v1, FR16).
- A hosted/cloud generation model of any kind (ADR 0006 stands unmodified).
- Persistence of chat/thread history across a backend process restart.
- Merging or extending a thread across more than one hotspot.
- Any mutation of the graph or vector store from chat — the agent's tools
  remain read-only, consistent with ADR 0006 and master FR61.
- Inline `[S1]`/`[G1]`-style citation-marker syntax exposed in the model's
  visible prose — grounding is enforced structurally (FR10), not by asking
  the user to read markers embedded in sentences.
- Reconciling the panel's design tokens with the rest of the app's existing
  token set.

## Reference

Full working markup: `mythrix_agent_panel.html` (this handoff). Note: the
mockup's "interface updated" receipt example (Interpretant → Monkey, Min score
→ 0.60) illustrates a **v1** capability — see Scope above.
