# LLM Wiki

General-purpose LLM Wiki chatbot experiment. The project starts SQLite-first and multimodal-first: raw files stay immutable, LLM/VLM ingest builds a persistent markdown wiki, and SQLite stores evidence, claims, graph state, jobs, chats, and evals.

## Current Status

Foundation scaffold only. Ingest, query, graph, and frontend features will be implemented incrementally.

## Quick Start

Recommended with `uv`:

```bash
uv sync --extra dev
uv run uvicorn backend.app.main:app --reload --port 8010
```

Alternative with `venv` and `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Edit `.env` and set your OpenAI key:

```bash
OPENAI_API_KEY=replace-with-your-openai-api-key
```

Run the API:

```bash
uv run uvicorn backend.app.main:app --reload --port 8010
```

Check health:

```bash
curl http://127.0.0.1:8010/api/health
```

Run tests:

```bash
uv run pytest
```

## Key Docs

- `docs/llm-wiki.md`
- `docs/llm-wiki-chatbot-solution.md`
- `AGENTS.md`
- `CLAUDE.md`
