# Artifact-first LLM Wiki Foundation

## 1. Mục tiêu

Tài liệu này là blueprint kỹ thuật cho một chatbot tri thức tổng quát dựa trên concept
LLM Wiki. Foundation phải hoạt động với nhiều domain, ngôn ngữ và định dạng tài liệu mà
không phụ thuộc vào taxonomy nghiệp vụ, keyword, regex hay quy tắc chia nội dung được
hard-code cho một loại tài liệu cụ thể.

Mục tiêu không phải xây một hệ thống RAG truyền thống tốt hơn. Mục tiêu là xây một
**knowledge compiler**:

```text
Raw sources bất biến
  -> LLM/VLM hiểu nguồn
  -> biên dịch thành artifacts có provenance
  -> tích hợp vào wiki và knowledge graph
  -> lập semantic index trên artifacts
  -> truy vấn trên tri thức đã biên dịch
  -> đọc lại nguồn khi phát hiện khoảng trống
  -> ghi tri thức hữu ích trở lại wiki
```

Thành công được đo bằng khả năng tích lũy tri thức, duy trì provenance, cải thiện sau
mỗi lần ingest/query và trả lời tốt trên corpus đa domain; không được đo đơn thuần bằng
số lượng chunk hoặc số vector.

## 2. Các nguyên tắc không được vi phạm

### 2.1 General-purpose

Không được hard-code:

- Domain taxonomy như ngân hàng, y tế, pháp luật hoặc kỹ thuật.
- Danh sách keyword để route query hoặc chọn extractor.
- Regex nhận diện cấu trúc nghiệp vụ như chương, điều, mục, bệnh, tài khoản hoặc API.
- Giả định mọi tài liệu đều có mục lục, heading, trang, sheet hoặc cấu trúc phân cấp.
- Schema entity hoặc relation chỉ phù hợp với một domain.
- Fixed-size chunk và overlap làm đơn vị tri thức hoặc retrieval chính.
- Prompt yêu cầu mọi nguồn đều phải sinh cùng một bộ artifact nghiệp vụ.

Foundation được phép có các contract hạ tầng tổng quát:

- Stable ID, source hash, timestamps, status và version.
- Provenance từ artifact tới evidence và raw source.
- Transaction, validation, retry, idempotency và audit log.
- Open artifact schema và open relation schema.
- Coverage, confidence, review state và quality gate.
- Giới hạn kỹ thuật của API như kích thước file hoặc context window.

Contract hạ tầng là cơ chế đảm bảo tính đúng đắn; nó không phải domain rule.

### 2.2 Artifact-first, không phải artifact-only

Artifact là retrieval substrate chính. Raw source vẫn là source of truth và được dùng để:

- Kiểm chứng claim quan trọng.
- Đọc lại khi artifact thiếu hoặc có độ tin cậy thấp.
- Biên dịch bổ sung sau một query thất bại.
- Rebuild artifacts khi prompt, model hoặc schema thay đổi.

Không xây raw-chunk vector corpus làm đường retrieval chính. Tuy nhiên không được cấm
model đọc lại raw source chỉ vì hệ thống mang tên artifact-first.

### 2.3 LLM/VLM-driven

Khi một quyết định phụ thuộc vào ý nghĩa nội dung, ưu tiên LLM/VLM:

- Nhận diện cấu trúc thể hiện trong chính tài liệu.
- Lập kế hoạch đọc và biên dịch.
- Đề xuất artifact types và relations.
- Tìm semantic candidates.
- Match artifact mới với knowledge hiện có.
- Đánh giá coverage, contradiction và knowledge gap.

Code deterministic chịu trách nhiệm cho storage, validation, orchestration, provenance,
deduplication, transaction và policy enforcement.

### 2.4 Compounding knowledge

Ingest không chỉ tạo source summary. Một source có thể:

- Tạo nhiều artifacts.
- Tạo hoặc cập nhật nhiều wiki pages.
- Bổ sung aliases và relations.
- Phát hiện contradiction/supersession.
- Cập nhật knowledge map.
- Cập nhật semantic indexes.

Query chất lượng cao có thể tạo synthesis artifact. Query thất bại có thể kích hoạt
source re-inspection và làm knowledge base đầy đủ hơn.

## 3. Kiến trúc đích

```text
                         Raw Source Store
                                |
                                v
                    Direct Multimodal Reader
                                |
                                v
                    LLM Source Profiler
                                |
                     Source Manifest + Plan
                                |
                                v
                 Multi-pass Knowledge Compiler
                                |
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
      Evidence Store       Artifact Store         Wiki Store
          |                     |                     |
          +---------------------+---------------------+
                                |
                                v
                    Integrated Knowledge Graph
                                |
                                v
                        Coverage Auditor
                                |
                                v
       FTS over artifacts + artifact embeddings + knowledge maps
                                |
                                v
                       Query Orchestrator
                                |
                  LLM semantic navigation/rerank
                                |
                                v
                   Context and Grounding Builder
                                |
               optional direct source re-inspection
                                |
                                v
                          Answer Agent
                                |
                       optional write-back
```

## 4. Các lớp dữ liệu

### 4.1 Raw Source Store

Raw source được lưu nguyên trạng và định danh theo content hash.

Metadata tối thiểu:

```json
{
  "id": "src_*",
  "path": "raw/sources/example.odt",
  "sha256": "...",
  "mime_type": "...",
  "source_type": "odt",
  "language": "vi",
  "status": "compiled",
  "compiler_version": "knowledge-compiler-v2",
  "created_at": "...",
  "ingested_at": "..."
}
```

Không sửa raw source sau upload. Re-ingest tạo source version hoặc compiler run mới.

### 4.2 Source Manifest

`SourceManifest` là bản đồ do LLM/VLM tạo sau khi đọc nguồn. Nó mô tả tài liệu theo
những gì nguồn thực sự thể hiện, không theo một template domain cố định.

Ví dụ contract mở:

```json
{
  "source_id": "src_*",
  "language": "vi",
  "document_profile": {
    "kind": "model-generated open string",
    "summary": "...",
    "modalities": ["text", "table"],
    "confidence": 0.94
  },
  "content_units": [
    {
      "local_id": "unit_001",
      "label": "...",
      "locator": {
        "kind": "section",
        "value": "..."
      },
      "summary": "...",
      "importance": 0.82
    }
  ],
  "candidate_knowledge_lenses": [
    {
      "name": "model-generated open string",
      "reason": "...",
      "priority": 0.9
    }
  ],
  "compilation_plan": [
    {
      "pass_id": "pass_*",
      "objective": "...",
      "target_unit_ids": ["unit_001"],
      "expected_outputs": ["model-generated artifact hints"]
    }
  ]
}
```

`content_units` không phải fixed chunks. Chúng là đơn vị điều hướng do model suy luận.
Tùy nguồn, đó có thể là:

- Một ý hoặc nhóm ý.
- Một bảng hoặc biểu đồ.
- Một slide.
- Một sheet.
- Một scene.
- Một module code.
- Một vùng ảnh.
- Một nhóm nội dung không có tên.

Nếu tài liệu đủ nhỏ, model có thể đọc toàn bộ source trong mỗi pass mà không cần phân
đơn vị vật lý.

### 4.3 Evidence Store

Evidence là dữ liệu bám sát nguồn, dùng để kiểm chứng artifact và citation.

```json
{
  "id": "ev_*",
  "source_id": "src_*",
  "local_id": "source-scoped stable local ID",
  "locator": {
    "kind": "page | section | sheet | slide | image | region | logical",
    "value": "...",
    "metadata": {}
  },
  "modality": "open string",
  "content": "...",
  "summary": "...",
  "confidence": 0.93
}
```

Artifact và claim phải tham chiếu `evidence.local_id` hoặc `evidence.id`, không tham
chiếu một chuỗi locator không unique. Nhiều evidence được phép có cùng page/section.

### 4.4 Artifact Store

Artifact là đơn vị tri thức có thể retrieve, link, version và đưa vào wiki.

Artifact schema phải mở:

```json
{
  "id": "art_*",
  "artifact_type": "model-generated open string",
  "title": "...",
  "summary": "...",
  "content": {},
  "aliases": [],
  "scope": {},
  "source_refs": [
    {
      "source_id": "src_*",
      "evidence_ids": ["ev_*"],
      "confidence": 0.92
    }
  ],
  "related_artifact_ids": [],
  "confidence": 0.9,
  "status": "active",
  "review_status": "unreviewed",
  "created_at": "...",
  "updated_at": "...",
  "metadata": {}
}
```

Các tên như `claim`, `concept`, `entity`, `rule`, `condition`, `formula`, `procedure`,
`event`, `metric`, `exception` là generic hints hữu ích cho model, không phải enum đóng.
Model được phép đề xuất artifact type khác khi nguồn cần biểu diễn khác.

Backend chỉ validate:

- Type là chuỗi hợp lệ.
- Artifact có title/content.
- Source-backed artifact có provenance.
- Status và review state tuân theo lifecycle chung.

### 4.5 Wiki Markdown Store

Wiki là lớp tri thức dễ đọc và dễ duyệt. SQLite artifacts là atomic IR; Markdown pages
là views/syntheses có giá trị cho con người và LLM.

Không tạo một file cho mọi atomic artifact. Page planner quyết định:

- Artifact nào cần trang riêng.
- Artifact nào hợp nhất vào concept/topic page.
- Trang hiện có nào cần cập nhật.
- Cross-links nào cần tạo.
- Summary nào cần viết lại sau khi có nguồn mới.

Mỗi generated page phải có frontmatter:

```yaml
---
id: page_*
title: ...
type: model-generated-open-type
status: active
sources:
  - src_*
artifacts:
  - art_*
confidence: 0.91
review_status: unreviewed
created_at: ...
updated_at: ...
---
```

`wiki/index.md` là catalog/routing layer. `wiki/map.md` có thể là semantic knowledge
map do LLM duy trì. `wiki/log.md` là append-only operational history.

### 4.6 Knowledge Graph

Graph là output bắt buộc của ingest, không phải thao tác tùy chọn của người dùng.

Ba lớp graph cùng tồn tại:

```text
Wiki graph:
  page -> wikilink -> page

Provenance graph:
  source -> evidence -> artifact -> page

Semantic graph:
  artifact/entity/concept -> typed relation -> artifact/entity/concept/literal
```

Relation schema mở:

```json
{
  "id": "edge_*",
  "source_node_id": "art_*",
  "target_node_id": "art_* | literal_*",
  "relation_type": "model-generated open string",
  "source_refs": ["ev_*"],
  "qualifiers": {},
  "confidence": 0.88,
  "status": "active"
}
```

LLM có thể dùng các primitives tổng quát như `related_to`, `part_of`, `supports`,
`contradicts`, `depends_on`, `derived_from`, nhưng không bị giới hạn bởi danh sách này.

Mọi edge semantic phải có evidence hoặc bị đánh dấu review-only.

### 4.7 Semantic Navigation Index

Semantic index chỉ lập trên compiled knowledge:

- Artifact title, summary và content projection.
- Wiki page summary và các section có nghĩa.
- Knowledge-map entries.
- Relation descriptions.
- Contradiction và synthesis artifacts.

Không tạo vector index chính trên arbitrary raw chunks.

Mỗi artifact có thể có nhiều representation:

```text
summary representation
detail representation
question-style representation
relation representation
```

Vector được lưu trong SQLite ở giai đoạn đầu. External vector database chỉ được thêm
khi evaluation chứng minh SQLite không đáp ứng scale/latency.

## 5. Ingest pipeline

Ingest là một transaction logic gồm nhiều stage. Bên ngoài vẫn là một job duy nhất.

```text
registered
  -> profiling
  -> planned
  -> compiling
  -> integrating
  -> graphing
  -> auditing
  -> indexing
  -> completed | needs_review | failed
```

### 5.1 Register source

- Lưu file bất biến.
- Tính SHA-256.
- Tạo source/version.
- Detect duplicate theo content.
- Ghi compiler/prompt/schema version.

### 5.2 Direct multimodal profiling

LLM/VLM đọc trực tiếp file và sinh `SourceManifest`.

Prompt phải yêu cầu model:

- Mô tả cấu trúc mà model quan sát được, không áp template có sẵn.
- Xác định modality và vùng khó đọc.
- Đề xuất knowledge lenses phù hợp với nguồn.
- Lập compilation plan để bao phủ nguồn.
- Gắn stable local IDs cho content units.

Không dùng keyword/regex domain để chọn plan.

### 5.3 Capacity handling

Nếu file nằm trong giới hạn context/API, ưu tiên đọc toàn bộ file.

Nếu vượt giới hạn, physical batching chỉ là transport concern:

- PDF: page batch.
- Presentation: slide batch.
- Spreadsheet: sheet/range batch.
- Image collection: image batch.
- Rich document: provider-supported range hoặc logical unit từ manifest.

Batch không trở thành retrieval chunks. Sau các batch phải có global synthesis pass để
khôi phục context toàn tài liệu.

Boundary strategy được chọn theo capability metadata và model plan; không dựa trên
domain keyword.

### 5.4 Dynamic multi-pass compilation

Compiler chạy các pass do `SourceManifest.compilation_plan` đề xuất. Không có một danh
sách pass bắt buộc cho mọi nguồn.

Mỗi pass nhận:

```text
source hoặc target source units
+ source manifest
+ existing wiki/knowledge candidates
+ output schema mở
+ provenance requirements
```

Mỗi pass trả:

- Evidence có local ID unique.
- Candidate artifacts.
- Candidate relations.
- Candidate page updates.
- Uncertainty/review items.
- Coverage claims đối với units đã đọc.

Orchestrator có thể giới hạn số pass, token/cost và retry, nhưng không quyết định nội
dung tri thức bằng hard-coded domain rules.

### 5.5 Existing knowledge matching

Trước khi tạo artifact/page:

1. LLM tạo semantic identity description cho candidate.
2. Search artifact embeddings và artifact FTS.
3. Load top candidates cùng provenance/scope.
4. LLM quyết định `create`, `update`, `link`, `possible_duplicate` hoặc `conflict`.
5. Ambiguous match trở thành review item, không tự merge.

### 5.6 Artifact and wiki integration

Integration plan phải được validate trước khi write:

- Artifact IDs và evidence refs tồn tại.
- Không có source-backed claim thiếu provenance.
- Update không làm mất source refs cũ.
- Page links trỏ tới stable page IDs/path.
- Write deterministic và transaction-aware.

SQLite là machine state chính. Markdown write và SQLite commit phải có recovery plan để
không rơi vào trạng thái một bên đã cập nhật, một bên chưa cập nhật.

### 5.7 Graph integration

Graph chạy ngay trong ingest:

1. Upsert provenance nodes/edges.
2. Resolve semantic identity bằng artifact matching.
3. Upsert semantic relations.
4. Detect contradiction/supersession candidates với knowledge liên quan.
5. Update graph-backed entity/concept pages.

Normal user flow không có bước “Build graph”.

Nút quản trị có thể tồn tại cho:

- Rebuild graph.
- Repair graph.
- Re-run entity/artifact resolution.
- Re-run contradiction detection.

### 5.8 Coverage audit

Một auditor call tách biệt so sánh:

```text
raw source + source manifest
vs
evidence + artifacts + wiki updates + graph
```

Auditor trả:

```json
{
  "coverage_status": "complete | incomplete | needs_review",
  "covered_unit_ids": [],
  "missing_or_weak_areas": [
    {
      "description": "...",
      "likely_unit_ids": [],
      "severity": "high",
      "recommended_pass": {
        "objective": "...",
        "target_unit_ids": []
      }
    }
  ],
  "provenance_issues": [],
  "overgeneralization_risks": [],
  "confidence": 0.87
}
```

Nếu thiếu coverage:

- Chạy follow-up pass do auditor đề xuất.
- Merge output.
- Audit lại trong giới hạn iteration.
- Chỉ đánh dấu `completed` khi đạt quality gate; nếu không, dùng `needs_review`.

Coverage không đo bằng số artifact cố định. Nó đo xem knowledge units quan trọng do
model nhận diện đã được biểu diễn và truy ngược về source hay chưa.

### 5.9 Indexing

Sau khi quality gate đạt:

- Update artifact FTS.
- Tạo artifact embeddings.
- Update knowledge map/index.
- Update graph indexes.
- Append ingest log.
- Frontend tự refresh wiki và graph.

## 6. Query pipeline

### 6.1 Query understanding

LLM planner trả một plan semantic:

```json
{
  "intent": "open string",
  "target_meaning": "...",
  "semantic_probes": [],
  "desired_artifact_hints": [],
  "answer_requirements": {},
  "evidence_strictness": "low | medium | high",
  "graph_policy": {
    "max_depth": 2,
    "max_nodes": 16,
    "relation_hints": []
  },
  "source_scope": []
}
```

`desired_artifact_hints` và `relation_hints` là soft hints do LLM sinh cho từng query,
không phải routing enum hard-code.

### 6.2 LLM hierarchical navigation

LLM không đọc toàn bộ artifact corpus trong một prompt. Hệ thống duy trì:

```text
global knowledge map
  -> dynamic topic/cluster maps
  -> artifact catalogs
  -> full artifacts
```

Các cluster được LLM tạo/cập nhật theo corpus. Chúng không phải taxonomy domain cố định.

Query navigator:

1. Đọc global map.
2. Chọn các nhánh semantic có khả năng liên quan.
3. Đọc catalog của nhánh.
4. Đề xuất artifact candidates và lý do.

Ở corpus nhỏ, LLM navigation có thể là retrieval chính. Ở corpus lớn, embedding/FTS
đóng vai trò candidate accelerator.

### 6.3 Hybrid artifact retrieval

Hybrid retrieval gồm:

```text
LLM hierarchical navigation
+ artifact embedding search
+ artifact/wiki FTS
+ index/map candidates
```

Không bao gồm raw chunk vector search trong core path.

Vai trò từng channel:

- LLM navigation: hiểu intent và chọn vùng tri thức.
- Embedding: semantic recall.
- FTS: exact name, code, date, number, phrase và locator.
- Index/map: corpus-level routing.

Candidate fusion nên dùng signal-aware ranking hoặc Reciprocal Rank Fusion, không cộng
trọng số tùy ý rồi coi các channel có cùng ý nghĩa.

### 6.4 LLM reranking

Reranker đọc:

- Query plan.
- Candidate title/type/summary/scope.
- Provenance summary.
- Retrieval signals.
- Contradiction/review status.

Output phải phân biệt:

- Direct answer artifact.
- Supporting context.
- Contradicting/qualifying artifact.
- Irrelevant candidate.
- Missing knowledge.

Không fallback tự động chọn top candidate khi LLM đánh giá tất cả đều irrelevant.

### 6.5 Graph expansion

Graph expansion chạy sau khi đã có semantic seeds.

LLM planner đưa soft relation hints và giới hạn traversal. Backend thực hiện traversal
deterministic theo node/edge IDs, confidence, status và source scope.

Expansion phải ưu tiên:

- Provenance ancestors.
- Conditions/exceptions/qualifiers.
- Contradictions/supersession.
- Direct semantic neighbors.

Không mở rộng toàn bộ entities của cùng source vì điều đó tạo noise.

### 6.6 Context assembly

Context Builder tổ chức theo vai trò, không nối phẳng candidates:

```markdown
# Query

# Direct answer artifacts

# Conditions, exceptions and qualifiers

# Supporting concepts/entities

# Contradictions and uncertainty

# Provenance and evidence
```

Mỗi factual statement trong context phải giữ artifact ID và evidence refs.

### 6.7 Grounding and gap decision

Trước synthesis, một grounding check quyết định:

- Artifacts có trực tiếp trả lời query không?
- Evidence có đủ cụ thể không?
- Có contradiction cần xử lý không?
- Có cần source verification không?
- Có knowledge gap không?

Không được trả `insufficient` chỉ vì retrieval miss nếu source scope có khả năng chứa
câu trả lời và còn budget để re-inspect.

### 6.8 Source re-inspection

Khi cần kiểm chứng hoặc artifact thiếu:

1. Dùng source summaries, knowledge map và provenance để chọn likely sources.
2. Gửi raw source trực tiếp cho LLM/VLM cùng query và current gap.
3. Yêu cầu evidence local IDs, candidate artifacts và source-grounded answer.
4. Validate provenance.
5. Compile artifact còn thiếu vào knowledge base.
6. Update graph/index.
7. Chạy lại retrieval hoặc synthesis.

Đây là on-demand compilation, không phải raw chunk RAG.

Nếu source quá lớn, dùng manifest để chọn source units có khả năng liên quan; selection
do semantic planner quyết định, không bằng domain keyword.

### 6.9 Answer synthesis

Answer Agent chỉ nhận context packet đã ground.

Yêu cầu:

- Trả lời cùng ngôn ngữ người dùng.
- Citation phải trỏ tới evidence/source refs thực sự hỗ trợ statement.
- Không tự gắn citation fallback không liên quan.
- Phân biệt “không có trong source” với “hệ thống chưa tìm/biên dịch được”.
- Nêu contradiction hoặc scope qualification.
- Không bổ sung kiến thức nền ngoài source trừ khi chế độ query cho phép rõ ràng.

### 6.10 Write-back

Một answer chỉ được write-back khi:

- Có giá trị tái sử dụng.
- Có provenance đầy đủ.
- Không chỉ lặp lại một atomic artifact.
- Không có unresolved contradiction nghiêm trọng.

Write-back tạo synthesis artifact, cập nhật wiki page, graph và semantic indexes.

## 7. SQLite-first technical design

### 7.1 Bảng đề xuất

```text
sources
source_versions
compiler_runs
compiler_passes
source_manifests
source_units

evidence_items
artifacts
artifact_versions
artifact_evidence
artifact_relations

wiki_pages
wiki_page_artifacts
wiki_links

graph_nodes
graph_edges
contradictions
resolution_candidates

coverage_reports
review_items

artifact_embeddings
knowledge_maps
knowledge_map_entries

query_runs
query_candidates
query_citations
query_gap_actions
```

JSON columns được dùng cho schema mở, nhưng các trường cần filter/join thường xuyên phải
có column/index riêng.

### 7.2 Vector trong SQLite

Giai đoạn đầu có thể:

- Lưu embedding blob/JSON cùng model và dimensions.
- Tính cosine similarity trong application với corpus nhỏ.
- Dùng SQLite vector extension khi corpus tăng.

Mỗi embedding record phải lưu:

```text
artifact_id
representation_type
embedding_model
dimensions
vector
content_hash
created_at
```

Re-embed chỉ khi content hash hoặc embedding model thay đổi.

### 7.3 FTS

FTS chạy trên artifact/wiki fields, không dùng domain keyword:

- title
- aliases
- summary
- normalized semantic text
- exact identifiers
- relation descriptions

Query terms do LLM planner sinh. Backend chỉ escape, normalize và thực thi an toàn.
Không thêm stopword/domain synonym thủ công như cơ chế chính.

### 7.4 Prompt và schema versioning

Mỗi compiler/query run phải lưu:

- Model.
- Prompt version.
- Schema version.
- Compiler version.
- Input source hash.
- Token/cost/latency metadata khi có.

Điều này cho phép rebuild và đánh giá regression.

## 8. Component boundaries

Backend nên chia thành các service độc lập:

```text
SourceRegistry
MultimodalSourceReader
SourceProfiler
CompilationPlanner
KnowledgeCompiler
ArtifactMatcher
ArtifactIntegrator
WikiIntegrator
GraphIntegrator
CoverageAuditor
SemanticIndexer
KnowledgeMapMaintainer

QueryPlanner
KnowledgeNavigator
ArtifactRetriever
CandidateFusion
ArtifactReranker
GraphExpander
ContextBuilder
GroundingChecker
SourceReinspector
AnswerSynthesizer
WriteBackService
```

LLM provider được đặt sau protocol/interface để workflow có thể test bằng fake clients.
Repository chỉ chịu trách nhiệm persistence, không chứa prompt logic.

## 9. Frontend workflow

Normal user flow:

```text
Upload
  -> Ingest
  -> profiling/compiling/integrating/graphing/auditing/indexing progress
  -> completed hoặc needs review
  -> wiki và graph tự xuất hiện
  -> chat
```

Không yêu cầu người dùng bấm “Build graph”.

Graph view phải:

- Có legend cho node types.
- Cho phép click mọi node.
- Entity/artifact node hiển thị summary, relations và provenance.
- Literal node hiển thị value, predicate, artifact/claim, evidence và source locator.
- Cho phép chuyển giữa wiki, provenance và semantic graph.

Admin actions:

- Re-ingest source.
- Re-run coverage audit.
- Rebuild/repair graph.
- Re-index embeddings.
- Resolve duplicate artifacts.
- Review contradiction.

## 10. Quality gates

Ingest chỉ hoàn tất khi:

- Evidence IDs unique và provenance hợp lệ.
- Source-backed artifacts đều có evidence.
- Không có dangling artifact/graph references.
- Coverage auditor không báo missing area nghiêm trọng chưa xử lý.
- Wiki/SQLite/graph/index cùng compiler version.
- Generated pages parse được và có stable frontmatter.

Query chỉ trả confidence cao khi:

- Direct answer artifacts được retrieve.
- Evidence trực tiếp hỗ trợ answer.
- Citations đã validate.
- Contradiction và scope đã được xử lý.

## 11. Evaluation

Foundation phải cho phép so sánh:

```text
A. Current one-shot compiler + FTS
B. Multi-pass compiler + artifact FTS
C. Multi-pass compiler + LLM navigation
D. Multi-pass compiler + artifact embeddings + FTS
E. D + graph expansion
F. E + source re-inspection/gap recovery
```

Metrics:

- Source coverage.
- Artifact completeness.
- Provenance correctness.
- Retrieval recall@k.
- Answer correctness.
- Faithfulness.
- Citation precision và recall.
- No-answer calibration.
- Contradiction handling.
- Query-failure recovery rate.
- Ingest/query cost và latency.
- Wiki drift.

Test fixture đầu tiên phải bao gồm các câu hỏi mà source thực sự có đáp án nhưng compiler
one-shot đã bỏ sót. Đây là phép đo trực tiếp cho compilation loss.

## 12. Failure modes và mitigation

### Compilation loss

Mitigation:

- Source manifest.
- Dynamic multi-pass compilation.
- Coverage audit.
- Query-triggered re-inspection.

### Artifact drift

Mitigation:

- Immutable source refs.
- Artifact versions.
- Revalidation khi update.
- Periodic source-backed lint.

### Duplicate hoặc over-merged artifacts

Mitigation:

- Semantic matching.
- Explicit scope.
- Possible-duplicate review state.
- Không auto-merge khi confidence thấp.

### Retrieval miss

Mitigation:

- LLM navigation.
- Multiple artifact representations.
- Artifact embeddings.
- Artifact FTS.
- Graph expansion.
- Gap recovery.

### Citation sai

Mitigation:

- Evidence IDs thay vì locator string.
- Citation entailment check.
- Không citation fallback.
- Query audit trace.

### Cost tăng

Mitigation:

- Cache theo source/content hash.
- Chỉ rerun pass bị ảnh hưởng.
- Re-embed theo artifact content hash.
- Budget/iteration limit.
- Model routing theo độ khó, không theo domain.

## 13. Migration từ implementation hiện tại

### Stage 1: Correctness foundation

- Sửa collision khi map evidence bằng locator.
- Dùng evidence local ID unique trong extraction contract.
- Xóa citation fallback không liên quan.
- Sửa entity/object resolution và literal detail.
- Graph tự chạy sau ingest.
- Lưu compiler run và stage status.

Outcome:

- Provenance đúng.
- Graph và wiki nhất quán ngay sau ingest.
- Không còn manual graph step trong normal flow.

### Stage 2: Knowledge Compiler V2

- Thêm SourceManifest.
- Thêm dynamic compilation plan.
- Thêm multi-pass compiler.
- Thêm open Artifact Store.
- Thêm Artifact Matcher/Wiki Integrator.
- Thêm Coverage Auditor và follow-up pass.

Outcome:

- Source không còn bị nén thành vài evidence/claim tùy ý.
- Artifacts phản ánh cấu trúc và knowledge lenses do model suy luận.
- Ingest có báo cáo coverage và trạng thái `needs_review`.

### Stage 3: Semantic retrieval và compounding loop

- Thêm knowledge maps.
- Thêm LLM hierarchical navigator.
- Thêm artifact embeddings trong SQLite.
- Thêm candidate fusion, semantic reranking và graph traversal.
- Thêm grounding checker, source re-inspection và write-back.

Outcome:

- Query không phụ thuộc exact keyword.
- Retrieval vẫn artifact-first.
- Query failure có thể tự bổ sung knowledge thiếu.
- Wiki cải thiện theo thời gian.

## 14. Acceptance criteria cho foundation mới

- Không có domain keyword/taxonomy trong orchestration code.
- Không dùng fixed raw chunks làm retrieval corpus chính.
- Source profiler và compilation planner là LLM-driven.
- Artifact và relation types là open strings.
- Graph được cập nhật trong ingest.
- Mọi artifact factual có valid evidence refs.
- Coverage audit có thể yêu cầu follow-up compilation.
- Query dùng LLM navigation, artifact semantic search, FTS và graph.
- Insufficient retrieval có thể kích hoạt source re-inspection.
- Citation không được tự gắn nếu evidence không hỗ trợ answer.
- Toàn bộ pipeline có version, trace và testable contracts.

## 15. Mental model

```text
Raw sources          = source code
Source manifest      = compiler analysis
Artifacts            = structured intermediate representation
Wiki pages           = human-readable compiled knowledge
Knowledge graph      = symbol/provenance graph
Semantic indexes     = navigation indexes over compiled knowledge
Query orchestrator   = runtime planner
Context builder      = execution context assembler
Source re-inspection = incremental recompilation
Write-back           = knowledge compounding
Coverage/lint        = static analysis and integrity checking
```

Nguyên tắc trung tâm:

> Để LLM/VLM hiểu và biên dịch tri thức trước; retrieve artifacts sau; đọc lại nguồn
> khi compiled knowledge chưa đủ.

Đây là foundation tổng quát: không phụ thuộc domain, không phụ thuộc một loại cấu trúc
tài liệu, không quay về raw-chunk RAG và vẫn giữ raw source làm nền tảng kiểm chứng.
