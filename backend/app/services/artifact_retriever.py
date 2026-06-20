from collections import defaultdict

from backend.app.domain.query import (
    ArtifactCandidate,
    KnowledgeNavigationResult,
    QueryPlan,
    RetrievalSignal,
)
from backend.app.repositories.semantic import ArtifactSearchHit, SQLiteSemanticRepository
from backend.app.services.semantic_indexer import EmbeddingClient


class ArtifactRetriever:
    def __init__(
        self,
        repository: SQLiteSemanticRepository,
        embedding_client: EmbeddingClient,
        embedding_model: str,
        rrf_k: int = 60,
    ) -> None:
        self.repository = repository
        self.embedding_client = embedding_client
        self.embedding_model = embedding_model
        self.rrf_k = rrf_k

    async def retrieve(
        self,
        question: str,
        plan: QueryPlan,
        navigation: KnowledgeNavigationResult,
        source_ids: list[str],
        tags: list[str],
        max_candidates: int,
    ) -> list[ArtifactCandidate]:
        score_by_id: dict[str, float] = defaultdict(float)
        channels_by_id: dict[str, set[str]] = defaultdict(set)
        signals_by_id: dict[str, list[RetrievalSignal]] = defaultdict(list)

        navigation_hits = [
            ArtifactSearchHit(
                artifact_id=item.artifact_id,
                channel="llm_navigation",
                rank=rank,
                score=item.confidence,
                detail=item.reason,
            )
            for rank, item in enumerate(navigation.selected_artifacts, start=1)
        ]
        self._add_hits(navigation_hits, score_by_id, channels_by_id, signals_by_id)

        fts_query = _build_fts_query(_query_terms(question, plan))
        fts_hits = self.repository.search_artifact_fts(
            fts_query=fts_query,
            source_ids=source_ids,
            tags=tags,
            limit=max_candidates,
        )
        self._add_hits(fts_hits, score_by_id, channels_by_id, signals_by_id)

        embedding_hits = await self._embedding_hits(
            question=question,
            plan=plan,
            source_ids=source_ids,
            tags=tags,
            max_candidates=max_candidates,
        )
        self._add_hits(embedding_hits, score_by_id, channels_by_id, signals_by_id)

        seed_artifact_ids = _ranked_ids(score_by_id)[:max_candidates]
        graph_depths = self.repository.expand_artifact_graph(
            seed_artifact_ids=seed_artifact_ids,
            source_ids=source_ids,
            max_depth=plan.graph_policy.max_depth,
            max_nodes=plan.graph_policy.max_nodes,
        )
        graph_hits = [
            ArtifactSearchHit(
                artifact_id=artifact_id,
                channel="artifact_graph",
                rank=rank,
                score=1.0 / (depth + 1),
                detail=f"Graph neighbor at depth {depth}.",
            )
            for rank, (artifact_id, depth) in enumerate(
                sorted(graph_depths.items(), key=lambda item: (item[1], item[0])),
                start=1,
            )
        ]
        self._add_hits(graph_hits, score_by_id, channels_by_id, signals_by_id)

        artifact_ids = _ranked_ids(score_by_id)[: max_candidates * 2]
        candidates = self.repository.hydrate_artifact_candidates(
            artifact_ids=artifact_ids,
            score_by_id=score_by_id,
            channels_by_id=channels_by_id,
            signals_by_id=signals_by_id,
            graph_depth_by_id=graph_depths,
        )
        return sorted(
            candidates,
            key=lambda candidate: (
                candidate.retrieval_score,
                candidate.confidence,
                len(candidate.statements),
            ),
            reverse=True,
        )[:max_candidates]

    async def _embedding_hits(
        self,
        question: str,
        plan: QueryPlan,
        source_ids: list[str],
        tags: list[str],
        max_candidates: int,
    ) -> list[ArtifactSearchHit]:
        probes = _embedding_probes(question, plan)
        if not probes:
            return []
        vectors = await self.embedding_client.embed_texts(probes, self.embedding_model)
        hits: list[ArtifactSearchHit] = []
        for probe, vector in zip(probes, vectors, strict=True):
            probe_hits = self.repository.search_artifact_embeddings(
                query_vector=vector,
                embedding_model=self.embedding_model,
                source_ids=source_ids,
                tags=tags,
                limit=max_candidates,
            )
            for hit in probe_hits:
                hits.append(
                    ArtifactSearchHit(
                        artifact_id=hit.artifact_id,
                        channel=hit.channel,
                        rank=hit.rank,
                        score=hit.score,
                        detail=f"{hit.detail}; probe: {probe}",
                    )
                )
        return hits

    def _add_hits(
        self,
        hits: list[ArtifactSearchHit],
        score_by_id: dict[str, float],
        channels_by_id: dict[str, set[str]],
        signals_by_id: dict[str, list[RetrievalSignal]],
    ) -> None:
        for hit in hits:
            score_by_id[hit.artifact_id] += 1.0 / (self.rrf_k + hit.rank)
            channels_by_id[hit.artifact_id].add(hit.channel)
            signals_by_id[hit.artifact_id].append(
                RetrievalSignal(
                    channel=hit.channel,
                    rank=hit.rank,
                    score=round(hit.score, 6),
                    detail=hit.detail,
                )
            )


def _query_terms(question: str, plan: QueryPlan) -> list[str]:
    return [
        question,
        plan.rewritten_question,
        *plan.keywords,
        *plan.entity_hints,
        *plan.subquestions,
        *plan.must_have_evidence,
        *plan.semantic_probes,
        *plan.desired_artifact_hints,
        *plan.answer_requirements,
        *plan.graph_policy.relation_hints,
    ]


def _embedding_probes(question: str, plan: QueryPlan) -> list[str]:
    probes = [
        question,
        plan.rewritten_question,
        *plan.semantic_probes,
        *plan.subquestions,
        *plan.desired_artifact_hints,
    ]
    return _clean_unique(probes)[:8]


def _build_fts_query(terms: list[str]) -> str:
    clean_terms = [
        " ".join(term.split())
        for term in terms
        if 1 < len(" ".join(term.split())) <= 160
    ]
    unique_terms = _clean_unique(clean_terms)[:40]
    return " OR ".join(f'"{_escape_fts_phrase(term)}"' for term in unique_terms)


def _escape_fts_phrase(term: str) -> str:
    return term.replace('"', '""')


def _clean_unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean_value = " ".join(value.split()).strip()
        if not clean_value:
            continue
        key = clean_value.casefold()
        if key in seen:
            continue
        output.append(clean_value)
        seen.add(key)
    return output


def _ranked_ids(score_by_id: dict[str, float]) -> list[str]:
    return [
        artifact_id
        for artifact_id, _ in sorted(
            score_by_id.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
    ]
