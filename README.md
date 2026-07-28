# Mythrix Engine

**A deterministic symbolic retrieval engine with an LLM-powered interpretation and knowledge-discovery assistant.**

> 🚧 **Work in Progress**
>
> Mythrix is an experimental system under active development. Its architecture, domain model, APIs, and user experience are evolving.

Mythrix explores how AI-assisted interpretation can work over **large, structured knowledge systems and source corpora** without making an LLM responsible for retrieving or inventing the underlying evidence.

The core architectural principle is simple:

> **The deterministic engine finds the evidence. The LLM helps the user interpret and explore it.**

---

## See it in action

![Mythrix Engine](docs/images/mythrix.png)

A query against a symbol produces ranked **convergence hotspots** with verbatim source passages and exact citations. A conversational assistant can then inspect and explore the same evidence through read-only tools, while its tool trace remains visible to the user.

---

## What is Mythrix?

Mythrix is a symbolic knowledge retrieval system that connects a structured symbolic model with a corpus of primary reference sources.

It currently explores symbolic interpretation through domains such as Tarot and semiotics, modeling relationships between:

* **Semiotic systems**
* **Signs**
* **Traditions**
* **Manifestations**
* **Interpretants**
* **Source documents and passages**

Given a symbolic context, Mythrix derives retrieval signals from the structured model and searches an independent corpus of reference material.

The deterministic query engine then:

1. Resolves the symbolic context.
2. Derives relevant retrieval signals.
3. Searches the source corpus.
4. Identifies converging evidence.
5. Ranks the resulting regions.
6. Returns traceable source passages and citations.

An LLM-powered conversational assistant sits above this engine.

It helps users:

* understand difficult or archaic passages;
* explore retrieved evidence;
* compare passages and concepts;
* ask follow-up questions;
* discover connections across sources;
* formulate new questions;
* request additional queries when exploration leads beyond the current evidence.

The LLM therefore acts as an **interpretation and knowledge-discovery assistant**, not as the primary retrieval engine.

---

## The Architectural Decision

The central design decision in Mythrix is to deliberately separate **retrieval** from **interpretation**.

```text
┌───────────────────────────────────────────────┐
│             INTERPRETATION LAYER              │
│                                               │
│  LLM Assistant                                │
│  • Explain difficult passages                 │
│  • Explore retrieved evidence                 │
│  • Compare concepts and sources               │
│  • Answer follow-up questions                 │
│  • Discover connections                       │
│  • Request additional queries                 │
│  • Maintain natural-language conversation     │
└───────────────────────┬───────────────────────┘
                        │
                 Evidence / Commands
                        │
                 ───────┼───────
                  TRUST BOUNDARY
                 ───────┼───────
                        │
┌───────────────────────▼───────────────────────┐
│              RETRIEVAL LAYER                  │
│                                               │
│  Deterministic Query Engine                   │
│  • Symbolic resolution                        │
│  • Retrieval                                  │
│  • Convergence                                │
│  • Ranking                                    │
│  • Provenance                                 │
│  • Citations                                  │
└───────────────────────┬───────────────────────┘
                        │
              ┌─────────┴─────────┐
              │                   │
              ▼                   ▼
       ┌──────────────┐    ┌───────────────┐
       │  SIGN GRAPH  │    │ SOURCE CORPUS │
       │              │    │               │
       │ Signs        │    │ Documents     │
       │ Traditions   │    │ Sections      │
       │ Interpretants│    │ Passages      │
       │ Relations    │    │ References    │
       └──────────────┘    └───────────────┘
```

This boundary is intentional.

The retrieval engine owns the question:

> **What evidence is relevant?**

The LLM helps with the question:

> **What can we understand or discover from that evidence?**

This separation allows the system to use each component where it provides the most value:

| Deterministic engine | LLM assistant          |
| -------------------- | ---------------------- |
| Symbolic resolution  | Language understanding |
| Retrieval            | Explanation            |
| Convergence          | Contextualization      |
| Ranking              | Comparison             |
| Provenance           | Exploration            |
| Citations            | Knowledge discovery    |

The goal is not to eliminate LLMs.

It is to avoid making them responsible for determining what evidence exists.

---

## Why Not Put the LLM in Charge of Retrieval?

Mythrix is designed to work with potentially large corpora of reference material.

A conventional LLM-centered RAG pipeline typically couples the user's natural-language question, query formulation, retrieval, and final generation:

```text
User question
      ↓
LLM
      ↓
Query formulation
      ↓
Vector retrieval
      ↓
Top-K chunks
      ↓
LLM context
      ↓
Generated answer
```

This approach can be useful, but it gives the model significant influence over which evidence enters the context.

Mythrix explores a different architecture:

```text
Structured symbolic model
          ↓
Deterministic retrieval signals
          ↓
Corpus search
          ↓
Convergence
          ↓
Ranking
          ↓
Evidence surface
          ↓
LLM interpretation and exploration
```

The deterministic engine reduces a potentially large corpus to a manageable and explainable **evidence surface**.

The LLM then operates over that surface.

This creates a clear trust boundary:

> **The LLM can interpret the evidence, but it does not define the evidence.**

---

## Symbolic Retrieval and Convergence

Mythrix does not treat the source corpus as a flat collection of documents.

The symbolic model provides structured context for retrieval.

Conceptually:

```text
Semiotic System
      │
      ▼
     Sign
      │
      ├── Tradition
      │
      ├── Manifestation
      │
      └── Interpretants
             │
             ▼
      Retrieval Signals
             │
             ▼
        Source Corpus
```

The symbolic model actively defines the retrieval space.

A query can produce multiple retrieval signals. For example:

```text
                 The Sun
                     │
       ┌─────────────┼─────────────┐
       │             │             │
  Laughter         Child          100
       │             │             │
       └─────────────┼─────────────┘
                     │
                     ▼
              Corpus retrieval
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
       Passage A  Passage B  Passage C
          │          │          │
          └──────────┼──────────┘
                     ▼
                Convergence
                     │
                     ▼
                  Ranking
                     │
                     ▼
                  Evidence
```

Rather than relying only on the similarity between a single query and a single document chunk, Mythrix can identify regions where multiple symbolic concepts converge.

This convergence contributes to ranking and provides a more explicit explanation of why a region surfaced.

The symbolic graph is therefore not merely metadata around the documents.

> **The symbolic model actively defines the retrieval space.**

---

## The LLM as an Interpretation and Discovery Layer

The LLM's role begins once evidence is available.

A query may surface passages written in:

* archaic language;
* complex prose;
* unfamiliar terminology;
* culturally specific references;
* dense philosophical or symbolic language.

The user can then ask:

> "What is this author actually saying here?"

The assistant can help explain the passage, clarify terminology, compare sources, and connect concepts across retrieved evidence.

But the evidence itself remains grounded in the underlying source corpus.

The interaction can then become iterative:

```text
Retrieve
   ↓
Interpret
   ↓
Explore
   ↓
Ask
   ↓
Retrieve more
   ↓
Interpret again
```

This creates a knowledge-discovery loop in which the LLM acts as a bridge between **retrieval and human inquiry**.

The assistant can also request a new structured query:

```text
User request
     ↓
LLM Assistant
     ↓
Structured query intent
     ↓
Application command
     ↓
Deterministic Query Engine
     ↓
New evidence
```

The LLM does not execute retrieval itself.

It requests an application action, and the normal query execution path remains responsible for producing the results.

This keeps conversational interaction separate from the deterministic query engine while allowing the two layers to work together.

---

## Architecture

Mythrix supports two complementary paths.

### Direct query

```text
User
  ↓
Query UI / API / CLI
  ↓
Deterministic Query Engine
  ↓
Symbolic Model
  ↓
Corpus Retrieval
  ↓
Convergence & Ranking
  ↓
Evidence
```

### Conversational exploration

```text
User
  ↓
Chat
  ↓
LLM Assistant
  │
  ├───────────────┐
  │               │
  ▼               ▼
Inspect         Request
Evidence        New Query
  │               │
  │               ▼
  │         Application Command
  │               │
  │               ▼
  │         Deterministic Query
  │               │
  └───────┬───────┘
          ▼
       Evidence
          │
          ▼
   LLM Interpretation
          │
          ▼
         User
```

The deterministic query engine remains the center of evidence retrieval regardless of how the user enters the system.

---

## Architecture Principles

### Retrieval is separate from interpretation

The system first establishes relevant evidence and then uses the LLM to help interpret and explore it.

### The LLM is not the retrieval authority

The LLM does not determine the underlying evidence or replace deterministic retrieval and ranking.

### Symbolic knowledge drives retrieval

The symbolic model is an active part of query construction and retrieval behavior.

### Evidence remains traceable

Results remain connected to their underlying source documents and passages.

### Conversation does not replace the application

The LLM can request application actions, but the application remains responsible for executing them.

### Large corpora are explored incrementally

The system narrows the corpus before asking the LLM to interpret or explore the resulting evidence.

### Human inquiry remains central

The LLM is an assistant for interpretation and discovery, not an autonomous authority over the knowledge domain.

---

## Technology

Mythrix is currently built with:

* **Python**
* **LangGraph** for conversational agent orchestration
* **Kùzu** for symbolic graph storage
* **Chroma** for corpus and vector retrieval
* **FastAPI** for the application API
* **CLI** for direct interaction
* **Web UI** for interactive exploration

The deterministic query engine is designed to remain usable independently of the conversational agent.

---

## Documentation

Mythrix is developed using specification-driven development, with system requirements and architectural decisions documented alongside the implementation.

* [Setup Guide](docs/SETUP.md) — Run Mythrix locally and explore the system.
* [System Specification](specs/spec.md) — Goals, non-goals, requirements, architecture, constraints, and end-to-end flows.
* [Architecture Decision Records](specs/architecture-decisions) — The reasoning behind key architectural decisions.

---

## Current Status

> 🚧 **Work in Progress**

Mythrix is an active research and engineering project.

Current areas of development include:

* evolving the symbolic domain model;
* improving retrieval and convergence ranking;
* expanding source provenance;
* refining conversational exploration;
* improving agent/application boundaries;
* evaluating interpretation quality;
* improving the web experience;
* documenting architectural decisions;
* expanding automated tests and evaluation.

The architecture and domain model are expected to evolve as the project develops.

---

## Project Goal

Mythrix explores a broader engineering question:

> **Can an LLM help people interpret and discover knowledge in large symbolic corpora without becoming responsible for retrieving or inventing the underlying evidence?**

The current architecture explores one possible answer:

```text
Structured Symbolic Knowledge
            +
Deterministic Retrieval
            +
Explicit Evidence
            +
LLM-Assisted Interpretation
            +
Human Exploration
            =
Explainable Knowledge Discovery
```

The Tarot domain is currently used as an experimental symbolic system, but the architecture is intended to remain independent of any single symbolic tradition.

---

## License

Mythrix Engine is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
