# Mythrix Engine

An explainable symbolic interpretation engine. Every interpretation is built from a transparent, auditable chain: structured symbolic data, retrieval-augmented generation grounded in primary sources, and a local LLM that explains relationships and cites its evidence.

See `specs/symbol-interpretation-core/` for the spec, technical plan, and task breakdown driving this project's development.

See `docs/SETUP.md` for installing Ollama, loading the reference dataset, and running your first query.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```
