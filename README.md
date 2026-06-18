# LLM Wiki

General-purpose LLM Wiki chatbot experiment. The target foundation is SQLite-first,
multimodal-first, and artifact-first: LLM/VLM compiles immutable raw sources into an
evidence-backed wiki, open knowledge artifacts, semantic indexes, and an integrated graph.

## Current Status

The current implementation includes source upload, one-pass OpenAI multimodal ingest,
source-grounded chat, SQLite graph build/visualization, contradiction inspection, and
a React workbench. The next foundation upgrade is specified in
`docs/artifact-first-llm-wiki-foundation.md`: LLM-driven multi-pass compilation,
coverage audit, graph integration during ingest, artifact semantic retrieval, and
source re-inspection.

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
LLM_WIKI_COMPILER_MAX_PASSES=8
LLM_WIKI_COMPILER_MAX_PASS_RETRIES=2
LLM_WIKI_COMPILER_MAX_AUDIT_ITERATIONS=2
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
3. Inspect the automatically built knowledge graph.
4. Ask grounded questions and inspect citations/evidence.

The graph build command is now an admin rebuild/repair action.

OpenAI file input accepts common document formats including PDF, ODT, DOCX, PPTX,
TXT, Markdown, and spreadsheets. For non-PDF documents such as ODT, the current
ingest path receives extracted text but not embedded images or charts. Convert an
ODT to PDF first when visual layout or embedded media is important evidence.

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

- source status becomes `ingested` or conservative `needs_review`
- `wiki/sources/<source-title>-<source-id>.md` is generated
- ignored runtime `wiki/log.md` gets an ingest entry
- SQLite stores manifests, compiler passes, coverage reports, artifacts, evidence, claims,
  graph state, wiki metadata, and FTS rows
- knowledge graph is built automatically within ingest

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
curl http://127.0.0.1:8020/api/sources/src_your_source_id/compilation

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
- `docs/artifact-first-llm-wiki-foundation.md`
- `docs/llm-wiki-chatbot-solution.md`
- `docs/implementation-architecture-current.md`
- `docs/knowledge-compiler-v2-implementation.md`
- `AGENTS.md`
- `CLAUDE.md`
