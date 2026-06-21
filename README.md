# LLM Wiki Agent

A general-purpose knowledge and chatbot foundation based on the LLM Wiki
pattern.

Instead of embedding arbitrary raw chunks and reconstructing knowledge for each
question, an LLM/VLM incrementally maintains a persistent Markdown wiki. The
wiki becomes the durable knowledge product; raw sources remain immutable
evidence.

## Architecture

```text
raw source + current wiki
        |
        v
Wiki Agent understands the source
        |
        v
Wiki Agent creates or updates pages
        |
        v
validation + controlled commit
        |
        v
Markdown wiki + SQLite provenance/search state
```

Semantic decisions belong to the model. Code supplies generic tools and
enforces integrity, provenance, persistence, budgets, and safe execution.

See:

- `docs/llm-wiki.md`
- `docs/guide_llm_wiki_nashu.md`
- `docs/wiki-agent-architecture.md`
- `docs/roadmap.md`
- `docs/evaluation.md`

## Current Reset

The previous multi-pass Knowledge Compiler and fixed retrieval assembly line
were removed from the core. The repository now provides a clean Wiki Agent
foundation:

- Source registration with content hashing and mutation detection.
- Markdown wiki store.
- SQLite page/provenance/operation state and FTS.
- Two-phase agentic ingest: understand, then maintain.
- Agentic query foundation with wiki search and optional source inspection.
- Review and telemetry contracts.

Advanced embeddings, graph analytics, OCR, specialized parsers, and semantic
lint remain optional future modules driven by evaluation.

## Setup

```bash
uv sync --extra dev
cp .env.example .env
uv run python -m backend.app.cli db migrate
uv run python -m backend.app.cli serve --reload
```

Frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

## CLI

```bash
uv run python -m backend.app.cli sources register raw/sources/example.pdf \
  --title "Example"

uv run python -m backend.app.cli sources ingest src_your_source_id

uv run python -m backend.app.cli query ask \
  "What does the wiki say about this topic?" --json

uv run python -m backend.app.cli wiki rebuild
```

## Validation

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
python3 -m compileall backend

cd frontend
pnpm test
pnpm lint
pnpm build
```

## Non-Goals

- Domain-specific mappings, taxonomies, keyword routers, or semantic regexes.
- Fixed raw chunk retrieval as the core.
- A mandatory external vector database.
- A large chain of profiler/compiler/auditor/reranker services.
- Optimizing the architecture around one test document.
