# AGENTS.md

## Project

This repository builds a general-purpose Wiki Agent inspired by
`docs/llm-wiki.md`.

The experiment is whether an LLM-maintained, persistent Markdown wiki can
accumulate useful knowledge and outperform retrieve-from-raw RAG on broad,
heterogeneous corpora.

Read before architecture or implementation work:

- `docs/llm-wiki.md`
- `docs/guide_llm_wiki_nashu.md`
- `docs/wiki-agent-architecture.md`
- `docs/roadmap.md`
- `docs/evaluation.md`

## Core Model

```text
immutable raw sources
        |
        v
Wiki Agent reads source + current wiki
        |
        v
creates and updates Markdown pages
        |
        v
deterministic validation and commit
        |
        v
SQLite indexes operational state and provenance
```

Markdown wiki pages are the primary semantic knowledge product. SQLite is the
control, provenance, search, and audit layer. It must not become a second,
competing ontology.

The three core operations are:

- Ingest: integrate a source into the existing wiki.
- Query: search/read the wiki, inspect sources when needed, and answer with
  citations.
- Lint: maintain links, provenance, consistency, duplication, contradictions,
  and stale knowledge.

## Responsibility Boundary

LLM/VLM decides meaning:

- What a source means and what matters.
- Which existing pages are relevant.
- Whether to create, update, link, qualify, contradict, or request review.
- Page granularity, page type, relations, and useful synthesis.
- Whether more wiki/source inspection is needed.

Deterministic code guarantees integrity:

- Immutable raw files, hashes, stable IDs, and safe paths.
- Tool authorization, budgets, retries, caching, and resumability.
- Parseable frontmatter and valid source/page references.
- No dangling wikilinks or stale index entries after commit.
- Atomic/recoverable Markdown and SQLite updates.
- Search execution, audit logs, telemetry, and migrations.

Code must not decide domain meaning.

## Forbidden Semantic Hard-Coding

Do not add:

- Domain taxonomies, business schemas, or fixed entity/relation types.
- Keyword routing, domain synonym tables, or semantic regex rules.
- Fixed document section recognizers.
- Rules such as “repeated subject means entity”.
- Mandatory page categories for all corpora.
- Fixed raw chunks or overlapping token windows as the primary knowledge or
  retrieval corpus.
- Fixed graph relevance weights presented as universal semantics.
- A new pipeline stage merely to compensate for one test document.

Syntax parsing, path validation, FTS escaping, file-size limits, and other
infrastructure rules are allowed.

## Architecture Rules

- Prefer one Wiki Agent runtime with a small generic tool set over many
  specialized semantic services.
- Normal ingest is two logical model phases: understand, then maintain.
- Current query combines LLM catalog selection, model-generated FTS searches,
  full-page reading, and optional raw-source inspection.
- Build phase 2 toward a bounded iterative search/read/follow-link loop.
- Critique, deep audit, embeddings, graph analysis, OCR, and specialized
  parsers are optional modules activated by evaluation or explicit policy.
- Do not add an external vector database unless the user explicitly requests it
  or evaluation demonstrates that SQLite is inadequate.
- Keep prompts and structured tool contracts versioned and small.
- Keep Markdown files human-readable and Obsidian-compatible.
- Preserve existing source provenance when a page is updated.
- Ambiguous merges and contradictions become review items, not silent guesses.

## Wiki Foundation

The base wiki contains:

```text
wiki/
  purpose.md
  schema.md
  index.md
  overview.md
  log.md
  pages/
  sources/
  queries/
  reviews/
```

These directories are lifecycle containers, not a domain ontology. Page
`type` remains an open string selected by the LLM.

## Evaluation

Never optimize against one document. Representative evaluation must cover
multiple domains, formats, languages, contradictions, synthesis questions, and
no-answer cases.

Track at least:

- Answer correctness and faithfulness.
- Citation precision.
- Cross-source integration quality.
- Duplicate/stale/broken wiki state.
- Ingest and query model calls, tokens, cost, and latency.
- Human review burden.
- Wiki improvement after later ingest/query operations.

## Stack and Commands

- Python, FastAPI, Pydantic, OpenAI Responses API.
- SQLite and FTS5.
- React, TypeScript, Vite.

Commands:

```bash
uv sync --extra dev
uv run python -m backend.app.cli db migrate
uv run python -m backend.app.cli serve --reload
uv run --extra dev pytest
uv run --extra dev ruff check .
python3 -m compileall backend

cd frontend
pnpm install
pnpm test
pnpm lint
pnpm build
```

## Collaboration

- Keep changes aligned with `docs/wiki-agent-architecture.md`.
- Preserve raw user sources unless deletion is explicitly requested.
- Do not restore the legacy compiler pipeline under a new name.
- Prefer deleting obsolete abstractions over maintaining parallel
  representations.
- Explain tradeoffs in terms of the persistent-wiki experiment.
