from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Iterable

from ingestion.chunkers.utils import pack_tokens
from ingestion.types import ChunkRecord, RawDocument


_RESUME_HEADINGS = {
    "professional summary",
    "summary",
    "education",
    "professional experience",
    "work experience",
    "experience",
    "selected projects",
    "projects",
    "certifications and achievements",
    "certifications",
    "achievements",
    "skills",
    "technical skills",
    "passion and interests",
    "interests",
    "additional information",
    "languages",
}


def _is_heading(line: str) -> bool:
    normalized = re.sub(r"[^a-z ]", "", line.lower()).strip()
    return normalized in _RESUME_HEADINGS


def _candidate_name(doc: RawDocument) -> str:
    first_page = doc.pages[0].text if doc.pages else doc.text
    first_line = next((line.strip() for line in first_page.splitlines() if line.strip()), "")
    # Resume contact lines often follow the name on the same extracted line.
    return first_line.split("|", 1)[0].strip() or Path(doc.path).stem


def _role_from_filename(doc: RawDocument) -> str:
    stem = Path(doc.path).stem
    stem = re.sub(r"\s*-\s*Copy$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"(?i)_?resume$", "", stem)
    parts = stem.split("_")
    role = " ".join(parts[1:]).replace("-", " ").strip()
    if role.lower() == "ai":
        first_page = doc.pages[0].text if doc.pages else doc.text
        summary_match = re.search(
            r"(?ims)^\s*professional summary\s*\n(.*?)(?=^\s*education\s*$)",
            first_page,
        )
        summary = " ".join(summary_match.group(1).split()) if summary_match else ""
        inferred = re.match(
            r"(.+?)\s+with\s+\d+\+?\s+years?\s+of experience",
            summary,
            flags=re.IGNORECASE,
        )
        if inferred:
            role = inferred.group(1).strip()
    return role or "Candidate profile"


class ResumeChunker:
    """Chunk resume PDFs by section while keeping page and profile metadata."""

    def __init__(self, max_tokens: int = 650, overlap: int = 80) -> None:
        self.max_tokens = max(1, int(max_tokens))
        self.overlap = max(0, min(int(overlap), self.max_tokens - 1))

    def chunk(self, docs: Iterable[RawDocument]) -> Iterable[ChunkRecord]:
        for doc in docs:
            candidate = _candidate_name(doc)
            role = _role_from_filename(doc)
            pages = doc.pages or []
            if not pages and doc.text:
                from ingestion.types import Page

                pages = [Page(number=1, text=doc.text)]

            section = "Profile"
            chunk_number = 0
            for page in pages:
                groups: list[tuple[str, list[str]]] = []
                current_lines: list[str] = []

                for raw_line in page.text.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if _is_heading(line):
                        if current_lines:
                            groups.append((section, current_lines))
                        section = line
                        current_lines = [line]
                    else:
                        current_lines.append(line)

                if current_lines:
                    groups.append((section, current_lines))

                for section_name, lines in groups:
                    section_text = "\n".join(lines).strip()
                    if not section_text:
                        continue
                    body_chunks = pack_tokens(
                        section_text, self.max_tokens, self.overlap
                    )
                    for body in body_chunks:
                        if not body.strip():
                            continue
                        chunk_number += 1
                        prefix = (
                            f"Candidate: {candidate}\n"
                            f"Role: {role}\n"
                            f"Resume section: {section_name}\n"
                        )
                        chunk_id = str(
                            uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"{doc.doc_id}:{page.number}:{section_name}:{chunk_number}",
                            )
                        )
                        metadata = dict(doc.metadata or {})
                        metadata.update(
                            {
                                "source_filename": Path(doc.path).name,
                                "candidate_name": candidate,
                                "role": role,
                                "section": section_name,
                                "page_number": page.number,
                                "chunk_number": chunk_number,
                            }
                        )
                        yield ChunkRecord(
                            id=chunk_id,
                            doc_id=doc.doc_id,
                            text=f"{prefix}\n{body}",
                            page=page.number,
                            start_offset=None,
                            end_offset=None,
                            metadata=metadata,
                        )
