from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analysis import Document, Segment
from app.repositories.analysis import SegmentRepository
from app.services.documents.document_extractor import extract_document_text


_SENTENCE_SEPARATOR = re.compile(r"(?<=[.!?。！？])\s+")
_WHITESPACE = re.compile(r"\s+")
_WORD = re.compile(r"\S+")
DEFAULT_MAX_WORDS = 150


@dataclass(frozen=True, slots=True)
class SegmentSlice:
    text: str
    start_offset: int
    end_offset: int


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


def segment_text_with_offsets(
    text: str, max_words: int = DEFAULT_MAX_WORDS
) -> list[SegmentSlice]:
    normalized_segments = segment_text(text, max_words)
    word_matches = list(_WORD.finditer(text or ""))
    word_index = 0
    slices: list[SegmentSlice] = []

    for normalized_segment in normalized_segments:
        word_count = len(normalized_segment.split())
        segment_matches = word_matches[word_index : word_index + word_count]
        if len(segment_matches) != word_count:
            raise RuntimeError("Não foi possível mapear o segmento no texto original.")

        start_offset = segment_matches[0].start()
        end_offset = segment_matches[-1].end()
        slices.append(
            SegmentSlice(
                text=text[start_offset:end_offset],
                start_offset=start_offset,
                end_offset=end_offset,
            )
        )
        word_index += word_count

    if word_index != len(word_matches):
        raise RuntimeError("Nem todas as palavras foram mapeadas nos segmentos.")

    return slices


class SegmentService:

    def __init__(
        self,
        db: Session,
        repository: SegmentRepository | None = None,
        max_words: int | None = None,
    ):
        self.repository = repository or SegmentRepository(db)
        self.max_words = settings.segment_max_words if max_words is None else max_words
        if self.max_words < 1:
            raise ValueError("max_words deve ser maior que zero")

    def persist_document_segments(
        self, document: Document, extracted_text: str
    ) -> list[Segment]:
        slices = segment_text_with_offsets(extracted_text, self.max_words)
        segments: list[Segment] = []

        for position, segment_slice in enumerate(slices, start=1):
            segments.append(
                Segment(
                    document_id=document.id,
                    position=position,
                    start_offset=segment_slice.start_offset,
                    end_offset=segment_slice.end_offset,
                    text_original=segment_slice.text,
                )
            )

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
