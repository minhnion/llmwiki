from pathlib import Path

from backend.app.core.clock import utc_now_iso
from backend.app.core.hashing import sha256_file
from backend.app.core.ids import artifact_id, statement_id, wiki_page_id
from backend.app.core.text import slugify
from backend.app.domain.compiler import CompilationBundle
from backend.app.domain.extraction import IngestExtractionResult
from backend.app.domain.models import SourceRef, WikiPage


class SourcePageWriter:
    def __init__(self, wiki_dir: Path) -> None:
        self.wiki_dir = wiki_dir

    def write(
        self,
        source: SourceRef,
        extraction: IngestExtractionResult,
        compilation: CompilationBundle | None = None,
        coverage_status: str = "needs_review",
        compiler_version: str = "",
    ) -> WikiPage:
        page_dir = self.wiki_dir / "sources"
        page_dir.mkdir(parents=True, exist_ok=True)
        page_path = page_dir / f"{slugify(extraction.source_title or source.title)}-{source.id}.md"
        now = utc_now_iso()
        body = self._render_body(
            source,
            extraction,
            now,
            compilation,
            coverage_status,
            compiler_version,
        )
        temporary_path = page_path.with_suffix(".md.tmp")
        temporary_path.write_text(body, encoding="utf-8")
        temporary_path.replace(page_path)
        self._update_index(source, extraction, page_path)
        return WikiPage(
            id=wiki_page_id(source.id),
            title=extraction.source_title or source.title,
            page_type="source",
            path=page_path,
            body=body,
            summary=extraction.source_summary,
            source_ids=(source.id,),
            artifact_ids=tuple(
                artifact_id(source.id, artifact.local_id)
                for artifact in (compilation.artifacts if compilation else [])
            ),
            sha256=sha256_file(page_path),
            created_at=now,
            updated_at=now,
        )

    def _render_body(
        self,
        source: SourceRef,
        extraction: IngestExtractionResult,
        timestamp: str,
        compilation: CompilationBundle | None,
        coverage_status: str,
        compiler_version: str,
    ) -> str:
        artifact_lines = self._artifact_lines(compilation)
        artifact_ids = [
            artifact_id(source.id, artifact.local_id)
            for artifact in (compilation.artifacts if compilation else [])
        ]
        claim_ids = [
            statement_id(source.id, artifact.local_id, statement.local_id)
            for artifact in (compilation.artifacts if compilation else [])
            for statement in artifact.statements
        ]
        status = "active" if coverage_status == "complete" else "needs_review"
        return "\n".join(
            [
                "---",
                f"id: {wiki_page_id(source.id)}",
                f"title: {self._yaml_string(extraction.source_title or source.title)}",
                "type: source",
                f"status: {status}",
                "review_status: unreviewed",
                f"coverage_status: {coverage_status}",
                f"compiler_version: {compiler_version}",
                f"created_at: {timestamp}",
                f"updated_at: {timestamp}",
                f"source_id: {source.id}",
                f"source_sha256: {source.sha256}",
                f"source_type: {source.source_type}",
                f"source_path: {self._yaml_string(str(source.path))}",
                "sources:",
                f"  - {source.id}",
                *self._yaml_list("artifacts", artifact_ids),
                *self._yaml_list("claims", claim_ids),
                f"confidence: {self._confidence_label(extraction)}",
                "---",
                "",
                f"# {extraction.source_title or source.title}",
                "",
                "## Tóm tắt",
                "",
                extraction.source_summary,
                "",
                "## Điểm chính",
                "",
                *self._bullet_list(extraction.key_takeaways),
                "",
                "## Bằng chứng",
                "",
                *[
                    f"- `{item.locator}` ({item.modality}, độ tin cậy {item.confidence:.2f}): "
                    f"{item.summary} {item.text}"
                    for item in extraction.evidence_items
                ],
                "",
                "## Mệnh đề",
                "",
                *[
                    f"- {claim.text} "
                    f"[{', '.join(f'`{locator}`' for locator in claim.evidence_locators)}] "
                    f"(độ tin cậy {claim.confidence:.2f}, trạng thái: {claim.status})"
                    for claim in extraction.claims
                ],
                "",
                "## Artifacts",
                "",
                *artifact_lines,
                "",
                "## Trạng thái biên dịch",
                "",
                f"- Coverage: `{coverage_status}`",
                f"- Compiler: `{compiler_version}`",
                "",
                "## Thực thể",
                "",
                *[
                    f"- [[{entity.name}]] ({entity.entity_type}): {entity.description} "
                    f"(độ tin cậy {entity.confidence:.2f})"
                    for entity in extraction.entities
                ],
                "",
                "## Mục cần rà soát",
                "",
                *self._review_lines(extraction),
                "",
                "## Câu hỏi mở",
                "",
                *self._bullet_list(extraction.open_questions),
                "",
            ]
        )

    @staticmethod
    def _artifact_lines(compilation: CompilationBundle | None) -> list[str]:
        if compilation is None or not compilation.artifacts:
            return ["- Không có."]
        lines: list[str] = []
        for artifact in compilation.artifacts:
            lines.extend(
                [
                    (
                        f"### {artifact.title} (`{artifact.artifact_type}`, "
                        f"`{artifact.local_id}`)"
                    ),
                    "",
                    artifact.summary,
                    "",
                    artifact.content,
                    "",
                    "Atomic statements:",
                    *[
                        (
                            f"- `{statement.local_id}` {statement.text} "
                            f"[evidence: {', '.join(statement.evidence_local_ids)}]"
                        )
                        for statement in artifact.statements
                    ],
                    "",
                ]
            )
        return lines

    @staticmethod
    def _review_lines(extraction: IngestExtractionResult) -> list[str]:
        if not extraction.review_items:
            return ["- Không có."]
        return [
            f"- **{item.severity} / {item.review_type}**: {item.title}. {item.body}"
            for item in extraction.review_items
        ]

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
            existing_lines = [
                "# Chỉ mục Wiki",
                "",
                "Tệp này liệt kê các trang wiki được hệ thống sinh tự động.",
            ]

        source_line = (
            f"- [[{page_path.relative_to(self.wiki_dir).as_posix()}|"
            f"{extraction.source_title or source.title}]] - "
            f"{extraction.source_summary} (source_id: `{source.id}`)"
        )
        source_marker = f"source_id: `{source.id}`"
        filtered_lines = [line for line in existing_lines if source_marker not in line]
        if "## Nguồn tài liệu" not in filtered_lines:
            if filtered_lines and filtered_lines[-1].strip():
                filtered_lines.append("")
            filtered_lines.extend(["## Nguồn tài liệu", ""])
        source_header_index = filtered_lines.index("## Nguồn tài liệu")
        insert_at = source_header_index + 1
        while insert_at < len(filtered_lines) and filtered_lines[insert_at].startswith("- "):
            insert_at += 1
        filtered_lines.insert(insert_at, source_line)
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

    @staticmethod
    def _yaml_list(name: str, values: list[str]) -> list[str]:
        if not values:
            return [f"{name}: []"]
        return [f"{name}:", *[f"  - {value}" for value in values]]

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
