from dataclasses import dataclass

from backend.app.core.clock import utc_now_iso
from backend.app.core.ids import graph_run_id
from backend.app.domain.graph import GraphBuildCommand, GraphBuildResult, RelationEdge
from backend.app.repositories.graph import SQLiteGraphRepository
from backend.app.services.contradiction_detector import ContradictionDetector
from backend.app.services.entity_page_writer import EntityPageWriter
from backend.app.services.graph_extractor import GraphExtractor
from backend.app.services.wiki_log import WikiLogWriter


@dataclass(frozen=True)
class GraphBuildArtifacts:
    relations: list[RelationEdge]
    entity_page_count: int


class GraphBuilder:
    def __init__(
        self,
        repository: SQLiteGraphRepository,
        extractor: GraphExtractor,
        contradiction_detector: ContradictionDetector,
        entity_page_writer: EntityPageWriter,
        wiki_log_writer: WikiLogWriter,
    ) -> None:
        self.repository = repository
        self.extractor = extractor
        self.contradiction_detector = contradiction_detector
        self.entity_page_writer = entity_page_writer
        self.wiki_log_writer = wiki_log_writer

    async def build(self, command: GraphBuildCommand) -> GraphBuildResult:
        started_at = utc_now_iso()
        current_run_id = graph_run_id()
        self.repository.create_graph_run(current_run_id, command.source_ids, started_at)
        try:
            if command.rebuild:
                self.repository.clear_graph_artifacts(command.source_ids)
            self.repository.sync_entity_aliases(started_at)
            contexts = self.repository.list_claim_contexts(command.source_ids)

            saved_relations: list[RelationEdge] = []
            saved_merge_count = 0
            for batch in _chunks(contexts, command.max_claims_per_batch):
                extraction = await self.extractor.extract(batch)
                saved_relations.extend(
                    self.repository.save_relations(
                        extraction.relations,
                        batch,
                        started_at,
                    )
                )
                saved_merge_count += len(
                    self.repository.save_merge_candidates(
                        extraction.entity_merge_candidates,
                        started_at,
                    )
                )

            contradiction_result = await self.contradiction_detector.detect(
                contexts,
                command.max_claims_per_batch,
            )
            saved_contradictions = self.repository.save_contradictions(
                contradiction_result.contradictions,
                contexts,
                started_at,
            )
            entity_page_count = self._write_entity_pages(saved_relations)
            finished_at = utc_now_iso()
            result = GraphBuildResult(
                graph_run_id=current_run_id,
                source_ids=command.source_ids,
                claim_count=len(contexts),
                relation_count=len(saved_relations),
                contradiction_count=len(saved_contradictions),
                merge_candidate_count=saved_merge_count,
                entity_page_count=entity_page_count,
                status="completed",
                started_at=started_at,
                finished_at=finished_at,
            )
            self.repository.finish_graph_run(result)
            self.wiki_log_writer.append_graph_built(
                timestamp=finished_at,
                graph_run_id=current_run_id,
                relation_count=result.relation_count,
                contradiction_count=result.contradiction_count,
                entity_page_count=result.entity_page_count,
            )
            return result
        except Exception as exc:
            self.repository.fail_graph_run(current_run_id, utc_now_iso(), str(exc))
            raise

    def _write_entity_pages(self, relations: list[RelationEdge]) -> int:
        entity_ids = sorted(
            {
                entity_id
                for relation in relations
                for entity_id in (relation.subject_entity_id, relation.object_entity_id)
                if entity_id is not None
            }
        )
        count = 0
        for entity_id in entity_ids:
            detail = self.repository.get_entity_detail(entity_id)
            if detail is None:
                continue
            page = self.entity_page_writer.write(detail)
            self.repository.save_entity_page(page, entity_id)
            count += 1
        return count


def _chunks(items: list, chunk_size: int) -> list[list]:
    return [items[start : start + chunk_size] for start in range(0, len(items), chunk_size)]
