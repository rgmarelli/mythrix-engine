# Conversational Agent

The in-app, tool-calling chat agent served by the [Backend API](api.md) and docked in the [Web Viewer](web-viewer.md), grounding every claim in a read-only tool result over the existing [Retrieval](../retrieval/retrieval.md)/[Ranking](../retrieval/ranking.md) pipeline.

## Vocabulary

- **agent**: A tool-calling loop, driven by a local chat model, that turns a natural-language request into calls against Mythrix's existing operations and reports the results conversationally.
- **tool**: A single, typed, read-only operation the agent may invoke, wrapping an existing Mythrix service function (e.g. run a query, fetch a segment range).
- **turn**: One user message plus the agent's full response to it, including any tool calls made while producing that response.
- **session**: An ordered series of turns sharing conversation history.
- **tool trace**: The ordered record of which tools the agent called during a turn, surfaced to the user so the evidence path is visible.
- **thread**: The portion of an agent chat session's history scoped to one active hotspot. Selecting a different hotspot starts a new thread; a thread never merges with or extends a prior one.
- **slug**: An entity's stable identifier, unique within its type, and the value the retrieval operations accept (`the-magician`, `rider-waite`, `tarot`).
- **display name**: An entity's human-readable name, as the viewer shows it (`The Magician`, `Rider-Waite-Smith`). Neither unique by construction nor derivable from the slug.
- **identity key**: A key in a tool result whose value identifies an entity, and from which the context object may be backfilled.
- **display key**: A key in a tool result whose value is a display name, carried for composing user-facing text and never used as an identifier.
- **entity-valued field**: A context-object field naming an entity — semiotic system, sign, or tradition.

## Functional requirements

### Agent loop and tools

- FR-AG-01: The system provides an in-app conversational agent, served by the backend API and surfaced as a chat panel in the web viewer, that runs an interactive, multi-turn conversational session and answers successive user requests until the user ends the session.
- FR-AG-02: The agent answers each request by invoking one or more read-only tools and composing their results into a natural-language reply. It maintains conversation history across turns within a session.
- FR-AG-03: The agent has access to exactly these tools, each wrapping an existing service function and returning structured data (not prose):
  - **list semiotic systems** — the available semiotic systems.
  - **list traditions** — the available traditions, optionally scoped to one semiotic system.
  - **list signs** — the available signs, optionally scoped to one semiotic system.
  - **get sign** — retrieve one named sign's facts: its canonical name, semiotic system, intrinsic properties, and, for a given tradition, its manifestation's interpretants, denotation, correspondences, and citations. This is a graph-facts lookup, not a corpus retrieval — it runs no similarity search.
  - **query sign** — run a region (hotspot) query for a given sign and tradition, returning ranked regions with their matched interpretants, verbatim segment text, and citations (the same operation as `GET /api/query`).
  - **fetch segments** — retrieve a contiguous ordinal range of one source's segments verbatim, by structural coordinate, running no similarity search (the same operation as `GET /api/segments`, [context-expansion.md](../retrieval/context-expansion.md) FR-CE-11).
  - **summarize passage** — produce a single-turn summary of supplied passage text scoped to supplied interpretants, using the generation model.
- FR-AG-04: The registered tool set contains no operation that writes to, mutates, or reloads either store. Read-only is a structural property of the tool set, not a runtime check.
- FR-AG-05: When a request to list traditions or signs, or to get or query a sign, does not determine which semiotic system to use and the choice is ambiguous (more than one semiotic system exists and the request names none), the agent asks the user which semiotic system to use before listing or retrieving, rather than guessing or silently listing across all systems. Once a semiotic system is established in the conversation, the agent may reuse it for subsequent turns without re-asking.
- FR-AG-06: The agent must not state any sign, interpretant, tradition, source, or passage as fact unless it appears in a tool result from the current session, and it must carry through the citation/locator the tool returned. It must not fabricate or infer signs or interpretations absent from tool results.
- FR-AG-07: When the get-sign tool returns `needs_tradition` (no interpretive content, only the sign's available traditions), the system presents the tradition choices to the user deterministically, without generation-model involvement. This guarantees FR-AG-06 cannot be violated in this specific case regardless of model behavior, since a tradition list is the entirety of what the tool returned and needs no model composition. The choices, and the sign the question names, are presented by display name; the tool result carries each candidate's slug alongside its display name, and the user's answer resolves under FR-AG-41.
- FR-AG-08: The agent's generation model is a local Ollama model. When no generation model is configured or the model cannot be reached, the command reports a distinct, actionable error rather than proceeding.
- FR-AG-09: The retrieval a tool triggers invokes no generation model and is unchanged from the existing query path ([retrieval.md](../retrieval/retrieval.md) FR-RT-10): the generation model is used only for the agent's own conversation/tool-selection and for the explicit summarize tool.
- FR-AG-10: Each turn surfaces a tool trace — which tools the agent called, in order — so the user can see the evidence path behind the answer.
- FR-AG-11: A tool that fails (e.g. an unknown sign or tradition, an unreachable model for summarization) returns a distinct error to the agent that the agent relays to the user, without terminating the session; the user can continue with further turns.
- FR-AG-12: The agent loop is bounded: a single turn cannot invoke tools indefinitely. On reaching the bound, the turn ends with a clear message rather than looping.
- FR-AG-13: The agent is additive and self-contained. It adds no command to the `mythrix` CLI; the existing `load-signs` and `load-documents` commands and all other `/api/*` routes are unchanged in behavior and output.

### Chat panel

Refines FR-AG-01–FR-AG-13 for the panel's web-UI-specific behavior; the underlying agent loop, tool set, and orchestration boundary ([ADR-006](../architecture-decisions/adr-006-conversational-agent-orchestration-boundary.md)) are unchanged.

- FR-AG-14: The chat panel is docked, floating, and has exactly two states — open and collapsed. Collapsing preserves the active thread; re-opening restores it unchanged. It never reflows the hotspot list, facets, or control panel.
- FR-AG-15: The panel is grounded in the currently active hotspot; a context strip displays that hotspot's structural reference and its matched interpretants at all times.
- FR-AG-16: Selecting a different hotspot starts a new thread (see Vocabulary): the prior thread's messages are replaced by a reset divider naming the new hotspot; threads are never merged or extended across hotspots. Changing a session-scoped context field via chat (a new sign or tradition) triggers the same reset. The backend, not the browser, detects the reset condition — by comparing the incoming turn's selection against the context it stored from the previous turn — and clears its message history before invoking the agent loop.
- FR-AG-17: Each user turn is sent with a context object: session-scoped fields (semiotic system, sign, tradition, facet/min-score selection) that persist across hotspot changes until explicitly changed, and thread-scoped fields (the active hotspot's structural reference and human-readable locator, FR-AG-21) that reset with the thread. The browser always sends its current selection as-is, never pre-clearing or diffing it; the backend returns an updated or confirmed-unchanged context alongside its reply. Fields fill in independently from either side — the UI's selection sets any of them directly, and the agent sets one when it resolves an entity from a chat message alone. The context object never carries passage or segment text; any verbatim text the agent needs is retrieved through its own tool calls. Its entity-valued fields carry slugs (FR-AG-37), so both writers set the same value for the same entity.
- FR-AG-18: Whenever an attempted tool call needs a field that is still unset, the agent distinguishes ambiguous (more than one value is plausible — the tool call names its own candidates, and the clarifying question is composed directly from that result, with no generation-model call) from not yet determined (nothing has been selected or searched yet — the agent says so plainly, with no candidates to offer). This generalizes FR-AG-05/FR-AG-07's semiotic-system-specific and tradition-specific bypasses to any field capable of the same ambiguity; neither case ends with the agent guessing a value.
- FR-AG-20: Thread and session history and context are retained only for the life of the browser session; none of it is persisted across a backend process restart.
- FR-AG-21: The context object's thread-scoped fields include the active hotspot's human-readable locator (e.g. "Ecclesiasticus 43:1-4") alongside its structural reference, giving the agent a ready citation to quote without a separate tool call purely to resolve it.
- FR-AG-22: The composer recognizes a `/clear` command: it is never sent to the agent or shown as a user message, and instead wipes the active thread and starts a new agent session, so the next turn carries no prior history.
- FR-AG-23: Each assistant-authored message's text is rendered with markdown formatting: at minimum, paragraphs, emphasis (bold/italic), ordered and unordered lists, inline code spans, fenced code blocks, and links are visually formatted rather than shown as literal syntax.
- FR-AG-24: Markdown rendering never executes script content or renders raw HTML tags present in the model's reply text; such content is escaped or stripped, not rendered as markup.
- FR-AG-25: User-authored messages, error messages, and reset dividers are unaffected by markdown rendering and continue to render as plain text.
- FR-AG-26: The backend API's agent chat response returns the model's reply text without stripping markdown decoration (bold, headings, bullets); citation-marker stripping and validation are unaffected and continue to apply.
- FR-AG-33: The `/summarize` command is handled deterministically: which tools are called (fetch the active hotspot's passage, then summarize it) and in what order is decided in code, not by the generation model's own tool selection. The generation model is invoked exactly once per `/summarize` turn, for the summarization itself.
- FR-AG-34: When `/summarize` is sent with no active hotspot, the agent replies that a passage must be selected first, deterministically, without invoking the generation model or any tool.
- FR-AG-35: Trailing text after `/summarize` scopes the summary to that focus; absent trailing text, the currently selected interpretant (if any) scopes it instead; absent both, the summary is unscoped.
- FR-AG-36: The `/summarize` command's turn is recorded in conversation history like any other turn — the stored user message is the literal text the user sent, not a rewritten or fabricated instruction — so later turns in the thread can refer back to the summary.

### Entity identity ([ADR-014](../architecture-decisions/adr-014-slug-as-agent-entity-identity.md))

- FR-AG-37: Every entity-valued field of the context object carries the entity's slug. It never carries a display name, whether the field was set from the browser's selection or backfilled from a tool result.
- FR-AG-38: A tool result that carries an entity's identity carries it as that entity's slug, under an identity key distinct from any display key naming the same entity. One key never carries a slug in one result and a display name in another, and no single key carries both forms.
- FR-AG-39: A tool result carries the display name of every entity it identifies, alongside that entity's slug, so a reply composed from the result alone can name entities as the viewer shows them.
- FR-AG-40: A tool result's identity keys and display keys are distinguishable by key alone, without knowledge of the entity type or of the values themselves, under one convention across every tool: where a result names an entity directly, the identity key is the entity type (`sign`, `tradition`, `semiotic_system`) and its display key is that name suffixed `_name`; where a result carries an object representing one entity, the object's identity key is `slug` and its display key is `name`. An identity key naming an entity type is spelled identically to the context field it backfills, so the mapping from result to context field introduces no per-tool translation.
- FR-AG-41: A tool argument naming a sign or a tradition accepts either that entity's slug or its display name, matched case-insensitively and ignoring surrounding whitespace. Neither of the two is resolvable by slug alone. A semiotic system has a single form, which is its slug; an argument naming one accepts that form, matched by the same rule.
- FR-AG-42: A tool resolves every entity-valued argument to a slug before invoking any retrieval operation. An unresolved argument value never reaches a store operation.
- FR-AG-43: An argument value matching no known entity of its type ends the tool call with the distinct, relayed error the agent already returns for an unknown entity (FR-AG-11), naming the value that did not resolve.
- FR-AG-44: An entity-valued context field is backfilled from the identity keys of a tool result, never from the arguments the generation model supplied for the call. A tool whose result would not otherwise identify the entities it operated on carries them, resolved, for this purpose. The context summary folded into the generation model's prompt names each entity by the value the tool arguments accept.

### Operational logging

- FR-AG-27: Every turn's input, resolved context, each model invocation's full input and response, each tool call and result, and the final outcome are logged to the process's standard log output at INFO level, for local debugging. This is operational visibility only — it adds no visible behavior for the user and never changes the API response.

### Prompt requirements

- FR-AG-28: The agent's system prompt must be kept clean, short, and simple: as few rules, as little wording per rule, and as little total length as satisfies the remaining requirements in this section. Every rule in the prompt must earn its place by changing which tool the model selects, when it selects one, or how it composes a reply from tool results; a rule that does neither is removed, not reworded ([ADR-009](../architecture-decisions/adr-009-minimal-agent-system-prompt.md)).
- FR-AG-29: The system prompt does not restate domain knowledge that a tool result already carries (e.g. the semiotic-system/sign/tradition/interpretant model), and does not duplicate a formatting or state-persistence rule that is enforced elsewhere in the system rather than by the model's own compliance.
- FR-AG-30: The system prompt places no formatting restriction on the model's reply text (e.g. no markdown ban); reply formatting is governed entirely by rendering (FR-AG-23–FR-AG-26).
- FR-AG-31: The system prompt asks the model to persist no state of its own across turns within its reply text. Any state that must carry across turns is held in the context object (FR-AG-17), populated deterministically from tool results and UI selections, never from model-authored text.
- FR-AG-32: Adding a new rule to the system prompt is justified only when the requirement cannot be enforced in code or in the UI instead; where enforcement in code is possible, that takes precedence over relying on the model to follow a prompt instruction.

## Non-goals

- Any mutating/administrative tool in the conversational agent's tool set (ingesting signs/documents, reloading stores), a cloud/hosted generation model, or persisting agent sessions across process restarts; the agent is an orchestration and presentation layer that introduces no new retrieval, ranking, or convergence behavior and does not parse free text into retrieval query text — except for the structured `/query` command path [agnostic-query.md](agnostic-query.md) defines under [ADR-010](../architecture-decisions/adr-010-agnostic-adhoc-interpretant-query.md), where a deterministic backend parser, never the model, turns an explicit command's operands into query text; that path remains the only exception to this rule.
- The agent returning an instruction that mutates application state on its own — changing a facet or min-score, navigating to a different hotspot, or opening/closing a tab from chat. The agent only ever answers conversationally and updates its own context object (FR-AG-17); this is deferred, not precluded by the context-object design.
