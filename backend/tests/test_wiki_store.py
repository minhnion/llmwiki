from backend.app.domain.agent import EvidenceDraft, PageChange, WikiChangeSet
from backend.tests.helpers import build_test_context, register_text_source


def test_wiki_store_commits_pages_and_rebuilds_index(tmp_path) -> None:
    database, wiki_dir, _, store = build_test_context(tmp_path)
    source = register_text_source(tmp_path, database, wiki_dir)
    changes = WikiChangeSet(
        changes=[
            PageChange(
                action="create",
                page_id=None,
                path="pages/topic.md",
                title="Topic",
                page_type="open type",
                summary="A reusable topic.",
                body="# Topic\n\nSource-grounded knowledge.",
                status="active",
                confidence=0.9,
                evidence=[
                    EvidenceDraft(
                        source_id=source.id,
                        locator="line 1",
                        quote_or_summary="A persistent wiki accumulates knowledge.",
                        modality="text",
                        confidence=0.9,
                    )
                ],
                related_page_ids=[],
            )
        ],
        reviews=[],
        overview_body="One topic is available.",
        notes=[],
    )

    changed = store.apply_change_set(changes)

    assert len(changed) == 1
    assert (wiki_dir / "pages" / "topic.md").exists()
    index = (wiki_dir / "index.md").read_text(encoding="utf-8")
    assert "[[pages/topic.md|Topic]]" in index
    assert store.search(["reusable topic"], 5)[0].id == changed[0].id


def test_wiki_store_preserves_existing_provenance_on_update(tmp_path) -> None:
    database, wiki_dir, _, store = build_test_context(tmp_path)
    source = register_text_source(tmp_path, database, wiki_dir)
    created = store.apply_change_set(
        WikiChangeSet(
            changes=[
                PageChange(
                    action="create",
                    page_id=None,
                    path="pages/topic.md",
                    title="Topic",
                    page_type="knowledge",
                    summary="Initial.",
                    body="# Topic\n\nInitial knowledge.",
                    status="active",
                    confidence=0.8,
                    evidence=[
                        EvidenceDraft(
                            source_id=source.id,
                            locator="line 1",
                            quote_or_summary="Initial evidence.",
                            modality="text",
                            confidence=0.8,
                        )
                    ],
                    related_page_ids=[],
                )
            ],
            reviews=[],
            overview_body=None,
            notes=[],
        )
    )[0]
    updated = store.apply_change_set(
        WikiChangeSet(
            changes=[
                PageChange(
                    action="update",
                    page_id=created.id,
                    path="pages/topic.md",
                    title="Topic",
                    page_type="knowledge",
                    summary="Updated.",
                    body="# Topic\n\nUpdated knowledge.",
                    status="active",
                    confidence=0.9,
                    evidence=[],
                    related_page_ids=[],
                )
            ],
            reviews=[],
            overview_body=None,
            notes=[],
        )
    )[0]

    assert len(updated.evidence_refs) == 1
    assert updated.evidence_refs[0].source_id == source.id
