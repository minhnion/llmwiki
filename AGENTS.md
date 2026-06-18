# AGENTS.md

## Project Context

This repository is for a general-purpose LLM Wiki chatbot inspired by `docs/llm-wiki.md`.

The project goal is to test whether a persistent, LLM-maintained markdown wiki plus SQLite-backed evidence/claim/graph state can outperform traditional retrieve-at-query-time RAG on broad, heterogeneous corpora.

Read these files before making architecture or implementation decisions:

- `docs/llm-wiki.md`
- `docs/artifact-first-llm-wiki-foundation.md`
- `docs/llm-wiki-chatbot-solution.md`
- `docs/implementation-architecture-current.md`

## Durable Architecture Decisions

- Use SQLite as the primary storage layer for the MVP.
- Do not add an external vector database unless the user explicitly asks or evaluation proves SQLite FTS is insufficient.
- Build toward artifact-first retrieval with LLM semantic navigation, artifact embeddings,
  artifact/wiki FTS, graph expansion, and LLM reranking.
- Treat markdown wiki files as first-class generated artifacts, not secondary exports.
- Keep raw sources immutable.
- Use LLM/VLM multimodal ingest directly for the MVP.
- Do not make OCR, PDF parsers, Excel parsers, or document-layout libraries mandatory in the first implementation.
- OCR and specialized parsers are optional fallback modules after evaluation shows a quality, cost, or auditability gap.
- Keep the ontology domain-agnostic. Do not hard-code a domain taxonomy, keyword list, or business-specific entity schema.
- Do not use fixed raw chunks or overlapping token windows as the primary retrieval corpus.
- Do not hard-code document structures, section recognizers, domain regexes, or keyword routing.
- Source structure, compilation passes, artifact types, and relation types should be
  inferred by LLM/VLM through open structured contracts.
- Treat graph integration, contradiction detection, coverage audit, and semantic indexing
  as stages of ingest. Manual graph build is a maintenance/rebuild action, not the target user flow.

## Knowledge Model

Preserve these layers:

- Raw sources: immutable user-provided files.
- Evidence: source-grounded snippets, visual descriptions, table summaries, page/sheet/cell locators.
- Claims: atomic factual statements linked to evidence.
- Artifacts: open-type, machine-addressable knowledge units linked to evidence.
- Wiki: markdown pages with frontmatter, wikilinks, summaries, synthesis, contradictions, and open questions.
- Graph: SQLite tables for page links, entities, claims, relations, contradictions, and provenance.

Important factual answers must cite raw evidence or source-backed wiki pages. Do not allow uncited high-impact claims to silently enter the wiki.

## Wiki Rules

- Every generated wiki page should have YAML frontmatter.
- Include stable page type, title, status, sources, claims, confidence, and timestamps when possible.
- Use wikilinks for related pages.
- Create review items for uncertain merges, duplicate entities, contradictions, and low-confidence claims.
- Append ingest/query/graph/lint actions to `wiki/log.md` once that file exists.
- Keep `wiki/index.md` content-oriented and updated after ingest.

## Implementation Guidance

- Prefer Python + FastAPI for the backend unless the user chooses otherwise.
- Prefer the OpenAI Responses API for multimodal/file input.
- Use Pydantic models for structured LLM outputs.
- Keep LLM prompts and schemas versioned in the repo.
- Make ingest jobs resumable and transaction-oriented.
- Implement ingest as source profiling, dynamic compilation planning, multi-pass knowledge
  compilation, artifact/wiki/graph integration, coverage audit, and semantic indexing.
- Use unique evidence IDs in extraction contracts; never use a non-unique locator string
  as the identity joining claims to evidence.
- Keep file writes deterministic: stable slugs, stable frontmatter fields, stable ordering.
- Use migrations for SQLite schema changes once code exists.
- Avoid introducing heavy orchestration frameworks until the local workflow is too complex to manage explicitly.

## Retrieval Guidance

Target retrieval should combine:

- LLM-generated semantic probes and hierarchical navigation through knowledge maps.
- Semantic search over generated artifacts, with vectors stored in SQLite initially.
- SQLite FTS over artifacts/wiki for exact names, identifiers, dates, numbers, and phrases.
- Graph expansion from selected artifact seeds.
- LLM reranking, context assembly, and grounding validation.
- Direct source re-inspection when compiled artifacts are incomplete or require verification.

Do not vector-search arbitrary raw chunks in the core path. Raw sources may be reopened
by provenance pointer or source manifest for verification and on-demand recompilation.

## Evaluation Guidance

Preserve the ability to compare:

- Raw-only SQLite FTS retrieval.
- Wiki-only retrieval.
- Wiki plus raw evidence.
- Wiki plus raw evidence plus graph expansion.

Track correctness, faithfulness, citation precision, contradiction handling, latency, ingest cost, query cost, human review load, and wiki drift.

## Frontend Guidance

When a frontend is added, build the actual knowledge workbench, not a marketing landing page.

Implemented views cover upload and ingest, source-scoped chat with citations and
evidence trace, graph visualization/entity inspection, and contradiction review.
Wiki browsing, a general review queue, and evaluation dashboard remain deferred.

Keep the UI dense, operational, and suitable for repeated knowledge work.

## Current Repo State

The repository currently has a Python/FastAPI backend plus a React/Vite/Tailwind
workbench. The UI supports HTTP upload, ingest, source scoping, grounded chat with
citations/evidence trace, knowledge graph build/visualization, entity inspection,
and contradiction review. The repository has no default source seed; runtime sources
are user-managed and may be present locally. Ingest and answer prompts preserve the
source/question language, with Vietnamese configured as the fallback language.

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

## Collaboration Rules

- Keep changes scoped to the user's request.
- Do not remove user-created files or unrelated local changes.
- Explain architecture tradeoffs in terms of this project's experiment: persistent wiki versus traditional RAG.
- If a requested change conflicts with the durable decisions above, call out the tradeoff and ask only when proceeding would be risky.
