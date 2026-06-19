# Knowledge Compiler V3 Quality

Tài liệu này mô tả phase Knowledge Compiler hiện đang được triển khai. File vẫn giữ tên
`knowledge-compiler-v2-implementation.md` để không làm gãy liên kết cũ, nhưng cấu hình
mặc định hiện tại là `knowledge-compiler-v3-quality`. Blueprint dài hạn nằm tại
`docs/artifact-first-llm-wiki-foundation.md`.

## Pipeline

```text
register
  -> profiling
  -> dynamic compilation passes
  -> provenance validation
  -> coverage hardening pass
  -> coverage audit
  -> optional follow-up passes
  -> artifact/wiki integration
  -> automatic graph build
  -> ingested | needs_review | failed
```

Embedding chưa được dùng trong phase này. Artifact FTS5 đã được tạo để phục vụ exact
retrieval và làm nền cho semantic retrieval phase sau. Khi thêm embedding, vector sẽ được
lưu SQLite trước và model embedding sẽ là cấu hình riêng; Artifact Store không phải đổi.

## Contract

`SourceManifest` do LLM/VLM sinh gồm document profile, semantic content units có local ID,
knowledge lenses mở và dynamic compilation plan.

Mỗi compilation pass sinh:

- Evidence có `local_id` source-scoped unique.
- Artifact type và relation type là open strings.
- Factual statements có subject, predicate, object, source unit IDs và evidence refs.
- Review items và covered unit IDs.

Backend không map provenance bằng locator. Locator chỉ dùng để hiển thị và citation.
Evidence ID ổn định được tạo từ `source_id + evidence.local_id`.

V3-quality giữ hướng foundation domain-agnostic: backend không tạo checklist semantic bằng
keyword, regex, taxonomy cố định hoặc cấu trúc tài liệu hard-code. Source profiling,
compilation pass, artifact type, semantic node và relation type được suy luận qua contract
mở của LLM/VLM. Sau các pass chính, hệ thống vẫn chạy một hardening pass toàn nguồn trước
coverage audit để model tự rà compilation loss theo chính ngữ cảnh của source.

## Validation và retry

Mỗi pass chỉ được merge khi:

- Evidence/artifact local IDs hợp lệ.
- Mọi source-backed artifact và factual statement có evidence.
- Relation không có dangling artifact/evidence reference.
- Covered units tồn tại trong manifest.
- `covered_unit_ids` phải được suy ra từ chuỗi provenance evidence + artifact + atomic
  statement, không phải model tự khai báo tùy ý.

Pass lỗi được lưu trạng thái `failed`, sau đó retry với lỗi validation được đưa lại cho
model. Output lỗi không được merge vào compilation state.

## Coverage gate

Auditor phải tạo đúng một assessment cho từng semantic source unit, gồm tri thức đã biểu
diễn, tri thức còn thiếu, trạng thái và confidence.

Backend không chấp nhận `complete` nếu còn unit incomplete, missing knowledge, coverage gap
hoặc provenance issue. Coverage gate chỉ kiểm tra invariant kỹ thuật: mọi semantic source
unit phải có chuỗi representation được nối qua evidence, artifact và atomic statement.
Semantic completeness vẫn là trách nhiệm của profiler/compiler/auditor qua raw source và
contract mở; khi không chắc, auditor đề xuất follow-up pass hoặc review item. Nếu hết
budget mà vẫn còn gap, source kết thúc với `needs_review`.

## Persistence

Migration `knowledge_compiler_v2` thêm:

- `compiler_runs`, `compiler_passes`.
- `source_manifests`, `source_units`.
- `artifacts`, `artifact_versions`, `artifact_evidence`, `artifact_relations`.
- `artifact_statements`, `artifact_statement_evidence`, `compiled_semantic_nodes`.
- `coverage_reports`.
- `artifacts_fts`, `artifact_relations_fts`.

Compiler run lưu model, compiler/prompt/schema version, source hash, stage, pass count,
coverage status và lỗi.

## Graph tự động

Artifact statements được projection sang claim/evidence read model hiện tại. Mỗi atomic
statement cũng sinh một artifact relation để relation retrieval không phụ thuộc hoàn toàn
vào explicit relations từ model. Projection có fallback entity cho statement subject lặp lại
khi model bỏ sót semantic node, nhưng không suy luận alias/entity bằng keyword hay cue ngôn
ngữ từ raw text. Sau integration, ingest tự gọi graph builder trong đúng source scope. Nút
frontend `Dựng lại graph` chỉ là thao tác quản trị.

## Inspection API

```text
GET /api/sources/{source_id}/compilation
```

Response gồm latest compiler run, manifest, pass statuses, coverage reports và artifacts.

## Cấu hình

```bash
LLM_WIKI_MAX_OUTPUT_TOKENS=16000
LLM_WIKI_COMPILER_VERSION=knowledge-compiler-v3-quality
LLM_WIKI_COMPILER_PROMPT_VERSION=compiler-prompts-v3
LLM_WIKI_COMPILER_SCHEMA_VERSION=compiler-schema-v3
LLM_WIKI_COMPILER_MAX_PASSES=16
LLM_WIKI_COMPILER_MAX_PASS_RETRIES=2
LLM_WIKI_COMPILER_MAX_AUDIT_ITERATIONS=2
```

## Kiểm thử

Automated regression tests bao phủ các điểm Phase 1 quan trọng:

- Coverage gap sinh follow-up pass và audit lại.
- Hardening pass luôn chạy trước audit khi còn pass budget.
- Validator từ chối dangling references, missing provenance và covered-unit inconsistency.
- Coverage gate không cho `complete` khi source unit chưa có chuỗi evidence + artifact +
  atomic statement.
- Artifact relations được sinh từ statement và tham gia query retrieval.
- Projection tạo fallback entity cho subject lặp lại mà không dùng cue semantic hard-code.

Khi chạy smoke test thật với tài liệu mẫu, dùng database/wiki tạm rồi xóa sau khi phân tích
để không trộn dữ liệu đánh giá vào runtime state của người dùng.
