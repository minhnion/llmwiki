from pathlib import Path


class WikiLogWriter:
    def __init__(self, wiki_dir: Path) -> None:
        self.log_path = wiki_dir / "log.md"

    def append_source_registered(
        self,
        timestamp: str,
        source_id: str,
        title: str,
        path: Path,
    ) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("# Nhật ký Wiki\n\n", encoding="utf-8")
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(
                f"\n## [{timestamp}] register | {title}\n\n"
                f"- source_id: `{source_id}`\n"
                f"- path: `{path}`\n"
            )

    def append_source_ingested(
        self,
        timestamp: str,
        source_id: str,
        title: str,
        page_path: Path,
    ) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("# Nhật ký Wiki\n\n", encoding="utf-8")
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(
                f"\n## [{timestamp}] ingest | {title}\n\n"
                f"- source_id: `{source_id}`\n"
                f"- page: `{page_path}`\n"
            )

    def append_query_answered(
        self,
        timestamp: str,
        query_id: str,
        question: str,
        confidence: str,
        citation_count: int,
    ) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("# Nhật ký Wiki\n\n", encoding="utf-8")
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(
                f"\n## [{timestamp}] query | {query_id}\n\n"
                f"- question: {question}\n"
                f"- confidence: `{confidence}`\n"
                f"- citations: {citation_count}\n"
            )

    def append_graph_built(
        self,
        timestamp: str,
        graph_run_id: str,
        relation_count: int,
        contradiction_count: int,
        entity_page_count: int,
    ) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("# Nhật ký Wiki\n\n", encoding="utf-8")
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(
                f"\n## [{timestamp}] graph | {graph_run_id}\n\n"
                f"- relations: {relation_count}\n"
                f"- contradictions: {contradiction_count}\n"
                f"- entity_pages: {entity_page_count}\n"
            )

    def append_compiler_completed(
        self,
        timestamp: str,
        compiler_run_id: str,
        source_id: str,
        pass_count: int,
        artifact_count: int,
        coverage_status: str,
        graph_run_id: str,
    ) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("# Nhật ký Wiki\n\n", encoding="utf-8")
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(
                f"\n## [{timestamp}] compiler | {compiler_run_id}\n\n"
                f"- source_id: `{source_id}`\n"
                f"- passes: {pass_count}\n"
                f"- artifacts: {artifact_count}\n"
                f"- coverage: `{coverage_status}`\n"
                f"- graph_run_id: `{graph_run_id}`\n"
            )
