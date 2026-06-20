# Knowledge Compiler V6 Source Ledger

Tài liệu này mô tả phase Knowledge Compiler hiện đang được triển khai. File vẫn giữ tên
`knowledge-compiler-v2-implementation.md` để không làm gãy liên kết cũ, nhưng cấu hình
mặc định hiện tại là `knowledge-compiler-v6-source-ledger`. Blueprint dài hạn nằm tại
`docs/artifact-first-llm-wiki-foundation.md`.

## Pipeline

```text
register
  -> profiling
  -> observed detail inventory
  -> dynamic semantic-unit compilation plan execution
  -> source-unit ledger accounting
  -> provenance validation
  -> detail-aware coverage audit
  -> optional consolidated selective repair pass
  -> artifact/wiki integration
  -> automatic graph build
  -> semantic artifact index
  -> ingested | needs_review | failed
```

Semantic Artifact Retrieval đã được thêm sau phase compiler: artifact representations được
embed bằng model cấu hình qua `LLM_WIKI_EMBEDDING_MODEL`, vector lưu trong SQLite, và
Artifact FTS5 tiếp tục phục vụ exact retrieval. Artifact Store không phải đổi vì embedding
được lập trên compiled artifacts, statements, relations và wiki map thay vì raw chunks.

## Contract

`SourceManifest` do LLM/VLM sinh gồm document profile, semantic content units có local ID,
`observed_details`, knowledge lenses mở và dynamic compilation plan.

`observed_details` không phải raw chunks hoặc keyword list. Đây là các chi tiết có thể
kiểm chứng mà profiler nhìn thấy trong từng source unit, có `detail_kind` mở, locator,
`source_unit_id`, importance và query hint semantic. Backend không hiểu meaning của chúng;
backend chỉ dùng ID để kiểm provenance và coverage. Manifest là bản đồ điều hướng, không
phải trần coverage.

Mỗi compilation pass sinh:

- `ledger_items` cho từng target source unit, tức inventory các source details/factual
  obligations độc lập cần được cover hoặc đánh dấu missing/weak.
- `discovered_details` cho factual details độc lập mà raw source có nhưng manifest bỏ sót.
- Evidence có `local_id` source-scoped unique.
- Artifact type và relation type là open strings.
- Factual statements có subject, predicate, object, source unit IDs và evidence refs.
- `detail_coverage` map observed/ledger/discovered detail sang evidence, artifact và statement refs.
- Review items và covered unit IDs.

Backend không map provenance bằng locator. Locator chỉ dùng để hiển thị và citation.
Evidence ID ổn định được tạo từ `source_id + evidence.local_id`.

V6 giữ hướng foundation domain-agnostic: backend không tạo checklist semantic bằng
keyword, regex, taxonomy cố định hoặc cấu trúc tài liệu hard-code. Source profiling,
compilation pass, artifact type, semantic node và relation type được suy luận qua contract
mở của LLM/VLM.

Khác V5, mỗi pass không được chỉ trả artifacts/evidence. Pass phải tạo `ledger_items` cho
mọi target unit và mỗi ledger item phải có `detail_coverage` tương ứng, kể cả khi coverage
đang `missing`, `weak` hoặc `ambiguous`. Nhờ đó một chi tiết nguồn không thể biến mất im lặng
giữa source unit và artifact store.

Khác V3, hệ thống không chạy hardening pass toàn nguồn mặc định. Đường bình thường là chạy
`compilation_plan` do profiler sinh theo các semantic source units, sau đó audit/gate quyết
định có cần repair hay không. Ingest chừa một phần pass budget cho repair khi còn gap; nếu
có nhiều gap, ingest gộp chúng thành một selective repair pass trong iteration đó để giảm chi
phí và latency.

Với file text-bearing như Markdown, text, ODT và DOCX, ingest cung cấp thêm
`SOURCE_TEXT_CONTEXT_JSON` cho profiler/compiler/auditor. Đây là bản đọc phụ trợ có locator
đoạn ổn định để giảm compilation loss khi model đọc file văn phòng; nó không phải raw chunk
retrieval corpus, không được embed như chunk, không quyết định semantic routing và không thay
thế raw source làm nguồn thẩm quyền.

## Validation và retry

Mỗi pass chỉ được merge khi qua structural provenance validation:

- Evidence/artifact local IDs hợp lệ.
- Mọi source-backed artifact và factual statement có evidence.
- Relation không có dangling artifact/evidence reference.
- Covered units tồn tại trong manifest.
- `covered_unit_ids` phải được suy ra từ chuỗi provenance evidence + artifact + atomic
  statement, không phải model tự khai báo tùy ý.
- Mỗi pass phải có ledger item cho mọi target source unit và mọi ledger item phải có
  `detail_coverage` entry.
- `detail_coverage` chỉ được tham chiếu observed/ledger/discovered detail, evidence, artifact và
  statement hợp lệ. Detail `covered` phải có đủ evidence, artifact và statement ref; nếu các
  ref không thật sự hỗ trợ đúng source unit của detail, coverage gate không tính detail đó là
  supported và sẽ sinh repair gap thay vì làm sập ingest.
- `ledger_items` và `discovered_details` phải có source unit hợp lệ; nếu dùng lại local ID từ
  manifest detail thì source unit phải nhất quán.

Pass lỗi được lưu trạng thái `failed`, sau đó retry với lỗi validation được đưa lại cho
model. Output lỗi không được merge vào compilation state.

Thiếu coverage semantic không còn được xử lý bằng retry mù của cùng pass. Nếu JSON/provenance
hợp lệ nhưng còn thiếu tri thức, auditor và coverage gate sẽ sinh repair pass chọn lọc.

## Coverage gate

Auditor phải tạo đúng một assessment cho từng semantic source unit và từng observed, ledger
hoặc discovered detail, gồm tri thức đã biểu diễn, tri thức còn thiếu, trạng thái và confidence.
Nếu auditor phát hiện source detail quan trọng chưa có trong manifest/ledger/discovered details,
nó trả `additional_details`; ingest promote các detail này vào ledger rồi coverage gate sinh
repair gap cụ thể.

Backend không chấp nhận `complete` nếu còn unit incomplete, missing knowledge, coverage gap
hoặc provenance issue. Khi manifest có observed details, backend cũng không chấp nhận
`complete` nếu còn detail chưa có chuỗi evidence + artifact + atomic statement hợp lệ.

Coverage gate chỉ kiểm tra invariant kỹ thuật: mọi semantic source unit và observed/ledger/discovered
detail phải có chuỗi representation được nối qua evidence, artifact và atomic statement.
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
LLM_WIKI_COMPILER_VERSION=knowledge-compiler-v6-source-ledger
LLM_WIKI_COMPILER_PROMPT_VERSION=compiler-prompts-v6
LLM_WIKI_COMPILER_SCHEMA_VERSION=compiler-schema-v6
LLM_WIKI_COMPILER_MAX_PASSES=5
LLM_WIKI_COMPILER_MAX_PASS_RETRIES=1
LLM_WIKI_COMPILER_MAX_AUDIT_ITERATIONS=3
LLM_WIKI_SOURCE_TEXT_CONTEXT_MAX_CHARS=120000
```

## Kiểm thử

Automated regression tests bao phủ các điểm Phase 1 quan trọng:

- Complete path chỉ cần các pass trong manifest plan và một coverage audit cuối.
- Ingest dùng dynamic compilation plan từ manifest thay vì ép mọi source vào một pass tổng quát.
- Compiler pass bị reject nếu target source unit không có ledger item hoặc ledger item không có
  `detail_coverage`.
- Coverage gate tạo repair gap cho ledger detail chưa được evidence/artifact/statement support.
- Auditor có thể trả `additional_details`; ingest promote chúng vào ledger để repair pass target được.
- ODT text context giữ nguyên các đoạn nguồn quan trọng để compiler/auditor có thể đối chiếu.
- Coverage gap sinh selective repair pass gộp và audit lại.
- Validator từ chối dangling references, missing provenance và covered-unit inconsistency.
- Coverage gate không cho `complete` khi source unit chưa có chuỗi evidence + artifact +
  atomic statement.
- Coverage gate không cho `complete` khi observed detail bị report là covered nhưng thiếu
  `detail_coverage` hợp lệ.
- Compiler có thể thêm và cover `discovered_details` khi manifest bỏ sót factual details.
- Artifact relations được sinh từ statement và tham gia query retrieval.
- Projection tạo fallback entity cho subject lặp lại mà không dùng cue semantic hard-code.

Khi chạy smoke test thật với tài liệu mẫu, dùng database/wiki tạm rồi xóa sau khi phân tích
để không trộn dữ liệu đánh giá vào runtime state của người dùng.
