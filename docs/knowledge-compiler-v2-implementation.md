# Knowledge Compiler V2

Tài liệu này mô tả phase Knowledge Compiler V2 đã được triển khai. Blueprint dài hạn nằm
tại `docs/artifact-first-llm-wiki-foundation.md`.

## Pipeline

```text
register
  -> profiling
  -> dynamic compilation passes
  -> provenance validation
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
- Factual statements có subject, predicate, object và evidence refs.
- Review items và covered unit IDs.

Backend không map provenance bằng locator. Locator chỉ dùng để hiển thị và citation.
Evidence ID ổn định được tạo từ `source_id + evidence.local_id`.

## Validation và retry

Mỗi pass chỉ được merge khi:

- Evidence/artifact local IDs hợp lệ.
- Mọi source-backed artifact và factual statement có evidence.
- Relation không có dangling artifact/evidence reference.
- Covered units tồn tại trong manifest.

Pass lỗi được lưu trạng thái `failed`, sau đó retry với lỗi validation được đưa lại cho
model. Output lỗi không được merge vào compilation state.

## Coverage gate

Auditor phải tạo đúng một assessment cho từng semantic source unit, gồm tri thức đã biểu
diễn, tri thức còn thiếu, trạng thái và confidence.

Backend không chấp nhận `complete` nếu còn unit incomplete, missing knowledge, coverage gap
hoặc provenance issue. Auditor có thể đề xuất follow-up pass. Nếu hết budget mà vẫn còn gap,
source kết thúc với `needs_review`.

## Persistence

Migration `knowledge_compiler_v2` thêm:

- `compiler_runs`, `compiler_passes`.
- `source_manifests`, `source_units`.
- `artifacts`, `artifact_versions`, `artifact_evidence`, `artifact_relations`.
- `coverage_reports`.
- `artifacts_fts`, `artifact_relations_fts`.

Compiler run lưu model, compiler/prompt/schema version, source hash, stage, pass count,
coverage status và lỗi.

## Graph tự động

Artifact statements được projection sang claim/evidence read model hiện tại. Sau integration,
ingest tự gọi graph builder trong đúng source scope. Nút frontend `Dựng lại graph` chỉ là
thao tác quản trị.

## Inspection API

```text
GET /api/sources/{source_id}/compilation
```

Response gồm latest compiler run, manifest, pass statuses, coverage reports và artifacts.

## Cấu hình

```bash
LLM_WIKI_COMPILER_VERSION=knowledge-compiler-v2
LLM_WIKI_COMPILER_PROMPT_VERSION=compiler-prompts-v2
LLM_WIKI_COMPILER_SCHEMA_VERSION=compiler-schema-v2
LLM_WIKI_COMPILER_MAX_PASSES=8
LLM_WIKI_COMPILER_MAX_PASS_RETRIES=2
LLM_WIKI_COMPILER_MAX_AUDIT_ITERATIONS=2
```

## Smoke test thật

`docs/artifact-first-llm-wiki-foundation.md` đã được ingest bằng OpenAI API trong database
tạm:

- 15 semantic source units.
- 7 successful passes, gồm follow-up do auditor đề xuất.
- 13 evidence, 16 artifacts, 32 factual claims và 32 graph relations.
- Không có duplicate evidence local ID, dangling provenance hoặc claim thiếu evidence.
- Auditor giữ `incomplete` cho một gap chi tiết, nên source được đánh dấu `needs_review`.
- Query tiếng Việt về compilation loss trả lời đúng từ phần failure modes với citation.

Kết quả này xác nhận quality gate hoạt động bảo thủ, không đánh dấu `complete` chỉ vì đã
chạy hết pass.
