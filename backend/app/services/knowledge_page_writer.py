from pathlib import Path

from backend.app.core.clock import utc_now_iso
from backend.app.core.hashing import sha256_file
from backend.app.core.ids import artifact_id, knowledge_page_id, statement_id
from backend.app.core.text import slugify
from backend.app.domain.compiler import (
    CompilationBundle,
    SourceManifest,
    WikiIntegrationPlan,
)
from backend.app.domain.models import SourceRef, WikiPage


class KnowledgePageWriter:
    def __init__(self, wiki_dir: Path) -> None:
        self.wiki_dir = wiki_dir

    def write(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        compilation: CompilationBundle,
        plan: WikiIntegrationPlan,
        coverage_status: str,
        compiler_version: str,
    ) -> list[WikiPage]:
        page_dir = self.wiki_dir / "knowledge"
        page_dir.mkdir(parents=True, exist_ok=True)
        artifacts = {artifact.local_id: artifact for artifact in compilation.artifacts}
        evidence = {item.local_id: item for item in compilation.evidence_items}
        page_ids = {
            page.local_id: knowledge_page_id(source.id, page.local_id)
            for page in plan.pages
        }
        paths = {
            page.local_id: page_dir
            / f"{slugify(page.title)}-{page_ids[page.local_id]}.md"
            for page in plan.pages
        }
        now = utc_now_iso()
        pages: list[WikiPage] = []
        for page_plan in sorted(plan.pages, key=lambda item: item.local_id):
            page_artifacts = [
                artifacts[local_id] for local_id in page_plan.artifact_local_ids
            ]
            body = self._render(
                source=source,
                manifest=manifest,
                page_plan=page_plan,
                page_artifacts=page_artifacts,
                evidence=evidence,
                page_ids=page_ids,
                paths=paths,
                coverage_status=coverage_status,
                compiler_version=compiler_version,
                timestamp=now,
            )
            page_path = paths[page_plan.local_id]
            temporary_path = page_path.with_suffix(".md.tmp")
            temporary_path.write_text(body, encoding="utf-8")
            temporary_path.replace(page_path)
            pages.append(
                WikiPage(
                    id=page_ids[page_plan.local_id],
                    title=page_plan.title,
                    page_type=page_plan.page_type,
                    path=page_path,
                    body=body,
                    summary=page_plan.summary,
                    source_ids=(source.id,),
                    artifact_ids=tuple(
                        artifact_id(source.id, item.local_id)
                        for item in page_artifacts
                    ),
                    related_page_ids=tuple(
                        page_ids[local_id]
                        for local_id in page_plan.related_page_local_ids
                    ),
                    claim_ids=tuple(
                        statement_id(source.id, artifact.local_id, statement.local_id)
                        for artifact in page_artifacts
                        for statement in artifact.statements
                    ),
                    sha256=sha256_file(page_path),
                    created_at=now,
                    updated_at=now,
                )
            )
        self._update_index(pages)
        return pages

    def _render(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        page_plan,
        page_artifacts,
        evidence,
        page_ids,
        paths,
        coverage_status: str,
        compiler_version: str,
        timestamp: str,
    ) -> str:
        status = "active" if coverage_status == "complete" else "needs_review"
        stable_artifact_ids = [
            artifact_id(source.id, artifact.local_id)
            for artifact in page_artifacts
        ]
        stable_claim_ids = [
            statement_id(source.id, artifact.local_id, statement.local_id)
            for artifact in page_artifacts
            for statement in artifact.statements
        ]
        lines = [
            "---",
            f"id: {page_ids[page_plan.local_id]}",
            f"title: {self._yaml_string(page_plan.title)}",
            f"type: {self._yaml_string(page_plan.page_type)}",
            f"status: {status}",
            "review_status: unreviewed",
            f"coverage_status: {coverage_status}",
            f"compiler_version: {compiler_version}",
            f"language: {self._yaml_string(manifest.language)}",
            "sources:",
            f"  - {source.id}",
            "artifacts:",
            *[f"  - {value}" for value in stable_artifact_ids],
            "claims:",
            *[f"  - {value}" for value in stable_claim_ids],
            f"confidence: {page_plan.confidence:.2f}",
            f"created_at: {timestamp}",
            f"updated_at: {timestamp}",
            "---",
            "",
            f"# {page_plan.title}",
            "",
            "## Tóm tắt",
            "",
            page_plan.summary,
            "",
        ]
        for artifact in page_artifacts:
            lines.extend(
                [
                    f"## {artifact.title}",
                    "",
                    artifact.summary,
                    "",
                    artifact.content,
                    "",
                    "### Mệnh đề có provenance",
                    "",
                ]
            )
            for statement in artifact.statements:
                citations = []
                for evidence_local_id in statement.evidence_local_ids:
                    item = evidence[evidence_local_id]
                    citations.append(
                        f"`{evidence_local_id}` ({item.locator.kind}: {item.locator.value})"
                    )
                lines.append(
                    f"- {statement.text} [{'; '.join(citations)}] "
                    f"(độ tin cậy {statement.confidence:.2f})"
                )
            lines.extend(["", "### Bằng chứng", ""])
            for evidence_local_id in artifact.evidence_local_ids:
                item = evidence[evidence_local_id]
                lines.append(
                    f"- `{evidence_local_id}` — {item.locator.kind}: {item.locator.value}: "
                    f"{item.content}"
                )
            lines.append("")
        lines.extend(["## Liên quan", ""])
        if page_plan.related_page_local_ids:
            for related_local_id in page_plan.related_page_local_ids:
                relative = paths[related_local_id].relative_to(self.wiki_dir).as_posix()
                lines.append(f"- [[{relative}]]")
        else:
            lines.append("- Không có.")
        lines.append("")
        return "\n".join(lines)

    def _update_index(self, pages: list[WikiPage]) -> None:
        index_path = self.wiki_dir / "index.md"
        existing = (
            index_path.read_text(encoding="utf-8").splitlines()
            if index_path.exists()
            else ["# Chỉ mục Wiki"]
        )
        page_ids = {page.id for page in pages}
        filtered = [
            line
            for line in existing
            if not any(f"page_id: `{page_id}`" in line for page_id in page_ids)
        ]
        if "## Tri thức đã biên dịch" not in filtered:
            if filtered and filtered[-1].strip():
                filtered.append("")
            filtered.extend(["## Tri thức đã biên dịch", ""])
        header_index = filtered.index("## Tri thức đã biên dịch")
        insert_at = header_index + 1
        while insert_at < len(filtered) and filtered[insert_at].startswith("- "):
            insert_at += 1
        for page in sorted(pages, key=lambda item: item.title, reverse=True):
            relative = page.path.relative_to(self.wiki_dir).as_posix()
            filtered.insert(
                insert_at,
                f"- [[{relative}|{page.title}]] - {page.summary} "
                f"(page_id: `{page.id}`)",
            )
        index_path.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")

    @staticmethod
    def _yaml_string(value: str) -> str:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
