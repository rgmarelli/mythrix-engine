# Authoring + loading

How the [Sign Graph](domain-model.md) is authored by curators and loaded by the structured-data loader.

## Functional requirements

- FR-SD-01: The structured-data loader accepts human-authored, version-controllable source files, validates their schema and referential integrity (e.g. a citation must reference an already-loaded source; an intersemiotic interpretant must reference existing sign/tradition pairs) before writing anything, and upserts idempotently — re-running the loader on edited data does not create duplicates.
- FR-SD-02: Invalid or referentially inconsistent structured data is rejected with an actionable error, not silently partially loaded.
- FR-SD-03: Structured-data files reference other entities (an intersemiotic interpretant's target sign, a citation's source, a manifestation's tradition) by human-readable name rather than requiring curators to invent and consistently repeat opaque slugs across files. An intersemiotic interpretant's target is resolved by name scoped to a named target semiotic system (`target_system`). The loader resolves names to the correct entity and reports a clear, actionable error on an unresolvable or ambiguous name, or on a target semiotic system with no matching sign, rather than guessing.
- FR-SD-04: An intersemiotic interpretant between two signs may be declared inline within the manifestation that asserts it, rather than requiring a separate relationship file — using the same attributable, multi-claim semantics as [domain-model.md](domain-model.md) FR-DM-03 (competing claims from different traditions/attribution-systems still coexist without conflicting). Each intersemiotic interpretant names its target sign's semiotic system and name.
- FR-SD-05: A manifestation may carry a lightweight list of descriptive interpretants — thematic concepts, notable depicted elements, or other free-text tokens — that does not create a new sign or intersemiotic interpretant. This is distinct from FR-DM-03/FR-SD-04's intersemiotic interpretants, which are reserved for a target that itself carries independently-tracked, citable meaning; curators choose per case which is appropriate, and a descriptive interpretant can later be promoted to a full cross-referenced sign without any schema change.

See [domain-model.md](domain-model.md) for a worked example showing FR-SD-03–FR-SD-05 together.
