import sqlite3

import pytest

from backend.app.core.source_integrity import verify_source
from backend.tests.helpers import build_test_context, register_text_source


def test_register_source_is_content_addressed(tmp_path) -> None:
    database, wiki_dir, _, _ = build_test_context(tmp_path)
    source = register_text_source(tmp_path, database, wiki_dir)

    assert source.id.startswith("src_")
    assert source.status == "registered"
    with sqlite3.connect(database.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM operations WHERE operation_type = 'register'"
            ).fetchone()[0]
            == 1
        )


def test_registered_source_mutation_is_detected(tmp_path) -> None:
    database, wiki_dir, _, _ = build_test_context(tmp_path)
    source = register_text_source(tmp_path, database, wiki_dir)
    source.path.write_text("Changed after registration.", encoding="utf-8")

    with pytest.raises(ValueError, match="changed after registration"):
        verify_source(source)
