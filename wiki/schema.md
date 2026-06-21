# Quy ước Wiki Agent

## Vai trò

LLM/VLM quyết định nội dung, cấu trúc tri thức, page type, liên kết và cách cập
nhật wiki. Code chỉ đảm bảo an toàn, provenance, persistence và tính nhất quán.

## Trang được sinh

- Trang tri thức chung nằm trong `pages/`.
- Trang tóm tắt nguồn nằm trong `sources/`.
- Câu trả lời hoặc synthesis được lưu nằm trong `queries/`.
- Page `type` là open string do agent chọn.
- Không bắt buộc các loại entity, concept, rule, event hoặc relation cố định.

Mỗi trang generated phải có frontmatter do backend quản lý:

- `id`, `title`, `type`, `status`, `summary`.
- `sources` và evidence locator khi có factual content.
- `related_pages`, `confidence`, `created_at`, `updated_at`.

## Ingest

Khi có source mới, agent:

1. Đọc source cùng mục đích và catalog wiki hiện tại.
2. Tìm và đọc các trang có liên quan.
3. Ưu tiên cập nhật trang hiện có nếu cùng semantic identity.
4. Tạo trang mới khi thực sự cần.
5. Giữ provenance cũ và thêm provenance mới.
6. Dùng review item nếu merge, contradiction hoặc identity chưa chắc chắn.

## Query

Agent tìm và đọc full wiki pages, theo wikilink khi hữu ích, và mở lại raw
source khi cần xác minh hoặc wiki chưa đủ. Không được gắn citation không hỗ trợ
khẳng định.

## Lint

Lint kiểm tra broken links, orphan pages, duplication, stale knowledge,
contradiction, unsupported statements và review items chưa xử lý.

## Cấm

Không dùng domain mapping, keyword routing, semantic regex, fixed taxonomy,
fixed document template hoặc raw fixed chunks làm core knowledge path.
