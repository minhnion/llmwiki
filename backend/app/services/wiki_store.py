import re
from collections import defaultdict
from pathlib import Path

import yaml

from backend.app.core.clock import utc_now_iso
from backend.app.core.ids import evidence_ref_id, page_id
from backend.app.domain.agent import PageChange, WikiChangeSet
from backend.app.domain.models import EvidenceRef, WikiPage, WikiPageSummary
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.repositories.wiki import SQLiteWikiRepository

SPECIAL_FILES = {"purpose.md", "schema.md", "index.md", "overview.md", "log.md"}
WRITABLE_ROOTS = {"pages", "sources", "queries"}
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


class WikiValidationError(ValueError):
    pass


class WikiStore:
    def __init__(
        self,
        wiki_dir: Path,
        repository: SQLiteWikiRepository,
        source_repository: SQLiteSourceRepository,
    ) -> None:
        self.wiki_dir = wiki_dir.resolve()
        self.repository = repository
        self.source_repository = source_repository

    def initialize(self) -> None:
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        for directory in ("pages", "sources", "queries", "reviews"):
            (self.wiki_dir / directory).mkdir(parents=True, exist_ok=True)
        defaults = {
            "purpose.md": "# Wiki Purpose\n\nDefine the goals and questions for this wiki.\n",
            "schema.md": "# Wiki Schema\n\nThe Wiki Agent owns page structure and semantics.\n",
            "index.md": "# Wiki Index\n\nNo generated pages yet.\n",
            "overview.md": "# Wiki Overview\n\nThe wiki is empty.\n",
            "log.md": "# Wiki Log\n",
        }
        for name, content in defaults.items():
            path = self.wiki_dir / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")

    def read_special(self, name: str) -> str:
        if name not in SPECIAL_FILES:
            raise ValueError(f"Not a special wiki file: {name}")
        path = self.wiki_dir / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def catalog(self, source_ids: list[str] | None = None) -> list[WikiPageSummary]:
        return self.repository.list_summaries(source_ids)

    def scan_pages(self) -> list[WikiPage]:
        pages: list[WikiPage] = []
        for path in sorted(self.wiki_dir.rglob("*.md")):
            relative = path.relative_to(self.wiki_dir).as_posix()
            if relative in SPECIAL_FILES or relative.startswith("reviews/"):
                continue
            pages.append(self._read_page(path))
        return pages

    def get_pages(self, page_ids: list[str]) -> list[WikiPage]:
        requested = set(page_ids)
        pages = {page.id: page for page in self.scan_pages() if page.id in requested}
        return [pages[current_id] for current_id in page_ids if current_id in pages]

    def search(
        self,
        queries: list[str],
        limit: int,
        source_ids: list[str] | None = None,
    ) -> list[WikiPage]:
        page_ids: list[str] = []
        for query in queries:
            page_ids.extend(self.repository.search(query, limit, source_ids))
        return self.get_pages(list(dict.fromkeys(page_ids))[:limit])

    def apply_change_set(
        self,
        change_set: WikiChangeSet,
        overview_body: str | None = None,
    ) -> list[WikiPage]:
        existing = self.scan_pages()
        by_id = {page.id: page for page in existing}
        result = dict(by_id)
        changed_ids: list[str] = []
        old_paths_to_remove: set[Path] = set()
        now = utc_now_iso()

        for change in change_set.changes:
            if change.action == "delete":
                current = by_id.get(change.page_id or "")
                if current is None:
                    raise WikiValidationError(f"Unknown page for deletion: {change.page_id}")
                result.pop(current.id, None)
                old_paths_to_remove.add(current.path)
                changed_ids.append(current.id)
                continue

            current = by_id.get(change.page_id or "") if change.action == "update" else None
            if change.action == "update" and current is None:
                raise WikiValidationError(f"Unknown page for update: {change.page_id}")
            current_page_id = current.id if current else page_id()
            path = self._safe_generated_path(change.path)
            if current and current.path != path:
                old_paths_to_remove.add(current.path)
            evidence = self._merge_evidence(current_page_id, current, change)
            page = WikiPage(
                id=current_page_id,
                path=path,
                title=change.title.strip(),
                page_type=change.page_type.strip(),
                summary=change.summary.strip(),
                body=change.body.strip() + "\n",
                status=change.status,
                confidence=change.confidence,
                evidence_refs=evidence,
                related_page_ids=list(dict.fromkeys(change.related_page_ids)),
                created_at=current.created_at if current else now,
                updated_at=now,
            )
            result[current_page_id] = page
            changed_ids.append(current_page_id)

        pages = sorted(result.values(), key=lambda item: item.path.as_posix())
        self._validate_pages(pages)
        self._write_pages(pages, changed_ids)
        live_paths = {page.path for page in pages}
        for path in old_paths_to_remove - live_paths:
            path.unlink(missing_ok=True)

        body = overview_body if overview_body is not None else change_set.overview_body
        if body is not None:
            (self.wiki_dir / "overview.md").write_text(
                "# Wiki Overview\n\n" + body.strip() + "\n",
                encoding="utf-8",
            )

        refreshed = self.scan_pages()
        links = self._validate_pages(refreshed)
        self.repository.sync(refreshed, links)
        self._rebuild_index(refreshed)
        return [page for page in refreshed if page.id in set(changed_ids)]

    def rebuild(self) -> list[WikiPage]:
        self.initialize()
        pages = self.scan_pages()
        links = self._validate_pages(pages)
        self.repository.sync(pages, links)
        self._rebuild_index(pages)
        return pages

    def _read_page(self, path: Path) -> WikiPage:
        text = path.read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(text)
        evidence: list[EvidenceRef] = []
        for source in frontmatter.get("sources", []):
            source_id = str(source.get("source_id", "")).strip()
            for item in source.get("evidence", []):
                locator = str(item.get("locator", "")).strip()
                evidence.append(
                    EvidenceRef(
                        id=str(item.get("id") or evidence_ref_id(
                            str(frontmatter.get("id", "")),
                            source_id,
                            locator,
                        )),
                        source_id=source_id,
                        locator=locator,
                        quote_or_summary=str(item.get("quote_or_summary", "")).strip(),
                        modality=str(item.get("modality", "text")).strip() or "text",
                        confidence=float(item.get("confidence", 1.0)),
                    )
                )
        return WikiPage(
            id=str(frontmatter["id"]),
            path=path.resolve(),
            title=str(frontmatter["title"]),
            page_type=str(frontmatter.get("type", "knowledge")),
            summary=str(frontmatter.get("summary", "")),
            body=body.strip() + "\n",
            status=str(frontmatter.get("status", "active")),
            confidence=float(frontmatter.get("confidence", 1.0)),
            evidence_refs=evidence,
            related_page_ids=[
                str(value) for value in frontmatter.get("related_pages", [])
            ],
            created_at=str(frontmatter["created_at"]),
            updated_at=str(frontmatter["updated_at"]),
        )

    def _safe_generated_path(self, value: str) -> Path:
        relative = Path(value.strip())
        if relative.is_absolute() or ".." in relative.parts:
            raise WikiValidationError(f"Unsafe wiki path: {value}")
        if relative.suffix.lower() != ".md":
            raise WikiValidationError(f"Wiki page must use .md: {value}")
        if not relative.parts or relative.parts[0] not in WRITABLE_ROOTS:
            raise WikiValidationError(
                f"Generated pages must live under {sorted(WRITABLE_ROOTS)}: {value}"
            )
        path = (self.wiki_dir / relative).resolve()
        if self.wiki_dir not in path.parents:
            raise WikiValidationError(f"Wiki path escapes root: {value}")
        return path

    def _merge_evidence(
        self,
        page_id_value: str,
        current: WikiPage | None,
        change: PageChange,
    ) -> list[EvidenceRef]:
        merged = {
            (item.source_id, item.locator): item
            for item in (current.evidence_refs if current else [])
        }
        for item in change.evidence:
            merged[(item.source_id, item.locator)] = EvidenceRef(
                id=evidence_ref_id(page_id_value, item.source_id, item.locator),
                source_id=item.source_id,
                locator=item.locator,
                quote_or_summary=item.quote_or_summary,
                modality=item.modality,
                confidence=item.confidence,
            )
        return [merged[key] for key in sorted(merged)]

    def _validate_pages(self, pages: list[WikiPage]) -> dict[str, set[str]]:
        ids = [page.id for page in pages]
        paths = [page.path for page in pages]
        if len(ids) != len(set(ids)):
            raise WikiValidationError("Wiki page IDs must be unique.")
        if len(paths) != len(set(paths)):
            raise WikiValidationError("Wiki page paths must be unique.")

        valid_source_ids = {source.id for source in self.source_repository.list()}
        by_path = {
            page.path.relative_to(self.wiki_dir).as_posix(): page.id for page in pages
        }
        by_id = {page.id: page for page in pages}
        links: dict[str, set[str]] = defaultdict(set)
        for page in pages:
            if not page.title or not page.page_type or not page.summary:
                raise WikiValidationError(f"Page {page.id} lacks required metadata.")
            unknown_sources = {
                item.source_id for item in page.evidence_refs
            } - valid_source_ids
            if unknown_sources:
                raise WikiValidationError(
                    f"Page {page.id} references unknown sources: {sorted(unknown_sources)}"
                )
            unknown_related = set(page.related_page_ids) - set(by_id)
            if unknown_related:
                raise WikiValidationError(
                    f"Page {page.id} references unknown page IDs: {sorted(unknown_related)}"
                )
            links[page.id].update(page.related_page_ids)
            for target in WIKILINK_PATTERN.findall(page.body):
                normalized = target.strip().removesuffix(".md") + ".md"
                target_id = by_path.get(normalized)
                if target_id is None:
                    raise WikiValidationError(
                        f"Page {page.id} has dangling wikilink: {target}"
                    )
                links[page.id].add(target_id)
        return links

    def _write_pages(self, pages: list[WikiPage], changed_ids: list[str]) -> None:
        changed = set(changed_ids)
        for page in pages:
            if page.id not in changed:
                continue
            page.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = page.path.with_suffix(".md.tmp")
            temporary.write_text(_render_page(page), encoding="utf-8")
            temporary.replace(page.path)

    def _rebuild_index(self, pages: list[WikiPage]) -> None:
        grouped: dict[str, list[WikiPage]] = defaultdict(list)
        for page in pages:
            grouped[page.page_type].append(page)
        lines = [
            "# Wiki Index",
            "",
            "Generated deterministically from the current Markdown page catalog.",
            "",
        ]
        if not pages:
            lines.append("No generated pages yet.")
        for page_type in sorted(grouped, key=str.casefold):
            lines.extend([f"## {page_type}", ""])
            for page in sorted(grouped[page_type], key=lambda item: item.title.casefold()):
                relative = page.path.relative_to(self.wiki_dir).as_posix()
                lines.append(f"- [[{relative}|{page.title}]] — {page.summary}")
            lines.append("")
        (self.wiki_dir / "index.md").write_text(
            "\n".join(lines).rstrip() + "\n",
            encoding="utf-8",
        )


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        raise WikiValidationError("Generated wiki page lacks YAML frontmatter.")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise WikiValidationError("Generated wiki page has invalid YAML frontmatter.")
    raw = text[4:end]
    payload = yaml.safe_load(raw) or {}
    if not isinstance(payload, dict):
        raise WikiValidationError("Wiki frontmatter must be a mapping.")
    required = {"id", "title", "created_at", "updated_at"}
    missing = required - set(payload)
    if missing:
        raise WikiValidationError(f"Wiki frontmatter missing: {sorted(missing)}")
    return payload, text[end + 5 :]


def _render_page(page: WikiPage) -> str:
    evidence_by_source: dict[str, list[EvidenceRef]] = defaultdict(list)
    for item in page.evidence_refs:
        evidence_by_source[item.source_id].append(item)
    sources = [
        {
            "source_id": source_id,
            "evidence": [
                {
                    "id": item.id,
                    "locator": item.locator,
                    "quote_or_summary": item.quote_or_summary,
                    "modality": item.modality,
                    "confidence": item.confidence,
                }
                for item in evidence_by_source[source_id]
            ],
        }
        for source_id in sorted(evidence_by_source)
    ]
    frontmatter = {
        "id": page.id,
        "title": page.title,
        "type": page.page_type,
        "status": page.status,
        "summary": page.summary,
        "sources": sources,
        "related_pages": page.related_page_ids,
        "confidence": page.confidence,
        "created_at": page.created_at,
        "updated_at": page.updated_at,
    }
    rendered = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    ).strip()
    return f"---\n{rendered}\n---\n\n{page.body.strip()}\n"
