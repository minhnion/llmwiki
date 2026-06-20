from backend.app.domain.agent import (
    AgentAnswer,
    QueryPlan,
    SourceAnalysis,
    WikiChangeSet,
)


def test_llm_output_schemas_require_every_object_property() -> None:
    for model in (SourceAnalysis, WikiChangeSet, QueryPlan, AgentAnswer):
        _assert_strict_objects(model.model_json_schema())


def _assert_strict_objects(node) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object":
            properties = node.get("properties", {})
            assert node.get("additionalProperties") is False
            assert set(node.get("required", [])) == set(properties)
        for value in node.values():
            _assert_strict_objects(value)
    elif isinstance(node, list):
        for value in node:
            _assert_strict_objects(value)
