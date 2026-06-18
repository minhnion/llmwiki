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

The frontend expects the backend API at `/api` through the Vite proxy. Configure the
proxy target in `frontend/.env` when the backend uses another port:

```bash
cp .env.example .env
pnpm dev
```

Default values:

```bash
VITE_API_BASE_URL=/api
VITE_BACKEND_URL=http://127.0.0.1:8020
```
