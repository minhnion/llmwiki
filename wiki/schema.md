# Quy ước Wiki

- `index.md` là chỉ mục nội dung, được cập nhật sau khi ingest nguồn và dựng graph.
- `sources/` chứa trang tổng hợp theo từng tài liệu đã ingest.
- `entities/` chứa trang thực thể và các quan hệ có provenance.
- Các trang sinh tự động sử dụng YAML frontmatter, ID ổn định và wikilink.
- Mệnh đề và quan hệ quan trọng phải tham chiếu được tới source/evidence trong SQLite.
- Nội dung không chắc chắn, mâu thuẫn hoặc có khả năng trùng thực thể phải được đưa vào diện rà soát.
- `log.md` là nhật ký runtime dạng append-only cho thao tác đăng ký, ingest, truy vấn và dựng graph.
