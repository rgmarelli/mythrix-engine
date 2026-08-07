# Development Guidelines

## Communication

- Be concise and answer the user's question directly.
- Avoid unnecessary explanations and repetition.

## Engineering Principles

- Prefer architecturally sound, long-term solutions over shortcuts or workarounds.
- Fix root causes rather than masking symptoms.
- Improve poor abstractions instead of adding special cases or compatibility layers.
- If a shortcut or architectural compromise is considered, clearly identify it, explain its trade-offs, and obtain explicit user approval before implementation.
- Present the recommended solution first; clearly label any alternative as a compromise.
- Do not modify LLM prompts without explicit user approval.

## Spec-Driven Development

Non-trivial changes follow four stages under `specs/tmp/<feature-slug>/`:

1. **Specify** — `spec.md`: problem, goals, non-goals, and functional requirements.
2. **Plan** — `plan.md`: architecture, technical approach, affected modules, and trade-offs.
3. **Tasks** — `tasks.md`: ordered, verifiable implementation steps.
4. **Implement** — complete tasks and keep implementation traceable to the plan.

### Rules

- Do not begin implementation until `spec.md`, `plan.md`, and `tasks.md` exist and have been agreed with the user.
- If requirements change, update the specification first.
- Trivial changes (typos, formatting, dependency bumps) may skip the full process.
- Keep `spec.md` focused on behavior, not implementation.
- Keep `plan.md` and `tasks.md` until the user explicitly confirms the feature is complete.

## Architecture Decision Records (ADRs)

- Record significant architectural decisions under `specs/architecture-decisions/`.
- Use ADRs only for decisions with lasting architectural impact.
- ADRs should capture **Context**, **Decision**, and **Consequences**.
- Focus on the architectural decision and its rationale, not implementation details or debugging history.
- Keep ADRs concise. Move implementation details, experiments, and failure analyses to design documents or Git history.
- Once accepted, supersede an ADR instead of rewriting it.

## Code Documentation

- Prefer self-documenting code over explanatory comments.
- Document public APIs, important constraints, and non-obvious design decisions.
- Avoid historical notes, obsolete rationale, and duplicated specifications in comments.
- Use Git history for implementation history.

## Git

- Never create a commit without explicit user approval.

## Tooling

- Lint and format with **Ruff**:

```bash
ruff check .
ruff format .
```

- Use the package manager defined by `pyproject.toml` (or equivalent).

## Licensing

Every new source code file must include:

```text
SPDX-FileCopyrightText: 2026 Guido Marelli
SPDX-License-Identifier: AGPL-3.0-or-later
```

- Apply SPDX headers only to source code files.
- Preserve existing SPDX headers when modifying files.
