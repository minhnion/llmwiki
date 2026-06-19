# LLM Wiki Frontend

React + Vite + Tailwind application for the LLM Wiki workbench.

## Commands

```bash
pnpm install
pnpm dev
pnpm test
pnpm lint
pnpm build
```

The frontend expects the backend API at `/api` through the Vite proxy. The proxy reads
the workspace root `.env` first, so `LLM_WIKI_PORT=8030` automatically points the proxy
to `http://127.0.0.1:8030`.

Use `frontend/.env` only when you want an explicit frontend override:

```bash
cp .env.example .env
pnpm dev
```

Default values:

```bash
VITE_API_BASE_URL=/api
# Optional override. If omitted, Vite uses root LLM_WIKI_HOST/LLM_WIKI_PORT.
# VITE_BACKEND_URL=http://127.0.0.1:8030
```
