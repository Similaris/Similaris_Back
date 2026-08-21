from __future__ import annotations

import math
import re

from sqlalchemy.orm import Session

from app.models.analysis import Document, Segment
from app.repositories.analysis import SegmentRepository
from app.services.documents.document_extractor import extract_document_text


_SENTENCE_SEPARATOR = re.compile(r"(?<=[.!?。！？])\s+")
_WHITESPACE = re.compile(r"\s+")
DEFAULT_MAX_WORDS = 150


def _split_long_sentence(words: list[str], max_words: int) -> list[str]:
    number_of_chunks = math.ceil(len(words) / max_words)
    base_size, remainder = divmod(len(words), number_of_chunks)
    chunks: list[str] = []
    start = 0

    for chunk_index in range(number_of_chunks):
        chunk_size = base_size + (1 if chunk_index < remainder else 0)
        chunks.append(" ".join(words[start : start + chunk_size]))
        start += chunk_size

    return chunks


def segment_text(text: str, max_words: int = DEFAULT_MAX_WORDS) -> list[str]:
    if max_words < 1:
        raise ValueError("max_words deve ser maior que zero")

    normalized_text = _WHITESPACE.sub(" ", text or "").strip()
    if not normalized_text:
        return []

    sentences = _SENTENCE_SEPARATOR.split(normalized_text)
    segments: list[str] = []
    current_words: list[str] = []

    def flush_current() -> None:
        if current_words:
            segments.append(" ".join(current_words))
            current_words.clear()

    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue

        if len(words) > max_words:
            flush_current()
            segments.extend(_split_long_sentence(words, max_words))
            continue

        if len(current_words) + len(words) <= max_words:
            current_words.extend(words)
        else:
            flush_current()
            current_words.extend(words)

    flush_current()
    return segments


class SegmentService:

    def __init__(self, db: Session, repository: SegmentRepository | None = None):
        self.repository = repository or SegmentRepository(db)

    def persist_document_segments(
        self, document: Document, extracted_text: str
    ) -> list[Segment]:
        texts = segment_text(extracted_text)
        offset = 0
        segments: list[Segment] = []

        for position, segment_text_value in enumerate(texts, start=1):
            start_offset = offset
            end_offset = start_offset + len(segment_text_value)
            segments.append(
                Segment(
                    document_id=document.id,
                    position=position,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    text_original=segment_text_value,
                )
            )
            offset = end_offset + 1

        return self.repository.replace_for_document(document.id, segments)

    def list_document_segments(
        self, document_id: int, user_id: int
    ) -> list[Segment]:
        return self.repository.list_by_document_for_user(document_id, user_id)

    def extract_and_persist(
        self, document: Document, content: bytes, filename: str
    ) -> list[Segment]:
        extracted_text = extract_document_text(content, filename)
        return self.persist_document_segments(document, extracted_text)
