from backend.app.services.llm_client import (
    _graph_extraction_instructions,
    _ingest_instructions,
    _query_plan_instructions,
    _query_synthesis_instructions,
)


def test_ingest_prompt_preserves_document_language() -> None:
    instructions = _ingest_instructions("vi")

    assert "giữ nguyên ngôn ngữ chính của tài liệu" in instructions
    assert "không tự dịch sang tiếng Anh" in instructions
    assert "ưu tiên `vi`" in instructions


def test_query_prompts_preserve_question_language() -> None:
    planning = _query_plan_instructions("vi")
    synthesis = _query_synthesis_instructions("vi")

    assert "ngôn ngữ của người hỏi" in planning
    assert "answer_language phải đúng ngôn ngữ câu hỏi" in planning
    assert "trả lời cùng ngôn ngữ với câu hỏi" in synthesis
    assert "tiếng Việt sang câu trả lời tiếng Anh" in synthesis


def test_graph_prompt_preserves_source_language() -> None:
    instructions = _graph_extraction_instructions("vi")

    assert "Giữ nguyên tên thực thể và ngôn ngữ của mệnh đề nguồn" in instructions
    assert "không ép predicate tiếng Việt sang tiếng Anh" in instructions
