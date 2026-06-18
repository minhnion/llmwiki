# Kiến trúc kỹ thuật LLM Wiki hiện tại

Tài liệu này mô tả implementation đang có trong codebase tại thời điểm hiện tại. Mục tiêu là giải thích hệ thống thực sự làm gì từ lúc người dùng tải tài liệu lên cho tới khi chatbot trả lời, knowledge graph được dựng ra sao, dữ liệu được lưu ở đâu và vai trò của từng lớp.

## Phạm vi hiện tại

Ứng dụng đã có một pipeline end-to-end:

```text
Người dùng tải tệp
  -> đăng ký source và hash nội dung
  -> LLM/VLM đọc trực tiếp tệp
  -> trích xuất evidence, claims, entities, review items
  -> sinh trang wiki Markdown
  -> lưu dữ liệu có cấu trúc và FTS vào SQLite
  -> dựng relation graph và phát hiện mâu thuẫn
  -> truy xuất đa kênh bằng SQLite FTS + graph
  -> LLM rerank bằng chứng
  -> LLM tổng hợp câu trả lời có citation
  -> frontend hiển thị source, chat, evidence và graph
```

Hệ thống chưa dùng vector database, OCR engine hoặc document parser bắt buộc. File được gửi trực tiếp cho OpenAI Responses API. Đây là chủ ý của giai đoạn hiện tại để đánh giá năng lực multimodal trực tiếp của LLM/VLM trước khi thêm lớp tiền xử lý chuyên biệt.

## Các lớp chính

Backend được tổ chức theo các lớp:

- `domain`: Pydantic model, schema structured output và object nghiệp vụ.
- `repositories`: đọc/ghi SQLite và FTS5.
- `services`: orchestration nghiệp vụ, LLM adapter, wiki writer.
- `api/routes`: FastAPI endpoint và dependency wiring.
- `cli.py`: các workflow tương đương qua dòng lệnh.
- `db/migrations.py`: schema SQLite có version.

Frontend được tổ chức theo:

- `domain/models.ts`: contract dữ liệu khớp với backend.
- `services/apiClient.ts`: HTTP adapter dạng class.
- `services/workbenchService.ts`: facade cho các use case frontend.
- `components`: control và panel độc lập.
- `App.tsx`: orchestration state của workbench.

## Upload và đăng ký source

Frontend gửi multipart form tới:

```text
POST /api/sources/upload
```

Backend thực hiện:

1. Chuẩn hóa tên tệp để tránh path traversal và tên không ổn định.
2. Ghi tệp vào `raw/sources/`.
3. Giới hạn kích thước bằng `LLM_WIKI_MAX_FILE_BYTES`.
4. Tính SHA-256 của toàn bộ nội dung.
5. Sinh `source_id` ổn định từ content hash.
6. Suy luận MIME type và source type.
7. Ghi metadata vào `sources`.
8. Ghi phiên bản vào `source_versions`.
9. Ghi một register job vào `ingest_jobs`.
10. Ghi hoạt động vào `wiki/log.md`.

Tệp raw được coi là immutable input. Hai tệp có cùng nội dung sẽ có cùng SHA-256 và cùng source identity, kể cả tên tệp khác nhau.

Các trường source quan trọng:

- `id`: ID ổn định dạng `src_*`.
- `original_path`: đường dẫn tệp raw.
- `sha256`: định danh nội dung.
- `source_type`, `mime_type`, `size_bytes`.
- `tags_json`.
- `status`: ban đầu là `registered`, sau ingest là `ingested`.

Không có source nào được code hard-code hoặc tự động đăng ký lúc khởi động. Danh sách trên web chỉ phản ánh bảng `sources` trong SQLite.

## Ingest trực tiếp bằng LLM/VLM

Ingest được gọi qua:

```text
POST /api/sources/{source_id}/ingest
```

hoặc:

```bash
python -m backend.app.cli sources ingest <source_id>
```

`SourceIngestService` điều phối workflow:

1. Tải source metadata từ SQLite.
2. Kiểm tra source tồn tại và kích thước hợp lệ.
3. Tạo `ingest_job` trạng thái running.
4. Gọi `OpenAIResponsesClient.extract_source()`.
5. Sinh trang source Markdown.
6. Ghi extraction artifacts vào SQLite trong transaction.
7. Cập nhật FTS indexes.
8. Chuyển source sang `ingested`.
9. Đánh dấu job completed hoặc failed.
10. Ghi wiki log.

### File input multimodal

File được đọc thành bytes, encode base64 và gửi dưới dạng:

```text
input_file
```

kèm metadata source trong một `input_text`. Cách này cho phép model xử lý:

- Markdown và text document.
- PDF có text.
- PDF scan.
- Ảnh.
- Bảng và biểu đồ khi model đọc được.
- Các định dạng file được OpenAI file input hỗ trợ.

Hệ thống chưa OCR trước. Đối với scan/ảnh, prompt yêu cầu model mô tả bằng chứng thị giác và chép lại phần đọc được.

### Structured output

Model phải trả về JSON đúng `INGEST_EXTRACTION_JSON_SCHEMA` với `strict: true`. Pydantic tiếp tục validate response trước khi dữ liệu được ghi.

Kết quả ingest gồm:

#### Source summary

- `source_title`.
- `source_summary`.
- `source_language`.
- `document_type`.
- `key_takeaways`.
- `open_questions`.

#### Evidence

Mỗi evidence item gồm:

- `locator`: trang, mục, slide, sheet/cell range hoặc hình.
- `modality`: text, image, table, chart, spreadsheet, pdf page hoặc mixed.
- `text`: nội dung trực tiếp hoặc mô tả thị giác.
- `summary`: vì sao evidence này quan trọng.
- `confidence`.

Evidence là lớp provenance chính. Claim và citation phải quay về evidence.

#### Claim

Claim là một khẳng định nguyên tử:

- `text`.
- `subject`.
- `predicate`.
- `object`.
- `evidence_locators`.
- `confidence`.
- `status`.

Claim được nối với evidence qua `claim_evidence`. Những claim không liên kết được locator hợp lệ sẽ không có support edge.

#### Entity

Entity gồm:

- tên chuẩn.
- loại thực thể.
- aliases.
- mô tả.
- evidence locators.
- confidence.

Entity ID được tạo ổn định từ tên chuẩn và entity type. Một entity có thể liên kết với nhiều source qua `source_entities`.

#### Review item

Review item lưu vấn đề cần người dùng kiểm tra:

- nội dung mơ hồ.
- dữ kiện thiếu.
- khả năng trùng entity.
- scope chưa rõ.
- chất lượng thấp hoặc contradiction cần xem lại.

### Chính sách ngôn ngữ

Pipeline hiện là Vietnamese-first nhưng không cưỡng ép dịch:

- Ingest giữ ngôn ngữ chính của tài liệu.
- Tài liệu tiếng Việt phải sinh summary, evidence, claims và entity descriptions bằng tiếng Việt.
- Tài liệu ngôn ngữ khác giữ ngôn ngữ nguồn.
- `LLM_WIKI_PREFERRED_LANGUAGE=vi` chỉ là fallback khi model không xác định được ngôn ngữ.
- Các mã nội bộ như `active`, `supports`, `entity`, `high` giữ tiếng Anh để schema ổn định.

## Dữ liệu sinh ra sau ingest

### SQLite

Các bảng được cập nhật:

- `evidence_items`.
- `claims`.
- `claim_evidence`.
- `entities`.
- `source_entities`.
- `review_items`.
- `wiki_pages`.
- `page_claims`.

Các FTS5 virtual table:

- `evidence_items_fts`.
- `claims_fts`.
- `entities_fts`.
- `wiki_pages_fts`.

Re-ingest cùng một source sẽ xóa artifacts cũ của source đó rồi ghi lại. ID evidence/claim được tạo deterministic từ source và nội dung, giúp kết quả ổn định hơn giữa các lần chạy.

### Markdown wiki

Trang source được ghi tại:

```text
wiki/sources/<slug>-<source_id>.md
```

Trang chứa:

- YAML frontmatter.
- tóm tắt.
- điểm chính.
- bằng chứng và locator.
- claims.
- entities.
- mục cần rà soát.
- câu hỏi mở.

`wiki/index.md` được cập nhật bằng link tới source page. Nội dung generated trong các thư mục wiki bị Git ignore; template và quy ước wiki vẫn được track.

## Xây dựng knowledge graph

Graph build được gọi qua:

```text
POST /api/graph/build
```

hoặc:

```bash
python -m backend.app.cli graph build
```

`GraphBuilder` thực hiện:

1. Tạo một `graph_run`.
2. Nếu `rebuild=true`, xóa relation/contradiction graph trong phạm vi yêu cầu.
3. Đồng bộ canonical name và aliases vào `entity_aliases`.
4. Đọc claims kèm evidence context từ SQLite.
5. Chia claim thành batch.
6. Gọi LLM structured output để trích xuất relation triples.
7. Resolve subject/object về entity ID nếu khớp canonical name hoặc alias.
8. Lưu relation cùng claim ID, evidence ID và source ID.
9. Nhóm claims theo subject để tìm candidate contradiction.
10. Gọi LLM judge phát hiện contradiction, qualification, duplication hoặc support.
11. Sinh trang entity Markdown.
12. Ghi graph run và wiki log.

### Relation edge

Mỗi relation có:

- subject name và optional subject entity ID.
- predicate.
- object value và optional object entity ID.
- object type: entity, text, number, date, metric hoặc unknown.
- claim ID.
- evidence ID.
- source ID.
- confidence, status và qualifiers.

Object không bắt buộc là entity. Điều này cho phép biểu diễn:

```text
Thuốc A -> có liều dùng -> 10 mg
Hướng dẫn B -> ban hành ngày -> 2024-01-01
Phương pháp C -> đạt độ chính xác -> 92%
```

### Contradiction

Detector chỉ so sánh các claim có subject gần nhau để giảm số cặp và chi phí. Kết quả lưu:

- `claim_a_id`, `claim_b_id`.
- relationship.
- reason.
- confidence.
- evidence IDs.
- review status.

### Entity page

Entity page được ghi tại:

```text
wiki/entities/<slug>-<entity_id>.md
```

Trang gồm description, aliases, quan hệ đi, quan hệ đến và merge candidates. Mỗi relation vẫn chỉ rõ claim/evidence provenance.

## Query pipeline

Query được gọi qua:

```text
POST /api/query
```

Input chính:

- `question`.
- `mode`.
- optional `source_ids`.
- optional tags.
- `max_candidates`.
- `max_evidence`.

`QueryEngine` chạy theo các bước sau.

### 1. Query planning

LLM chuyển câu hỏi thành `QueryPlan`:

- rewritten question.
- intent.
- answer language.
- retrieval strategy.
- keywords.
- entity hints.
- subquestions.
- must-have evidence.
- source/time filters.

Planner không trả lời ở bước này. Ngôn ngữ query được giữ nguyên, đặc biệt câu hỏi tiếng Việt không bị chuyển mặc định sang tiếng Anh.

### 2. Xây FTS query

Repository gom:

- câu hỏi gốc.
- câu hỏi rewrite.
- keywords.
- entity hints.
- subquestions.
- must-have evidence.

Các cụm và token được chuẩn hóa rồi ghép thành truy vấn FTS5 dùng toán tử `OR` để ưu tiên recall ở first pass.

### 3. Retrieval đa kênh

Hệ thống tìm evidence ID qua nhiều channel:

- `evidence`: match trực tiếp evidence text/summary/locator.
- `claim`: match claim rồi đi qua `claim_evidence`.
- `graph`: match subject/predicate/object trong relation graph.
- `entity`: match entity rồi mở rộng về evidence của source.
- `wiki_page`: match title/summary/body của wiki page.

Mỗi channel có trọng số:

- evidence trực tiếp cao nhất.
- claim tiếp theo.
- graph expansion.
- entity.
- wiki page.

Candidate nhận retrieval score tổng hợp, confidence, claim IDs, claim text, entities, source metadata và danh sách channel đã match.

### 4. Source scope

Frontend cho phép chọn phạm vi tài liệu:

- Không chọn tài liệu nào: backend không nhận `source_ids`, retrieval dùng toàn bộ source đã ingest.
- Chọn một hoặc nhiều tài liệu: query và graph build chỉ dùng đúng các source ID đó.

Checkbox này không bật/tắt tài liệu trong database và không làm thay đổi trạng thái ingest. Nó chỉ giới hạn phạm vi của thao tác tiếp theo.

### 5. LLM evidence reranking

FTS ưu tiên recall nên có thể trả candidate nhiễu. `EvidenceRanker` gửi candidate cho LLM judge để:

- phân loại direct/indirect/background/conflicting/irrelevant.
- xác định supports/contradicts/qualifies.
- chọn tối đa `max_evidence`.
- nêu contradiction.
- nêu missing evidence.

Backend loại mọi evidence ID model trả về nhưng không tồn tại trong candidate set. Nếu model trả selection rỗng bất thường, hệ thống có fallback theo retrieval score.

### 6. Answer synthesis

`AnswerSynthesizer` chỉ gửi selected evidence cho LLM. Prompt bắt buộc:

- chỉ sử dụng evidence đã cung cấp.
- claim quan trọng phải có citation.
- trả lời cùng ngôn ngữ câu hỏi.
- nói rõ nếu không đủ bằng chứng.
- không che contradiction hoặc uncertainty.

Backend tiếp tục lọc citation để chỉ giữ evidence ID thực sự có trong selected evidence.

Nếu không retrieve được evidence, hệ thống không gọi synthesis và trả lời deterministic rằng chưa đủ bằng chứng.

### 7. Query trace

Mỗi query được lưu vào:

- `query_runs`.
- `query_citations`.

Trace gồm query plan, ranking result, final result, candidate count, selected evidence count và timestamp. Điều này phục vụ debug và evaluation về sau.

## Frontend workbench

Frontend sử dụng React, TypeScript, Vite, Tailwind CSS và pnpm.

Các khu vực chính:

- Upload tài liệu.
- Danh sách source và trạng thái ingest.
- Chọn phạm vi source cho chat/graph.
- Chat có citation và evidence trace.
- Knowledge graph visualization.
- Entity detail.
- Contradiction queue.

Frontend gọi `/api` qua Vite proxy. `VITE_BACKEND_URL` quy định backend target; mặc định hiện tại là `http://127.0.0.1:8020`.

## SQLite migrations

Schema hiện có bốn migration:

1. Source registry và ingest jobs.
2. Extraction artifacts, wiki pages và FTS.
3. Query runs và query citations.
4. Knowledge graph, aliases, contradictions và merge candidates.

Lệnh áp dụng:

```bash
python -m backend.app.cli db migrate
```

Migration chỉ bổ sung version chưa chạy, không tự seed source mẫu.

## Tính nhất quán và an toàn dữ liệu

- Raw source được hash trước khi đăng ký.
- Foreign key được bật trên mỗi SQLite connection.
- SQLite dùng WAL mode.
- Repository operation commit hoặc rollback theo context manager.
- Structured output được validate bằng Pydantic.
- Citation và relation ID do model trả về được kiểm tra với dữ liệu có thật.
- Re-ingest không cộng dồn artifact cũ của cùng source.
- Generated wiki data được Git ignore để test corpus lớn không làm bẩn repository.

## Giới hạn hiện tại

- File lớn mới chỉ bị giới hạn kích thước, chưa chia batch theo trang/sheet tự động.
- Không có OCR/parser fallback chuyên biệt.
- Không có background worker; ingest/graph/query chạy trong request.
- Graph layout frontend đang dùng circular deterministic layout, chưa có physics engine.
- Entity resolution hiện chủ yếu dựa trên normalized canonical name và aliases.
- Contradiction detection mới nhóm theo normalized subject.
- SQLite FTS chưa có tokenizer tối ưu riêng cho tiếng Việt.
- Chưa có evaluation framework hoặc baseline comparison.

Các giới hạn này được giữ có chủ ý để trước hết đánh giá chất lượng application và multimodal LLM/VLM trên dữ liệu thật.
