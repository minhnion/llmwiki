from pydantic import BaseModel, ConfigDict, Field


class ClaimEvidenceContext(BaseModel):
    evidence_id: str
    locator: str
    text: str
    summary: str

    model_config = ConfigDict(extra="forbid")


class ClaimGraphContext(BaseModel):
    claim_id: str
    source_id: str
    source_title: str
    text: str
    subject: str
    predicate: str
    object: str
    status: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[ClaimEvidenceContext]
    entities: list[str]

    model_config = ConfigDict(extra="forbid")


class ExtractedRelation(BaseModel):
    subject: str
    predicate: str
    object: str
    object_type: str = Field(description="entity, text, number, date, metric, or unknown.")
    claim_id: str
    evidence_id: str
    confidence: float = Field(ge=0, le=1)
    status: str = Field(description="active, uncertain, contradicted, superseded, or review.")
    qualifiers: list[str]

    model_config = ConfigDict(extra="forbid")


class ExtractedEntityMergeCandidate(BaseModel):
    entity_a: str
    entity_b: str
    reason: str
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class GraphExtractionResult(BaseModel):
    relations: list[ExtractedRelation]
    entity_merge_candidates: list[ExtractedEntityMergeCandidate]
    notes: list[str]

    model_config = ConfigDict(extra="forbid")


class ExtractedContradiction(BaseModel):
    claim_a_id: str
    claim_b_id: str
    relationship: str = Field(
        description="contradicts, qualifies, duplicates, supports, or unrelated."
    )
    reason: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]

    model_config = ConfigDict(extra="forbid")


class ContradictionDetectionResult(BaseModel):
    contradictions: list[ExtractedContradiction]
    notes: list[str]

    model_config = ConfigDict(extra="forbid")


class RelationEdge(BaseModel):
    id: str
    subject_entity_id: str | None
    subject_name: str
    predicate: str
    object_entity_id: str | None
    object_value: str
    object_type: str
    claim_id: str
    evidence_id: str
    source_id: str
    confidence: float = Field(ge=0, le=1)
    status: str
    qualifiers: list[str]
    created_at: str
    updated_at: str

    model_config = ConfigDict(extra="forbid")


class EntityMergeCandidate(BaseModel):
    id: str
    entity_a_id: str | None
    entity_b_id: str | None
    entity_a_name: str
    entity_b_name: str
    reason: str
    confidence: float = Field(ge=0, le=1)
    status: str
    created_at: str

    model_config = ConfigDict(extra="forbid")


class Contradiction(BaseModel):
    id: str
    claim_a_id: str
    claim_b_id: str
    relationship: str
    reason: str
    confidence: float = Field(ge=0, le=1)
    status: str
    evidence_ids: list[str]
    created_at: str

    model_config = ConfigDict(extra="forbid")


class GraphBuildCommand(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    rebuild: bool = True
    max_claims_per_batch: int = Field(default=40, ge=2, le=120)

    model_config = ConfigDict(extra="forbid")


class GraphBuildResult(BaseModel):
    graph_run_id: str
    source_ids: list[str]
    claim_count: int
    relation_count: int
    contradiction_count: int
    merge_candidate_count: int
    entity_page_count: int
    status: str
    started_at: str
    finished_at: str

    model_config = ConfigDict(extra="forbid")


class GraphEntity(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: str
    aliases: list[str]
    description: str
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class GraphEntityDetail(BaseModel):
    entity: GraphEntity
    outgoing_relations: list[RelationEdge]
    incoming_relations: list[RelationEdge]
    merge_candidates: list[EntityMergeCandidate]
    page_path: str | None = None

    model_config = ConfigDict(extra="forbid")


class GraphSearchResult(BaseModel):
    entities: list[GraphEntity]
    relations: list[RelationEdge]

    model_config = ConfigDict(extra="forbid")


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: str
    confidence: float | None = None

    model_config = ConfigDict(extra="forbid")


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    confidence: float
    claim_id: str
    evidence_id: str

    model_config = ConfigDict(extra="forbid")


class GraphVisualization(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    model_config = ConfigDict(extra="forbid")


GRAPH_EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "object_type": {"type": "string"},
                    "claim_id": {"type": "string"},
                    "evidence_id": {"type": "string"},
                    "confidence": {"type": "number"},
                    "status": {"type": "string"},
                    "qualifiers": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "subject",
                    "predicate",
                    "object",
                    "object_type",
                    "claim_id",
                    "evidence_id",
                    "confidence",
                    "status",
                    "qualifiers",
                ],
            },
        },
        "entity_merge_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "entity_a": {"type": "string"},
                    "entity_b": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["entity_a", "entity_b", "reason", "confidence"],
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["relations", "entity_merge_candidates", "notes"],
}


CONTRADICTION_DETECTION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim_a_id": {"type": "string"},
                    "claim_b_id": {"type": "string"},
                    "relationship": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "claim_a_id",
                    "claim_b_id",
                    "relationship",
                    "reason",
                    "confidence",
                    "evidence_ids",
                ],
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["contradictions", "notes"],
}
