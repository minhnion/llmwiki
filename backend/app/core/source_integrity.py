from backend.app.core.hashing import sha256_file
from backend.app.domain.models import SourceRef


def verify_source(source: SourceRef) -> None:
    if not source.path.is_file():
        raise ValueError(f"Raw source is missing: {source.path}")
    current_hash = sha256_file(source.path)
    if current_hash != source.sha256:
        raise ValueError(
            f"Raw source changed after registration: {source.id}. "
            "Register the changed file as a new source."
        )
