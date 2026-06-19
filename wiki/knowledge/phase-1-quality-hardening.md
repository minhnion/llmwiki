---
page_type: project_note
title: Phase 1 Foundation Alignment
status: active
sources:
  - docs/knowledge-compiler-v2-implementation.md
  - docs/implementation-architecture-current.md
  - backend/app/services/source_ingest.py
  - backend/app/services/compilation_validator.py
  - backend/app/repositories/compiler.py
  - backend/app/services/artifact_projector.py
claims:
  - phase1-open-contract-hardening
  - provenance-only-deterministic-validation
  - domain-agnostic-artifact-projection
  - statement-derived-artifact-relations
  - recurring-subject-entity-fallback
confidence: 0.9
created_at: 2026-06-18
updated_at: 2026-06-19
---

# Phase 1 Foundation Alignment

Phase 1 phải giữ đúng hướng foundation chatbot: backend kiểm tra invariant kỹ thuật và
provenance, còn cấu trúc tri thức, artifact type, semantic node, relation type và mức độ
quan trọng của nội dung được suy luận qua contract mở của LLM/VLM. Hệ thống không hard-code
keyword, regex, taxonomy domain hoặc cấu trúc tài liệu để tối ưu cho một corpus mẫu.

## Decisions

- Ingest chạy thêm một hardening pass toàn nguồn trước coverage audit khi còn pass budget,
  nhưng pass này là LLM-directed và domain-agnostic.
- Validator chỉ chặn lỗi contract: dangling reference, thiếu evidence/source unit,
  provenance không nhất quán và `covered_unit_ids` không khớp chuỗi evidence + artifact +
  atomic statement.
- Coverage gate tự chặn `complete` khi source unit chưa có representation được provenance
  gate xác nhận; semantic completeness nằm ở compiler/auditor và review items.
- Mỗi atomic statement sinh thêm artifact relation để query retrieval có thể bắt được quan
  hệ ngay cả khi model không khai báo explicit relation.
- Projection tạo fallback entity cho statement subject lặp lại khi semantic node bị thiếu,
  nhưng không suy luận alias/entity bằng cue ngôn ngữ hoặc regex semantic.

## Links

- [[../schema|Quy ước Wiki]]
- [[../purpose|Mục đích Wiki]]
