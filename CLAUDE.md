# CLAUDE.md

## Project Brief

This repository is for a general-purpose chatbot based on the LLM Wiki pattern. The system should incrementally build and maintain a persistent markdown wiki from heterogeneous sources, then answer questions using that wiki plus source-grounded evidence.

Primary references:

- `docs/llm-wiki.md`
- `docs/artifact-first-llm-wiki-foundation.md`
- `docs/llm-wiki-chatbot-solution.md`
- `docs/implementation-architecture-current.md`
- `docs/knowledge-compiler-v2-implementation.md`

The core experiment is to compare a compounding LLM-maintained wiki against traditional RAG, especially for broad multi-domain corpora and synthesis-heavy questions.

## Non-Negotiable MVP Direction

- SQLite-first.
- Multimodal-first.
- Markdown-wiki-first.
- Evidence-backed claims.
- Domain-agnostic ontology.
- Human review for uncertainty.
- LLM-driven source profiling and compilation planning.
- Artifact-first retrieval with source re-inspection.

Do not introduce an external vector database by default. Store artifact embeddings in
SQLite first and keep FTS for exact artifact/wiki retrieval.

Do not make OCR, PDF parsing libraries, Excel parsing libraries, or table extraction libraries mandatory in the first ingest path. The first ingest path should use LLM/VLM multimodal and file input directly. Specialized parsers can be added later as optional fallback modules after evaluation.

Do not hard-code domain taxonomies, keyword routing, section recognizers, document
structures, or fixed raw-token chunking. Source manifests, compilation plans, artifact
types, and semantic relations are inferred by LLM/VLM through open structured contracts.

## System Layers

The implementation should preserve these layers:

```text
raw sources
  -> multimodal source profiling
  -> source manifest and dynamic compilation plan
  -> multi-pass evidence and artifact compilation
  -> wiki and graph integration
  -> coverage audit and semantic indexing
  -> artifact-first query with LLM navigation
  -> optional source re-inspection
  -> grounded answer with citations
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

Frontend:

- React or Next.js.
- Operational dashboard style, not a landing page.
- Implemented views cover chat, uploads, source ingest, source evidence, graph, and contradictions.
- Evaluation dashboard remains deferred until representative data exists.

## Ingest Workflow

Implement ingest as a resumable staged job:

1. Register source metadata and content hash.
2. Let LLM/VLM profile the source and infer its structure/modalities.
3. Generate a dynamic compilation plan with source-local content unit IDs.
4. Run model-directed passes to create evidence and open-type artifacts.
5. Match candidates semantically against existing artifacts/wiki.
6. Validate and integrate artifacts and deterministic markdown pages.
7. Build/update provenance and semantic graph in the same ingest pipeline.
8. Run coverage audit and follow-up compilation when required.
9. Update artifact FTS, embeddings, knowledge maps, and wiki log.

For files beyond provider/context limits, physical batching is a transport concern:

- Use natural provider boundaries such as pages, slides, sheets, images, or model-inferred
  source units.
- Do not turn these batches into the primary retrieval corpus.
- Run a global synthesis/coverage pass after batch processing.

## Query Workflow

Chat answers should retrieve compiled knowledge through:

- LLM semantic probes and hierarchical knowledge-map navigation.
- Artifact embeddings stored in SQLite.
- Artifact/wiki FTS for exact retrieval.
- Graph expansion from semantically selected artifact seeds.
- LLM reranking and structured context assembly.

Important answers need citations. If the available evidence is insufficient, answer that the system does not have enough evidence instead of inventing.

Before returning insufficient, detect whether likely sources can be reopened. Source
re-inspection should compile missing artifacts and retry the answer when budget permits.
Never attach a fallback citation that does not support the answer.

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

Graph creation/update belongs to ingest. The graph build command remains a maintenance,
repair, or explicit rebuild operation.

## Evaluation Requirements

Keep the system evaluable against these variants:

- Raw-only SQLite FTS.
- Wiki-only.
- Wiki plus raw evidence.
- Wiki plus raw evidence plus graph expansion.

Measure correctness, faithfulness, citation quality, contradiction handling, latency, cost, review burden, and wiki drift.

## Current Repo State

The repository currently implements Knowledge Compiler V2: LLM-generated source
manifests, dynamic multi-pass compilation, open artifacts, source-local evidence IDs,
coverage audit/follow-up, pass retry, and automatic graph build inside ingest. Embedding
is deferred to the semantic retrieval phase; SQLite artifact FTS is already present.

## Project Commands

Use `uv` as the preferred local runner:

- Install/sync dependencies: `uv sync --extra dev`
- Run API: `uv run python -m backend.app.cli serve --reload`
- Run migrations: `uv run python -m backend.app.cli db migrate`
- Register a source: `uv run python -m backend.app.cli sources register raw/sources/example.pdf --title "Example PDF" --type pdf`
- Ingest a source: `uv run python -m backend.app.cli sources ingest src_your_source_id`
- Ask a query: `uv run python -m backend.app.cli query ask "How is LLM Wiki different from traditional RAG?"`
- Ask a query as JSON: `uv run python -m backend.app.cli query ask "How is LLM Wiki different from traditional RAG?" --json`
- Build graph: `uv run python -m backend.app.cli graph build`
- Search graph: `uv run python -m backend.app.cli graph search "LLM Wiki"`
- Inspect entity graph: `uv run python -m backend.app.cli graph inspect "LLM Wiki" --json`
- List graph contradictions: `uv run python -m backend.app.cli graph contradictions`
- Install frontend: `cd frontend && pnpm install`
- Run frontend: `cd frontend && pnpm dev`
- Test frontend: `cd frontend && pnpm test`
- Lint frontend: `cd frontend && pnpm lint`
- Build frontend: `cd frontend && pnpm build`
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
