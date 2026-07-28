# Mythrix Query Viewer (web/)

React + TypeScript + Vite frontend for the query viewer. Independent toolchain from the Python package — see `specs/interfaces/web-viewer.md` and `specs/interfaces/api.md` for the full contract with `api/src/mythrix/api/`.

## Dev

```bash
npm install
npm run dev        # http://localhost:5173, expects the API at VITE_API_BASE_URL (.env.development)
```

Requires `uv run --project api uvicorn mythrix.api.app:app --reload` (run from the repo root) running separately (default `http://localhost:8000`).

## Build

```bash
npm run build       # outputs to dist/
```

`dist/` is served directly by the FastAPI process (`mythrix.api.app`) when present — no separate frontend server needed in production, and no `VITE_API_BASE_URL` is required since the frontend then calls the API same-origin.
