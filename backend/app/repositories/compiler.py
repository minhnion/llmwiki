import json

from backend.app.core.ids import (
    artifact_id,
    artifact_relation_id,
    artifact_version_id,
    coverage_report_id,
    evidence_id_from_local,
    statement_id,
)
from backend.app.core.text import stable_hash
from backend.app.domain.compiler import (
    CompilationBundle,
    CompilationInspection,
    CompilationPassPlan,
    CompilationPassResult,
    CompiledArtifact,
    CompiledRelation,
    CompiledSemanticNode,
    CompilerPassStatus,
    CoverageReport,
    SourceManifest,
)
from backend.app.domain.models import SourceRef
from backend.app.repositories.base import SQLiteRepository


class SQLiteCompilerRepository(SQLiteRepository):
    def get_latest_inspection(self, source_id: str) -> CompilationInspection | None:
        with self.database.connect() as connection:
            run = connection.execute(
                """
                SELECT *
                FROM compiler_runs
                WHERE source_id = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (source_id,),
            ).fetchone()
            if run is None:
                return None
            manifest_row = connection.execute(
                "SELECT manifest_json FROM source_manifests WHERE compiler_run_id = ?",
                (run["id"],),
            ).fetchone()
            if manifest_row is None:
                return None
            pass_rows = connection.execute(
                """
                SELECT pass_id, iteration, objective, status, error, started_at, finished_at
                FROM compiler_passes
                WHERE compiler_run_id = ?
                ORDER BY started_at, id
                """,
                (run["id"],),
            ).fetchall()
            coverage_rows = connection.execute(
                """
                SELECT report_json
                FROM coverage_reports
                WHERE compiler_run_id = ?
                ORDER BY iteration
                """,
                (run["id"],),
            ).fetchall()
            artifact_rows = connection.execute(
                """
                SELECT av.artifact_json
                FROM artifact_versions av
                JOIN artifacts a ON a.id = av.artifact_id
                WHERE av.compiler_run_id = ? AND a.source_id = ?
                ORDER BY a.title, a.id
                """,
                (run["id"], source_id),
            ).fetchall()
            semantic_node_rows = connection.execute(
                """
                SELECT node_json
                FROM compiled_semantic_nodes
                WHERE compiler_run_id = ? AND source_id = ?
                ORDER BY local_id
                """,
                (run["id"], source_id),
            ).fetchall()

        return CompilationInspection(
            compiler_run_id=run["id"],
            source_id=run["source_id"],
            status=run["status"],
            current_stage=run["current_stage"],
            compiler_version=run["compiler_version"],
            prompt_version=run["prompt_version"],
            schema_version=run["schema_version"],
            model=run["model"],
            pass_count=run["pass_count"],
            coverage_status=run["coverage_status"],
            started_at=run["started_at"],
            finished_at=run["finished_at"],
            error=run["error"],
            manifest=SourceManifest.model_validate(json.loads(manifest_row["manifest_json"])),
            passes=[
                CompilerPassStatus(
                    pass_id=row["pass_id"],
                    iteration=row["iteration"],
                    objective=row["objective"],
                    status=row["status"],
                    error=row["error"],
                    started_at=row["started_at"],
                    finished_at=row["finished_at"],
                )
                for row in pass_rows
            ],
            coverage_reports=[
                CoverageReport.model_validate(json.loads(row["report_json"]))
                for row in coverage_rows
            ],
            artifacts=[
                CompiledArtifact.model_validate(json.loads(row["artifact_json"]))
                for row in artifact_rows
            ],
            semantic_nodes=[
                CompiledSemanticNode.model_validate(json.loads(row["node_json"]))
                for row in semantic_node_rows
            ],
        )

    def create_run(
        self,
        run_id: str,
        source: SourceRef,
        compiler_version: str,
        prompt_version: str,
        schema_version: str,
        model: str,
        started_at: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO compiler_runs (
                    id, source_id, status, current_stage, compiler_version,
                    prompt_version, schema_version, model, source_sha256, started_at
                )
                VALUES (?, ?, 'running', 'profiling', ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    source.id,
                    compiler_version,
                    prompt_version,
                    schema_version,
                    model,
                    source.sha256,
                    started_at,
                ),
            )
            connection.execute(
                """
                UPDATE sources
                SET status = 'profiling', compiler_version = ?, updated_at = ?
                WHERE id = ?
                """,
                (compiler_version, started_at, source.id),
            )

    def update_stage(self, run_id: str, source_id: str, stage: str, timestamp: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE compiler_runs SET current_stage = ? WHERE id = ?",
                (stage, run_id),
            )
            connection.execute(
                "UPDATE sources SET status = ?, updated_at = ? WHERE id = ?",
                (stage, timestamp, source_id),
            )

    def save_manifest(
        self,
        run_id: str,
        source_id: str,
        manifest: SourceManifest,
        timestamp: str,
    ) -> None:
        manifest_id = f"manifest_{stable_hash(run_id, length=20)}"
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO source_manifests (
                    id, compiler_run_id, source_id, language, manifest_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest_id,
                    run_id,
                    source_id,
                    manifest.language,
                    _json(manifest.model_dump()),
                    timestamp,
                ),
            )
            for unit in manifest.content_units:
                connection.execute(
                    """
                    INSERT INTO source_units (
                        id, compiler_run_id, source_id, local_id, label,
                        locator_json, summary, importance, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"unit_{stable_hash(run_id, unit.local_id, length=20)}",
                        run_id,
                        source_id,
                        unit.local_id,
                        unit.label,
                        _json(unit.locator.model_dump()),
                        unit.summary,
                        unit.importance,
                        timestamp,
                    ),
                )
            connection.execute(
                "UPDATE sources SET language = ?, updated_at = ? WHERE id = ?",
                (manifest.language, timestamp, source_id),
            )

    def start_pass(
        self,
        pass_run_id: str,
        run_id: str,
        plan: CompilationPassPlan,
        iteration: int,
        started_at: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO compiler_passes (
                    id, compiler_run_id, pass_id, iteration, objective,
                    target_unit_ids_json, expected_outputs_json, status, started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
                """,
                (
                    pass_run_id,
                    run_id,
                    plan.pass_id,
                    iteration,
                    plan.objective,
                    _json(plan.target_unit_ids),
                    _json(plan.expected_outputs),
                    started_at,
                ),
            )

    def finish_pass(
        self,
        pass_run_id: str,
        result: CompilationPassResult,
        finished_at: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE compiler_passes
                SET status = 'completed', result_json = ?, finished_at = ?, error = NULL
                WHERE id = ?
                """,
                (_json(result.model_dump()), finished_at, pass_run_id),
            )
            connection.execute(
                """
                UPDATE compiler_runs
                SET pass_count = pass_count + 1
                WHERE id = (SELECT compiler_run_id FROM compiler_passes WHERE id = ?)
                """,
                (pass_run_id,),
            )

    def fail_pass(self, pass_run_id: str, error: str, finished_at: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE compiler_passes
                SET status = 'failed', error = ?, finished_at = ?
                WHERE id = ?
                """,
                (error, finished_at, pass_run_id),
            )

    def save_coverage(
        self,
        run_id: str,
        source_id: str,
        iteration: int,
        report: CoverageReport,
        created_at: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO coverage_reports (
                    id, compiler_run_id, source_id, iteration,
                    coverage_status, report_json, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    coverage_report_id(run_id, iteration),
                    run_id,
                    source_id,
                    iteration,
                    report.coverage_status,
                    _json(report.model_dump()),
                    report.confidence,
                    created_at,
                ),
            )
            connection.execute(
                "UPDATE compiler_runs SET coverage_status = ? WHERE id = ?",
                (report.coverage_status, run_id),
            )

    def save_artifacts(
        self,
        run_id: str,
        source: SourceRef,
        bundle: CompilationBundle,
        timestamp: str,
    ) -> None:
        artifact_ids = {
            artifact.local_id: artifact_id(source.id, artifact.local_id)
            for artifact in bundle.artifacts
        }
        evidence_ids = {
            evidence.local_id: evidence_id_from_local(source.id, evidence.local_id)
            for evidence in bundle.evidence_items
        }
        with self.database.connect() as connection:
            old_artifact_rows = connection.execute(
                "SELECT id FROM artifacts WHERE source_id = ?",
                (source.id,),
            ).fetchall()
            old_artifact_ids = [row["id"] for row in old_artifact_rows]
            if old_artifact_ids:
                placeholders = ",".join("?" for _ in old_artifact_ids)
                old_statement_rows = connection.execute(
                    f"""
                    SELECT id FROM artifact_statements
                    WHERE artifact_id IN ({placeholders})
                    """,
                    tuple(old_artifact_ids),
                ).fetchall()
                for row in old_statement_rows:
                    connection.execute(
                        "DELETE FROM artifact_statements_fts WHERE id = ?",
                        (row["id"],),
                    )
                old_relation_rows = connection.execute(
                    f"""
                    SELECT id FROM artifact_relations
                    WHERE source_artifact_id IN ({placeholders})
                    """,
                    tuple(old_artifact_ids),
                ).fetchall()
                for row in old_relation_rows:
                    connection.execute(
                        "DELETE FROM artifact_relations_fts WHERE id = ?",
                        (row["id"],),
                    )
            for row in old_artifact_rows:
                connection.execute("DELETE FROM artifacts_fts WHERE id = ?", (row["id"],))
            connection.execute("DELETE FROM artifacts WHERE source_id = ?", (source.id,))
            connection.execute(
                "DELETE FROM compiled_semantic_nodes WHERE source_id = ?",
                (source.id,),
            )

            for artifact in bundle.artifacts:
                current_id = artifact_ids[artifact.local_id]
                artifact_payload = artifact.model_dump()
                content_hash = stable_hash(_json(artifact_payload), length=64)
                connection.execute(
                    """
                    INSERT INTO artifacts (
                        id, source_id, local_id, artifact_type, title, summary,
                        content, aliases_json, scope_json, confidence, status,
                        review_status, metadata_json, compiler_run_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_id,
                        source.id,
                        artifact.local_id,
                        artifact.artifact_type,
                        artifact.title,
                        artifact.summary,
                        artifact.content,
                        _json(artifact.aliases),
                        _json([item.model_dump() for item in artifact.scope]),
                        artifact.confidence,
                        artifact.status,
                        artifact.review_status,
                        _json([item.model_dump() for item in artifact.metadata]),
                        run_id,
                        timestamp,
                        timestamp,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO artifacts_fts (
                        id, source_id, artifact_type, title, aliases, summary, content
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_id,
                        source.id,
                        artifact.artifact_type,
                        artifact.title,
                        " ".join(artifact.aliases),
                        artifact.summary,
                        artifact.content,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO artifact_versions (
                        id, artifact_id, compiler_run_id, content_hash,
                        artifact_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact_version_id(current_id, content_hash),
                        current_id,
                        run_id,
                        content_hash,
                        _json(artifact_payload),
                        timestamp,
                    ),
                )
                for local_evidence_id in artifact.evidence_local_ids:
                    connection.execute(
                        """
                        INSERT INTO artifact_evidence (artifact_id, evidence_id, confidence)
                        VALUES (?, ?, ?)
                        """,
                        (
                            current_id,
                            evidence_ids[local_evidence_id],
                            artifact.confidence,
                        ),
                    )
                for unit_local_id in artifact.source_unit_ids:
                    connection.execute(
                        """
                        INSERT INTO artifact_source_units (
                            artifact_id, compiler_run_id, source_id, unit_local_id
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (current_id, run_id, source.id, unit_local_id),
                    )
                for statement in artifact.statements:
                    current_statement_id = statement_id(
                        source.id,
                        artifact.local_id,
                        statement.local_id,
                    )
                    connection.execute(
                        """
                        INSERT INTO artifact_statements (
                            id, artifact_id, source_id, compiler_run_id, local_id,
                            statement_type, statement_text, subject, predicate,
                            object_value, object_type, source_unit_ids_json,
                            qualifiers_json, confidence, status, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            current_statement_id,
                            current_id,
                            source.id,
                            run_id,
                            statement.local_id,
                            statement.statement_type,
                            statement.text,
                            statement.subject,
                            statement.predicate,
                            statement.object,
                            statement.object_type,
                            _json(statement.source_unit_ids),
                            _json(
                                [item.model_dump() for item in statement.qualifiers]
                            ),
                            statement.confidence,
                            statement.status,
                            timestamp,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO artifact_statements_fts (
                            id, artifact_id, source_id, statement_type,
                            statement_text, subject, predicate, object_value
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            current_statement_id,
                            current_id,
                            source.id,
                            statement.statement_type,
                            statement.text,
                            statement.subject,
                            statement.predicate,
                            statement.object,
                        ),
                    )
                    for local_evidence_id in statement.evidence_local_ids:
                        connection.execute(
                            """
                            INSERT INTO artifact_statement_evidence (
                                statement_id, evidence_id
                            )
                            VALUES (?, ?)
                            """,
                            (
                                current_statement_id,
                                evidence_ids[local_evidence_id],
                            ),
                        )

            for node in bundle.semantic_nodes:
                connection.execute(
                    """
                    INSERT INTO compiled_semantic_nodes (
                        id, source_id, compiler_run_id, local_id, node_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"snode_{stable_hash(source.id, node.local_id, length=20)}",
                        source.id,
                        run_id,
                        node.local_id,
                        _json(node.model_dump()),
                        timestamp,
                    ),
                )

            relations = _statement_relations(bundle)
            relations.extend(bundle.relations)
            relation_keys = {
                (
                    relation.source_artifact_local_id,
                    relation.relation_type,
                    relation.target_artifact_local_id,
                    relation.target_literal,
                )
                for relation in relations
                if relation.target_artifact_local_id
            }
            for artifact in bundle.artifacts:
                for related_local_id in artifact.related_artifact_local_ids:
                    if (artifact.local_id, "related_to", related_local_id, "") in relation_keys:
                        continue
                    relations.append(
                        CompiledRelation(
                            source_artifact_local_id=artifact.local_id,
                            target_artifact_local_id=related_local_id,
                            target_literal="",
                            relation_type="related_to",
                            evidence_local_ids=artifact.evidence_local_ids,
                            qualifiers=[],
                            confidence=artifact.confidence,
                            status=artifact.status,
                        )
                    )
            deduped_relations: dict[tuple[str, str, str, str], CompiledRelation] = {}
            for relation in relations:
                deduped_relations[
                    (
                        relation.source_artifact_local_id,
                        relation.relation_type,
                        relation.target_artifact_local_id,
                        relation.target_literal,
                    )
                ] = relation

            for relation in deduped_relations.values():
                source_artifact_id = artifact_ids[relation.source_artifact_local_id]
                target_artifact_id = artifact_ids.get(relation.target_artifact_local_id)
                target_value = target_artifact_id or relation.target_literal
                current_id = artifact_relation_id(
                    source_artifact_id,
                    target_value,
                    relation.relation_type,
                )
                relation_evidence_ids = [
                    evidence_ids[local_id] for local_id in relation.evidence_local_ids
                ]
                connection.execute(
                    """
                    INSERT INTO artifact_relations (
                        id, source_artifact_id, target_artifact_id, target_literal,
                        relation_type, evidence_ids_json, qualifiers_json, confidence,
                        status, compiler_run_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_id,
                        source_artifact_id,
                        target_artifact_id,
                        relation.target_literal,
                        relation.relation_type,
                        _json(relation_evidence_ids),
                        _json([item.model_dump() for item in relation.qualifiers]),
                        relation.confidence,
                        relation.status,
                        run_id,
                        timestamp,
                        timestamp,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO artifact_relations_fts (
                        id, source_artifact_id, relation_type, target_literal
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        current_id,
                        source_artifact_id,
                        relation.relation_type,
                        relation.target_literal,
                    ),
                )

    def finish_run(
        self,
        run_id: str,
        source_id: str,
        status: str,
        coverage_status: str,
        finished_at: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE compiler_runs
                SET status = ?, current_stage = 'completed', coverage_status = ?,
                    finished_at = ?, error = NULL
                WHERE id = ?
                """,
                (status, coverage_status, finished_at, run_id),
            )
            connection.execute(
                """
                UPDATE sources
                SET status = ?, ingested_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, finished_at, finished_at, source_id),
            )

    def fail_run(self, run_id: str, source_id: str, error: str, finished_at: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE compiler_runs
                SET status = 'failed', current_stage = 'failed',
                    finished_at = ?, error = ?
                WHERE id = ?
                """,
                (finished_at, error, run_id),
            )
            connection.execute(
                "UPDATE sources SET status = 'failed', updated_at = ? WHERE id = ?",
                (finished_at, source_id),
            )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _statement_relations(bundle: CompilationBundle) -> list[CompiledRelation]:
    relations: list[CompiledRelation] = []
    for artifact in bundle.artifacts:
        for statement in artifact.statements:
            if not statement.object.strip():
                continue
            relations.append(
                CompiledRelation(
                    source_artifact_local_id=artifact.local_id,
                    target_artifact_local_id="",
                    target_literal=statement.object,
                    relation_type=statement.predicate,
                    evidence_local_ids=statement.evidence_local_ids,
                    qualifiers=statement.qualifiers,
                    confidence=statement.confidence,
                    status=statement.status,
                )
            )
    return relations
