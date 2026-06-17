from uuid import uuid4

from backend.app.core.text import stable_hash


def source_id_from_hash(sha256: str) -> str:
    return f"src_{sha256[:16]}"


def source_version_id(source_id: str, sha256: str) -> str:
    return f"srcv_{source_id.removeprefix('src_')}_{sha256[:12]}"


def ingest_job_id() -> str:
    return f"job_{uuid4().hex[:16]}"


def evidence_id(source_id: str, locator: str, text: str | None, index: int) -> str:
    return f"ev_{stable_hash(source_id, locator, text or '', str(index), length=20)}"


def claim_id(source_id: str, text: str, index: int) -> str:
    return f"cl_{stable_hash(source_id, text, str(index), length=20)}"


def entity_id(name: str, entity_type: str) -> str:
    return f"ent_{stable_hash(name.lower().strip(), entity_type.lower().strip(), length=20)}"


def review_item_id(source_id: str, title: str, body: str, index: int) -> str:
    return f"rev_{stable_hash(source_id, title, body, str(index), length=20)}"


def wiki_page_id(source_id: str) -> str:
    return f"page_{stable_hash(source_id, 'source', length=20)}"
