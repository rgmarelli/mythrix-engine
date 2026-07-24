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

TODO

1) ui_selection when calling the agent sould carry: "locator": "Ecclesiasticus 43:1–4", the descriptor of the region to help the IA with context
2) reducir ancho maximo texto, que no vaya a toda la pantalla
3) rediseño: mover reference al lado boton add context (no al lado, extremo opuesto de la misma barra)
4) Agregar un /clear para limpiar todo el contexto y la pantalla

