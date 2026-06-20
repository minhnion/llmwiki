from dataclasses import dataclass
from typing import Protocol

from backend.app.core.clock import utc_now_iso
from backend.app.core.text import compact_text, stable_hash
from backend.app.repositories.semantic import (
    ArtifactEmbeddingRecord,
    ArtifactIndexRecord,
    SQLiteSemanticRepository,
)


class EmbeddingClient(Protocol):
    async def embed_texts(self, texts: list[str], model: str) -> list[list[float]]:
        """Return one embedding vector per input text."""


@dataclass(frozen=True)
class SemanticIndexResult:
    artifact_count: int
    embedding_count: int
    knowledge_map_entry_count: int


@dataclass(frozen=True)
class ArtifactRepresentation:
    artifact_id: str
    source_id: str
    representation_type: str
    text: str
    content_hash: str


class SemanticIndexer:
    def __init__(
        self,
        repository: SQLiteSemanticRepository,
        embedding_client: EmbeddingClient,
        embedding_model: str,
    ) -> None:
        self.repository = repository
        self.embedding_client = embedding_client
        self.embedding_model = embedding_model

    async def index_source(self, source_id: str) -> SemanticIndexResult:
        return await self.index(source_ids=[source_id])

    async def index(self, source_ids: list[str] | None = None) -> SemanticIndexResult:
        artifacts = self.repository.list_artifacts_for_indexing(source_ids or [])
        representations = [
            representation
            for artifact in artifacts
            for representation in _represent_artifact(artifact)
            if representation.text.strip()
        ]
        existing_hashes = self.repository.embedding_content_hashes(self.embedding_model)
        pending = [
            representation
            for representation in representations
            if existing_hashes.get(
                (representation.artifact_id, representation.representation_type)
            )
            != representation.content_hash
        ]

        embedding_records: list[ArtifactEmbeddingRecord] = []
        if pending:
            vectors = await self.embedding_client.embed_texts(
                [item.text for item in pending],
                self.embedding_model,
            )
            if len(vectors) != len(pending):
                raise ValueError("Embedding client returned a different number of vectors.")
            embedding_records = [
                ArtifactEmbeddingRecord(
                    artifact_id=item.artifact_id,
                    source_id=item.source_id,
                    representation_type=item.representation_type,
                    embedding_model=self.embedding_model,
                    vector=vector,
                    content_hash=item.content_hash,
                )
                for item, vector in zip(pending, vectors, strict=True)
            ]
            self.repository.save_embeddings(embedding_records, utc_now_iso())

        map_entry_count = self.repository.refresh_knowledge_map(utc_now_iso())
        return SemanticIndexResult(
            artifact_count=len(artifacts),
            embedding_count=len(embedding_records),
            knowledge_map_entry_count=map_entry_count,
        )


def _represent_artifact(artifact: ArtifactIndexRecord) -> list[ArtifactRepresentation]:
    summary_text = _join_lines(
        [
            f"Artifact: {artifact.title}",
            f"Type: {artifact.artifact_type}",
            _optional_line("Aliases", artifact.aliases),
            _optional_line("Scope", artifact.scope),
            f"Summary: {artifact.summary}",
            f"Status: {artifact.status}; review: {artifact.review_status}",
        ]
    )
    detail_text = _join_lines(
        [
            f"Artifact: {artifact.title}",
            f"Type: {artifact.artifact_type}",
            _optional_line("Aliases", artifact.aliases),
            _optional_line("Scope", artifact.scope),
            f"Summary: {artifact.summary}",
            f"Content: {artifact.content}",
            _optional_line("Atomic statements", artifact.statements),
        ]
    )
    question_text = _join_lines(
        [
            f"Knowledge unit: {artifact.title}",
            f"Useful for questions about: {artifact.summary}",
            _optional_line("Also known as", artifact.aliases),
            _optional_line("Evidence-backed statements", artifact.statements[:12]),
        ]
    )
    relation_text = _join_lines(
        [
            f"Artifact: {artifact.title}",
            _optional_line("Relations", artifact.relations),
            _optional_line("Statements", artifact.statements[:16]),
        ]
    )
    return [
        _representation(artifact, "summary", summary_text),
        _representation(artifact, "detail", detail_text),
        _representation(artifact, "question", question_text),
        _representation(artifact, "relation", relation_text),
    ]


def _representation(
    artifact: ArtifactIndexRecord,
    representation_type: str,
    text: str,
) -> ArtifactRepresentation:
    compacted = compact_text(text, 6000)
    return ArtifactRepresentation(
        artifact_id=artifact.artifact_id,
        source_id=artifact.source_id,
        representation_type=representation_type,
        text=compacted,
        content_hash=stable_hash(
            artifact.content_hash,
            representation_type,
            compacted,
            length=64,
        ),
    )


def _optional_line(label: str, values: list[str]) -> str:
    clean_values = [value.strip() for value in values if value.strip()]
    if not clean_values:
        return ""
    return f"{label}: " + "; ".join(clean_values)


def _join_lines(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line.strip())
