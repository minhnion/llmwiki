# Artifact-first LLM Wiki Knowledge Chatbot

> A technical blueprint for building a general-purpose, domain-agnostic knowledge chatbot based on the LLM Wiki concept, extended with artifact-level embeddings and semantic navigation.

---

## 0. Executive Summary

This document describes a proposed architecture for a general-purpose knowledge chatbot that can ingest many types of files across many domains, build a persistent LLM-maintained knowledge base, and answer questions by retrieving compiled knowledge artifacts rather than raw text chunks.

The core principle is:

```text
Do not retrieve raw chunks as the primary unit of knowledge.
Retrieve LLM-built knowledge artifacts.
```

Traditional RAG usually follows this pattern:

```text
Raw files
  -> text extraction
  -> chunking
  -> embeddings
  -> vector retrieval over chunks
  -> answer generation
```

The proposed system follows this pattern instead:

```text
Raw files
  -> LLM/VLM Knowledge Builder
  -> Wiki pages + knowledge objects + graph + provenance
  -> embeddings over generated artifacts
  -> semantic artifact retrieval
  -> graph expansion / LLM semantic navigation
  -> context assembly
  -> answer generation
  -> optional write-back into the wiki
```

Raw files remain the immutable source of truth, but they are not the primary retrieval substrate. The primary searchable corpus is the LLM-built knowledge layer.

This design is intended for a setting where LLM/VLM and embedding resources are abundant. Therefore, the system intentionally shifts cost from query-time retrieval to ingest-time knowledge compilation.

---

## 1. Design Goals

### 1.1 Primary goal

Build a general-purpose knowledge chatbot that can ingest arbitrary documents from many domains and answer questions without relying on domain-specific chunking rules, hardcoded keywords, hardcoded mappings, or domain-specific regex logic.

### 1.2 Constraints

The system should satisfy these constraints:

```text
- General across domains.
- General across document types.
- No domain-specific hardcoded extraction logic.
- No hardcoded keyword routing.
- No raw chunk retrieval as the core mechanism.
- Use LLM/VLM heavily during ingest.
- Use embeddings, but only over LLM-built artifacts.
- Preserve provenance to raw sources.
- Support iterative improvement and write-back.
```

### 1.3 Non-goals

This system is not trying to be:

```text
- A normal vector RAG system.
- A raw chunk search engine.
- A set of domain-specific parsers.
- A collection of static summaries.
- A one-shot document QA pipeline.
```

The objective is to build a compounding knowledge layer.

---

## 2. Core Concept

The system is based on the LLM Wiki idea:

```text
Raw sources are immutable.
The LLM builds and maintains a persistent wiki.
The wiki accumulates knowledge over time.
Queries are answered from the compiled wiki first.
Useful answers can be written back into the wiki.
```

The key difference from traditional RAG is that knowledge is not rediscovered from raw chunks for every query. Instead, the system uses LLM/VLMs during ingest to compile raw documents into durable artifacts:

```text
- source summaries
- concept pages
- entity pages
- rule pages
- procedure pages
- claim objects
- relationship objects
- contradiction records
- synthesis pages
- index entries
- graph edges
```

These generated artifacts become the main retrieval surface.

---

## 3. High-level Architecture

```text
                         +----------------------+
                         |      Raw Sources      |
                         | pdf/docx/pptx/xlsx... |
                         +-----------+----------+
                                     |
                                     v
                         +----------------------+
                         | LLM/VLM Knowledge     |
                         | Builder               |
                         +-----------+----------+
                                     |
        +----------------------------+----------------------------+
        |                            |                            |
        v                            v                            v
+---------------+            +----------------+           +----------------+
| Wiki Markdown |            | Knowledge Obj  |           | Knowledge Graph |
| pages         |            | Store          |           | links/relations |
+-------+-------+            +-------+--------+           +-------+--------+
        |                            |                            |
        +----------------------------+----------------------------+
                                     |
                                     v
                         +----------------------+
                         | Artifact Embedding    |
                         | Index                 |
                         +-----------+----------+
                                     |
                                     v
                         +----------------------+
                         | Query Orchestrator    |
                         | LLM semantic planner  |
                         +-----------+----------+
                                     |
                                     v
                         +----------------------+
                         | Context Builder       |
                         | pages + objects+graph |
                         +-----------+----------+
                                     |
                                     v
                         +----------------------+
                         | Answer Agent          |
                         +-----------+----------+
                                     |
                                     v
                         +----------------------+
                         | Optional Write-back   |
                         +----------------------+
```

---

## 4. Core Storage Layers

The system uses several storage layers. Each layer has a different purpose.

### 4.1 Raw Source Store

Raw files are stored unchanged.

Example:

```text
raw/
  documents/
    contract_001.pdf
    policy_2024.docx
    product_manual.pptx
    financial_report.xlsx
    meeting_transcript.txt
```

Each source has metadata:

```json
{
  "source_id": "src_policy_2024",
  "path": "raw/documents/policy_2024.docx",
  "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "sha256": "...",
  "language": "vi",
  "created_at": "2026-06-18T10:00:00+07:00",
  "ingested_at": "2026-06-18T10:05:00+07:00",
  "status": "compiled"
}
```

Raw sources are used for:

```text
- provenance
- audit
- re-ingest
- source verification by pointer
- rebuilding artifacts
```

Raw sources are not used for primary semantic retrieval.

---

### 4.2 Wiki Markdown Store

The wiki is the human-readable knowledge layer.

Example layout:

```text
wiki/
  index.md
  log.md
  map.md

  sources/
    policy_2024_summary.md
    contract_001_summary.md

  concepts/
    early_repayment.md
    prepayment_penalty.md
    fee_waiver.md
    promotional_loan.md

  entities/
    product_a.md
    customer.md
    bank_x.md

  rules/
    early_repayment_after_12_months.md
    promotional_loan_not_eligible_for_fee_waiver.md

  procedures/
    reset_device.md

  contradictions/
    prepayment_policy_2023_vs_2024.md

  syntheses/
    early_repayment_conditions_across_products.md
```

The wiki is LLM-maintained. Humans may inspect it, but the primary writer is the Knowledge Builder.

---

### 4.3 Knowledge Object Store

The object store contains structured knowledge units that can be indexed, retrieved, linked, and converted into wiki pages.

Universal object types:

```text
source_summary
concept
entity
claim
rule
condition
exception
procedure
metric
relationship
contradiction
synthesis
open_question
```

Example:

```json
{
  "artifact_id": "rule_early_repayment_after_12_months",
  "artifact_type": "rule",
  "title": "Early repayment after 12 months",
  "statement": "Customers may prepay without penalty after the loan has been active for at least 12 months.",
  "conditions": [
    "loan age >= 12 months",
    "product is not a promotional loan"
  ],
  "source_refs": [
    {
      "source_id": "src_policy_2024",
      "page": 12,
      "section": "Early Repayment",
      "anchor": "early-repayment-section"
    }
  ],
  "related_artifacts": [
    "concept_prepayment_penalty",
    "concept_fee_waiver",
    "exception_promotional_loan_fee_waiver"
  ],
  "confidence": 0.91,
  "status": "active"
}
```

---

### 4.4 Knowledge Graph

The graph stores relationships between artifacts.

Example edges:

```json
[
  {
    "from": "rule_early_repayment_after_12_months",
    "to": "concept_fee_waiver",
    "relation": "condition_for"
  },
  {
    "from": "exception_promotional_loan_fee_waiver",
    "to": "concept_fee_waiver",
    "relation": "exception_of"
  },
  {
    "from": "concept_prepayment_penalty",
    "to": "concept_early_repayment",
    "relation": "related_to"
  }
]
```

Graph edges are not hardcoded by domain. They are inferred by the LLM using general relationship primitives.

Recommended relation primitives:

```text
related_to
part_of
instance_of
defines
contradicts
supports
supersedes
condition_for
exception_of
applies_to
causes
depends_on
compares_with
derived_from
```

---

### 4.5 Artifact Embedding Index

The embedding index stores vectors for generated artifacts only.

Recommended embedding records:

```text
- wiki page summaries
- wiki page sections
- knowledge objects
- concept/entity cards
- relationship records
- contradiction records
- synthesis pages
- parsed index entries
```

Not recommended as primary index:

```text
- raw chunks
- arbitrary token windows from source documents
```

Example embedding record:

```json
{
  "embedding_id": "emb_rule_early_repayment_after_12_months",
  "artifact_id": "rule_early_repayment_after_12_months",
  "artifact_type": "rule",
  "target": "wiki/rules/early_repayment_after_12_months.md",
  "text_for_embedding": "Rule: Early repayment after 12 months. Customers may prepay without penalty after the loan has been active for at least 12 months. Conditions: loan age >= 12 months; product is not a promotional loan. Related: prepayment penalty, fee waiver, early repayment.",
  "source_refs": ["src_policy_2024#page=12"]
}
```

---

## 5. Ingest Pipeline

The ingest pipeline is centered around a single high-level component:

```text
LLM/VLM Knowledge Builder
```

Internally, the Knowledge Builder may run multiple passes, but externally it can be treated as one job.

---

## 5.1 Ingest Input

Input:

```json
{
  "source": {
    "source_id": "src_policy_2024",
    "path": "raw/documents/policy_2024.docx",
    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  },
  "existing_wiki_state": {
    "index": "wiki/index.md",
    "recent_log": "wiki/log.md",
    "candidate_related_pages": [
      "wiki/concepts/early_repayment.md",
      "wiki/concepts/prepayment_penalty.md"
    ]
  },
  "global_schema": "schema/global_knowledge_builder.md"
}
```

---

## 5.2 Ingest Output

Output:

```json
{
  "source_summary_page": "wiki/sources/policy_2024_summary.md",
  "pages_to_create": [],
  "pages_to_update": [],
  "knowledge_objects": [],
  "relationships": [],
  "contradictions": [],
  "index_updates": [],
  "log_entry": "...",
  "embedding_records": [],
  "coverage_report": {}
}
```

---

## 5.3 Ingest Step-by-step

### Step 1: Source registration

Input:

```text
raw/documents/policy_2024.docx
```

Output:

```json
{
  "source_id": "src_policy_2024",
  "sha256": "...",
  "status": "registered"
}
```

Purpose:

```text
- assign stable source ID
- detect duplicates
- support incremental rebuild
- preserve provenance
```

---

### Step 2: LLM/VLM source reading

The Knowledge Builder reads the source using appropriate multimodal capability.

Possible source types:

```text
- PDF
- DOCX
- PPTX
- XLSX
- HTML
- markdown
- images
- scans
- transcripts
- mixed documents
```

The model should infer:

```text
- document type
- structure
- important sections
- tables
- figures
- definitions
- claims
- rules
- procedures
- entities
- relationships
- exceptions
- contradictions
- uncertainty
```

No domain-specific parser is required. The model uses general knowledge operations.

---

### Step 3: Broad knowledge extraction

Input:

```text
source content + existing wiki index + global schema
```

Output example:

```json
{
  "detected_document_profile": {
    "document_kind": "policy_document",
    "domain_guess": "banking_or_financial_services",
    "confidence": 0.82,
    "extraction_lenses": [
      "rules",
      "conditions",
      "exceptions",
      "fees",
      "eligibility"
    ]
  },
  "candidate_concepts": [
    "Early Repayment",
    "Prepayment Penalty",
    "Fee Waiver",
    "Promotional Loan"
  ],
  "candidate_entities": [
    "Customer",
    "Product A",
    "Bank X"
  ],
  "candidate_rules": [
    {
      "title": "Early repayment after 12 months",
      "statement": "Customers may prepay without penalty after 12 months.",
      "conditions": ["loan age >= 12 months"],
      "source_refs": [{"source_id": "src_policy_2024", "page": 12}]
    }
  ],
  "candidate_exceptions": [
    {
      "title": "Promotional loans excluded from fee waiver",
      "statement": "Promotional loans are not eligible for the early repayment fee waiver.",
      "source_refs": [{"source_id": "src_policy_2024", "page": 13}]
    }
  ]
}
```

Purpose:

```text
Create candidate knowledge units before integrating them into the persistent wiki.
```

---

### Step 4: Existing knowledge matching

The builder compares new candidates against existing artifacts.

Input:

```text
candidate concepts/entities/rules + existing wiki index + artifact store
```

Output:

```json
{
  "matches": [
    {
      "candidate": "Early Repayment",
      "existing_artifact": "concept_early_repayment",
      "action": "update"
    },
    {
      "candidate": "Promotional Loan",
      "existing_artifact": null,
      "action": "create"
    }
  ]
}
```

Purpose:

```text
- avoid duplicate pages
- update existing concepts
- create new pages only when needed
- preserve continuity of the wiki
```

This step should use LLM semantic judgment and artifact embeddings. It should not rely on exact string matching.

---

### Step 5: Artifact creation/update plan

Input:

```text
new candidates + matched existing artifacts
```

Output:

```json
{
  "create_pages": [
    {
      "path": "wiki/concepts/promotional_loan.md",
      "type": "concept"
    },
    {
      "path": "wiki/rules/early_repayment_after_12_months.md",
      "type": "rule"
    }
  ],
  "update_pages": [
    {
      "path": "wiki/concepts/early_repayment.md",
      "reason": "new policy adds 12-month fee waiver condition"
    },
    {
      "path": "wiki/concepts/prepayment_penalty.md",
      "reason": "new exception about promotional loans"
    }
  ],
  "create_objects": [
    "rule_early_repayment_after_12_months",
    "exception_promotional_loan_fee_waiver"
  ]
}
```

Purpose:

```text
Turn analysis into concrete file/object operations.
```

---

### Step 6: Write source summary page

Output example:

```markdown
---
id: source_summary_src_policy_2024
type: source_summary
source_id: src_policy_2024
status: active
created_at: 2026-06-18
related:
  - [[Early Repayment]]
  - [[Prepayment Penalty]]
  - [[Fee Waiver]]
  - [[Promotional Loan]]
---

# Policy 2024 Summary

## One-sentence summary

This policy defines eligibility, conditions, fees, and exceptions for customer early repayment.

## Key rules

- Customers may prepay without penalty after the loan has been active for at least 12 months.
- Promotional loans are excluded from the fee waiver.
- Corporate loans may require separate approval.

## Important concepts

- [[Early Repayment]]
- [[Prepayment Penalty]]
- [[Fee Waiver]]
- [[Promotional Loan]]

## Evidence map

- Page 12: early repayment eligibility.
- Page 13: promotional loan exclusion.
- Page 14: corporate loan approval requirement.
```

Purpose:

```text
Create a durable source-level artifact that summarizes the document without forcing future queries to inspect the raw file.
```

---

### Step 7: Create/update concept pages

Example:

```markdown
---
id: concept_prepayment_penalty
type: concept
title: Prepayment Penalty
aliases:
  - early repayment fee
  - early settlement penalty
related:
  - [[Early Repayment]]
  - [[Fee Waiver]]
  - [[Promotional Loan]]
sources:
  - src_policy_2024
status: active
confidence: 0.88
---

# Prepayment Penalty

## Summary

A prepayment penalty is a fee charged when a customer repays a loan before a permitted date or before satisfying eligibility conditions for a fee waiver.

## Current known rules

- A customer may avoid the penalty if the loan has been active for at least 12 months.
- Promotional loans are excluded from the fee waiver.

## Exceptions

- [[Promotional Loan]] may not qualify for waiver.

## Evidence

- `src_policy_2024`, page 12: fee waiver after 12 months.
- `src_policy_2024`, page 13: promotional loan exclusion.
```

Purpose:

```text
Accumulate knowledge about a concept across many sources.
```

---

### Step 8: Create structured knowledge objects

Example:

```json
{
  "artifact_id": "exception_promotional_loan_fee_waiver",
  "artifact_type": "exception",
  "title": "Promotional loans excluded from early repayment fee waiver",
  "statement": "Promotional loans are not eligible for the early repayment fee waiver.",
  "scope": "early repayment fee waiver",
  "conditions": ["loan product is promotional"],
  "source_refs": [
    {
      "source_id": "src_policy_2024",
      "page": 13,
      "section": "Promotional Loan Exclusion"
    }
  ],
  "related_artifacts": [
    "concept_promotional_loan",
    "concept_fee_waiver",
    "concept_prepayment_penalty"
  ],
  "confidence": 0.9,
  "status": "active"
}
```

Purpose:

```text
Provide machine-addressable, retrievable, linkable knowledge units.
```

---

### Step 9: Create graph edges

Output:

```json
[
  {
    "from": "exception_promotional_loan_fee_waiver",
    "to": "concept_promotional_loan",
    "relation": "applies_to"
  },
  {
    "from": "exception_promotional_loan_fee_waiver",
    "to": "concept_fee_waiver",
    "relation": "exception_of"
  },
  {
    "from": "rule_early_repayment_after_12_months",
    "to": "concept_prepayment_penalty",
    "relation": "condition_for"
  }
]
```

Purpose:

```text
Enable graph expansion during query.
```

---

### Step 10: Detect contradictions and supersession

Input:

```text
new claims/rules + existing claims/rules
```

Output example:

```json
{
  "contradictions": [
    {
      "id": "contradiction_prepayment_fee_2023_vs_2024",
      "claim_a": {
        "source_id": "src_policy_2023",
        "statement": "Customers must pay a 2% fee for all early repayments."
      },
      "claim_b": {
        "source_id": "src_policy_2024",
        "statement": "Customers may prepay without penalty after 12 months."
      },
      "possible_resolution": "2024 policy may supersede 2023 policy or may apply to a narrower product scope.",
      "status": "needs_review"
    }
  ]
}
```

Purpose:

```text
Avoid silently merging conflicting information.
```

---

### Step 11: Update index.md

Example:

```markdown
# Index

## Concepts

- [[Early Repayment]] — Repaying a loan before scheduled maturity.
- [[Prepayment Penalty]] — Fee applied when early repayment does not qualify for waiver.
- [[Fee Waiver]] — Removal of a fee under defined eligibility conditions.
- [[Promotional Loan]] — Loan type that may be excluded from certain waivers.

## Rules

- [[Early Repayment After 12 Months]] — Customers may prepay without penalty after 12 months if conditions are satisfied.
- [[Promotional Loan Not Eligible For Fee Waiver]] — Promotional loans are excluded from early repayment fee waiver.

## Sources

- [[Policy 2024 Summary]] — Policy defining early repayment eligibility and fee waiver exceptions.
```

Purpose:

```text
The index is a human/LLM-readable catalog and routing layer.
```

---

### Step 12: Update log.md

Example:

```markdown
## [2026-06-18] ingest | Policy 2024

Source:
- `src_policy_2024`

Created:
- [[Policy 2024 Summary]]
- [[Promotional Loan]]
- [[Early Repayment After 12 Months]]
- [[Promotional Loan Not Eligible For Fee Waiver]]

Updated:
- [[Early Repayment]]
- [[Prepayment Penalty]]
- [[Fee Waiver]]

Notes:
- Added 12-month fee waiver rule.
- Added promotional loan exclusion.
- Possible supersession of 2023 prepayment fee policy should be reviewed.
```

Purpose:

```text
Maintain chronological memory of wiki evolution.
```

---

### Step 13: Generate embedding records

For every generated or updated artifact, generate embedding records.

Example:

```json
[
  {
    "embedding_id": "emb_concept_prepayment_penalty_summary",
    "artifact_id": "concept_prepayment_penalty",
    "artifact_type": "concept",
    "target": "wiki/concepts/prepayment_penalty.md",
    "text_for_embedding": "Prepayment Penalty. Early repayment fee. A fee charged when a customer repays a loan before satisfying eligibility conditions for a fee waiver. Related: Early Repayment, Fee Waiver, Promotional Loan."
  },
  {
    "embedding_id": "emb_exception_promotional_loan_fee_waiver",
    "artifact_id": "exception_promotional_loan_fee_waiver",
    "artifact_type": "exception",
    "target": "wiki/rules/promotional_loan_not_eligible_for_fee_waiver.md",
    "text_for_embedding": "Exception: Promotional loans are not eligible for the early repayment fee waiver. Applies to early repayment and prepayment penalty."
  }
]
```

Purpose:

```text
Enable semantic retrieval over compiled artifacts.
```

---

### Step 14: Coverage report

The Knowledge Builder should produce a coverage report.

Example:

```json
{
  "source_id": "src_policy_2024",
  "coverage": {
    "definitions": "high",
    "rules": "high",
    "conditions": "high",
    "exceptions": "medium",
    "tables": "medium",
    "figures": "not_applicable",
    "effective_dates": "medium"
  },
  "possible_missing_items": [
    "Some fee table details may need a second pass.",
    "Effective dates should be checked against older policy documents."
  ],
  "recommended_followup_passes": [
    "table_detail_pass",
    "supersession_check_against_prior_policies"
  ]
}
```

Purpose:

```text
Compensate for not using raw chunk retrieval by checking whether the compiled artifacts are complete enough.
```

---

## 6. Query Pipeline

The query pipeline retrieves compiled artifacts first.

---

## 6.1 Query Input

Example user query:

```text
Trong các tài liệu này, trường hợp nào khách hàng không được miễn phí tất toán trước hạn?
```

---

## 6.2 Query Step-by-step

### Step 1: Query understanding

Input:

```text
User query
```

Output:

```json
{
  "intent": "find_conditions_or_exceptions",
  "domain_guess": "financial_services",
  "target_meaning": "conditions where customer is not eligible for free early repayment",
  "desired_artifact_types": [
    "rule",
    "condition",
    "exception",
    "concept",
    "source_summary"
  ],
  "evidence_strictness": "high",
  "answer_style": "structured list with source references"
}
```

Important:

```text
Domain guess is a soft signal, not a hardcoded route.
```

---

### Step 2: Semantic probe generation

The LLM query planner generates several semantic probes.

Output:

```json
{
  "semantic_probes": [
    "conditions where customer is not eligible for early repayment fee waiver",
    "exceptions to free early repayment",
    "prepayment penalty exclusion conditions",
    "loan products excluded from fee waiver",
    "cases where early settlement is not free"
  ]
}
```

Purpose:

```text
Improve recall without hardcoded keywords.
```

---

### Step 3: Artifact vector search

For each semantic probe, search the artifact embedding index.

Search space:

```text
- wiki page summaries
- wiki sections
- knowledge objects
- concept/entity cards
- rule/condition/exception artifacts
- contradiction records
- synthesis pages
- index entries
```

Not searched:

```text
- raw chunks
```

Example result:

```json
[
  {
    "artifact_id": "exception_promotional_loan_fee_waiver",
    "artifact_type": "exception",
    "target": "wiki/rules/promotional_loan_not_eligible_for_fee_waiver.md",
    "score": 0.89
  },
  {
    "artifact_id": "rule_early_repayment_after_12_months",
    "artifact_type": "rule",
    "target": "wiki/rules/early_repayment_after_12_months.md",
    "score": 0.86
  },
  {
    "artifact_id": "concept_prepayment_penalty",
    "artifact_type": "concept",
    "target": "wiki/concepts/prepayment_penalty.md",
    "score": 0.80
  }
]
```

---

### Step 4: Optional lexical artifact search

Lexical search is optional but useful for:

```text
- exact article numbers
- product names
- codes
- dates
- acronyms
- legal clause references
- account IDs
```

Lexical search should run over artifacts, not raw chunks.

Example:

```text
Search wiki pages and object store for "Điều 7.2.1"
```

Output:

```json
[
  {
    "artifact_id": "rule_clause_7_2_1",
    "artifact_type": "rule",
    "target": "wiki/rules/clause_7_2_1.md",
    "match_type": "exact_reference"
  }
]
```

---

### Step 5: Candidate merge and normalization

Input:

```text
vector results + optional lexical results + index candidates
```

Output:

```json
{
  "merged_candidates": [
    {
      "artifact_id": "exception_promotional_loan_fee_waiver",
      "artifact_type": "exception",
      "signals": ["vector", "graph_seed"],
      "score": 0.91
    },
    {
      "artifact_id": "rule_early_repayment_after_12_months",
      "artifact_type": "rule",
      "signals": ["vector"],
      "score": 0.87
    },
    {
      "artifact_id": "concept_prepayment_penalty",
      "artifact_type": "concept",
      "signals": ["vector", "index"],
      "score": 0.82
    }
  ]
}
```

---

### Step 6: LLM reranking

The LLM reads the candidate titles/summaries and reranks them according to the query intent.

Input:

```json
{
  "query": "Trong các tài liệu này, trường hợp nào khách hàng không được miễn phí tất toán trước hạn?",
  "candidates": [
    "exception_promotional_loan_fee_waiver",
    "rule_early_repayment_after_12_months",
    "concept_prepayment_penalty"
  ]
}
```

Output:

```json
{
  "selected_candidates": [
    {
      "artifact_id": "exception_promotional_loan_fee_waiver",
      "reason": "Directly answers cases where customer is not eligible for waiver."
    },
    {
      "artifact_id": "rule_early_repayment_after_12_months",
      "reason": "Defines the positive eligibility condition, useful for identifying failure cases."
    },
    {
      "artifact_id": "concept_prepayment_penalty",
      "reason": "Provides broader concept context."
    }
  ]
}
```

---

### Step 7: Graph expansion

Start from selected artifacts and expand related nodes.

Example:

```text
exception_promotional_loan_fee_waiver
  -> exception_of -> concept_fee_waiver
  -> applies_to -> concept_promotional_loan
  -> related_to -> concept_prepayment_penalty
  -> sourced_from -> source_summary_src_policy_2024
```

Expansion policy:

```json
{
  "max_depth": 2,
  "max_nodes": 12,
  "preferred_relations": [
    "exception_of",
    "condition_for",
    "applies_to",
    "related_to",
    "contradicts",
    "supersedes",
    "derived_from"
  ]
}
```

Output:

```json
{
  "expanded_artifacts": [
    "concept_fee_waiver",
    "concept_promotional_loan",
    "concept_prepayment_penalty",
    "source_summary_src_policy_2024"
  ]
}
```

---

### Step 8: Load full artifacts

The system loads the full markdown pages and object records for selected and expanded artifacts.

Input:

```text
artifact IDs
```

Output:

```text
full content of relevant wiki pages and objects
```

Example loaded content:

```markdown
# Promotional Loan Not Eligible For Fee Waiver

Promotional loans are not eligible for the early repayment fee waiver.

## Conditions

- Loan product is promotional.
- Early repayment occurs under the promotional campaign terms.

## Evidence

- `src_policy_2024`, page 13, Promotional Loan Exclusion.
```

---

### Step 9: Optional source verification by provenance pointer

This is not raw chunk retrieval.

The system may open a raw source directly using provenance pointers if:

```text
- evidence strictness is high
- artifact confidence is low
- contradiction exists
- user asks for exact source wording
- answer requires source-level verification
```

Example:

```json
{
  "source_id": "src_policy_2024",
  "page": 13,
  "section": "Promotional Loan Exclusion"
}
```

The system opens that page/section directly. It does not run semantic vector search over raw chunks.

Purpose:

```text
Preserve grounding without returning to chunk-based RAG.
```

---

### Step 10: Context assembly

The system compiles selected artifacts into a compact context packet.

Output:

```markdown
# Context Packet

## User question

Trong các tài liệu này, trường hợp nào khách hàng không được miễn phí tất toán trước hạn?

## Relevant rules and exceptions

### Promotional loans excluded from fee waiver

Promotional loans are not eligible for the early repayment fee waiver.

Evidence:
- `src_policy_2024`, page 13, Promotional Loan Exclusion.

### Early repayment after 12 months

Customers may prepay without penalty after the loan has been active for at least 12 months.

Evidence:
- `src_policy_2024`, page 12, Early Repayment.

## Related concepts

### Prepayment Penalty

A fee charged when the customer repays early without satisfying waiver conditions.

### Fee Waiver

A removal of fee under specified eligibility conditions.
```

Purpose:

```text
Give the Answer Agent only the relevant compiled knowledge, not a pile of retrieved text.
```

---

### Step 11: Answer generation

Example answer:

```markdown
Khách hàng không được miễn phí tất toán trước hạn trong các trường hợp sau:

1. Khoản vay là khoản vay khuyến mại.
   - Lý do: chính sách loại trừ promotional loans khỏi fee waiver.
   - Nguồn: `src_policy_2024`, trang 13.

2. Khoản vay chưa đủ 12 tháng hoạt động.
   - Lý do: điều kiện được miễn phí là khoản vay phải active ít nhất 12 tháng.
   - Nguồn: `src_policy_2024`, trang 12.

Nếu cần kết luận chắc chắn cho từng sản phẩm vay cụ thể, cần đối chiếu thêm product terms tương ứng.
```

---

### Step 12: Optional write-back

If the answer is a useful synthesis, save it as a new artifact.

Example:

```text
wiki/syntheses/early_repayment_fee_waiver_exclusions.md
```

Generated page:

```markdown
---
id: synthesis_early_repayment_fee_waiver_exclusions
type: synthesis
created_from_query: true
sources:
  - src_policy_2024
related:
  - [[Prepayment Penalty]]
  - [[Fee Waiver]]
  - [[Promotional Loan]]
---

# Early Repayment Fee Waiver Exclusions

## Summary

Customers are not eligible for free early repayment when the loan is promotional or when the minimum active loan age condition has not been satisfied.

## Conditions

1. Promotional loan exclusion.
2. Loan age below 12 months.

## Evidence

- `src_policy_2024`, page 12.
- `src_policy_2024`, page 13.
```

Purpose:

```text
Make useful query-time synthesis compound into the knowledge base.
```

---

## 7. Data Transformation Summary

The overall data transformation looks like this:

```text
Raw file
  -> source metadata
  -> LLM/VLM interpretation
  -> candidate knowledge units
  -> artifact creation/update plan
  -> markdown wiki pages
  -> structured knowledge objects
  -> graph edges
  -> embedding records
  -> searchable artifact index
```

Example:

```text
policy_2024.docx
  -> src_policy_2024
  -> detected as policy document
  -> extracts rules/conditions/exceptions
  -> creates concept/rule/exception pages
  -> creates graph edges
  -> embeds generated artifacts
  -> answers future questions using artifacts
```

---

## 8. Universal Artifact Schema

A generic schema should be domain-agnostic.

```json
{
  "artifact_id": "string",
  "artifact_type": "source_summary | concept | entity | claim | rule | condition | exception | procedure | metric | relationship | contradiction | synthesis | open_question",
  "title": "string",
  "summary": "string",
  "content": "string or structured object",
  "aliases": ["string"],
  "source_refs": [
    {
      "source_id": "string",
      "page": "number or null",
      "section": "string or null",
      "anchor": "string or null",
      "confidence": "number"
    }
  ],
  "related_artifacts": ["artifact_id"],
  "relationships": [
    {
      "target": "artifact_id",
      "relation": "string"
    }
  ],
  "confidence": "number",
  "status": "active | disputed | superseded | incomplete | needs_review",
  "created_at": "datetime",
  "updated_at": "datetime",
  "embedding_text": "string"
}
```

---

## 9. Artifact Types

### 9.1 Source Summary

Represents one raw source.

Contains:

```text
- one-sentence summary
- key claims
- key concepts
- key entities
- evidence map
- generated artifacts
- possible missing areas
```

---

### 9.2 Concept

Represents a reusable idea.

Examples:

```text
- Prepayment Penalty
- Fee Waiver
- LLM Wiki
- Knowledge Compilation
- Customer Eligibility
```

---

### 9.3 Entity

Represents a named object/person/org/product/system.

Examples:

```text
- Product A
- Bank X
- Customer
- GPT-4o
```

---

### 9.4 Rule

Represents a normative or operational rule.

Example:

```text
Customers may prepay without penalty after the loan has been active for at least 12 months.
```

---

### 9.5 Condition

Represents a condition required for a rule to apply.

Example:

```text
Loan age must be at least 12 months.
```

---

### 9.6 Exception

Represents exclusion or exception.

Example:

```text
Promotional loans are excluded from the fee waiver.
```

---

### 9.7 Procedure

Represents steps.

Example:

```text
How to reset a device.
```

---

### 9.8 Claim

Represents a factual assertion.

Example:

```text
The system uses artifact-level embeddings rather than raw chunk embeddings.
```

---

### 9.9 Relationship

Represents a link between artifacts.

Example:

```text
Promotional loan -> exception_of -> fee waiver
```

---

### 9.10 Contradiction

Represents conflict, inconsistency, or potential supersession.

Example:

```text
2023 policy says all early repayments incur 2% fee.
2024 policy says fee may be waived after 12 months.
```

---

### 9.11 Synthesis

Represents query-time or ingest-time synthesis across multiple artifacts.

Example:

```text
Early repayment fee waiver exclusions across all products.
```

---

## 10. Embedding Strategy

The system embeds only generated artifacts.

### 10.1 What to embed

```text
- artifact title
- artifact type
- aliases
- summary
- normalized statement
- conditions
- related artifacts
- source summary pointer
```

### 10.2 What not to embed as the primary corpus

```text
- arbitrary raw chunks
- fixed token windows
- overlapping raw text chunks
```

### 10.3 Example embedding text

```text
Rule: Early repayment after 12 months.
Customers may prepay without penalty after the loan has been active for at least 12 months.
Conditions: loan age >= 12 months; product is not promotional.
Related concepts: early repayment, prepayment penalty, fee waiver, promotional loan.
Source: policy 2024.
```

### 10.4 Multiple embeddings per artifact

For important artifacts, create multiple embeddings:

```text
- summary embedding
- detail embedding
- question-style embedding
- relation embedding
```

Example:

```json
[
  {
    "embedding_id": "emb_rule_summary",
    "text_for_embedding": "Rule: customers may prepay without penalty after 12 months."
  },
  {
    "embedding_id": "emb_rule_question_style",
    "text_for_embedding": "When can a customer repay early without a penalty? What are the eligibility conditions for fee waiver?"
  },
  {
    "embedding_id": "emb_rule_relation",
    "text_for_embedding": "This rule is a condition for fee waiver and relates to prepayment penalty and early repayment."
  }
]
```

This improves retrieval without relying on raw chunks.

---

## 11. Query Orchestrator Design

The Query Orchestrator is responsible for planning retrieval.

Input:

```text
User question
```

Output:

```json
{
  "intent": "string",
  "semantic_probes": [],
  "desired_artifact_types": [],
  "graph_expansion_policy": {},
  "evidence_strictness": "low | medium | high",
  "answer_format": "string"
}
```

Example:

```json
{
  "intent": "compare",
  "semantic_probes": [
    "difference between LLM Wiki and traditional RAG",
    "artifact retrieval versus raw chunk retrieval",
    "compiled knowledge retrieval"
  ],
  "desired_artifact_types": [
    "concept",
    "comparison",
    "synthesis",
    "relationship"
  ],
  "graph_expansion_policy": {
    "max_depth": 2,
    "preferred_relations": [
      "contrasts_with",
      "depends_on",
      "related_to"
    ]
  },
  "evidence_strictness": "medium",
  "answer_format": "explanation_with_examples"
}
```

---

## 12. Context Assembly

The Context Builder should not simply concatenate retrieved artifacts.

It should assemble context by role:

```text
- direct answer artifacts
- supporting concepts
- exceptions/contradictions
- source summaries
- provenance pointers
- uncertainty notes
```

Template:

```markdown
# Context Packet

## Query

{user_query}

## Directly relevant artifacts

{rules/exceptions/claims/procedures}

## Supporting concepts

{concept summaries}

## Related entities

{entity summaries}

## Contradictions or uncertainty

{contradiction records}

## Evidence pointers

{source refs}
```

---

## 13. Answer Agent

The Answer Agent receives the context packet and produces an answer.

Rules:

```text
- Answer only from provided artifacts unless source verification is performed.
- Cite source_refs or wiki artifacts.
- Mention uncertainty when artifacts are incomplete or disputed.
- If answer requires missing knowledge, trigger artifact gap handling.
- If synthesis is useful, propose or perform write-back depending on policy.
```

---

## 14. Source Verification Without Raw Chunk Retrieval

The system does not run vector search over raw chunks.

Instead, it verifies by provenance pointer:

```text
artifact -> source_ref -> exact source page/section/anchor
```

Example:

```json
{
  "artifact_id": "exception_promotional_loan_fee_waiver",
  "source_refs": [
    {
      "source_id": "src_policy_2024",
      "page": 13,
      "section": "Promotional Loan Exclusion"
    }
  ]
}
```

If verification is needed:

```text
Open src_policy_2024 at page 13 / section Promotional Loan Exclusion.
Ask LLM/VLM to inspect that exact part.
Update artifact if needed.
Answer.
```

This keeps the system grounded without returning to chunk-based RAG.

---

## 15. Gap Handling

If retrieval finds insufficient artifacts:

```text
1. Search source summaries.
2. Identify likely raw sources by source-level metadata and summaries.
3. Re-open likely sources with LLM/VLM.
4. Compile missing artifacts.
5. Update wiki and embedding index.
6. Answer using newly created artifacts.
```

This is on-demand knowledge compilation, not raw chunk retrieval.

Example:

```json
{
  "gap_detected": true,
  "gap_type": "missing_exception_details",
  "likely_sources": ["src_policy_2024", "src_product_terms_a"],
  "action": "reinspect_sources_and_compile_missing_artifacts"
}
```

---

## 16. Lint / Maintenance Loop

The wiki must be maintained over time.

Lint tasks:

```text
- detect duplicate concepts
- detect orphan pages
- detect missing provenance
- detect stale claims
- detect contradictions
- detect weak source coverage
- detect over-broad artifacts
- detect underspecified artifacts
- detect missing cross-links
- detect query failures that should create new artifacts
```

Example lint output:

```json
{
  "issues": [
    {
      "type": "duplicate_concepts",
      "artifacts": [
        "concept_early_repayment",
        "concept_prepayment"
      ],
      "recommendation": "merge or establish alias relationship",
      "severity": "medium"
    },
    {
      "type": "missing_provenance",
      "artifact": "concept_fee_waiver",
      "recommendation": "add source_refs to all major claims",
      "severity": "high"
    }
  ]
}
```

---

## 17. Suggested System Components

### 17.1 Ingest Service

Responsibilities:

```text
- register raw source
- call Knowledge Builder
- write wiki pages
- write knowledge objects
- write graph edges
- write embedding records
- update index/log
```

---

### 17.2 Knowledge Builder

Responsibilities:

```text
- multimodal document understanding
- knowledge extraction
- artifact planning
- artifact generation
- contradiction detection
- coverage reporting
```

---

### 17.3 Artifact Store

Responsibilities:

```text
- store structured objects
- provide lookup by artifact_id
- provide source_ref lookup
- version artifacts
```

---

### 17.4 Wiki Store

Responsibilities:

```text
- store markdown pages
- support full-page read/write
- support section extraction
- maintain index.md and log.md
```

---

### 17.5 Graph Store

Responsibilities:

```text
- store artifact relations
- support neighbor expansion
- support relation filtering
- support backlink lookup
```

---

### 17.6 Embedding Index

Responsibilities:

```text
- store vectors over artifacts
- support semantic probe search
- return artifact IDs, not raw text chunks
```

---

### 17.7 Query Orchestrator

Responsibilities:

```text
- classify intent
- generate semantic probes
- search artifact embeddings
- merge candidates
- rerank with LLM
- expand graph
- request source verification when needed
```

---

### 17.8 Context Builder

Responsibilities:

```text
- load selected artifacts
- compress/organize context
- include evidence pointers
- include contradiction/uncertainty notes
```

---

### 17.9 Answer Agent

Responsibilities:

```text
- generate final answer
- cite artifacts/source_refs
- state uncertainty
- trigger write-back if useful
```

---

## 18. Recommended Repository Structure

```text
project/
  raw/
    documents/
    assets/

  wiki/
    index.md
    log.md
    map.md
    sources/
    concepts/
    entities/
    rules/
    procedures/
    contradictions/
    syntheses/

  objects/
    source_summary/
    concepts/
    entities/
    claims/
    rules/
    conditions/
    exceptions/
    procedures/
    relationships/
    contradictions/
    syntheses/

  graph/
    edges.jsonl

  embeddings/
    artifact_embeddings.jsonl

  schema/
    global_knowledge_builder.md
    artifact_schema.json
    query_orchestrator_schema.json

  logs/
    ingest_runs/
    query_runs/
    lint_runs/
```

---

## 19. Example End-to-end Walkthrough

### Input files

```text
raw/documents/policy_2023.pdf
raw/documents/policy_2024.docx
raw/documents/product_terms_a.pdf
```

---

### Ingest result

Generated artifacts:

```text
wiki/sources/policy_2024_summary.md
wiki/concepts/early_repayment.md
wiki/concepts/prepayment_penalty.md
wiki/concepts/fee_waiver.md
wiki/concepts/promotional_loan.md
wiki/rules/early_repayment_after_12_months.md
wiki/rules/promotional_loan_not_eligible_for_fee_waiver.md
wiki/contradictions/prepayment_policy_2023_vs_2024.md
```

Embedding records:

```text
emb_source_policy_2024_summary
emb_concept_early_repayment
emb_concept_prepayment_penalty
emb_rule_early_repayment_after_12_months
emb_exception_promotional_loan_fee_waiver
emb_contradiction_policy_2023_vs_2024
```

Graph edges:

```text
rule_early_repayment_after_12_months -> condition_for -> concept_fee_waiver
exception_promotional_loan_fee_waiver -> exception_of -> concept_fee_waiver
concept_promotional_loan -> related_to -> concept_prepayment_penalty
contradiction_policy_2023_vs_2024 -> contradicts -> old_fee_rule
```

---

### User query

```text
Trường hợp nào khách hàng không được miễn phí tất toán trước hạn?
```

---

### Retrieval

Semantic probes:

```text
conditions where customer is not eligible for early repayment fee waiver
exceptions to free early repayment
loan products excluded from fee waiver
```

Artifact search results:

```text
exception_promotional_loan_fee_waiver
rule_early_repayment_after_12_months
concept_prepayment_penalty
concept_fee_waiver
```

Graph expansion:

```text
concept_promotional_loan
source_summary_policy_2024
contradiction_policy_2023_vs_2024
```

Context packet created.

---

### Answer

```text
Khách hàng không được miễn phí tất toán trước hạn nếu:

1. Khoản vay là khoản vay khuyến mại.
2. Khoản vay chưa thỏa điều kiện active ít nhất 12 tháng.
3. Nếu là sản phẩm doanh nghiệp, có thể cần kiểm tra điều kiện phê duyệt riêng.

Có một điểm cần lưu ý: policy 2023 và policy 2024 có dấu hiệu thay đổi về phí trả trước hạn, nên với khoản vay cũ cần kiểm tra chính sách hiệu lực theo thời điểm ký hợp đồng.
```

---

### Write-back

New synthesis page:

```text
wiki/syntheses/early_repayment_fee_waiver_exclusions.md
```

---

## 20. Key Design Decisions

### 20.1 Artifact-first retrieval

Decision:

```text
Retrieve generated knowledge artifacts first.
```

Reason:

```text
Artifacts are more semantic, stable, structured, and domain-general than raw chunks.
```

---

### 20.2 No raw chunk vector retrieval in core path

Decision:

```text
Do not embed/retrieve raw chunks as primary search units.
```

Reason:

```text
Raw chunk retrieval reintroduces chunking dependence, domain-specific splitting, and noisy context assembly.
```

---

### 20.3 Raw source by pointer only

Decision:

```text
Use raw sources only through provenance pointers.
```

Reason:

```text
Maintains grounding without falling back to semantic raw chunk retrieval.
```

---

### 20.4 Universal schema, not domain schema

Decision:

```text
Use generic artifact types such as claim, rule, condition, exception, procedure, concept, entity, contradiction.
```

Reason:

```text
These are domain-agnostic primitives of knowledge.
```

---

### 20.5 LLM semantic planning

Decision:

```text
Use LLM to generate semantic probes and retrieval strategy.
```

Reason:

```text
Avoids hardcoded keyword routing while improving recall.
```

---

### 20.6 Write-back

Decision:

```text
Allow valuable answers to become new synthesis artifacts.
```

Reason:

```text
Makes the knowledge base compound over time.
```

---

## 21. Risks and Mitigations

### Risk 1: Compilation loss

Problem:

```text
The LLM may fail to compile important source details into artifacts.
```

Mitigation:

```text
- multi-pass ingest
- coverage reports
- query failure-triggered reinspection
- source verification by pointer
- periodic lint
```

---

### Risk 2: Artifact drift

Problem:

```text
Wiki artifacts may drift away from original sources over repeated updates.
```

Mitigation:

```text
- mandatory source_refs
- confidence scores
- status fields
- contradiction records
- source verification
```

---

### Risk 3: Duplicate concepts

Problem:

```text
The system may create Early Repayment and Prepayment as separate concepts when they should be aliases.
```

Mitigation:

```text
- existing knowledge matching during ingest
- duplicate concept lint
- alias management
```

---

### Risk 4: Over-generalization

Problem:

```text
The LLM may merge rules that have different scopes.
```

Mitigation:

```text
- explicit scope fields
- source_refs
- conditions
- applies_to relations
- contradiction/supersession records
```

---

### Risk 5: Query misses artifact

Problem:

```text
The right artifact exists but semantic search fails to retrieve it.
```

Mitigation:

```text
- multiple embeddings per artifact
- semantic probe expansion
- index entry embeddings
- graph expansion
- optional lexical artifact search
```

---

## 22. Implementation Checklist

### Minimal viable version

```text
[ ] Raw source store
[ ] Wiki markdown store
[ ] Basic Knowledge Builder prompt
[ ] Source summary page generation
[ ] Concept/entity/rule page generation
[ ] Artifact object schema
[ ] Artifact embedding index
[ ] Query planner
[ ] Artifact vector retrieval
[ ] Context assembler
[ ] Answer agent
[ ] index.md and log.md updates
```

### Next version

```text
[ ] Graph store
[ ] Graph expansion
[ ] Contradiction detection
[ ] Coverage report
[ ] Write-back of useful answers
[ ] Multi-pass ingest
[ ] Source verification by provenance pointer
```

### Advanced version

```text
[ ] Artifact lint agent
[ ] Duplicate concept merge suggestions
[ ] Supersession detection
[ ] Evaluation set from query logs
[ ] Continuous wiki health reports
[ ] Human review workflow
[ ] Versioned artifact history
```

---

## 23. Minimal Pseudocode

### Ingest

```python
def ingest_source(source_path: str):
    source_meta = register_source(source_path)

    existing_state = load_wiki_state()

    build_result = llm_vlm_knowledge_builder(
        source=source_meta,
        existing_state=existing_state,
        schema=load_global_schema(),
    )

    write_wiki_pages(build_result.pages_to_create)
    update_wiki_pages(build_result.pages_to_update)
    write_objects(build_result.knowledge_objects)
    write_graph_edges(build_result.relationships)
    write_contradictions(build_result.contradictions)
    update_index(build_result.index_updates)
    append_log(build_result.log_entry)

    embedding_records = create_embedding_records(build_result)
    upsert_embeddings(embedding_records)

    store_coverage_report(build_result.coverage_report)

    return build_result
```

---

### Query

```python
def answer_query(user_query: str):
    plan = llm_query_planner(user_query)

    vector_candidates = []
    for probe in plan.semantic_probes:
        vector_candidates.extend(
            artifact_vector_search(
                query=probe,
                artifact_types=plan.desired_artifact_types,
            )
        )

    lexical_candidates = optional_artifact_lexical_search(user_query)

    candidates = merge_candidates(vector_candidates, lexical_candidates)
    selected = llm_rerank(user_query, candidates)

    expanded = graph_expand(
        seed_artifacts=selected,
        policy=plan.graph_expansion_policy,
    )

    artifacts = load_artifacts(selected + expanded)

    if needs_source_verification(plan, artifacts):
        verified_evidence = verify_by_source_pointers(artifacts)
    else:
        verified_evidence = []

    context_packet = build_context_packet(
        query=user_query,
        artifacts=artifacts,
        verified_evidence=verified_evidence,
    )

    answer = llm_answer_agent(context_packet)

    if should_write_back(answer):
        write_back_synthesis(answer, context_packet)

    return answer
```

---

## 24. Final Mental Model

Think of this system as a knowledge compiler.

```text
Raw documents = source code
LLM/VLM Knowledge Builder = compiler
Wiki pages = readable compiled knowledge
Knowledge objects = structured intermediate representation
Graph = symbol/reference graph
Embeddings = semantic index over compiled artifacts
Query orchestrator = runtime planner
Context builder = execution context packer
Answer agent = interpreter
Write-back = incremental compilation
Lint = static analysis
```

The most important principle:

```text
Build knowledge first. Retrieve artifacts later.
```

This keeps the system general, avoids domain-specific chunking, and allows knowledge to compound over time.
