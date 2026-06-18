# LLM Wiki

General-purpose LLM Wiki chatbot experiment. The project starts SQLite-first and multimodal-first: raw files stay immutable, LLM/VLM ingest builds a persistent markdown wiki, and SQLite stores evidence, claims, graph state, jobs, chats, and evals.

## Current Status

The application now includes source upload, OpenAI multimodal ingest, source-grounded chat, SQLite knowledge graph build/visualization, contradiction inspection, and a React workbench. Evaluation workflows will be added after representative data exists.

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
LLM_WIKI_PORT=8020
LLM_WIKI_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
LLM_WIKI_MODEL=gpt-4o
LLM_WIKI_PREFERRED_LANGUAGE=vi
LLM_WIKI_MAX_FILE_BYTES=50000000
LLM_WIKI_MAX_OUTPUT_TOKENS=6000
```

Run the API:

```bash
uv run python -m backend.app.cli serve --reload
```

Run the React workbench in a second terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

Open `http://127.0.0.1:5173`. The Vite dev server proxies `/api` to the backend on port `8020`.

The application workflow is:

1. Upload a source file.
2. Ingest the registered source with the multimodal model.
3. Build and explore the knowledge graph.
4. Ask grounded questions and inspect citations/evidence.

Check health:

```bash
curl http://127.0.0.1:8020/api/health
```

Initialize the database:

```bash
uv run python -m backend.app.cli db migrate
```

Register a local source file:

```bash
mkdir -p raw/sources
cp /path/to/tai-lieu.pdf raw/sources/tai-lieu.pdf
uv run python -m backend.app.cli sources register raw/sources/tai-lieu.pdf --title "Tài liệu của tôi" --type pdf
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
uv run python -m backend.app.cli query ask "Tài liệu trình bày những nội dung chính nào?"
```

Use JSON output for inspection or eval scripts:

```bash
uv run python -m backend.app.cli query ask \
  "Tài liệu trình bày những nội dung chính nào?" \
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
uv run python -m backend.app.cli graph search "tên thực thể"
uv run python -m backend.app.cli graph inspect "tên thực thể"
uv run python -m backend.app.cli graph contradictions
```

Expected graph outputs:

- `relation_edges`, `contradictions`, `entity_aliases`, and `graph_runs` rows in SQLite
- generated entity pages under `wiki/entities/`
- graph-expanded evidence becomes available to query retrieval
- ignored runtime `wiki/log.md` gets a graph entry

API equivalents:

```bash
curl -X POST http://127.0.0.1:8020/api/sources/upload \
  -F "file=@/path/to/tai-lieu.pdf" \
  -F "title=Tài liệu của tôi" \
  -F "source_type=pdf"

curl -X POST http://127.0.0.1:8020/api/sources/register \
  -H "Content-Type: application/json" \
  -d '{"path":"raw/sources/tai-lieu.pdf","title":"Tài liệu của tôi","source_type":"pdf"}'

curl -X POST http://127.0.0.1:8020/api/sources/src_your_source_id/ingest
curl http://127.0.0.1:8020/api/sources

curl -X POST http://127.0.0.1:8020/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Tài liệu trình bày những nội dung chính nào?","mode":"deep"}'

curl -X POST http://127.0.0.1:8020/api/graph/build \
  -H "Content-Type: application/json" \
  -d '{"source_ids":[],"rebuild":true}'

curl "http://127.0.0.1:8020/api/graph/search?q=ten%20thuc%20the"
curl "http://127.0.0.1:8020/api/graph/visualization?limit=80"
curl http://127.0.0.1:8020/api/graph/entities/ten-thuc-the
curl http://127.0.0.1:8020/api/graph/contradictions
```

Run tests:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .

cd frontend
pnpm lint
pnpm test
pnpm build
```

## Key Docs

- `docs/llm-wiki.md`
- `docs/llm-wiki-chatbot-solution.md`
- `docs/implementation-architecture-current.md`
- `AGENTS.md`
- `CLAUDE.md`
