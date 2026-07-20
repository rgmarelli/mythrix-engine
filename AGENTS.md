# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tooling

- Lint/format with **Ruff**:
  ```bash
  ruff check .
  ruff format .
  ```
- Use the package manager defined by `pyproject.toml` (or equivalent).

## Communication

- Be concise by default.
- Answer the user's question directly.
- Avoid unnecessary explanations or repetition.

## Spec-Driven Development

This project follows Spec-Driven Development (SDD). Every non-trivial feature or change moves through four stages before it's considered done, each producing an artifact under `specs/<feature-slug>/`:

1. **Specify** — write `spec.md`: the problem, goals, non-goals, and functional requirements. Focus on what the system does, not implementation.
2. **Plan** — write `plan.md`: the technical approach, architecture, affected modules, data flow, and key trade-offs. This is *how*, grounded in the actual codebase.
3. **Tasks** — write `tasks.md`: an ordered, checkable breakdown of the plan into concrete, independently verifiable steps.
4. **Implement** — execute the tasks, checking each one off as it lands. Implementation must trace back to a task; a task must trace back to a plan; a plan must trace back to a spec.

Rules:

- **Keep `spec.md` and `tasks.md` factual.** State only what the system does, never why. Avoid rationale, justification, testing evidence, or clauses like "because", "since", or "so that". When requirements change, replace the old text instead of documenting revision history—Git already does that.
- Do not start writing implementation code until `spec.md`, `plan.md`, and `tasks.md` exist and have been agreed with the user for the feature in question.
- If a requirement changes mid-implementation, update `spec.md` (and `plan.md`/`tasks.md` as needed) first, then continue.
- Trivial changes (typo fixes, dependency bumps, formatting) don't need the full flow—use judgment, but default to writing a spec when in doubt.
- Keep `plan.md` and `tasks.md` while the feature is under discussion or implementation. Remove them only after the user explicitly confirms the feature is complete.