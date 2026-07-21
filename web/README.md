# Mythrix Query Viewer (web/)

React + TypeScript + Vite frontend for the query viewer. Independent toolchain from the Python package — see `specs/symbol-interpretation-core/plan.md` ("Web viewer and backend API") for the full contract with `src/mythrix/api/`.

## Dev

```bash
npm install
npm run dev        # http://localhost:5173, expects the API at VITE_API_BASE_URL (.env.development)
```

Requires `uv run uvicorn mythrix.api.app:app --reload` running separately (default `http://localhost:8000`).

The AI Summary button (`PassageDetailPanel`) calls `POST /api/summarize`, which requires `MYTHRIX_GENERATION_MODEL` to be set (`.env`, or the environment) to a model pulled in Ollama — unlike the rest of the query viewer, which only needs the embedding model. Without it, the button surfaces a client-visible error (FR19) rather than failing the rest of the page.

## Build

```bash
npm run build       # outputs to dist/
```

`dist/` is served directly by the FastAPI process (`mythrix.api.app`) when present — no separate frontend server needed in production, and no `VITE_API_BASE_URL` is required since the frontend then calls the API same-origin.
