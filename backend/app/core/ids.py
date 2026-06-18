from uuid import uuid4

from backend.app.core.text import stable_hash


def source_id_from_hash(sha256: str) -> str:
    return f"src_{sha256[:16]}"


def source_version_id(source_id: str, sha256: str) -> str:
    return f"srcv_{source_id.removeprefix('src_')}_{sha256[:12]}"


def ingest_job_id() -> str:
    return f"job_{uuid4().hex[:16]}"


def compiler_run_id() -> str:
    return f"crun_{uuid4().hex[:16]}"


def compiler_pass_run_id() -> str:
    return f"cpass_{uuid4().hex[:16]}"


def evidence_id_from_local(source_id: str, local_id: str) -> str:
    return f"ev_{stable_hash(source_id, local_id, length=20)}"


def evidence_id(source_id: str, locator: str, text: str | None, index: int) -> str:
    return f"ev_{stable_hash(source_id, locator, text or '', str(index), length=20)}"


def claim_id(source_id: str, text: str, index: int) -> str:
    return f"cl_{stable_hash(source_id, text, str(index), length=20)}"


def claim_id_from_local(source_id: str, local_id: str) -> str:
    return f"cl_{stable_hash(source_id, local_id, length=20)}"


def entity_id(name: str, entity_type: str) -> str:
    return f"ent_{stable_hash(name.lower().strip(), entity_type.lower().strip(), length=20)}"


def review_item_id(source_id: str, title: str, body: str, index: int) -> str:
    return f"rev_{stable_hash(source_id, title, body, str(index), length=20)}"


def wiki_page_id(source_id: str) -> str:
    return f"page_{stable_hash(source_id, 'source', length=20)}"


def knowledge_page_id(source_id: str, local_id: str) -> str:
    return f"page_{stable_hash(source_id, local_id, 'knowledge', length=20)}"


def statement_id(source_id: str, artifact_local_id: str, statement_local_id: str) -> str:
    return f"stmt_{stable_hash(source_id, artifact_local_id, statement_local_id, length=20)}"


def query_run_id() -> str:
    return f"qry_{uuid4().hex[:16]}"


def graph_run_id() -> str:
    return f"grun_{uuid4().hex[:16]}"


def relation_edge_id(
    claim_id: str,
    evidence_id: str,
    subject_name: str,
    predicate: str,
    object_value: str,
) -> str:
    return "rel_" + stable_hash(
        claim_id,
        evidence_id,
        subject_name,
        predicate,
        object_value,
        length=20,
    )


def contradiction_id(claim_a_id: str, claim_b_id: str, relationship: str) -> str:
    first, second = sorted((claim_a_id, claim_b_id))
    return f"ctr_{stable_hash(first, second, relationship, length=20)}"


def entity_merge_candidate_id(entity_a_id: str, entity_b_id: str) -> str:
    first, second = sorted((entity_a_id, entity_b_id))
    return f"merge_{stable_hash(first, second, length=20)}"


def entity_page_id(entity_id_value: str) -> str:
    return f"page_{stable_hash(entity_id_value, 'entity', length=20)}"


def artifact_id(source_id: str, local_id: str) -> str:
    return f"art_{stable_hash(source_id, local_id, length=20)}"


def artifact_version_id(artifact_id_value: str, content_hash: str) -> str:
    return f"artv_{stable_hash(artifact_id_value, content_hash, length=20)}"


def artifact_relation_id(
    source_artifact_id: str,
    target_value: str,
    relation_type: str,
) -> str:
    return f"aredge_{stable_hash(source_artifact_id, target_value, relation_type, length=20)}"


def coverage_report_id(compiler_run_id_value: str, iteration: int) -> str:
    return f"cov_{stable_hash(compiler_run_id_value, str(iteration), length=20)}"
