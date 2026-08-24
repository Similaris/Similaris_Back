import re

from app.models.analysis import Document
from app.services.analysis.segment_service import SegmentService, segment_text


class FakeRepository:
    def __init__(self):
        self.segments = None

    def replace_for_document(self, document_id, segments):
        self.segments = list(segments)
        return self.segments


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_segment_text_ignores_empty_text():
    assert segment_text(" \n\t ") == []


def test_segment_text_keeps_small_text_and_punctuation():
    text = "  Primeiro   trecho.\n\nSegundo trecho!  "

    assert segment_text(text) == ["Primeiro trecho. Segundo trecho!"]


def test_segment_text_normalizes_excessive_whitespace_without_losing_words():
    text = "Um\n\ntexto\tcom espaços   excessivos."

    result = segment_text(text)

    assert result == ["Um texto com espaços excessivos."]
    assert "".join(result).split() == normalize(text).split()


def test_segment_text_prefers_sentence_boundaries_and_preserves_order():
    text = "Primeira frase. Segunda frase? Terceira frase!"

    result = segment_text(text, max_words=3)

    assert result == ["Primeira frase.", "Segunda frase?", "Terceira frase!"]


def test_segment_text_splits_text_above_150_words():
    words = [f"palavra{i}" for i in range(301)]

    result = segment_text(" ".join(words))

    assert [len(segment.split()) for segment in result] == [101, 100, 100]
    assert " ".join(result).split() == words


def test_segment_text_splits_sentence_larger_than_limit_without_cutting_words():
    words = [f"palavra{i}" for i in range(151)]

    result = segment_text(" ".join(words) + ".")

    assert all(len(segment.split()) <= 150 for segment in result)
    assert " ".join(result).split() == words[:-1] + ["palavra150."]


def test_segment_text_does_not_lose_words_with_multiple_segments():
    text = " ".join(f"word{i}" for i in range(450))

    result = segment_text(text)

    assert len(result) == 3
    assert " ".join(result).split() == text.split()


def test_persist_document_segments_replaces_previous_segments():
    repository = FakeRepository()
    service = SegmentService(db=None, repository=repository)
    document = Document(id=12)

    result = service.persist_document_segments(document, "A. B.")

    assert result is repository.segments
    assert [segment.position for segment in result] == [1]
    assert result[0].document_id == 12
    assert result[0].text_original == "A. B."


def test_persist_document_segments_preserves_original_text_and_offsets():
    repository = FakeRepository()
    service = SegmentService(db=None, repository=repository, max_words=2)
    document = Document(id=12)
    original_text = "  Primeira   frase.\n\nSegunda frase?  "

    result = service.persist_document_segments(document, original_text)

    assert [segment.position for segment in result] == [1, 2]
    assert [segment.text_original for segment in result] == [
        "Primeira   frase.",
        "Segunda frase?",
    ]
    for segment in result:
        assert (
            original_text[segment.start_offset : segment.end_offset]
            == segment.text_original
        )
