from uuid import uuid4

from backend.app.core.text import stable_hash


def source_id_from_hash(sha256: str) -> str:
    return f"src_{sha256[:16]}"


def source_version_id(source_id: str, sha256: str) -> str:
    return f"srcv_{stable_hash(source_id, sha256, length=20)}"


def page_id() -> str:
    return f"page_{uuid4().hex[:20]}"


def evidence_ref_id(page_id_value: str, source_id: str, locator: str) -> str:
    return f"evref_{stable_hash(page_id_value, source_id, locator, length=20)}"


def operation_id() -> str:
    return f"op_{uuid4().hex[:20]}"


def review_id() -> str:
    return f"review_{uuid4().hex[:20]}"


def query_id() -> str:
    return f"qry_{uuid4().hex[:20]}"


def llm_call_id() -> str:
    return f"call_{uuid4().hex[:20]}"
