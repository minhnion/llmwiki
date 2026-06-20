# Wiki Agent Architecture

## 1. Objective

Build a domain-agnostic foundation where an LLM/VLM incrementally creates and
maintains a persistent Markdown wiki from heterogeneous sources.

The system tests a different hypothesis from traditional RAG:

> Useful knowledge should be integrated once into a living wiki and improved
> over time, rather than reconstructed from raw chunks for every question.

The architecture should stay close to the original LLM Wiki pattern and use
modern models as agents with tools.

## 2. Principles

### 2.1 The wiki is the semantic product

Markdown pages contain the maintained knowledge: summaries, concepts,
comparisons, entities, procedures, contradictions, open questions, and
synthesis. SQLite mirrors only the fields needed for search, provenance,
operations, and validation.

### 2.2 One semantic decision-maker

The Wiki Agent decides:

- What matters in a source.
- Which pages to inspect.
- Which pages to create or update.
- How knowledge should be grouped and linked.
- Whether new evidence supports, qualifies, or conflicts with existing pages.
- When uncertainty needs human review.

The backend must not reproduce these decisions through domain rules or a chain
of specialized semantic services.

### 2.3 Code enforces integrity, not meaning

Deterministic code owns:

- Source immutability and hashing.
- Stable identifiers and safe paths.
- Tool permissions and execution budgets.
- Frontmatter, citation, source-reference, and wikilink validation.
- Recoverable Markdown/SQLite commits.
- FTS indexing, telemetry, cache, jobs, and audit logs.

### 2.4 General-purpose by construction

Page types and relation labels are open strings. Directory names do not define
a domain ontology. No document format is assumed to have a particular semantic
structure.

### 2.5 Complexity must be earned

Embeddings, OCR, parsers, graph analytics, additional model passes, and
specialized indexes are optional. Add them only when evaluation identifies a
measurable gap.

## 3. Durable Layers

```text
Raw Sources
  Immutable user files and source metadata.

Markdown Wiki
  Primary LLM-maintained knowledge product.

SQLite Control Plane
  Sources, page catalog, provenance, links, operations, reviews, query traces,
  telemetry, and FTS.

Wiki Agent Runtime
  Generic read/search/source-inspection/change/review tools.
```

There is no mandatory artifact/claim/entity/graph pipeline between source and
wiki.

## 4. Minimal Data Model

### Source

```text
id, path, title, type, hash, status, timestamps, metadata
```

### Wiki page

```yaml
---
id: page_...
title: ...
type: model-selected-open-string
status: active
sources:
  - source_id: src_...
    evidence:
      - locator: ...
        quote_or_summary: ...
confidence: 0.9
created_at: ...
updated_at: ...
---
```

The page body is free Markdown owned by the agent.

### Review item

Used for uncertain identity, merge, contradiction, missing evidence, or another
issue the agent cannot safely resolve.

### Operation

Records an ingest, query, lint, or maintenance run:

- Inputs and sources.
- Pages read and changed.
- Validation result.
- Model, prompts, tokens, cost, and latency.
- Error or completion status.

## 5. Generic Agent Tools

The semantic runtime exposes a small tool surface:

```text
read_purpose
read_schema
read_index
list_pages
search_wiki
read_page
follow_links
inspect_source
propose_page_changes
create_review
validate_changes
commit_changes
```

Search can use FTS, embeddings, or another implementation internally. The agent
does not depend on the search technology.

Write tools operate on structured page drafts. The backend renders frontmatter,
validates references, stages files, commits them, and refreshes SQLite.

## 6. Ingest

Normal ingest has two logical model phases.

### Understand

Inputs:

- Raw source.
- `purpose.md`, `schema.md`, and compact wiki catalog.

Output:

- Concise source understanding.
- Wiki search requests.
- Suspected connections, conflicts, and uncertainties.

This is a decision brief, not stored chain-of-thought.

### Maintain

The backend executes the requested searches and gives relevant full pages to
the model. The model returns a change set:

- Create/update/delete page drafts.
- Source evidence references.
- Wikilinks and related pages.
- Review items.
- Optional overview update.

The backend validates and commits the change set.

Critique is conditional: validation failure, explicit uncertainty, difficult
source policy, evaluation sampling, or user request. It is not a mandatory
full-source coverage loop.

## 7. Query

The current query foundation:

1. Reads purpose, overview, index, and a compact page/source catalog.
2. Selects page IDs semantically and issues additional model-generated FTS
   searches.
3. Reads the selected full pages.
4. Inspects raw sources when citations require verification or the wiki is
   incomplete.
5. Answers with page/source evidence citations.
6. Deterministically rejects citations to unavailable pages, sources, or
   evidence locators.

Phase 2 turns this into an iterative search/read/follow-link loop and can save
reusable synthesis through the normal validated change path.

`fast`, `deep`, and `audit` are budget/verification policies, not separate
semantic pipelines.

## 8. Lint

The Lint Agent periodically inspects:

- Broken or orphaned links.
- Duplicate or overlapping pages.
- Stale summaries.
- Unsupported high-impact statements.
- Contradictions and unresolved review items.
- Missing cross-links and useful synthesis opportunities.

Deterministic checks find syntactic/integrity errors. The LLM handles semantic
maintenance.

## 9. Search and Graph

Initial retrieval is SQLite FTS over complete wiki pages and metadata.

Optional semantic embeddings index pages or model-selected semantic sections,
never arbitrary fixed raw chunks as the primary corpus.

The core graph is derived from:

- Wikilinks.
- Page-to-source provenance.
- Explicit open relations recorded by the agent when useful.

Advanced graph extraction or clustering is optional and must not block ingest.

## 10. Commit and Recovery

Every write operation follows:

```text
structured change set
  -> stage files
  -> validate frontmatter, sources, citations, IDs, and links
  -> record operation journal
  -> atomically replace files
  -> refresh SQLite page/link/FTS state
  -> rebuild deterministic index
  -> mark operation complete
```

SQLite indexes must be rebuildable from the Markdown wiki. The wiki must never
contain stale index entries or dangling generated links after a successful
commit.

## 11. Explicit Non-Goals

- Reconstructing a domain ontology in backend code.
- Guaranteeing every possible future question is precompiled during ingest.
- Treating graph size, artifact count, or vector count as knowledge quality.
- Building a mandatory parser-first document ETL system.
- Splitting model cognition into many fixed services.
- Optimizing against one sample document.
