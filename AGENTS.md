# Development Guidelines

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

## Engineering Approach and Solution Quality

* **Prioritize the correct solution over the quickest solution.** The primary proposed solution must address the underlying problem properly within the project's architecture, design principles, and long-term maintainability goals. Do not default to shortcuts, workarounds, hacks, or narrowly scoped fixes simply because they are faster or easier to implement.
* **Do not preserve poor abstractions for compatibility.** If existing code has an abstraction that no longer fits the problem, prefer improving or replacing the abstraction over layering additional conditionals, flags, or special cases on top of it.
* **Do not silently introduce shortcuts.** If the technically correct solution is more complex, requires architectural changes, or takes significantly more effort, propose that solution first.
* **Explicitly disclose shortcuts and compromises.** If a shortcut, workaround, temporary fix, or technically inferior alternative is being considered, clearly identify it as such, explain what the proper solution would be, and describe the trade-offs, limitations, and technical debt it introduces.
* **Require explicit user approval for shortcuts.** Do not implement a shortcut, workaround, or deliberate architectural compromise without the user's explicit approval. The user's approval must be obtained before implementation, not inferred from the request to "make it work" or from time constraints.
* **Require explicit user approval before modifying LLM prompts.** Do not modify, rewrite, extend, or otherwise alter an LLM prompt without explicit user approval. If a prompt change appears necessary, propose it first and wait for approval.
* **Do not optimize for implementation speed at the expense of correctness.** A solution that merely makes the current test, request, or use case pass is not sufficient if it leaves the underlying design problem unresolved.
* **Prefer root-cause fixes.** When encountering a bug or design problem, investigate and address the underlying cause rather than masking symptoms with patches or special cases.
* **When presenting options, lead with the recommended proper solution.** If alternatives exist, present the architecturally sound solution as the primary recommendation and clearly label any shortcut or compromise as an alternative requiring explicit approval.
* **Never present a shortcut as the proper solution.** Do not frame a workaround as if it were the final or recommended architecture merely because it is simpler to implement.

## Spec-Driven Development

This project follows Spec-Driven Development (SDD). Every non-trivial feature or change moves through four stages before it's considered done, each producing an artifact under `specs/tmp/<feature-slug>/`:

1. **Specify** — write `spec.md`: the problem, goals, non-goals, and functional requirements. Focus on what the system does, not implementation.
2. **Plan** — write `plan.md`: the technical approach, architecture, affected modules, data flow, and key trade-offs. This is *how*, grounded in the actual codebase.
3. **Tasks** — write `tasks.md`: an ordered, checkable breakdown of the plan into concrete, independently verifiable steps.
4. **Implement** — execute the tasks, checking each one off as it lands. Implementation must be traceable to tasks. Tasks must be derived from the plan. The plan must satisfy the spec.

Rules:

- **Keep `spec.md` factual.** State only what the system does. Do not include implementation details, rationale, historical context, or test results.
- Do not start writing implementation code until `spec.md`, `plan.md`, and `tasks.md` exist and have been agreed with the user for the feature in question.
- If a requirement changes mid-implementation, update `spec.md` (and `plan.md`/`tasks.md` as needed) first, then continue.
- Trivial changes (typo fixes, dependency bumps, formatting) don't need the full flow—use judgment, but default to writing a spec when in doubt.
- Keep `plan.md` and `tasks.md` during feature planning and implementation. Do not delete them automatically after tests pass, implementation completion, or code review. Remove them only after the user explicitly confirms that the feature is complete.

## Architecture Decision Records (ADRs)

- Record significant architectural and design decisions as ADRs under `specs/architecture-decisions/`.
- Create an ADR when a decision has meaningful, long-term impact on the architecture, system boundaries, technology choices, data flow, or operational characteristics.
- Do not create ADRs for routine implementation details, minor refactorings, or decisions that are local and easily reversible.
- During feature planning, identify architectural decisions that warrant an ADR. Create or update the ADR before implementation when the decision affects the architecture beyond the scope of the feature.
- The `plan.md` explains how a specific feature or change will be implemented. An ADR explains why a significant architectural decision was made and remains relevant beyond that feature.
- Each ADR should include:
  - **Context** — the problem or forces driving the decision.
  - **Decision** — the chosen approach.
  - **Consequences** — the expected benefits, trade-offs, and limitations.
- Keep ADRs concise and focused on the decision and its rationale.
- Once accepted, do not rewrite an ADR to reflect later changes. Supersede it with a new ADR when a decision changes.

## Code Documentation

- Prefer clear code over explanatory comments.
- Avoid long comments that explain obvious code flow or restate the architecture.
- Keep comments and docstrings focused on current behavior and design decisions.
- Public APIs should document purpose, inputs, outputs, and important constraints.
- Do not include implementation history, migration notes, abandoned approaches, or references to previous versions.
- Do not copy requirements or specifications into comments.
- Use Git history for historical context.

## Git

- Follow the Conventional Commits specification (e.g. `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`).
- Keep commit messages concise.
- The first line should summarize the primary change.
- Commit bodies should explain intent and major impacts, not enumerate every modified file or implementation detail.
- Prefer describing the outcome of a change over the sequence of edits performed.
- Avoid writing commit messages as changelogs or pull request descriptions.
- Include detailed migration notes, file lists, or implementation history only when explicitly requested.
- Do not add yourself as an author or co-author of the commits.
- All commit messages and logs must be reviewed and explicitly approved by the user before execution.

## Licensing

- Every new source code file must include the following SPDX header at the top of the file:

```text
SPDX-FileCopyrightText: 2026 Guido Marelli
SPDX-License-Identifier: AGPL-3.0-or-later
```

- Apply this only to source code files (e.g. `.py`, `.java`, `.cpp`, `.go`, `.sh`).
- Do not add SPDX headers to documentation files (`README.md`, `docs/*.md`, `CHANGELOG.md`, etc.).
- Preserve existing SPDX headers when modifying files.
