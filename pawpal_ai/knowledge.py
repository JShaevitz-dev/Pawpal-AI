"""Load the pet-care knowledge base (markdown files with a small header) into memory."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from pawpal_system import FREQUENCIES, PRIORITY_RANK, parse_time

log = logging.getLogger("pawpal.knowledge")

DEFAULT_KB_DIR = Path(__file__).resolve().parent.parent / "knowledge"
SPECIES_ANY = "any"


@dataclass(frozen=True)
class KBTask:
    """A care task a knowledge-base document recommends."""

    title: str
    duration_minutes: int
    priority: str
    frequency: str
    preferred_time: str | None
    keys: tuple[str, ...]
    source_id: str


@dataclass
class Document:
    """One knowledge-base document."""

    id: str
    title: str
    species: str
    tags: list[str]
    body: str
    tasks: list[KBTask] = field(default_factory=list)

    def applies_to(self, species: str) -> bool:
        return self.species == SPECIES_ANY or self.species == species

    @property
    def search_text(self) -> str:
        """Text the retriever indexes. Title and tags are repeated so they weigh more than body words."""
        task_words = " ".join(f"{t.title} {' '.join(t.keys)}" for t in self.tasks)
        tags = " ".join(self.tags)
        return f"{self.title} {self.title} {tags} {tags} {self.body} {task_words}"

    def sentences(self) -> list[str]:
        text = re.sub(r"\s+", " ", self.body).strip()
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _parse_task_line(line: str, source_id: str) -> KBTask:
    parts = [p.strip() for p in line.lstrip("- ").split("|")]
    if len(parts) != 6:
        raise ValueError(f"expected 6 fields, got {len(parts)}")
    title, minutes, priority, frequency, at, keys = parts
    if priority not in PRIORITY_RANK:
        raise ValueError(f"bad priority {priority!r}")
    if frequency not in FREQUENCIES:
        raise ValueError(f"bad frequency {frequency!r}")
    if at:
        parse_time(at)
    keys = keys.removeprefix("keys:").strip()
    return KBTask(
        title=title,
        duration_minutes=int(minutes),
        priority=priority,
        frequency=frequency,
        preferred_time=at or None,
        keys=tuple(k.strip().lower() for k in keys.split(",") if k.strip()),
        source_id=source_id,
    )


def parse_document(text: str, name: str = "<string>") -> Document:
    """Parse one markdown document. Raises ValueError if the header is missing or malformed."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not match:
        raise ValueError(f"{name}: missing '---' header")
    header: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            header[key.strip()] = value.strip()
    for required in ("id", "title", "species"):
        if not header.get(required):
            raise ValueError(f"{name}: header is missing '{required}'")

    body, _, task_block = match.group(2).partition("## Tasks")
    doc = Document(
        id=header["id"],
        title=header["title"],
        species=header["species"].lower(),
        tags=[t.strip().lower() for t in header.get("tags", "").split(",") if t.strip()],
        body=body.strip(),
    )
    for line in task_block.splitlines():
        if line.strip().startswith("- "):
            try:
                doc.tasks.append(_parse_task_line(line.strip(), doc.id))
            except ValueError as exc:
                log.warning("%s: skipping bad task line %r (%s)", name, line.strip(), exc)
    return doc


def load_knowledge_base(directory: str | Path = DEFAULT_KB_DIR) -> list[Document]:
    """Load every document in the directory (README.md is skipped). Bad files are logged and skipped."""
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Knowledge base folder not found: {directory}")
    docs: list[Document] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        try:
            doc = parse_document(path.read_text(encoding="utf-8"), path.name)
        except ValueError as exc:
            log.warning("Skipping knowledge file: %s", exc)
            continue
        if doc.id in seen:
            log.warning("Skipping %s: duplicate id %r", path.name, doc.id)
            continue
        seen.add(doc.id)
        docs.append(doc)
    if not docs:
        raise ValueError(f"No usable documents in {directory}")
    log.info("Loaded %d knowledge documents from %s", len(docs), directory)
    return docs
