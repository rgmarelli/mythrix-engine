# Mythrix Engine

A symbolic knowledge retrieval system that maps semiotic structures (semiotic systems, signs, traditions, and interpretants) to relevant passages within a corpus of reference sources.

See `specs/symbol-interpretation-core/` for the spec, technical plan, and task breakdown driving this project's development.

See `docs/SETUP.md` for installing Ollama, loading the reference dataset, and running your first query.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```
