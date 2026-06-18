from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OpenMetadataItem(BaseModel):
    key: str
    value: str

    model_config = ConfigDict(extra="forbid")


class SourceLocator(BaseModel):
    kind: str
    value: str
    metadata: list[OpenMetadataItem]

    model_config = ConfigDict(extra="forbid")


class SourceProfile(BaseModel):
    kind: str
    summary: str
    modalities: list[str]
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class SourceUnit(BaseModel):
    local_id: str
    label: str
    locator: SourceLocator
    summary: str
    importance: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class KnowledgeLens(BaseModel):
    name: str
    reason: str
    priority: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class CompilationPassPlan(BaseModel):
    pass_id: str
    objective: str
    target_unit_ids: list[str]
    expected_outputs: list[str]

    model_config = ConfigDict(extra="forbid")


class SourceManifest(BaseModel):
    source_id: str
    language: str
    document_profile: SourceProfile
    content_units: list[SourceUnit]
    candidate_knowledge_lenses: list[KnowledgeLens]
    compilation_plan: list[CompilationPassPlan]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_manifest_references(self) -> "SourceManifest":
        unit_ids = [unit.local_id for unit in self.content_units]
        if not unit_ids:
            raise ValueError("Source manifest must contain semantic content units.")
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("Source manifest content unit local IDs must be unique.")
        pass_ids = [plan.pass_id for plan in self.compilation_plan]
        if not pass_ids:
            raise ValueError("Source manifest must contain a compilation plan.")
        if len(pass_ids) != len(set(pass_ids)):
            raise ValueError("Source manifest compilation pass IDs must be unique.")
        valid_unit_ids = set(unit_ids)
        for plan in self.compilation_plan:
            if not plan.target_unit_ids:
                raise ValueError(
                    f"Compilation pass {plan.pass_id} must target source units."
                )
            unknown = set(plan.target_unit_ids) - valid_unit_ids
            if unknown:
                raise ValueError(
                    f"Compilation pass {plan.pass_id} references unknown units: "
                    f"{sorted(unknown)}"
                )
        return self


class CompiledEvidence(BaseModel):
    local_id: str
    source_unit_ids: list[str]
    locator: SourceLocator
    modality: str
    content: str
    summary: str
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class ArtifactStatement(BaseModel):
    local_id: str
    statement_type: str
    text: str
    subject: str
    predicate: str
    object: str
    object_type: str
    evidence_local_ids: list[str]
    source_unit_ids: list[str]
    qualifiers: list[OpenMetadataItem]
    confidence: float = Field(ge=0, le=1)
    status: Literal["active", "uncertain", "contradicted", "superseded", "needs_review"]

    model_config = ConfigDict(extra="forbid")


class CompiledArtifact(BaseModel):
    local_id: str
    artifact_type: str
    title: str
    summary: str
    content: str
    aliases: list[str]
    scope: list[OpenMetadataItem]
    evidence_local_ids: list[str]
    source_unit_ids: list[str]
    related_artifact_local_ids: list[str]
    statements: list[ArtifactStatement]
    confidence: float = Field(ge=0, le=1)
    status: Literal["active", "uncertain", "contradicted", "superseded", "needs_review"]
    review_status: Literal["unreviewed"]
    metadata: list[OpenMetadataItem]

    model_config = ConfigDict(extra="forbid")


class CompiledRelation(BaseModel):
    source_artifact_local_id: str
    target_artifact_local_id: str
    target_literal: str
    relation_type: str
    evidence_local_ids: list[str]
    qualifiers: list[OpenMetadataItem]
    confidence: float = Field(ge=0, le=1)
    status: Literal["active", "uncertain", "contradicted", "superseded", "needs_review"]

    model_config = ConfigDict(extra="forbid")


class CompilerReviewItem(BaseModel):
    review_type: str
    title: str
    body: str
    severity: str
    evidence_local_ids: list[str]
    artifact_local_ids: list[str]

    model_config = ConfigDict(extra="forbid")


class CompiledSemanticNode(BaseModel):
    local_id: str
    name: str
    node_type: str
    aliases: list[str]
    description: str
    evidence_local_ids: list[str]
    source_unit_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    status: Literal["active", "uncertain", "needs_review"]

    model_config = ConfigDict(extra="forbid")


class CompilationPassResult(BaseModel):
    pass_id: str
    evidence_items: list[CompiledEvidence]
    artifacts: list[CompiledArtifact]
    semantic_nodes: list[CompiledSemanticNode]
    relations: list[CompiledRelation]
    review_items: list[CompilerReviewItem]
    covered_unit_ids: list[str]
    notes: list[str]

    model_config = ConfigDict(extra="forbid")


class RecommendedCompilationPass(BaseModel):
    pass_id: str
    objective: str
    target_unit_ids: list[str]
    expected_outputs: list[str]

    model_config = ConfigDict(extra="forbid")

    def as_plan(self) -> CompilationPassPlan:
        return CompilationPassPlan.model_validate(self.model_dump())


class CoverageGap(BaseModel):
    description: str
    likely_unit_ids: list[str]
    severity: str
    recommended_pass: RecommendedCompilationPass

    model_config = ConfigDict(extra="forbid")


class CoverageUnitAssessment(BaseModel):
    unit_id: str
    status: Literal["complete", "incomplete", "needs_review"]
    represented_knowledge: list[str]
    missing_knowledge: list[str]
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class CoverageReport(BaseModel):
    coverage_status: Literal["complete", "incomplete", "needs_review"]
    covered_unit_ids: list[str]
    unit_assessments: list[CoverageUnitAssessment]
    missing_or_weak_areas: list[CoverageGap]
    provenance_issues: list[str]
    overgeneralization_risks: list[str]
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class CompilationBundle(BaseModel):
    evidence_items: list[CompiledEvidence]
    artifacts: list[CompiledArtifact]
    semantic_nodes: list[CompiledSemanticNode]
    relations: list[CompiledRelation]
    review_items: list[CompilerReviewItem]
    covered_unit_ids: list[str]
    notes: list[str]

    model_config = ConfigDict(extra="forbid")


class WikiPagePlan(BaseModel):
    local_id: str
    title: str
    page_type: str
    summary: str
    artifact_local_ids: list[str]
    related_page_local_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    review_status: Literal["unreviewed"]

    model_config = ConfigDict(extra="forbid")


class WikiIntegrationPlan(BaseModel):
    pages: list[WikiPagePlan]
    notes: list[str]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_page_references(self) -> "WikiIntegrationPlan":
        page_ids = [page.local_id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("Wiki page local IDs must be unique.")
        valid_page_ids = set(page_ids)
        for page in self.pages:
            unknown = set(page.related_page_local_ids) - valid_page_ids
            if unknown:
                raise ValueError(
                    f"Wiki page {page.local_id} references unknown pages: {sorted(unknown)}"
                )
        return self


class CompilerPassStatus(BaseModel):
    pass_id: str
    iteration: int
    objective: str
    status: str
    error: str | None
    started_at: str
    finished_at: str | None

    model_config = ConfigDict(extra="forbid")


class CompilationInspection(BaseModel):
    compiler_run_id: str
    source_id: str
    status: str
    current_stage: str
    compiler_version: str
    prompt_version: str
    schema_version: str
    model: str
    pass_count: int
    coverage_status: str | None
    started_at: str
    finished_at: str | None
    error: str | None
    manifest: SourceManifest
    passes: list[CompilerPassStatus]
    coverage_reports: list[CoverageReport]
    artifacts: list[CompiledArtifact]
    semantic_nodes: list[CompiledSemanticNode]

    model_config = ConfigDict(extra="forbid")


SOURCE_MANIFEST_JSON_SCHEMA = SourceManifest.model_json_schema()
COMPILATION_PASS_JSON_SCHEMA = CompilationPassResult.model_json_schema()
COVERAGE_REPORT_JSON_SCHEMA = CoverageReport.model_json_schema()
WIKI_INTEGRATION_PLAN_JSON_SCHEMA = WikiIntegrationPlan.model_json_schema()
