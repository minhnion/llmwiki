from pathlib import Path

from backend.app.core.clock import utc_now_iso
from backend.app.core.hashing import sha256_file
from backend.app.core.ids import wiki_page_id
from backend.app.core.text import slugify
from backend.app.domain.extraction import IngestExtractionResult
from backend.app.domain.models import SourceRef, WikiPage


class SourcePageWriter:
    def __init__(self, wiki_dir: Path) -> None:
        self.wiki_dir = wiki_dir

    def write(self, source: SourceRef, extraction: IngestExtractionResult) -> WikiPage:
        page_dir = self.wiki_dir / "sources"
        page_dir.mkdir(parents=True, exist_ok=True)
        page_path = page_dir / f"{slugify(extraction.source_title or source.title)}-{source.id}.md"
        now = utc_now_iso()
        body = self._render_body(source, extraction, now)
        page_path.write_text(body, encoding="utf-8")
        self._update_index(source, extraction, page_path)
        return WikiPage(
            id=wiki_page_id(source.id),
            title=extraction.source_title or source.title,
            page_type="source",
            path=page_path,
            body=body,
            summary=extraction.source_summary,
            source_ids=(source.id,),
            sha256=sha256_file(page_path),
            created_at=now,
            updated_at=now,
        )

    def _render_body(
        self,
        source: SourceRef,
        extraction: IngestExtractionResult,
        timestamp: str,
    ) -> str:
        return "\n".join(
            [
                "---",
                f"id: {wiki_page_id(source.id)}",
                f"title: {self._yaml_string(extraction.source_title or source.title)}",
                "type: source",
                "status: ingested",
                f"created_at: {timestamp}",
                f"updated_at: {timestamp}",
                f"source_id: {source.id}",
                f"source_sha256: {source.sha256}",
                f"source_type: {source.source_type}",
                f"source_path: {self._yaml_string(str(source.path))}",
                f"confidence: {self._confidence_label(extraction)}",
                "---",
                "",
                f"# {extraction.source_title or source.title}",
                "",
                "## Summary",
                "",
                extraction.source_summary,
                "",
                "## Key Takeaways",
                "",
                *self._bullet_list(extraction.key_takeaways),
                "",
                "## Evidence",
                "",
                *[
                    f"- `{item.locator}` ({item.modality}, confidence {item.confidence:.2f}): "
                    f"{item.summary} {item.text}"
                    for item in extraction.evidence_items
                ],
                "",
                "## Claims",
                "",
                *[
                    f"- {claim.text} "
                    f"[{', '.join(f'`{locator}`' for locator in claim.evidence_locators)}] "
                    f"(confidence {claim.confidence:.2f}, status: {claim.status})"
                    for claim in extraction.claims
                ],
                "",
                "## Entities",
                "",
                *[
                    f"- [[{entity.name}]] ({entity.entity_type}): {entity.description} "
                    f"(confidence {entity.confidence:.2f})"
                    for entity in extraction.entities
                ],
                "",
                "## Review Items",
                "",
                *[
                    f"- **{item.severity} / {item.review_type}**: {item.title}. {item.body}"
                    for item in extraction.review_items
                ],
                "",
                "## Open Questions",
                "",
                *self._bullet_list(extraction.open_questions),
                "",
            ]
        )

    def _update_index(
        self,
        source: SourceRef,
        extraction: IngestExtractionResult,
        page_path: Path,
    ) -> None:
        index_path = self.wiki_dir / "index.md"
        if index_path.exists():
            existing_lines = index_path.read_text(encoding="utf-8").splitlines()
        else:
            existing_lines = ["# Wiki Index", "", "This file catalogs generated wiki pages."]

        source_line = (
            f"- [[{page_path.relative_to(self.wiki_dir).as_posix()}|"
            f"{extraction.source_title or source.title}]] - "
            f"{extraction.source_summary} (source_id: `{source.id}`)"
        )
        source_marker = f"source_id: `{source.id}`"
        filtered_lines = [line for line in existing_lines if source_marker not in line]
        if "## Sources" not in filtered_lines:
            if filtered_lines and filtered_lines[-1].strip():
                filtered_lines.append("")
            filtered_lines.extend(["## Sources", ""])
        source_header_index = filtered_lines.index("## Sources")
        insert_at = source_header_index + 1
        while insert_at < len(filtered_lines) and filtered_lines[insert_at].startswith("- "):
            insert_at += 1
        filtered_lines.insert(insert_at, source_line)
        index_path.write_text("\n".join(filtered_lines).rstrip() + "\n", encoding="utf-8")

    @staticmethod
    def _bullet_list(items: list[str]) -> list[str]:
        if not items:
            return ["- None."]
        return [f"- {item}" for item in items]

    @staticmethod
    def _yaml_string(value: str) -> str:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _confidence_label(extraction: IngestExtractionResult) -> str:
        scores = [item.confidence for item in extraction.evidence_items]
        if not scores:
            return "low"
        average = sum(scores) / len(scores)
        if average >= 0.8:
            return "high"
        if average >= 0.55:
            return "medium"
        return "low"
