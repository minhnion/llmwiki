from pydantic import BaseModel, ConfigDict, Field


class ExtractedEvidence(BaseModel):
    locator: str = Field(description="Source-local locator such as page, section, sheet, or image.")
    modality: str = Field(description="text, image, table, chart, spreadsheet, pdf_page, or mixed.")
    text: str = Field(description="Short direct evidence text or visual/table description.")
    summary: str = Field(description="Concise explanation of why this evidence matters.")
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class ExtractedClaim(BaseModel):
    text: str
    subject: str
    predicate: str
    object: str
    evidence_locators: list[str]
    confidence: float = Field(ge=0, le=1)
    status: str = Field(description="active, uncertain, contradicted, superseded, or needs_review.")

    model_config = ConfigDict(extra="forbid")


class ExtractedEntity(BaseModel):
    name: str
    entity_type: str
    aliases: list[str]
    description: str
    evidence_locators: list[str]
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class ExtractedReviewItem(BaseModel):
    review_type: str
    title: str
    body: str
    severity: str = Field(description="low, medium, high, or critical.")
    evidence_locators: list[str]

    model_config = ConfigDict(extra="forbid")


class IngestExtractionResult(BaseModel):
    source_title: str
    source_summary: str
    source_language: str
    document_type: str
    key_takeaways: list[str]
    evidence_items: list[ExtractedEvidence]
    claims: list[ExtractedClaim]
    entities: list[ExtractedEntity]
    review_items: list[ExtractedReviewItem]
    open_questions: list[str]

    model_config = ConfigDict(extra="forbid")


INGEST_EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "source_title": {"type": "string"},
        "source_summary": {"type": "string"},
        "source_language": {"type": "string"},
        "document_type": {"type": "string"},
        "key_takeaways": {"type": "array", "items": {"type": "string"}},
        "evidence_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "locator": {"type": "string"},
                    "modality": {"type": "string"},
                    "text": {"type": "string"},
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["locator", "modality", "text", "summary", "confidence"],
            },
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "evidence_locators": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "status": {"type": "string"},
                },
                "required": [
                    "text",
                    "subject",
                    "predicate",
                    "object",
                    "evidence_locators",
                    "confidence",
                    "status",
                ],
            },
        },
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "description": {"type": "string"},
                    "evidence_locators": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "name",
                    "entity_type",
                    "aliases",
                    "description",
                    "evidence_locators",
                    "confidence",
                ],
            },
        },
        "review_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "review_type": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "severity": {"type": "string"},
                    "evidence_locators": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["review_type", "title", "body", "severity", "evidence_locators"],
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "source_title",
        "source_summary",
        "source_language",
        "document_type",
        "key_takeaways",
        "evidence_items",
        "claims",
        "entities",
        "review_items",
        "open_questions",
    ],
}
