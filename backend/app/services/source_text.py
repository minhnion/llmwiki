from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


@dataclass(frozen=True)
class SourceTextContext:
    text: str
    char_count: int
    truncated: bool


TEXT_SOURCE_TYPES = {
    "csv",
    "json",
    "markdown",
    "md",
    "text",
    "tsv",
    "txt",
    "xml",
    "yaml",
    "yml",
}


def extract_source_text_context(
    path: Path,
    source_type: str,
    max_chars: int,
) -> SourceTextContext | None:
    """Best-effort generic text aid for LLM source reading.

    This is not a retrieval corpus and does not decide semantics. It only gives the
    model a faithful, inspectable text view when the raw file format exposes text.
    """

    if max_chars <= 0:
        return None
    suffix = path.suffix.casefold().lstrip(".")
    normalized_type = source_type.casefold().strip()
    if suffix == "odt" or normalized_type == "odt":
        lines = _extract_odt_lines(path)
    elif suffix == "docx" or normalized_type == "docx":
        lines = _extract_docx_lines(path)
    elif suffix in TEXT_SOURCE_TYPES or normalized_type in TEXT_SOURCE_TYPES:
        lines = _read_text_lines(path)
    else:
        return None
    if not lines:
        return None
    text = "\n".join(
        f"P{index:04d}: {line}" for index, line in enumerate(lines, start=1)
    )
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars].rstrip()
    return SourceTextContext(text=text, char_count=len(text), truncated=truncated)


def _extract_odt_lines(path: Path) -> list[str]:
    try:
        with ZipFile(path) as archive:
            data = archive.read("content.xml")
    except (BadZipFile, KeyError, OSError):
        return []
    return _extract_xml_text_blocks(data)


def _extract_docx_lines(path: Path) -> list[str]:
    try:
        with ZipFile(path) as archive:
            data = archive.read("word/document.xml")
    except (BadZipFile, KeyError, OSError):
        return []
    return _extract_xml_text_blocks(data)


def _extract_xml_text_blocks(data: bytes) -> list[str]:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return []
    lines: list[str] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in {"h", "p"}:
            continue
        text = _normalize_text("".join(element.itertext()))
        if text:
            lines.append(text)
    return lines


def _read_text_lines(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
    except OSError:
        return []
    return [line for raw_line in text.splitlines() if (line := _normalize_text(raw_line))]


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())
