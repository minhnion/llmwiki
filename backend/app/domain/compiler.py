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


class ObservedDetail(BaseModel):
    local_id: str
    source_unit_id: str
    detail_kind: str
    description: str
    locator: SourceLocator
    importance: float = Field(ge=0, le=1)
    query_hint: str

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
    target_detail_ids: list[str] = Field(default_factory=list)
    expected_outputs: list[str]

    model_config = ConfigDict(extra="forbid")


class SourceManifest(BaseModel):
    source_id: str
    language: str
    document_profile: SourceProfile
    content_units: list[SourceUnit]
    observed_details: list[ObservedDetail] = Field(default_factory=list)
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
        detail_ids = [detail.local_id for detail in self.observed_details]
        if len(detail_ids) != len(set(detail_ids)):
            raise ValueError("Source manifest observed detail local IDs must be unique.")
        detail_unit_refs = {detail.source_unit_id for detail in self.observed_details}
        unknown_detail_units = detail_unit_refs - valid_unit_ids
        if unknown_detail_units:
            raise ValueError(
                "Source manifest observed details reference unknown units: "
                f"{sorted(unknown_detail_units)}"
            )
        valid_detail_ids = set(detail_ids)
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
            unknown_details = set(plan.target_detail_ids) - valid_detail_ids
            if unknown_details:
                raise ValueError(
                    f"Compilation pass {plan.pass_id} references unknown details: "
                    f"{sorted(unknown_details)}"
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


class StatementReference(BaseModel):
    artifact_local_id: str
    statement_local_id: str

    model_config = ConfigDict(extra="forbid")


class CompiledDetailCoverage(BaseModel):
    detail_id: str
    status: Literal["covered", "weak", "missing", "ambiguous"]
    evidence_local_ids: list[str]
    artifact_local_ids: list[str]
    statement_refs: list[StatementReference]
    notes: str
    confidence: float = Field(ge=0, le=1)

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
    ledger_items: list[ObservedDetail] = Field(default_factory=list)
    discovered_details: list[ObservedDetail] = Field(default_factory=list)
    evidence_items: list[CompiledEvidence]
    artifacts: list[CompiledArtifact]
    semantic_nodes: list[CompiledSemanticNode]
    relations: list[CompiledRelation]
    detail_coverage: list[CompiledDetailCoverage] = Field(default_factory=list)
    review_items: list[CompilerReviewItem]
    covered_unit_ids: list[str]
    notes: list[str]

    model_config = ConfigDict(extra="forbid")


class RecommendedCompilationPass(BaseModel):
    pass_id: str
    objective: str
    target_unit_ids: list[str]
    target_detail_ids: list[str] = Field(default_factory=list)
    expected_outputs: list[str]

    model_config = ConfigDict(extra="forbid")

    def as_plan(self) -> CompilationPassPlan:
        return CompilationPassPlan.model_validate(self.model_dump())


class CoverageGap(BaseModel):
    description: str
    likely_unit_ids: list[str]
    likely_detail_ids: list[str] = Field(default_factory=list)
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


class CoverageDetailAssessment(BaseModel):
    detail_id: str
    unit_id: str
    status: Literal["covered", "missing", "weak", "ambiguous"]
    represented_knowledge: list[str]
    missing_knowledge: list[str]
    evidence_local_ids: list[str]
    artifact_local_ids: list[str]
    statement_refs: list[StatementReference]
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class CoverageReport(BaseModel):
    additional_details: list[ObservedDetail] = Field(default_factory=list)
    coverage_status: Literal["complete", "incomplete", "needs_review"]
    covered_unit_ids: list[str]
    unit_assessments: list[CoverageUnitAssessment]
    detail_assessments: list[CoverageDetailAssessment] = Field(default_factory=list)
    missing_or_weak_areas: list[CoverageGap]
    provenance_issues: list[str]
    overgeneralization_risks: list[str]
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class CompilationBundle(BaseModel):
    ledger_items: list[ObservedDetail] = Field(default_factory=list)
    discovered_details: list[ObservedDetail] = Field(default_factory=list)
    evidence_items: list[CompiledEvidence]
    artifacts: list[CompiledArtifact]
    semantic_nodes: list[CompiledSemanticNode]
    relations: list[CompiledRelation]
    detail_coverage: list[CompiledDetailCoverage] = Field(default_factory=list)
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


def _structured_output_schema(
    model: type[BaseModel],
    root_required: tuple[str, ...] = (),
    def_required: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, object]:
    schema = model.model_json_schema()
    _require_fields(schema, root_required)
    for def_name, fields in (def_required or {}).items():
        definition = schema.get("$defs", {}).get(def_name)
        if isinstance(definition, dict):
            _require_fields(definition, fields)
    return schema


def _require_fields(schema: dict[str, object], fields: tuple[str, ...]) -> None:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return
    required = list(schema.get("required", []))
    for field in fields:
        if field in properties and field not in required:
            required.append(field)
    schema["required"] = required


SOURCE_MANIFEST_JSON_SCHEMA = _structured_output_schema(
    SourceManifest,
    root_required=("observed_details",),
    def_required={"CompilationPassPlan": ("target_detail_ids",)},
)
COMPILATION_PASS_JSON_SCHEMA = _structured_output_schema(
    CompilationPassResult,
    root_required=("ledger_items", "discovered_details", "detail_coverage"),
)
COVERAGE_REPORT_JSON_SCHEMA = _structured_output_schema(
    CoverageReport,
    root_required=("additional_details", "detail_assessments"),
    def_required={
        "CoverageGap": ("likely_detail_ids",),
        "RecommendedCompilationPass": ("target_detail_ids",),
    },
)
WIKI_INTEGRATION_PLAN_JSON_SCHEMA = WikiIntegrationPlan.model_json_schema()
