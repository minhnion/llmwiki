import asyncio
import base64
import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from openai import OpenAI

from backend.app.core.text import compact_text
from backend.app.domain.compiler import (
    COMPILATION_PASS_JSON_SCHEMA,
    COVERAGE_REPORT_JSON_SCHEMA,
    SOURCE_MANIFEST_JSON_SCHEMA,
    WIKI_INTEGRATION_PLAN_JSON_SCHEMA,
    CompilationBundle,
    CompilationPassPlan,
    CompilationPassResult,
    CoverageReport,
    SourceManifest,
    WikiIntegrationPlan,
)
from backend.app.domain.extraction import (
    INGEST_EXTRACTION_JSON_SCHEMA,
    IngestExtractionResult,
)
from backend.app.domain.graph import (
    CONTRADICTION_DETECTION_JSON_SCHEMA,
    GRAPH_EXTRACTION_JSON_SCHEMA,
    ClaimGraphContext,
    ContradictionDetectionResult,
    GraphExtractionResult,
)
from backend.app.domain.models import SourceRef
from backend.app.domain.query import (
    ARTIFACT_RANKING_JSON_SCHEMA,
    EVIDENCE_RANKING_JSON_SCHEMA,
    KNOWLEDGE_NAVIGATION_JSON_SCHEMA,
    QUERY_PLAN_JSON_SCHEMA,
    QUERY_SYNTHESIS_JSON_SCHEMA,
    ArtifactCandidate,
    ArtifactRankingResult,
    EvidenceCandidate,
    EvidenceRankingResult,
    KnowledgeMapEntryCandidate,
    KnowledgeNavigationResult,
    QueryAskCommand,
    QueryPlan,
    QuerySynthesisResult,
)


@dataclass(frozen=True)
class LLMRequest:
    instructions: str
    inputs: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    structured: dict[str, object] | None = None


class LLMClient(Protocol):
    async def create_response(self, request: LLMRequest) -> LLMResponse:
        """Create a model response for an application workflow."""

    async def extract_source(self, source: SourceRef) -> IngestExtractionResult:
        """Extract wiki-ready knowledge from a source file."""

    async def embed_texts(self, texts: list[str], model: str) -> list[list[float]]:
        """Embed texts for semantic artifact retrieval."""


class OpenAIResponsesClient:
    """Adapter for OpenAI Responses API file and structured-output calls."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_output_tokens: int = 6000,
        preferred_language: str = "vi",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.preferred_language = preferred_language
        self.client = OpenAI(api_key=api_key)

    async def create_response(self, request: LLMRequest) -> LLMResponse:
        response = await asyncio.to_thread(
            self.client.responses.create,
            model=self.model,
            instructions=request.instructions,
            input=request.inputs,
            max_output_tokens=self.max_output_tokens,
        )
        return LLMResponse(text=response.output_text)

    async def embed_texts(self, texts: list[str], model: str) -> list[list[float]]:
        if not texts:
            return []
        response = await asyncio.to_thread(
            self.client.embeddings.create,
            model=model,
            input=texts,
        )
        return [list(item.embedding) for item in response.data]

    async def extract_source(self, source: SourceRef) -> IngestExtractionResult:
        file_data = _base64_file_data(source.path, source.mime_type)
        payload = await self._create_structured_response(
            name="llm_wiki_ingest_extraction",
            schema=INGEST_EXTRACTION_JSON_SCHEMA,
            instructions=_ingest_instructions(self.preferred_language),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": source.path.name,
                            "file_data": file_data,
                        },
                        {
                            "type": "input_text",
                            "text": _source_prompt(source, self.preferred_language),
                        },
                    ],
                }
            ],
        )
        return IngestExtractionResult.model_validate(payload)

    async def profile_source(self, source: SourceRef) -> SourceManifest:
        payload = await self._create_structured_response(
            name="llm_wiki_source_manifest_v2",
            schema=SOURCE_MANIFEST_JSON_SCHEMA,
            instructions=_source_profile_instructions(self.preferred_language),
            inputs=[_file_input(source, _source_profile_prompt(source))],
        )
        manifest = SourceManifest.model_validate(payload)
        if manifest.source_id != source.id:
            manifest = manifest.model_copy(update={"source_id": source.id})
        return manifest

    async def compile_source_pass(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        plan: CompilationPassPlan,
        existing: CompilationBundle,
    ) -> CompilationPassResult:
        payload = await self._create_structured_response(
            name="llm_wiki_compilation_pass_v2",
            schema=COMPILATION_PASS_JSON_SCHEMA,
            instructions=_compilation_pass_instructions(self.preferred_language),
            inputs=[
                _file_input(
                    source,
                    json.dumps(
                        {
                            "source_id": source.id,
                            "manifest": manifest.model_dump(),
                            "pass_plan": plan.model_dump(),
                            "existing_compilation": _compact_compilation(existing),
                        },
                        ensure_ascii=False,
                    ),
                )
            ],
        )
        result = CompilationPassResult.model_validate(payload)
        if result.pass_id != plan.pass_id:
            result = result.model_copy(update={"pass_id": plan.pass_id})
        return result

    async def audit_compilation(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        compilation: CompilationBundle,
        iteration: int,
    ) -> CoverageReport:
        payload = await self._create_structured_response(
            name="llm_wiki_coverage_report_v2",
            schema=COVERAGE_REPORT_JSON_SCHEMA,
            instructions=_coverage_audit_instructions(self.preferred_language),
            inputs=[
                _file_input(
                    source,
                    json.dumps(
                        {
                            "source_id": source.id,
                            "audit_iteration": iteration,
                            "manifest": manifest.model_dump(),
                            "compiled_knowledge": _audit_compilation_payload(compilation),
                        },
                        ensure_ascii=False,
                    ),
                )
            ],
        )
        return CoverageReport.model_validate(payload)

    async def plan_wiki_integration(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        compilation: CompilationBundle,
    ) -> WikiIntegrationPlan:
        payload = await self._create_structured_response(
            name="llm_wiki_integration_plan_v3",
            schema=WIKI_INTEGRATION_PLAN_JSON_SCHEMA,
            instructions=_wiki_integration_instructions(self.preferred_language),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "source_id": source.id,
                                    "source_title": source.title,
                                    "manifest": manifest.model_dump(),
                                    "compiled_knowledge": _audit_compilation_payload(
                                        compilation
                                    ),
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        )
        return WikiIntegrationPlan.model_validate(payload)

    async def plan_query(self, command: QueryAskCommand) -> QueryPlan:
        payload = await self._create_structured_response(
            name="llm_wiki_query_plan",
            schema=QUERY_PLAN_JSON_SCHEMA,
            instructions=_query_plan_instructions(self.preferred_language),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(command.model_dump(), ensure_ascii=False),
                        }
                    ],
                }
            ],
        )
        return QueryPlan.model_validate(payload)

    async def navigate_knowledge(
        self,
        question: str,
        plan: QueryPlan,
        map_entries: list[KnowledgeMapEntryCandidate],
        max_artifacts: int,
    ) -> KnowledgeNavigationResult:
        payload = await self._create_structured_response(
            name="llm_wiki_knowledge_navigation",
            schema=KNOWLEDGE_NAVIGATION_JSON_SCHEMA,
            instructions=_knowledge_navigation_instructions(
                max_artifacts,
                self.preferred_language,
            ),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "question": question,
                                    "plan": plan.model_dump(),
                                    "max_artifacts": max_artifacts,
                                    "knowledge_map_entries": [
                                        _map_entry_payload(entry)
                                        for entry in map_entries
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        )
        return KnowledgeNavigationResult.model_validate(payload)

    async def rank_artifacts(
        self,
        question: str,
        plan: QueryPlan,
        candidates: list[ArtifactCandidate],
        max_artifacts: int,
        max_evidence: int,
    ) -> ArtifactRankingResult:
        payload = await self._create_structured_response(
            name="llm_wiki_artifact_ranking",
            schema=ARTIFACT_RANKING_JSON_SCHEMA,
            instructions=_artifact_ranking_instructions(
                max_artifacts,
                max_evidence,
                self.preferred_language,
            ),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "question": question,
                                    "plan": plan.model_dump(),
                                    "max_artifacts": max_artifacts,
                                    "max_evidence": max_evidence,
                                    "candidates": [
                                        _artifact_candidate_payload(candidate)
                                        for candidate in candidates
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        )
        return ArtifactRankingResult.model_validate(payload)

    async def rank_evidence(
        self,
        question: str,
        plan: QueryPlan,
        candidates: list[EvidenceCandidate],
        max_evidence: int,
    ) -> EvidenceRankingResult:
        payload = await self._create_structured_response(
            name="llm_wiki_evidence_ranking",
            schema=EVIDENCE_RANKING_JSON_SCHEMA,
            instructions=_evidence_ranking_instructions(
                max_evidence,
                self.preferred_language,
            ),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "question": question,
                                    "plan": plan.model_dump(),
                                    "max_evidence": max_evidence,
                                    "candidates": [
                                        _candidate_payload(candidate)
                                        for candidate in candidates
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        )
        return EvidenceRankingResult.model_validate(payload)

    async def synthesize_answer(
        self,
        question: str,
        plan: QueryPlan,
        evidence: list[EvidenceCandidate],
        ranking: EvidenceRankingResult,
    ) -> QuerySynthesisResult:
        payload = await self._create_structured_response(
            name="llm_wiki_query_synthesis",
            schema=QUERY_SYNTHESIS_JSON_SCHEMA,
            instructions=_query_synthesis_instructions(self.preferred_language),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "question": question,
                                    "plan": plan.model_dump(),
                                    "ranking": ranking.model_dump(),
                                    "selected_evidence": [
                                        _candidate_payload(candidate)
                                        for candidate in evidence
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        )
        return QuerySynthesisResult.model_validate(payload)

    async def extract_graph_relations(
        self,
        claims: list[ClaimGraphContext],
    ) -> GraphExtractionResult:
        payload = await self._create_structured_response(
            name="llm_wiki_graph_extraction",
            schema=GRAPH_EXTRACTION_JSON_SCHEMA,
            instructions=_graph_extraction_instructions(self.preferred_language),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "claims": [
                                        _claim_context_payload(claim)
                                        for claim in claims
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        )
        return GraphExtractionResult.model_validate(payload)

    async def detect_contradictions(
        self,
        claims: list[ClaimGraphContext],
    ) -> ContradictionDetectionResult:
        payload = await self._create_structured_response(
            name="llm_wiki_contradiction_detection",
            schema=CONTRADICTION_DETECTION_JSON_SCHEMA,
            instructions=_contradiction_detection_instructions(
                self.preferred_language
            ),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "claims": [
                                        _claim_context_payload(claim)
                                        for claim in claims
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        )
        return ContradictionDetectionResult.model_validate(payload)

    async def _create_structured_response(
        self,
        name: str,
        schema: dict[str, object],
        instructions: str,
        inputs: list[dict[str, object]],
    ) -> dict[str, object]:
        response = await asyncio.to_thread(
            self.client.responses.create,
            model=self.model,
            instructions=instructions,
            input=inputs,
            text={
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "schema": schema,
                    "strict": True,
                }
            },
            max_output_tokens=self.max_output_tokens,
        )
        return json.loads(response.output_text)


def _base64_file_data(path: Path, mime_type: str | None) -> str:
    guessed_mime = mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{guessed_mime};base64,{encoded}"


def _file_input(source: SourceRef, prompt: str) -> dict[str, object]:
    return {
        "role": "user",
        "content": [
            {
                "type": "input_file",
                "filename": source.path.name,
                "file_data": _base64_file_data(source.path, source.mime_type),
            },
            {"type": "input_text", "text": prompt},
        ],
    }


def _source_profile_instructions(preferred_language: str) -> str:
    return (
        "Bạn là Source Profiler của một knowledge compiler tổng quát. Đọc trực tiếp toàn bộ "
        "tệp và mô tả cấu trúc thực sự quan sát được, không áp taxonomy domain, keyword route, "
        "fixed chunk hay template tài liệu có sẵn. Tạo content_units làm đơn vị điều hướng "
        "semantic, mỗi unit có local_id duy nhất dạng ổn định như `unit_1`, `unit_2` "
        "hoặc `unit_topic`; không dùng số trần như `1`. Locator phải kiểm tra được. "
        "Đề xuất knowledge "
        "lenses và một dynamic compilation plan đủ bao phủ các unit quan trọng. Content unit "
        "phải đủ hẹp để kiểm tra coverage độc lập; không gộp các nội dung có chức năng tri "
        "thức khác nhau chỉ vì chúng nằm gần nhau trong file. Mỗi pass phải "
        "có mục tiêu khác biệt và target_unit_ids chỉ được tham chiếu unit đã khai báo. "
        "Hợp của target_unit_ids từ toàn bộ compilation_plan bắt buộc bao phủ mọi content "
        "unit; không được để unit chỉ xuất hiện trong manifest mà không có pass xử lý. "
        "Không trích xuất artifacts ở bước profiling. Bắt buộc giữ ngôn ngữ nguồn cho language, "
        "labels, summaries, objectives và expected_outputs; nếu không xác định được thì dùng "
        f"`{preferred_language}`. Chỉ trả JSON đúng schema."
    )


def _source_profile_prompt(source: SourceRef) -> str:
    return (
        f"Profile source `{source.id}` có tiêu đề `{source.title}`, loại "
        f"`{source.source_type}` và SHA-256 `{source.sha256}`. Lập manifest và kế hoạch "
        "biên dịch động để các đơn vị tri thức quan trọng và quan hệ giữa chúng không bị bỏ sót."
    )


def _compilation_pass_instructions(preferred_language: str) -> str:
    return (
        "Bạn là Knowledge Compiler V3 quality tổng quát. Thực hiện đúng pass_plan trên raw source, "
        "manifest và compiled knowledge hiện có. Không dùng fixed chunks hoặc taxonomy domain. "
        "Evidence phải bám sát nguồn, có local_id source-scoped duy nhất và locator kiểm tra "
        "được. Artifact type và relation type là open strings do nội dung quyết định. "
        "Mỗi evidence phải chỉ rõ source_unit_ids mà nó trực tiếp hỗ trợ. Mỗi source-backed "
        "artifact phải có evidence_local_ids và source_unit_ids. Mỗi artifact phải có atomic "
        "statements đủ nhỏ để kiểm chứng từng factual detail và quan hệ ngữ nghĩa mà source hỗ "
        "trợ; không được giấu nhiều factual claims chỉ trong prose content. Mỗi statement có "
        "local_id duy nhất trong artifact, statement_type mở, subject/predicate/object, "
        "object_type, qualifiers, evidence_local_ids và source_unit_ids. Mọi chi tiết có thể "
        "kiểm chứng được nhắc trong artifact.content phải xuất hiện trong atomic statement và "
        "trong evidence được statement trích dẫn. "
        "Tạo semantic_nodes riêng cho thực thể, khái niệm hoặc đơn vị tri thức thực sự xuất hiện "
        "trong nguồn; tuyệt đối không biến tiêu đề artifact thành semantic node chỉ vì artifact "
        "tồn tại. Các subject/object lặp lại trong nhiều statement thường là semantic node hoặc "
        "alias cần khai báo, trừ khi có lý do rõ ràng để đưa vào review_items. "
        "Với mỗi target unit, phải biên dịch nội dung có chức năng tri thức riêng theo đúng ngữ "
        "cảnh source; không được thay cả unit bằng một câu tóm tắt chung chung. Toàn bộ nội dung "
        "tự nhiên, gồm title, summary, content, statement, "
        "relation và review item, phải cùng ngôn ngữ với manifest.language; chỉ giữ nguyên tên "
        "riêng và thuật ngữ kỹ thuật cần thiết. "
        "review_status của artifact luôn phải là `unreviewed`; model không có quyền xác nhận "
        "human review. Không dùng locator text làm ID. Không lặp artifact/evidence đã có; nếu "
        "pass bổ sung "
        "một artifact hiện có, dùng lại local_id đó với bản đầy đủ hơn. Relations chỉ được "
        "tham chiếu artifact local IDs tồn tại trong output hiện tại hoặc compiled knowledge "
        "đã cung cấp và phải có evidence. Giữ ngôn ngữ nguồn; nếu không xác định được thì dùng "
        f"`{preferred_language}`. Không bịa, đưa bất định vào review_items. Chỉ trả JSON."
    )


def _coverage_audit_instructions(preferred_language: str) -> str:
    return (
        "Bạn là Coverage Auditor độc lập cho knowledge compiler. So sánh trực tiếp raw source "
        "và source manifest với evidence, artifacts, statements và relations đã biên dịch. "
        "Đánh giá coverage theo các knowledge units quan trọng, không theo số lượng artifact. "
        "Bắt buộc tạo đúng một unit_assessment cho từng content unit trong manifest. Với từng "
        "unit, đối chiếu trực tiếp raw source, liệt kê tri thức đã được biểu diễn và tri thức "
        "còn thiếu; không suy ra complete chỉ từ covered_unit_ids do compiler tự khai báo. "
        "Một unit chỉ complete khi có evidence, artifact và atomic statements trực tiếp mang "
        "source_unit_id tương ứng. represented_knowledge phải nêu nội dung thực sự nhìn thấy "
        "trong compiled knowledge, không được chép lại summary của manifest rồi coi là covered. "
        "Kiểm tra provenance thiếu/sai, nội dung bị khái quát quá mức, source unit bị bỏ sót "
        "và compilation loss theo chính ngữ cảnh của tài liệu. Nếu chi tiết có thể kiểm chứng "
        "chỉ có trong prose artifact.content nhưng không có statement/evidence riêng, unit đó "
        "chưa complete. "
        "Chỉ trả complete "
        "khi mọi unit có status complete, missing_knowledge rỗng, không còn gap quan trọng và "
        "không còn provenance issue. "
        "Nếu incomplete hoặc needs_review, đề xuất các follow-up pass cụ thể với pass_id mới "
        "và target_unit_ids hợp lệ. Không đề xuất lại nội dung đã đủ. Viết theo ngôn ngữ nguồn, "
        f"mặc định `{preferred_language}`. Chỉ trả JSON đúng schema."
    )


def _wiki_integration_instructions(preferred_language: str) -> str:
    return (
        "Bạn là Wiki Integrator cho một LLM Wiki tổng quát. Lập kế hoạch các trang Markdown "
        "dễ đọc từ compiled artifacts đã được kiểm chứng. Không tạo một trang cho mọi atomic "
        "statement. Hãy nhóm các artifact có cùng semantic identity hoặc cùng chủ đề tự nhiên, "
        "nhưng không trộn các scope khác nhau gây mất nghĩa. Mọi artifact bắt buộc xuất hiện "
        "trong ít nhất một page. page_type là open string theo nội dung, local_id ổn định và "
        "related_page_local_ids chỉ tham chiếu page trong chính plan. review_status luôn là "
        "`unreviewed`. Không bịa tri thức mới; page chỉ là view của artifacts. Giữ ngôn ngữ "
        f"nguồn, mặc định `{preferred_language}`. Chỉ trả JSON đúng schema."
    )


def _compact_compilation(bundle: CompilationBundle) -> dict[str, object]:
    return {
        "evidence": [
            {
                "local_id": item.local_id,
                "source_unit_ids": item.source_unit_ids,
                "locator": item.locator.model_dump(),
                "summary": compact_text(item.summary, 280),
                "content": compact_text(item.content, 700),
            }
            for item in bundle.evidence_items
        ],
        "artifacts": [
            {
                "local_id": item.local_id,
                "artifact_type": item.artifact_type,
                "title": item.title,
                "summary": compact_text(item.summary, 400),
                "content": compact_text(item.content, 1000),
                "evidence_local_ids": item.evidence_local_ids,
                "source_unit_ids": item.source_unit_ids,
                "statements": [statement.model_dump() for statement in item.statements],
            }
            for item in bundle.artifacts
        ],
        "semantic_nodes": [item.model_dump() for item in bundle.semantic_nodes],
        "relations": [item.model_dump() for item in bundle.relations],
        "covered_unit_ids": bundle.covered_unit_ids,
        "review_items": [item.model_dump() for item in bundle.review_items],
    }


def _audit_compilation_payload(bundle: CompilationBundle) -> dict[str, object]:
    return {
        "evidence": [item.model_dump() for item in bundle.evidence_items],
        "artifacts": [item.model_dump() for item in bundle.artifacts],
        "semantic_nodes": [item.model_dump() for item in bundle.semantic_nodes],
        "relations": [item.model_dump() for item in bundle.relations],
        "covered_unit_ids": bundle.covered_unit_ids,
        "review_items": [item.model_dump() for item in bundle.review_items],
        "notes": bundle.notes,
    }


def _ingest_instructions(preferred_language: str) -> str:
    return (
        "Bạn là bộ máy ingest cho một LLM Wiki tổng quát. "
        "Đọc trực tiếp tệp được cung cấp, bao gồm chữ, hình ảnh, bố cục trang, bảng và "
        "biểu đồ khi có. Trích xuất tri thức bám sát nguồn để lưu vào wiki lâu dài. "
        "TUYỆT ĐỐI giữ nguyên ngôn ngữ chính của tài liệu cho tiêu đề, tóm tắt, bằng chứng, "
        "mệnh đề, mô tả thực thể, mục cần rà soát và câu hỏi mở; không tự dịch sang tiếng Anh. "
        f"Nếu tài liệu không xác định rõ ngôn ngữ, ưu tiên `{preferred_language}`. "
        "Ưu tiên các mệnh đề nguyên tử, hữu ích và có vị trí bằng chứng hơn tóm tắt chung chung. "
        "Không bịa dữ kiện. Nội dung mơ hồ phải được đưa vào review_items. "
        "Có thể dùng mã entity_type ổn định như person, organization, place, product, method, "
        "concept, event, dataset, metric, file, law, system hoặc other, nhưng description và "
        "name phải theo ngôn ngữ nguồn. Locator phải ổn định và kiểm tra được, ví dụ "
        "trang 3, mục 'Kiến trúc', sheet 'Doanh thu'!A1:D20, hình 2 hoặc slide 5. "
        "Với PDF scan/ảnh, mô tả bằng chứng thị giác và chép lại nội dung đọc được "
        "tốt nhất có thể. "
        "Chỉ trả về JSON đúng schema yêu cầu."
    )


def _source_prompt(source: SourceRef, preferred_language: str) -> str:
    return (
        f"Metadata nguồn:\n"
        f"- source_id: {source.id}\n"
        f"- tiêu đề: {source.title}\n"
        f"- loại nguồn: {source.source_type}\n"
        f"- sha256: {source.sha256}\n"
        f"- đường dẫn: {source.path}\n"
        f"- ngôn ngữ ưu tiên khi không xác định được: {preferred_language}\n\n"
        "Hãy tạo biểu diễn tri thức wiki tốt nhất từ nguồn này. Bao gồm bằng chứng, mệnh đề, "
        "thực thể, mục cần rà soát và câu hỏi mở quan trọng nhất. Giữ bằng chứng ngắn gọn "
        "nhưng đủ để trích dẫn về sau. Nếu tài liệu dài, ưu tiên định nghĩa, quan hệ, bảng, "
        "hình, dữ kiện bền vững, điểm mâu thuẫn và nội dung hữu ích cho truy vấn tương lai. "
        "Không dịch nội dung sang ngôn ngữ khác."
    )


def _query_plan_instructions(preferred_language: str) -> str:
    return (
        "Bạn là bộ lập kế hoạch truy vấn cho LLM Wiki tổng quát. "
        "Chuyển câu hỏi thành kế hoạch semantic retrieval độc lập domain trên compiled "
        "artifacts, artifact statements, compiled evidence, wiki map và graph. "
        "semantic_probes là các diễn đạt ý nghĩa mà hệ thống sẽ embed/search; "
        "desired_artifact_hints là mô tả mềm về loại artifact cần tìm, không phải enum "
        "đóng hoặc route keyword. Giữ từ khóa, gợi ý thực thể và câu hỏi con bằng ngôn ngữ "
        "của người hỏi để tăng recall chính xác; chỉ thêm biến thể ngôn ngữ khác khi thực "
        "sự giúp tìm tên riêng hoặc thuật ngữ trong nguồn. graph_policy đặt giới hạn traversal "
        "nhỏ, relation_hints là gợi ý mềm theo câu hỏi. "
        f"Nếu không xác định được ngôn ngữ câu hỏi, dùng `{preferred_language}`. "
        "Trường answer_language phải đúng ngôn ngữ câu hỏi. Không trả lời câu hỏi ở bước này. "
        "Chỉ trả về JSON đúng schema."
    )


def _knowledge_navigation_instructions(max_artifacts: int, preferred_language: str) -> str:
    return (
        "Bạn là navigator của LLM Wiki. Đọc knowledge_map_entries như một catalog phân cấp "
        "wiki page -> compiled artifact, rồi chọn các artifact_id có khả năng liên quan về "
        f"ngữ nghĩa đến câu hỏi, tối đa {max_artifacts}. Không dùng taxonomy cố định, không "
        "suy diễn ngoài map, không bịa artifact_id hoặc entry_id. Nếu map thiếu vùng tri thức "
        "cần thiết, ghi vào missing_map_areas thay vì chọn bừa. Lý do viết theo ngôn ngữ câu "
        f"hỏi, mặc định `{preferred_language}`. Chỉ trả JSON đúng schema."
    )


def _artifact_ranking_instructions(
    max_artifacts: int,
    max_evidence: int,
    preferred_language: str,
) -> str:
    return (
        "Bạn là artifact reranker cho LLM Wiki artifact-first. Đánh giá candidate artifacts "
        "theo câu hỏi, query plan, retrieval signals, statements và evidence summaries. "
        f"Chọn tối đa {max_artifacts} artifact_id và tối đa {max_evidence} evidence_id thực "
        "sự hỗ trợ câu trả lời. Phân biệt direct, supporting, qualifying, conflicting, "
        "background và irrelevant. Nếu artifact chỉ liên quan chung hoặc không có evidence "
        "cụ thể, không chọn evidence_id đó. Nếu không có artifact/evidence đủ trực tiếp, "
        "selected_artifact_ids và selected_evidence_ids phải rỗng; không chọn top candidate "
        "chỉ để luôn có kết quả. Không bịa artifact_id hoặc evidence_id. Nêu missing_knowledge "
        "khi compiled artifacts không đủ trả lời. "
        f"Viết reason theo ngôn ngữ câu hỏi, mặc định `{preferred_language}`. Chỉ trả JSON."
    )


def _evidence_ranking_instructions(max_evidence: int, preferred_language: str) -> str:
    return (
        "Bạn là bộ đánh giá bằng chứng của LLM Wiki bám sát nguồn. "
        f"Chọn tối đa {max_evidence} evidence_id trực tiếp hoặc hỗ trợ mạnh cho câu hỏi. "
        "Loại bằng chứng yếu, trùng hoặc lạc đề. Nêu rõ mâu thuẫn và phần bằng chứng còn thiếu. "
        "Nếu không có evidence trực tiếp hoặc hỗ trợ đủ mạnh, selected_evidence_ids phải rỗng; "
        "không chọn candidate chỉ để luôn có kết quả. "
        f"Viết reason/summary theo ngôn ngữ câu hỏi, mặc định `{preferred_language}`. "
        "Không bịa evidence_id. Chỉ trả về JSON đúng schema."
    )


def _query_synthesis_instructions(preferred_language: str) -> str:
    return (
        "Bạn là bộ tổng hợp câu trả lời cho chatbot LLM Wiki bám sát nguồn. "
        "Chỉ trả lời từ các bằng chứng đã được chọn. Mọi khẳng định quan trọng phải có citation "
        "dùng evidence_id được cung cấp. Nếu không đủ bằng chứng, phải nói rõ và đặt confidence "
        "là insufficient hoặc low. BẮT BUỘC trả lời cùng ngôn ngữ với câu hỏi của người dùng; "
        f"nếu không xác định được thì dùng `{preferred_language}`. Không tự chuyển câu hỏi "
        "tiếng Việt sang câu trả lời tiếng Anh. Tách riêng mâu thuẫn và câu hỏi mở, không che "
        "giấu bất định. Không tạo citation cho bằng chứng không trực tiếp hỗ trợ câu trả lời; "
        "nếu không có citation hợp lệ thì trả citations rỗng. Chỉ trả về JSON đúng schema."
    )


def _graph_extraction_instructions(preferred_language: str) -> str:
    return (
        "Bạn là bộ trích xuất knowledge graph cho LLM Wiki bám sát nguồn. "
        "Chuyển các claim context thành bộ ba quan hệ ngắn gọn và chỉ dùng claim_id/evidence_id "
        "được cung cấp. Giữ nguyên tên thực thể và ngôn ngữ của mệnh đề nguồn. Predicate phải "
        "là cụm động từ ngắn, nhất quán và có ý nghĩa trong ngôn ngữ nguồn; không ép predicate "
        f"tiếng Việt sang tiếng Anh. Khi nguồn không rõ ngôn ngữ, dùng `{preferred_language}`. "
        "Cho phép object literal với số, ngày, metric và văn bản. Không tạo quan hệ không được "
        "bằng chứng hỗ trợ. Chỉ đề xuất merge candidate khi alias/gần trùng thực sự hợp lý và "
        "không tự merge. Chỉ trả về JSON đúng schema."
    )


def _contradiction_detection_instructions(preferred_language: str) -> str:
    return (
        "Bạn là bộ phát hiện mâu thuẫn cho LLM Wiki bám sát nguồn. So sánh các claims và chỉ "
        "trả về quan hệ ngữ nghĩa có ý nghĩa giữa từng cặp: contradicts, qualifies, duplicates, "
        "supports hoặc unrelated. Các mã relationship giữ tiếng Anh để ổn định schema, nhưng "
        f"reason và notes phải theo ngôn ngữ claims, mặc định `{preferred_language}`. "
        "Ưu tiên precision cao hơn recall. Không bịa claim_id/evidence_id. "
        "Chỉ trả về JSON đúng schema."
    )


def _candidate_payload(candidate: EvidenceCandidate) -> dict[str, object]:
    return {
        "evidence_id": candidate.evidence_id,
        "source_id": candidate.source_id,
        "source_title": candidate.source_title,
        "source_path": candidate.source_path,
        "wiki_page_path": candidate.wiki_page_path,
        "locator": candidate.locator,
        "modality": candidate.modality,
        "text": compact_text(candidate.text, 900),
        "summary": compact_text(candidate.summary, 400),
        "confidence": candidate.confidence,
        "claim_ids": candidate.claim_ids,
        "claims": [compact_text(claim, 400) for claim in candidate.claims],
        "entities": candidate.entities[:20],
        "retrieval_score": candidate.retrieval_score,
        "retrieval_channels": candidate.retrieval_channels,
    }


def _map_entry_payload(entry: KnowledgeMapEntryCandidate) -> dict[str, object]:
    return {
        "entry_id": entry.entry_id,
        "parent_entry_id": entry.parent_entry_id,
        "page_id": entry.page_id,
        "artifact_id": entry.artifact_id,
        "entry_type": entry.entry_type,
        "title": compact_text(entry.title, 240),
        "summary": compact_text(entry.summary, 500),
        "source_ids": entry.source_ids,
    }


def _artifact_candidate_payload(candidate: ArtifactCandidate) -> dict[str, object]:
    return {
        "artifact_id": candidate.artifact_id,
        "source_id": candidate.source_id,
        "source_title": candidate.source_title,
        "wiki_page_path": candidate.wiki_page_path,
        "artifact_type": candidate.artifact_type,
        "title": compact_text(candidate.title, 240),
        "summary": compact_text(candidate.summary, 700),
        "content": compact_text(candidate.content, 1200),
        "aliases": candidate.aliases[:20],
        "scope": candidate.scope[:20],
        "confidence": candidate.confidence,
        "status": candidate.status,
        "review_status": candidate.review_status,
        "retrieval_score": candidate.retrieval_score,
        "retrieval_channels": candidate.retrieval_channels,
        "retrieval_signals": [
            signal.model_dump() for signal in candidate.retrieval_signals[:12]
        ],
        "graph_depth": candidate.graph_depth,
        "statements": [
            {
                "statement_id": statement.statement_id,
                "statement_type": statement.statement_type,
                "text": compact_text(statement.text, 500),
                "subject": compact_text(statement.subject, 160),
                "predicate": compact_text(statement.predicate, 160),
                "object": compact_text(statement.object, 240),
                "confidence": statement.confidence,
                "status": statement.status,
                "evidence_ids": statement.evidence_ids,
            }
            for statement in candidate.statements[:20]
        ],
        "evidence": [
            {
                "evidence_id": evidence.evidence_id,
                "locator": evidence.locator,
                "text": compact_text(evidence.text, 700),
                "summary": compact_text(evidence.summary, 400),
                "confidence": evidence.confidence,
                "claim_ids": evidence.claim_ids,
                "claims": [compact_text(claim, 300) for claim in evidence.claims[:6]],
            }
            for evidence in candidate.evidence[:12]
        ],
    }


def _claim_context_payload(claim: ClaimGraphContext) -> dict[str, object]:
    return {
        "claim_id": claim.claim_id,
        "source_id": claim.source_id,
        "source_title": claim.source_title,
        "text": compact_text(claim.text, 700),
        "subject": claim.subject,
        "predicate": claim.predicate,
        "object": claim.object,
        "status": claim.status,
        "confidence": claim.confidence,
        "entities": claim.entities[:30],
        "evidence": [
            {
                "evidence_id": evidence.evidence_id,
                "locator": evidence.locator,
                "text": compact_text(evidence.text, 700),
                "summary": compact_text(evidence.summary, 300),
            }
            for evidence in claim.evidence[:5]
        ],
    }
