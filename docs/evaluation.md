# Evaluation

Evaluation protects the general-purpose foundation from being optimized around
one convenient document.

## Corpus

Maintain a small but heterogeneous regression corpus:

- Policy or legal document.
- Technical documentation.
- Research paper.
- Meeting transcript.
- Narrative or book chapter.
- Spreadsheet or table-heavy source.
- Image or diagram.
- Multilingual sources.
- Two sources that support, qualify, or contradict each other.

The current certificate-of-deposit document is one fixture only. It must not
define page types, extraction rules, query routing, or success criteria.

## Question Classes

- Direct factual lookup.
- Conditions, exceptions, and scope.
- Cross-source synthesis.
- Comparison.
- Change over time.
- Contradiction handling.
- Numeric/table reasoning.
- Visual evidence.
- No-answer calibration.
- Query whose answer exists in raw source but is missing from the wiki.

## System Variants

Compare at least:

1. Raw-source baseline.
2. Wiki-only FTS.
3. Wiki Agent with source verification.
4. Optional semantic search.
5. A tagged historical result from the removed compiler, if available.

## Metrics

### Quality

- Answer correctness.
- Faithfulness to supplied sources.
- Citation precision.
- Cross-source synthesis quality.
- Contradiction and qualification handling.
- No-answer calibration.

### Wiki health

- Duplicate page rate.
- Broken link/index rate.
- Unsupported statement rate.
- Cross-source update success.
- Stale page rate.
- Human review burden.

### Economics

- Model calls per ingest/query.
- Input/output tokens.
- Estimated cost.
- End-to-end latency.
- Retry rate.
- Cache hit rate.

### Compounding

Measure whether later operations improve the system:

- Does source two enrich pages created by source one?
- Does saving a useful query reduce later query work?
- Does lint reduce duplicate/stale knowledge?
- Does source reinspection repair a previous query miss?

## Decision Rule

Do not add a mandatory pipeline stage because it improves one example.

A new module belongs in the default path only when:

- It improves representative quality or reliability.
- The gain is repeatable across multiple fixtures.
- Its cost and complexity are measured.
- A simpler prompt/tool change is insufficient.
