# Sign Graph

The domain-agnostic data model representing signs, interpretive traditions, and their cross-references. See [Structured Data](structured-data.md) for how this model is authored and loaded.

## Vocabulary

- **`semiotic_system`**: The overarching domain or system of signs being classified (e.g., `tarot`, `hebrew_alef_bet`).
- **`sign`**: The single, primary symbol or entity being modeled in a file (e.g., The Sun, Qoph).
- **`manifestations`**: The specific historical, cultural, or textual traditions where a sign is contextualized and described (e.g., `rider-waite`, `sepher-yetzirah-gra`).
- **`properties`**: Static, structural attributes of a sign (e.g., card number, letter type). They provide informational context but are never used for dynamic search queries.
- **`interpretants`**: The conceptual tokens, values, or meanings evoked by a sign within its own domain — the primary source of retrieval query text.
- **`intersemiotic_interpretants`**: Graph-edge pointers that bridge distinct domains, mapping how a sign translates directly into a specific target sign of an external system.

## Functional requirements

- FR-DM-01: The system represents `Sign`, `Tradition`, `Manifestation` (a sign as understood within one tradition), `Property`, `Interpretant`, and `Source` as distinct entities, with no domain-specific fields baked into the core schema.
- FR-DM-02: A sign may have multiple `Manifestation`s, one per tradition, each with its own display name/title (a sign's name is not assumed to be tradition-invariant — e.g. the same tarot card may be titled differently across traditions), denotation, properties, interpretants, and citations, all scoped to that manifestation only.
- FR-DM-03: Intersemiotic interpretants between signs (including across traditions, across domains — e.g. a tarot sign related to a Kabbalah sign — and across nested sub-contexts within a domain, e.g. a concept that manifests distinctly within each of several parallel contexts such as a sephirah within a given "world") are first-class, typed (a free-text relationship, not a fixed enum), and attributable: each intersemiotic interpretant records which tradition/attribution-system asserts it (`according_to`) and may cite a source, so multiple alternative or competing claims can coexist for the same sign without conflicting or silently overwriting one another. No domain-specific structural concepts (such as a fixed notion of "world" or "level") are introduced into the core schema — nested contexts are represented as ordinary data using the same sign/manifestation/intersemiotic-interpretant primitives.
- FR-DM-04: A sign may carry intrinsic, tradition-independent properties — facts true of the sign itself regardless of interpretive lens (e.g. a Hebrew letter's position in its alphabet or its numeric value). A manifestation may also carry its own tradition-scoped properties — structural facts specific to that one tradition's rendering (e.g. a card's position number within one specific deck). Properties, at either scope, are kept structurally distinct from a manifestation's interpretants (FR-DM-02), which can genuinely vary by tradition and are eligible for retrieval; a property is never used to build retrieval query text (see [Retrieval](../retrieval/retrieval.md) FR-RT-05).
- FR-DM-05: A sign is not required to have any manifestation to exist in the graph or to participate in an intersemiotic interpretant. Intersemiotic interpretants (FR-DM-03, and [Structured Data](structured-data.md) FR-SD-04) are asserted between signs directly, not between specific manifestations of them, so a sign serving purely as an intersemiotic-interpretant target or structural anchor (e.g. a Tree of Life path or a sephirah referenced only as someone else's correspondence) never needs interpretive content written for it.

## Non-goals

- Cross-tradition comparison synthesis as a query capability — e.g. surfacing two *interpretive* traditions' competing readings of the same sign (Crowley's vs. Waite's) side by side and adjudicating which one a document corpus better supports. The data model must support intersemiotic interpretants between traditions (FR-DM-03), but no query surface for comparing traditions ships in v1. This is distinct from reading an independent, non-interpretive document corpus through one tradition's established symbolism, which is in scope (see [Corpus](../retrieval/corpus.md) FR-CO-02).

## Worked example

A tarot card and a Hebrew letter, showing every mechanism above together:

```yaml
# data/semiotic_systems/tarot/signs/the-fool.yaml
semiotic_system: tarot
sign:
  name: "The Fool"
  type: major-arcana

  manifestations:
    - tradition: rider-waite
      display_name: "The Fool"
      denotation: >
        A man dressed in ragged, colorful jester-like clothes with small bells walks
        briskly across a rocky ground. He holds a walking stick in his right hand and
        carries a stick with a small pouch slung over his left shoulder. A quadruped
        animal resembling a small dog or cat tears at his trousers from behind, pulling
        them down to expose the flesh of his thigh and backside. He looks forward and
        slightly upward while walking, ignoring the animal entirely, and the space at
        the very top of the card contains no number.
      interpretants:
        - type: concept
          value: dog
        - type: concept
          value: white rose
        - type: concept
          value: cliff
      cites: "Waite, Pictorial Key to the Tarot, p. 97"
      intersemiotic_interpretants:
        - target_system: hebrew_alef_bet
          target_sign: "Samekh"
          relationship: hebrew_letter
          according_to: "Golden Dawn"
```

```yaml
# data/semiotic_systems/hebrew_alef_bet/signs/samekh.yaml
semiotic_system: hebrew_alef_bet
sign:
  name: "Samekh"
  type: hebrew-letter
  properties:
    - {key: alphabet_position, value: "15"}
    - {key: numeric_value, value: "60"}

  manifestations:
    - tradition: golden-dawn-kabbalah
      display_name: "Samekh (ס)"
      denotation: "Support and protection; the serpent encircling the initiate."
      intersemiotic_interpretants:
        - target_system: hebrew_alef_bet
          target_sign: "Path: Tiphareth–Yesod"
          relationship: tree_of_life_path
          according_to: "Golden Dawn"
        - target_system: hebrew_alef_bet
          target_sign: "Tiphareth"
          relationship: sephirah
          according_to: "Golden Dawn"
        - target_system: hebrew_alef_bet
          target_sign: "Yesod"
          relationship: sephirah
          according_to: "Golden Dawn"
```

Reading this against the requirements: `interpretants` ([Structured Data](structured-data.md) FR-SD-05) here holds depicted objects from the card's artwork ("dog", "white rose", "cliff") — no sign is created for any of them. `intersemiotic_interpretants` (FR-SD-04) references `"Samekh"` by name (FR-SD-03) scoped to its `target_system` (`hebrew_alef_bet`) rather than a pre-coordinated slug, and asserts a claim attributed to a specific tradition ("Golden Dawn"), so a competing attribution system could add a second, independent `intersemiotic_interpretants` entry for the same card without conflict (FR-DM-03). Samekh's `properties` (FR-DM-04) — alphabet position, numeric value — sit on the sign itself, not on its `golden-dawn-kabbalah` manifestation. `"Path: Tiphareth–Yesod"`, `"Tiphareth"`, and `"Yesod"` are referenced purely as intersemiotic-interpretant targets. Per FR-SD-03 the loader requires each to be declared in its own sign file, in the same semiotic system, before it can be referenced — but per FR-DM-05 that file needs nothing beyond a bare `semiotic_system:` and `sign:` block, e.g. `semiotic_system: hebrew_alef_bet` / `sign: {name: "Tiphareth", type: sephirah}`, with no `manifestations:` at all. Either can be enriched with a full manifestation later without changing anything that already references it.
