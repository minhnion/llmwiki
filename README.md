# LLM Wiki

General-purpose LLM Wiki chatbot experiment. The project starts SQLite-first and multimodal-first: raw files stay immutable, LLM/VLM ingest builds a persistent markdown wiki, and SQLite stores evidence, claims, graph state, jobs, chats, and evals.

## Current Status

Source registry, OpenAI multimodal ingest, source-grounded query synthesis, and SQLite knowledge graph build/inspect are implemented. Eval workflows and frontend features will be implemented incrementally.

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

Ask a question against the ingested wiki/evidence store:

```bash
uv run python -m backend.app.cli query ask "How is LLM Wiki different from traditional RAG?"
```

Use JSON output for inspection or eval scripts:

```bash
uv run python -m backend.app.cli query ask \
  "How is LLM Wiki different from traditional RAG?" \
  --mode deep \
  --max-evidence 8 \
  --json
```

Expected query outputs:

- answer synthesized from selected source-grounded evidence
- citation list with source title, locator, and evidence ID
- `query_runs` and `query_citations` rows in SQLite
- ignored runtime `wiki/log.md` gets a query entry

Build the knowledge graph from ingested claims and evidence:

```bash
uv run python -m backend.app.cli graph build
```

Inspect graph state:

```bash
uv run python -m backend.app.cli graph search "LLM Wiki"
uv run python -m backend.app.cli graph inspect "LLM Wiki"
uv run python -m backend.app.cli graph contradictions
```

Expected graph outputs:

- `relation_edges`, `contradictions`, `entity_aliases`, and `graph_runs` rows in SQLite
- generated entity pages under `wiki/entities/`
- graph-expanded evidence becomes available to query retrieval
- ignored runtime `wiki/log.md` gets a graph entry

API equivalents:

```bash
curl -X POST http://127.0.0.1:8010/api/sources/register \
  -H "Content-Type: application/json" \
  -d '{"path":"docs/llm-wiki.md","title":"LLM Wiki Concept","source_type":"markdown"}'

curl -X POST http://127.0.0.1:8010/api/sources/src_your_source_id/ingest
curl http://127.0.0.1:8010/api/sources

curl -X POST http://127.0.0.1:8010/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"How is LLM Wiki different from traditional RAG?","mode":"deep"}'

curl -X POST http://127.0.0.1:8010/api/graph/build \
  -H "Content-Type: application/json" \
  -d '{"source_ids":[],"rebuild":true}'

curl "http://127.0.0.1:8010/api/graph/search?q=LLM%20Wiki"
curl http://127.0.0.1:8010/api/graph/entities/LLM%20Wiki
curl http://127.0.0.1:8010/api/graph/contradictions
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
