from pathlib import Path


class WikiLogWriter:
    def __init__(self, wiki_dir: Path) -> None:
        self.log_path = wiki_dir / "log.md"

    def append(
        self,
        timestamp: str,
        operation: str,
        title: str,
        details: dict[str, object],
    ) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("# Wiki Log\n", encoding="utf-8")
        lines = [f"\n## [{timestamp}] {operation} | {title}\n"]
        lines.extend(f"- {key}: `{value}`" for key, value in details.items())
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
