# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Mythrix Engine is a Python project licensed under GNU AGPL v3.

## Tooling

The `.gitignore` includes entries for **Ruff** (`.ruff_cache/`), indicating it is the intended linter/formatter. Once configured:

```bash
ruff check .       # lint
ruff format .      # format
```

The `.gitignore` also covers common Python package managers (pip, uv, poetry, pdm, pipenv, pixi) — the chosen one will be determined when `pyproject.toml` or equivalent is added.

## Spec-Driven Development

This project follows Spec-Driven Development (SDD). Every non-trivial feature or change moves through four stages before it's considered done, each producing a durable artifact under `specs/<feature-slug>/`:

1. **Specify** — write `spec.md`: the problem, goals, non-goals, and functional requirements. Focus on *what* and *why*, not implementation. No code yet.
2. **Plan** — write `plan.md`: the technical approach, architecture, affected modules, data flow, and key trade-offs. This is *how*, grounded in the actual codebase.
3. **Tasks** — write `tasks.md`: an ordered, checkable breakdown of the plan into concrete, independently verifiable steps.
4. **Implement** — execute the tasks, checking each one off as it lands. Implementation must trace back to a task; a task must trace back to a plan; a plan must trace back to a spec.

Rules:

- Do not start writing implementation code until `spec.md` and `plan.md` exist and are aligned with the user for the feature in question.
- If a requirement changes mid-implementation, update `spec.md` (and `plan.md`/`tasks.md` as needed) first, then continue — specs are living documents, not write-once artifacts.
- Trivial changes (typo fixes, dependency bumps, formatting) don't need the full flow — use judgment, but default to writing a spec when in doubt.
- Keep specs in version control alongside the code they describe.
