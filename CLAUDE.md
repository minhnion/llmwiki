# CLAUDE.md

## Project Brief

This repository is for a general-purpose chatbot based on the LLM Wiki pattern. The system should incrementally build and maintain a persistent markdown wiki from heterogeneous sources, then answer questions using that wiki plus source-grounded evidence.

Primary references:

- `docs/llm-wiki.md`
- `docs/llm-wiki-chatbot-solution.md`

The core experiment is to compare a compounding LLM-maintained wiki against traditional RAG, especially for broad multi-domain corpora and synthesis-heavy questions.

## Non-Negotiable MVP Direction

- SQLite-first.
- Multimodal-first.
- Markdown-wiki-first.
- Evidence-backed claims.
- Domain-agnostic ontology.
- Human review for uncertainty.

Do not introduce an external vector database by default. Use SQLite tables and SQLite FTS5 first.

Do not make OCR, PDF parsing libraries, Excel parsing libraries, or table extraction libraries mandatory in the first ingest path. The first ingest path should use LLM/VLM multimodal and file input directly. Specialized parsers can be added later as optional fallback modules after evaluation.

## System Layers

The implementation should preserve these layers:

```text
raw sources
  -> multimodal ingest
  -> evidence, claims, entities, relations
  -> wiki update plan
  -> markdown wiki
  -> SQLite FTS and graph tables
  -> chatbot answer with citations
  -> optional save-back-to-wiki
```

Raw sources are immutable. The wiki is generated and maintained by the model. SQLite stores operational state, search data, provenance, graph edges, review items, conversations, and evals.

## Recommended Stack

Backend:

- Python.
- FastAPI.
- OpenAI SDK with Responses API for multimodal/file input.
- Pydantic for structured model outputs.
- SQLite with migrations.
- SQLite FTS5.
- Background jobs for ingest.

Frontend, when added:

- React or Next.js.
- Operational dashboard style, not a landing page.
- Views for chat, uploads, ingest queue, wiki browser, source evidence, review queue, graph, and evals.

## Ingest Workflow

Implement ingest as a resumable job:

1. Register source metadata and content hash.
2. Send the file or file segment to a multimodal model.
3. Extract structured source summary, evidence, claims, entities, relations, contradictions, and review items.
4. Search existing wiki and claim/entity state through SQLite FTS.
5. Generate a wiki update plan.
6. Validate the plan.
7. Write deterministic markdown pages.
8. Update SQLite tables.
9. Append to wiki log.

For large documents, process logical batches:

- PDF by page range or section.
- Scanned PDF by page image batches.
- Spreadsheet by workbook summary and sheet-level passes.
- Slide deck by slide batches.
- Long document by section.

## Query Workflow

Chat answers should retrieve from multiple local layers:

- `wiki/index.md`, `wiki/schema.md`, and relevant wiki pages.
- SQLite FTS evidence.
- SQLite FTS claims and entities.
- Graph neighbors from page/entity/relation tables.

Important answers need citations. If the available evidence is insufficient, answer that the system does not have enough evidence instead of inventing.

Useful answers may be saved into `wiki/queries/` or `wiki/synthesis/` and treated as derived wiki artifacts.

## Wiki Page Requirements

Generated wiki pages should use YAML frontmatter with stable fields when possible:

- `id`
- `title`
- `type`
- `status`
- `created_at`
- `updated_at`
- `sources`
- `claims`
- `confidence`
- `review_status`

Body sections should usually include summary, key claims, evidence, related pages, contradictions if any, and open questions.

Use wikilinks for related pages. Do not silently merge ambiguous entities. Create review items instead.

## Knowledge Graph Requirements

Start with SQLite graph tables. A graph database is not required for MVP.

Represent at least:

- Page-to-page wikilinks.
- Source-to-evidence provenance.
- Claim-to-evidence support.
- Entity/relation triples with claim evidence.
- Contradicts and supersedes links.

Every semantic relation should have evidence or be marked low-confidence/review-only.

## Evaluation Requirements

Keep the system evaluable against these variants:

- Raw-only SQLite FTS.
- Wiki-only.
- Wiki plus raw evidence.
- Wiki plus raw evidence plus graph expansion.

Measure correctness, faithfulness, citation quality, contradiction handling, latency, cost, review burden, and wiki drift.

## Current Repo State

This repository currently has a Python/FastAPI backend scaffold, SQLite-first project layout, placeholder frontend folder, and generated wiki/raw/data directories.

## Project Commands

Use `uv` as the preferred local runner:

- Install/sync dependencies: `uv sync --extra dev`
- Run API: `uv run python -m backend.app.cli serve --reload`
- Run migrations: `uv run python -m backend.app.cli db migrate`
- Register a source: `uv run python -m backend.app.cli sources register raw/sources/example.pdf --title "Example PDF" --type pdf`
- Ingest a source: `uv run python -m backend.app.cli sources ingest src_your_source_id`
- Run tests: `uv run --extra dev pytest`
- Run lint: `uv run --extra dev ruff check .`
- Compile check: `python3 -m compileall backend`

If `uv` is unavailable, use `python3 -m venv .venv`, activate it, then run `pip install -e ".[dev]"`. This fallback requires `python3-venv` on Debian/Ubuntu systems.

## Development Conduct

- Keep architecture decisions aligned with the docs.
- Keep changes small and reviewable.
- Prefer explicit, auditable pipelines over opaque orchestration.
- Do not hard-code a domain.
- Do not treat the wiki as a disposable cache.
- Preserve provenance and citations at every step.
