# ADR-014 — The slug is the only entity identity across the agent boundary; display names are carried separately

- **Status**: Accepted
- **Date**: 2026-07-28
- **Realized by**: [agent.md](../interfaces/agent.md) FR-AG-37–FR-AG-44, amending FR-AG-07 and FR-AG-17

## Context

The agent's context object ([agent.md](../interfaces/agent.md) FR-AG-17) holds
the session's semiotic system, sign, and tradition. It has two independent
writers by design: the browser sets a field from the user's picker selection,
and the backend backfills a field when the agent resolves an entity from a chat
message alone (FR-AG-31, [ADR-006](adr-006-conversational-agent-orchestration-boundary.md) —
deterministically, from tool results, never from model-authored prose).

Those two writers were putting different things in the same field. The viewer's
pickers are populated from `/api/signs` and `/api/traditions` and send slugs.
The backfill path took its values from the get-sign tool's result, which
rendered a sign as its canonical name and a tradition as its display name. For
signs the two forms differ only in case and punctuation; for traditions they are
unrelated strings — `rider-waite` against `Rider-Waite-Smith`,
`sepher-yetzirah-gra` against `Sepher Yetzirah Gra`.

Two things depend on that field being one thing:

- **The graph store accepts slugs only.** `get_manifestation` looks a tradition
  up by slug and raises otherwise. A tradition display name that the model read
  out of one tool result and passed into the next therefore failed the call. A
  sign happened to survive the same path because the sign tools already resolved
  their argument against slug *or* canonical name before touching the store — an
  asymmetry with no basis the model could observe, and one that any new caller
  bypassing that resolver would inherit.
- **The field is compared as an identifier.** Thread-reset detection (FR-AG-16)
  decides whether the conversation is still about the same subject by comparing
  the incoming selection against the stored context, string against string. Two
  spellings of one tradition read as two traditions.

The field is, in other words, an identity key that was being written with
display text. The question this ADR settles is which of the two forms wins, and
what happens to the other.

## Decision

**The slug is the sole identity representation for every entity the agent
names.** Concretely:

- Every entity-valued field of the context object carries a slug, from either
  writer, always (FR-AG-37).
- A tool result carries an entity's slug under an identity key, and its display
  name under a separate display key, distinguishable by key alone (FR-AG-38,
  FR-AG-40). Display names are not removed — the model still needs them to write
  prose, and a deterministically composed reply (FR-AG-07) still needs them to
  address the user in the words the viewer shows.
- Context backfill reads identity keys only, never the arguments the model
  supplied for the call (FR-AG-44).
- **Every** entity-valued tool argument accepts either form and resolves it to a
  slug before any store operation (FR-AG-41, FR-AG-42). Tolerance becomes a
  property of the tool boundary rather than an accident of which tool happened
  to have a resolver, and it is uniform across entity types.

The two halves are deliberate and not redundant, and they answer different
questions. Rendering slugs as identity is what makes the context *correct*.
Resolving both forms at the argument boundary is what lets a user's own words
reach a tool at all: "tell me about The Magician in the Tarot de Marseille"
names two entities by display name, before any tool has run and with no slug
anywhere in the turn for the model to have read. That is the boundary where
natural language becomes an identifier, and it is why `_resolve_sign` already
exists for signs. Traditions have the same entry path and no resolver; this
decision removes that asymmetry rather than introducing something new.

Tolerance also happens to absorb a display name the model echoes back out of a
tool result, but that is a secondary benefit and explicitly not the
justification — a resolver adopted *for that reason* would be a patch over
tool results that should not be putting display names in identity positions in
the first place, which is precisely what the first half of this decision stops
them doing.

## Consequences

- One entity has one representation everywhere it is used as an identifier: the
  browser's selection and the agent's own resolution produce the same string, so
  the context object can be compared, logged, and reasoned about as identity.
- Spurious thread resets caused purely by the two writers spelling one entity
  differently disappear. This is a partial remedy and was accepted as one: reset
  detection compares an absent incoming field as a value, while selection
  merging treats the same absence as "unset, preserve", so a session where the
  agent resolved the sign from chat and the browser's picker was never touched
  still resets on every turn. That asymmetry is independent of how entities are
  spelled and is not addressed here; how reset conditions are compared
  (FR-AG-16) remains as specified and is being revisited separately.
- A tradition display name reaching a tool argument now resolves instead of
  erroring, so the model can no longer fail a turn by echoing a name the backend
  itself gave it.
- The generation model sees slugs where identity is meant and names where prose
  is meant, in the same result. This is more keys per result, and the tool
  descriptions carry the distinction; the alternative — hiding names from the
  model — costs the ability to write natural replies.
- Resolution is by exact match on slug or display name, case-insensitively. Two
  entities of one type sharing a display name would resolve to whichever is
  declared first; the current data has no such collision, and disambiguation is
  out of scope.
- Slugs become load-bearing in a way they were only implicitly before: changing
  an entity's slug in the data is a breaking change to any live session's
  context. It already was for the viewer's pickers.

## Alternatives considered

- **Adjust the UI to send display names instead.** Rejected. The pickers receive
  slugs from the API and would have to invent display text for values they hold
  as identifiers; display names are not unique by construction, are expected to
  change as editorial text, and are not what the store accepts — the mismatch
  would simply move to the retrieval boundary, where it fails harder.
- **Normalize at comparison time — slugify or casefold both sides before
  comparing.** Rejected. It patches the reset symptom and leaves the field
  holding text that is still not an identifier, so anything else consuming the
  field (a tool argument, a log line, a future instruction payload) keeps the
  original bug. Tradition names would not survive slugification back to their
  slugs in any case.
- **Add the resolver only, and leave tool results rendering display names.**
  Rejected as a half-fix: it makes the tools tolerant but leaves the context
  object storing display text, so identity comparison stays broken. It is the
  weaker half of the decision above, not an alternative to it.
- **Make context fields composite objects carrying both slug and name.**
  Rejected. It changes the wire shape the browser sends and receives for a
  benefit the separate display keys in tool results already deliver, and it
  invites the same ambiguity back in at the next consumer that has to choose a
  member.
- **Have the store accept either form.** Rejected — it pushes display-name
  tolerance down into deterministic retrieval, which is exactly the layer
  ADR-006 keeps free of the model's phrasing. Tolerance belongs at the tool
  boundary, where the model's input arrives.
