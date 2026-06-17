# General LLM Wiki Chatbot: Problem, Technical Solution, Roadmap

## 1. Problem Statement

This project explores a general-purpose chatbot built around the LLM Wiki concept described in `docs/llm-wiki.md`. The goal is not to build another domain-specific RAG chatbot. The goal is to test whether a persistent, compounding, LLM-maintained wiki can answer better than traditional retrieve-at-query-time systems when the corpus grows across many unrelated domains, formats, and document qualities.

The target corpus is intentionally broad:

- Markdown, text, source code, web clips, meeting notes, and general docs.
- Word, PowerPoint, Excel, CSV, TSV, and other office files.
- PDFs, including born-digital PDFs and scanned PDFs.
- Images and other visual material that may contain diagrams, tables, handwriting, screenshots, or text.
- Future mixed-domain corpora where no hard-coded ontology, keyword list, or domain rule should be assumed.

The intended experiment is simple: ingest many heterogeneous documents, let the system build and maintain a persistent markdown wiki, then compare answer quality against more traditional RAG-style retrieval.

## 2. Core Position

The system should be SQLite-first and multimodal-first.

SQLite-first means the first implementation stores operational state, metadata, search indexes, claims, evidence, links, graph edges, jobs, chats, reviews, and eval results directly in SQLite. No external vector database is needed for the MVP. SQLite FTS5, normal relational tables, JSON columns, and careful indexing are enough to build the first useful version.

Multimodal-first means the first ingest path should use LLM/VLM models directly on files and images instead of requiring a mandatory OCR or document parser stage. OCR, PDF layout parsers, Excel parsers, and table extraction libraries remain valuable, but they should be fallback or quality-improvement modules, not mandatory architectural dependencies at the beginning.

This matches the project hypothesis: the main value comes from the LLM/VLM reading sources, extracting durable knowledge, maintaining a wiki, detecting contradictions, and improving the knowledge base over time.

## 3. OpenAI Multimodal Capability Assumption

For the MVP, it is reasonable to use OpenAI multimodal models directly for file and visual ingestion.

The OpenAI file input docs state that the API supports files as model inputs and includes PDFs, spreadsheets, rich documents, presentations, text, and code among supported file categories. The same docs say PDF parsing with text and page images requires vision-capable models such as `gpt-4o` and later models. The image and vision docs also describe image inputs for vision-capable models, including `gpt-4o`.

Practical interpretation for this project:

- PDF and scanned PDF ingestion can start with file input to a vision-capable model. For scanned PDFs, the page images are the useful signal.
- Images can be passed directly as visual inputs.
- Excel and spreadsheet files can be passed as supported file inputs for first-pass understanding, sheet summaries, table detection, schema inference, and claim extraction.
- Deep spreadsheet operations such as formulas, joins, strict aggregation checks, chart recreation, and cell-level audit may later need a parser or sandboxed computation path.
- OCR should not be a hard requirement in the MVP. Add OCR only when evals show a recurring quality gap, cost issue, traceability issue, or need for exact text coordinates.

References:

- `docs/llm-wiki.md`
- https://developers.openai.com/api/docs/guides/file-inputs
- https://developers.openai.com/api/docs/guides/images-vision

## 4. Desired Product Shape

The product should behave like a chatbot, but the chatbot is not the whole system. The chatbot is the conversational interface over a living knowledge base.

Expected user workflows:

- Upload or drop sources into the system.
- Run ingest jobs that read the source, extract knowledge, and update the wiki.
- Ask questions against the wiki and raw evidence.
- Inspect citations and source references.
- Review uncertain merges, contradictions, and high-impact claims.
- Browse the generated wiki in markdown or a web UI.
- Browse the knowledge graph generated from wiki links, entities, claims, and relations.
- Save useful answers back into the wiki so future answers improve.

The first UI can be minimal. The durable architecture should already anticipate a later frontend with chat, upload, job status, wiki browsing, graph browsing, and review queues.

## 5. High-Level Architecture

```text
raw files
  -> source registry in SQLite
  -> multimodal LLM/VLM ingest
  -> extracted evidence, claims, entities, relations
  -> wiki update plan
  -> markdown wiki files
  -> SQLite FTS + graph tables
  -> chatbot retrieval and answer generation
  -> answer citations and optional save-back-to-wiki
```

The system has four durable knowledge layers:

1. Raw sources: immutable files and source metadata.
2. Evidence store: extracted snippets, page references, visual descriptions, table summaries, and provenance.
3. Wiki: human-readable markdown pages maintained by the LLM.
4. Graph: page links, entities, claims, relations, contradictions, and source links stored in SQLite.

The wiki remains the main compounding artifact. SQLite makes it queryable, auditable, and usable by the future backend and frontend.

## 6. Repository and Data Layout

Recommended layout once implementation starts:

```text
raw/
  sources/
  attachments/

wiki/
  index.md
  log.md
  purpose.md
  schema.md
  sources/
  entities/
  concepts/
  events/
  methods/
  datasets/
  claims/
  contradictions/
  synthesis/
  queries/

data/
  app.sqlite
  migrations/
  exports/

backend/
  app/
  tests/

frontend/
  app/
  tests/

docs/
  llm-wiki.md
  llm-wiki-chatbot-solution.md
```

The exact code layout can change when a framework is chosen, but the knowledge layout should remain stable: raw files are immutable, wiki files are generated artifacts with reviewable diffs, and SQLite stores machine-readable state.

## 7. SQLite Data Model

The MVP should start with a compact but expressive schema:

```text
sources
  id, title, source_type, original_path, sha256, mime_type,
  size_bytes, created_at, ingested_at, status

source_versions
  id, source_id, sha256, path, created_at, metadata_json

evidence_items
  id, source_id, locator, modality, text, summary,
  page_number, sheet_name, cell_range, image_ref,
  confidence, created_at, metadata_json

claims
  id, claim_text, normalized_subject, normalized_predicate,
  normalized_object, status, confidence, created_at, updated_at

claim_evidence
  claim_id, evidence_id, support_type, confidence

entities
  id, canonical_name, entity_type, aliases_json,
  description, confidence, created_at, updated_at

relations
  id, subject_entity_id, predicate, object_entity_id,
  claim_id, confidence, status, created_at

wiki_pages
  id, path, title, page_type, summary, sha256,
  created_at, updated_at, frontmatter_json

wiki_links
  from_page_id, to_page_id, link_text, link_type

page_claims
  page_id, claim_id

ingest_jobs
  id, source_id, status, started_at, finished_at,
  model, cost_json, error

review_items
  id, review_type, title, body, status,
  source_id, page_id, claim_id, severity, created_at

conversations
  id, title, created_at, updated_at

messages
  id, conversation_id, role, content, created_at, metadata_json

answer_citations
  message_id, evidence_id, page_id, claim_id, quote, locator

eval_cases
  id, question, expected_behavior, gold_answer,
  source_scope_json, tags_json

eval_runs
  id, case_id, system_variant, answer, metrics_json,
  created_at
```

Use SQLite FTS5 tables for:

- `wiki_pages_fts`: title, summary, body.
- `evidence_fts`: text, summary, locator.
- `claims_fts`: claim text and normalized fields.
- `entities_fts`: canonical names and aliases.

This gives a strong first retrieval layer without adding vector infrastructure. Later, if semantic search becomes a proven bottleneck, a vector index can be added as an implementation detail rather than a conceptual dependency.

## 8. Wiki Page Contract

Every generated wiki page should have YAML frontmatter.

Example:

```md
---
id: page_...
title: Example Concept
type: concept
status: active
created_at: 2026-06-17
updated_at: 2026-06-17
sources:
  - source_...
claims:
  - claim_...
confidence: medium
review_status: unreviewed
---

# Example Concept

## Summary

...

## Key Claims

- ...

## Evidence

- `source_...#page=3`: ...

## Related

- [[Another Concept]]

## Open Questions

- ...
```

Rules:

- Important factual claims need a source or evidence reference.
- Pages should use wikilinks for related entities, concepts, sources, contradictions, and syntheses.
- If evidence is visual, cite the file locator and describe the visual basis.
- If the model is uncertain, create a review item instead of silently merging.
- Derived pages, including saved answers, should clearly say they are generated from prior sources.

## 9. Ingest Workflow

The ingest workflow should be implemented as a transaction-oriented pipeline:

```text
register source
  -> inspect file metadata
  -> call LLM/VLM for structured extraction
  -> store evidence, entities, claims, relations
  -> search existing wiki through SQLite FTS
  -> generate wiki update plan
  -> validate update plan
  -> write markdown files
  -> update page/link/claim tables
  -> append log entry
  -> create review items
```

The LLM/VLM should produce structured outputs, not only prose. A single ingest response should include:

- Source summary.
- Document structure.
- Key entities and aliases.
- Key concepts.
- Events, dates, metrics, methods, datasets, or tables if present.
- Atomic claims with evidence locators.
- Candidate relations.
- Contradictions against known claims if detected.
- Suggested wiki pages to create or update.
- Review items for uncertainty.

For large files, ingest should be chunked by logical units:

- PDF: page ranges or sections.
- Scanned PDF: page image batches.
- Spreadsheet: workbook summary, then per-sheet passes.
- PowerPoint: slide batches.
- Long documents: section batches.

The compiler should then run a synthesis pass over the extracted intermediate state before editing wiki pages.

## 10. Query Workflow

The chatbot should answer from a combination of wiki pages and raw evidence.

```text
user question
  -> classify intent
  -> read purpose/schema/index
  -> retrieve wiki pages with SQLite FTS
  -> retrieve claims/evidence with SQLite FTS
  -> expand graph neighbors
  -> rerank in prompt
  -> answer with citations
  -> optionally save answer into wiki
```

Intent categories:

- Factual lookup.
- Multi-source synthesis.
- Comparison.
- Contradiction check.
- Timeline or evolution question.
- Graph/exploration question.
- Data/table question.
- No-answer or insufficient-evidence question.

For high-risk factual answers, the model should cite raw evidence, not only a wiki page. Wiki pages are useful for synthesis and navigation; raw evidence remains the grounding layer.

## 11. Knowledge Graph

The project can build a knowledge graph naturally from the wiki and extraction pipeline.

Three graph levels should coexist:

```text
Level 1: Wiki graph
  node = markdown page
  edge = wikilink

Level 2: Evidence graph
  node = source, evidence, claim, page
  edge = cites, derived_from, supports, contradicts, supersedes

Level 3: Semantic graph
  node = entity/concept/event/method/dataset
  edge = typed relation extracted from claims
```

All three can live in SQLite initially. A graph database is not required for MVP. The frontend can render graph data from SQLite query results.

The graph should be evidence-aware. A relation without evidence is just a model guess and should be treated as low-confidence or review-only.

## 12. Frontend Direction

The future FE should be an operational knowledge workbench, not a landing page.

Core views:

- Chat view with citations, source cards, and save-to-wiki action.
- Upload and ingest queue view.
- Wiki browser with markdown preview.
- Source viewer with evidence locators.
- Review queue for uncertain claims, duplicate entities, and contradictions.
- Graph view for pages, entities, claims, and relations.
- Eval dashboard comparing system variants.

Recommended frontend stack when implementation starts:

- React or Next.js if SSR/routing is useful.
- A dense, utilitarian layout optimized for repeated knowledge work.
- Graph visualization with a library such as React Flow, Sigma.js, Cytoscape.js, or D3 depending on graph size.
- Playwright tests for the main UI workflows once the frontend exists.

## 13. Backend Direction

Recommended backend stack:

- Python + FastAPI.
- OpenAI SDK with Responses API for multimodal/file input.
- Pydantic models for every structured LLM output.
- SQLite with SQL migrations.
- SQLite FTS5 for retrieval.
- Background job execution for ingest.
- Markdown file writer with deterministic slugs and frontmatter.
- Git optional but useful for wiki diff history.

Keep the orchestration explicit at first. LangChain or LangGraph can be added later if the workflow becomes complex enough to justify it. The early implementation should make prompts, structured schemas, database writes, and wiki diffs easy to audit.

## 14. Evaluation Plan

The system should be evaluated against several variants:

```text
A. Raw-only SQLite FTS retrieval
B. Wiki-only retrieval
C. Wiki + raw evidence retrieval
D. Wiki + raw evidence + graph expansion
```

If a vector database is added later, it should become another variant, not the baseline assumption.

Evaluation question types:

- Single-source factual.
- Multi-source synthesis.
- Contradiction detection.
- Entity disambiguation.
- Timeline and change-over-time.
- Table/numeric reasoning.
- Scanned PDF or image-grounded question.
- No-answer / insufficient evidence.
- Cross-domain broad synthesis.

Metrics:

- Correctness.
- Faithfulness to evidence.
- Citation precision.
- Citation recall.
- Contradiction handling.
- Multi-hop coverage.
- Latency.
- Ingest cost.
- Query cost.
- Human review load.
- Wiki drift and stale claim rate.

The key comparison is not just answer quality at one moment. The experiment should measure whether the wiki compounds: after more ingests and saved answers, does the system answer synthesis questions better with lower query-time work?

## 15. Roadmap

### Phase 1: Foundation and Knowledge Contract

Build the basic repository structure, SQLite schema, markdown wiki conventions, and prompt contracts.

Expected outcomes:

- `raw/`, `wiki/`, and `data/` conventions are established.
- SQLite schema supports sources, evidence, claims, entities, relations, pages, links, jobs, chats, and evals.
- `wiki/index.md`, `wiki/log.md`, `wiki/purpose.md`, and `wiki/schema.md` exist.
- Ingest and query prompt schemas are defined with Pydantic models.
- SQLite FTS works over wiki pages and evidence.

Evaluation:

- Can register a source and store deterministic metadata.
- Can create/update a wiki page with valid frontmatter.
- Can search wiki/evidence through SQLite FTS.
- Can produce a citation-bearing answer from hand-seeded evidence.

### Phase 2: Multimodal Ingest and Wiki Compiler

Implement first-pass ingest using LLM/VLM directly on files.

Expected outcomes:

- Ingest supports at least PDF, image, markdown/text, and spreadsheet files through the OpenAI multimodal/file input path.
- The model returns structured source summaries, evidence items, claims, entities, relations, and review items.
- The wiki compiler creates source pages and updates entity/concept pages.
- Contradictions and uncertain merges become review items.
- The system appends consistent entries to `wiki/log.md`.

Evaluation:

- Ingest 20-50 mixed-format files and inspect wiki quality manually.
- Measure claim citation coverage.
- Track extraction failures by file type.
- Compare direct VLM ingest against optional manual extraction for a small scanned-PDF sample.

### Phase 3: Chatbot, Review, Graph, and Frontend

Turn the backend into an interactive system.

Expected outcomes:

- Chatbot answers from wiki + raw evidence + graph expansion.
- Answers include citations to source/evidence/wiki pages.
- Useful answers can be saved back into `wiki/queries/` or `wiki/synthesis/`.
- Review queue supports duplicate entities, low-confidence claims, and contradictions.
- Basic frontend supports chat, uploads, ingest status, wiki preview, source evidence, review queue, and graph view.

Evaluation:

- Run the same question set against raw-only FTS, wiki-only, wiki+raw, and wiki+raw+graph.
- Track answer correctness, citation precision, latency, and user review effort.
- Confirm graph navigation reveals useful cross-source connections.

### Phase 4: Scale, Quality Gates, and Optional Specialized Parsers

Harden the system after real corpus pressure exposes failure modes.

Expected outcomes:

- Batch ingest is reliable and resumable.
- Incremental re-ingest uses file hashes and source versions.
- Lint jobs detect orphan pages, broken links, stale claims, duplicate entities, missing citations, and unresolved contradictions.
- Optional OCR, document parsing, spreadsheet parsing, or table extraction modules can be enabled per source type when direct VLM quality is insufficient.
- Evaluation dashboard tracks regression across corpus versions.

Evaluation:

- Ingest hundreds to thousands of mixed files.
- Measure cost and latency trends.
- Measure wiki drift and stale claim rates.
- Decide from evidence whether to add OCR/parser/vector DB components.

## 16. Design Decisions for MVP

Use SQLite, not a vector DB.

Use OpenAI multimodal/file input directly, not mandatory OCR.

Use markdown wiki files as first-class artifacts, not just database rows.

Use structured LLM outputs for extraction and update plans.

Use raw evidence citations for important factual answers.

Use review queues for uncertainty instead of silently trusting the model.

Keep the ontology general. Allow domain-specific pages and relations to emerge, but do not hard-code a fixed domain taxonomy.

## 17. Expected Final Outcome

The expected outcome is a general chatbot that accumulates knowledge over time:

- It can ingest heterogeneous files without a domain-specific parser-first pipeline.
- It maintains a readable, Obsidian-compatible wiki.
- It builds an evidence-backed knowledge graph.
- It answers with citations and can save valuable answers back into the wiki.
- It supports evaluation against traditional retrieval approaches.
- It exposes enough review and linting tools to keep the wiki from drifting into ungrounded summaries.

The success condition is not that the system never uses OCR, vector search, or specialized parsers. The success condition is that those components are added only when evaluation proves they solve a real bottleneck.
