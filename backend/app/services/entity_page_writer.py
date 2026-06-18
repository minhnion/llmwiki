from pathlib import Path

from backend.app.core.clock import utc_now_iso
from backend.app.core.hashing import sha256_file
from backend.app.core.ids import entity_page_id
from backend.app.core.text import slugify
from backend.app.domain.graph import GraphEntityDetail
from backend.app.domain.models import WikiPage


class EntityPageWriter:
    def __init__(self, wiki_dir: Path) -> None:
        self.wiki_dir = wiki_dir

    def write(self, detail: GraphEntityDetail) -> WikiPage:
        page_dir = self.wiki_dir / "entities"
        page_dir.mkdir(parents=True, exist_ok=True)
        page_path = page_dir / (
            f"{slugify(detail.entity.canonical_name)}-{detail.entity.entity_id}.md"
        )
        now = utc_now_iso()
        body = self._render_body(detail, now)
        page_path.write_text(body, encoding="utf-8")
        self._update_index(detail, page_path)
        return WikiPage(
            id=entity_page_id(detail.entity.entity_id),
            title=detail.entity.canonical_name,
            page_type="entity",
            path=page_path,
            body=body,
            summary=detail.entity.description,
            source_ids=tuple(
                sorted(
                    {
                        relation.source_id
                        for relation in [
                            *detail.outgoing_relations,
                            *detail.incoming_relations,
                        ]
                    }
                )
            ),
            sha256=sha256_file(page_path),
            created_at=now,
            updated_at=now,
        )

    def _render_body(self, detail: GraphEntityDetail, timestamp: str) -> str:
        return "\n".join(
            [
                "---",
                f"id: {entity_page_id(detail.entity.entity_id)}",
                f"entity_id: {detail.entity.entity_id}",
                f"title: {self._yaml_string(detail.entity.canonical_name)}",
                "type: entity",
                "status: generated",
                f"entity_type: {detail.entity.entity_type}",
                f"confidence: {detail.entity.confidence:.2f}",
                f"created_at: {timestamp}",
                f"updated_at: {timestamp}",
                "---",
                "",
                f"# {detail.entity.canonical_name}",
                "",
                "## Tóm tắt",
                "",
                detail.entity.description,
                "",
                "## Tên khác",
                "",
                *self._bullet_list(detail.entity.aliases),
                "",
                "## Quan hệ đi",
                "",
                *[
                    f"- {relation.subject_name} **{relation.predicate}** "
                    f"{relation.object_value} "
                    f"(mệnh đề `{relation.claim_id}`, bằng chứng `{relation.evidence_id}`, "
                    f"độ tin cậy {relation.confidence:.2f})"
                    for relation in detail.outgoing_relations
                ],
                "",
                "## Quan hệ đến",
                "",
                *[
                    f"- {relation.subject_name} **{relation.predicate}** "
                    f"{relation.object_value} "
                    f"(mệnh đề `{relation.claim_id}`, bằng chứng `{relation.evidence_id}`, "
                    f"độ tin cậy {relation.confidence:.2f})"
                    for relation in detail.incoming_relations
                ],
                "",
                "## Đề xuất hợp nhất",
                "",
                *[
                    f"- {candidate.entity_a_name} <-> {candidate.entity_b_name}: "
                    f"{candidate.reason} (độ tin cậy {candidate.confidence:.2f}, "
                    f"trạng thái {candidate.status})"
                    for candidate in detail.merge_candidates
                ],
                "",
            ]
        )

    def _update_index(self, detail: GraphEntityDetail, page_path: Path) -> None:
        index_path = self.wiki_dir / "index.md"
        if index_path.exists():
            existing_lines = index_path.read_text(encoding="utf-8").splitlines()
        else:
            existing_lines = [
                "# Chỉ mục Wiki",
                "",
                "Tệp này liệt kê các trang wiki được hệ thống sinh tự động.",
            ]

        entity_line = (
            f"- [[{page_path.relative_to(self.wiki_dir).as_posix()}|"
            f"{detail.entity.canonical_name}]] - {detail.entity.entity_type} "
            f"(entity_id: `{detail.entity.entity_id}`)"
        )
        marker = f"entity_id: `{detail.entity.entity_id}`"
        filtered_lines = [line for line in existing_lines if marker not in line]
        if "## Thực thể" not in filtered_lines:
            if filtered_lines and filtered_lines[-1].strip():
                filtered_lines.append("")
            filtered_lines.extend(["## Thực thể", ""])
        header_index = filtered_lines.index("## Thực thể")
        insert_at = header_index + 1
        while insert_at < len(filtered_lines) and filtered_lines[insert_at].startswith("- "):
            insert_at += 1
        filtered_lines.insert(insert_at, entity_line)
        index_path.write_text("\n".join(filtered_lines).rstrip() + "\n", encoding="utf-8")

    @staticmethod
    def _bullet_list(items: list[str]) -> list[str]:
        if not items:
            return ["- Không có."]
        return [f"- {item}" for item in items]

    @staticmethod
    def _yaml_string(value: str) -> str:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
