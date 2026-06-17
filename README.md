# LLM Wiki

General-purpose LLM Wiki chatbot experiment. The project starts SQLite-first and multimodal-first: raw files stay immutable, LLM/VLM ingest builds a persistent markdown wiki, and SQLite stores evidence, claims, graph state, jobs, chats, and evals.

## Current Status

Source registry and OpenAI multimodal ingest are implemented. Query, graph browsing, and frontend features will be implemented incrementally.

## Quick Start

Recommended with `uv`:

```bash
uv sync --extra dev
uv run python -m backend.app.cli serve --reload
```

Alternative with `venv` and `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Edit `.env` and set your OpenAI key and port:

```bash
OPENAI_API_KEY=replace-with-your-openai-api-key
LLM_WIKI_PORT=8010
LLM_WIKI_MODEL=gpt-4o
LLM_WIKI_MAX_FILE_BYTES=50000000
LLM_WIKI_MAX_OUTPUT_TOKENS=6000
```

Run the API:

```bash
uv run python -m backend.app.cli serve --reload
```

Check health:

```bash
curl http://127.0.0.1:8010/api/health
```

Initialize the database:

```bash
uv run python -m backend.app.cli db migrate
```

Register a local source file:

```bash
mkdir -p raw/sources
cp /path/to/example.pdf raw/sources/example.pdf
uv run python -m backend.app.cli sources register raw/sources/example.pdf --title "Example PDF" --type pdf
```

Ingest a registered source with OpenAI multimodal/file input:

```bash
uv run python -m backend.app.cli sources ingest src_your_source_id
```

Expected ingest outputs:

- source status becomes `ingested`
- `wiki/sources/<source-title>-<source-id>.md` is generated
- ignored runtime `wiki/log.md` gets an ingest entry
- SQLite stores evidence, claims, entities, review items, wiki page metadata, and FTS rows

API equivalents:

```bash
curl -X POST http://127.0.0.1:8010/api/sources/register \
  -H "Content-Type: application/json" \
  -d '{"path":"docs/llm-wiki.md","title":"LLM Wiki Concept","source_type":"markdown"}'

curl -X POST http://127.0.0.1:8010/api/sources/src_your_source_id/ingest
curl http://127.0.0.1:8010/api/sources
```

Run tests:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
```

## Key Docs

- `docs/llm-wiki.md`
- `docs/llm-wiki-chatbot-solution.md`
- `AGENTS.md`
- `CLAUDE.md`
