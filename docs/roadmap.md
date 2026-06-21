# Wiki Agent Roadmap

This roadmap is organized by architectural modules. A module is accepted only
when it improves the general-purpose system on a heterogeneous evaluation set.

## Completed — Architecture Reset

The repository has one current architecture:

- Markdown is the maintained knowledge product.
- SQLite stores source, provenance, search, review, operation, and telemetry
  state.
- The LLM/VLM owns semantic decisions through open structured contracts.
- The legacy compiler, artifact, fixed graph, and retrieval assembly pipeline
  has been removed.
- The database and generated wiki were reset to a clean foundation.

The initial runtime now provides:

- Hash-verified source registration.
- Open-type wiki pages with evidence references.
- LLM catalog navigation plus SQLite FTS.
- Two-call ingest: understand, then maintain.
- Query planning, full-page retrieval, optional raw-source inspection, answer
  generation, and citation grounding.
- A source/chat/wiki workbench.

## Phase 1 — Wiki Maintenance Quality

Purpose: make the simple ingest path reliable before adding retrieval
infrastructure.

Scope:

- Improve prompts and change contracts for cross-source updates, duplicate
  avoidance, qualification, contradiction, and uncertainty.
- Make multi-page writes staged and recoverable after interruption.
- Add source re-ingest/version behavior without mutating prior evidence.
- Add conditional model critique only for risky or sampled changes.
- Expose review items and deterministic integrity lint.
- Evaluate page usefulness, unsupported statements, duplicates, broken links,
  cross-source updates, model calls, tokens, and latency.

Exit criteria:

- A later source reliably enriches or qualifies an existing page.
- Uncertain identity and contradiction are surfaced instead of silently merged.
- Failed writes can be resumed or rolled back without corrupting the wiki.
- Quality holds across domains, formats, and languages.
- Extra model calls are justified by measured quality gains.

## Phase 2 — Semantic Navigation and Query Quality

Purpose: improve recall while keeping the wiki—not raw chunks—as the primary
retrieval corpus.

Scope:

- Turn query retrieval into an iterative model-operated search/read loop.
- Let the model reformulate after a miss and selectively follow wikilinks.
- Add direct source recovery when the wiki is incomplete.
- Evaluate page-level embeddings stored in SQLite as an optional search tool.
- Add LLM reranking only when candidate noise measurably hurts answers.
- Save valuable query synthesis through the same validated wiki change path.
- Compare fast, deep, and audit as budget policies over one agent.

Exit criteria:

- Semantic paraphrases retrieve the right knowledge without keyword rules.
- Initial search misses can recover within a bounded tool budget.
- Source inspection improves verification without becoming the normal path for
  every query.
- Optional embeddings improve representative recall enough to justify their
  ingest, storage, and query cost.
- Citations remain precise after synthesis and retrieval expansion.

## Phase 3 — Maintenance Lifecycle

Purpose: keep a growing wiki useful without rebuilding a semantic pipeline.

Scope:

- Semantic lint for duplicate, stale, unsupported, or weakly connected pages.
- Review workflow and user-approved maintenance.
- Incremental overview/index maintenance at larger scale.
- Evaluation dashboard for quality, economics, drift, and human review load.

Exit criteria:

- Wiki health does not degrade materially as sources accumulate.
- Maintenance actions remain auditable and source-grounded.
- The default ingest/query path remains understandable and small.

## Optional Modules

OCR, specialized parsers, advanced graph analysis, and external vector storage
remain outside the core. Add one only when evaluation shows a gap that cannot be
closed by a simpler prompt, contract, or tool change.
