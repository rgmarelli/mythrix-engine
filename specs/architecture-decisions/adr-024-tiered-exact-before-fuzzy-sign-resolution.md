# ADR-024 — Sign resolution is tiered (exact slug, then exact name, then fuzzy), optionally scoped to one semiotic system

- **Status**: Accepted
- **Date**: 2026-08-04
- **Realized by**: [agent.md](../interfaces/agent.md) FR-AG-41, narrowing [ADR-014](adr-014-slug-as-agent-entity-identity.md)

## Context

[ADR-014](adr-014-slug-as-agent-entity-identity.md) specified that a tool
argument naming a sign resolves by exact match on slug or display name,
case-insensitively, and treated a same-name collision as out of scope.

It did not fully document the resolver's actual behavior. `_resolve_sign`
(the resolver `get_sign`/`query_sign` both use) also contained a substring
fallback — needed because a request names a sign in shortened or elaborated
form ("Magician" for "The Magician") before any tool has surfaced its slug —
and treated an ambiguous match as unresolved rather than guessing.

Because the fuzzy fallback was evaluated across all semiotic systems, an
exact identifier could become ambiguous through an unrelated substring
match: `hebrew_alef_bet`'s letter slug `he` is contained in tarot's slug
`the-sun`, so `get_sign(sign="the-sun", ...)` — the exact, unique slug a
prior `list_signs` result had already surfaced — failed as "unknown sign."

## Decision

`_resolve_sign` evaluates three tiers in strict priority order, each
authoritative the moment it produces any candidates:

1. Exact slug match.
2. Exact display-name match.
3. Substring containment in either direction (the pre-existing fuzzy
   fallback, unchanged in what it matches).

A tier with exactly one match resolves immediately, without evaluating any
weaker tier. A tier with more than one match ends resolution as unresolved —
it does not fall through to a looser tier, and it does not guess.

`get_sign` and `query_sign` additionally accept an optional
`semiotic_system` argument, matched by slug (mirroring `list_signs` and
`list_traditions`). When given, every tier is evaluated only against that
system's signs, so a slug or name from an unrelated system is never a
candidate at any tier.

This makes explicit two guarantees ADR-014's text did not state, and that
the prior flat implementation did not hold: an exact match always wins over
a fuzzy one, and a caller that already knows which semiotic system it is
operating in can eliminate cross-system name collisions entirely rather than
merely reduce their odds.

## Consequences

- Narrows [ADR-014](adr-014-slug-as-agent-entity-identity.md)'s "Resolution
  is by exact match on slug or display name... resolve to whichever is
  declared first" consequence: that line described neither the fuzzy tier
  that already existed nor the fail-closed ambiguity behavior
  `_resolve_sign` already had. This ADR is the accurate record of sign
  resolution's actual semantics. ADR-014's core decision — slug as the sole
  entity identity, resolved at the tool boundary — is unchanged.
- A slug a prior tool result already surfaced now always resolves,
  regardless of what else exists in the graph — closing the failure mode
  where a legitimate, already-known identifier was rejected as unknown.
- Two signs sharing a display name are ambiguous only when no
  `semiotic_system` scope is given. A caller that already knows the system
  (e.g. via FR-AG-05's established-system reuse) is unaffected by that
  collision.
- `_resolve_tradition` is unchanged — it was already exact-slug-or-exact-name
  only, with no fuzzy tier and so no equivalent collision risk. This
  decision is scoped to sign resolution.
- One additional optional argument on `get_sign`/`query_sign`; the
  tool-selecting model learns of it from each tool's own docstring, not the
  system prompt (ADR-009).

## Alternatives considered

- **Infer the semiotic system from conversation context automatically,
  instead of a new argument.** Rejected. Nothing in `get_sign`/`query_sign`'s
  existing contract guarantees a system is known before the call; silently
  narrowing candidates to a system the caller never named risks resolving to
  the wrong system's sign of the same name with no signal that it happened.
- **Drop the fuzzy fallback tier and require exact match only.** Rejected.
  It is an exercised path, not a hypothetical one — a request routinely names
  a sign in shortened or elaborated form before any slug is known. Removing
  it would trade a rare cross-system collision for a routine, common
  phrasing failing to resolve.
- **Pre-build a `{semiotic_system: {slug: sign}}` lookup index.** Rejected as
  unwarranted. The sign set is a small, curated corpus (tens of entries, not
  a scale where a linear scan's cost matters), and `list_signs()` already
  re-fetches from the graph store on every call; an index would add
  complexity with no measurable benefit.
