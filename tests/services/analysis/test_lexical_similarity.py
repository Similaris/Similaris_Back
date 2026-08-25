from app.core.config import settings
from app.services.analysis.lexical_similarity import (
    compare_texts,
    compute_cosine_similarity,
    compute_jaccard_similarity,
)

BASE_TEXT = (
    "Plagiarism detection systems compare academic documents to find copied content."
)


def test_identical_texts_have_maximum_similarity():
    result = compare_texts(BASE_TEXT, BASE_TEXT)

    assert result.cosine == 1.0
    assert result.jaccard == 1.0
    assert result.exceeds_cosine
    assert result.exceeds_jaccard
    assert result.is_suspicious


def test_direct_copy_inside_larger_text_is_suspicious():
    source = (
        "Plagiarism detection systems compare academic documents to find copied "
        "content. The evaluation uses the PAN-PC-11 corpus as a standard reference."
    )

    result = compare_texts(source, BASE_TEXT)

    assert result.cosine >= 0.5
    assert result.jaccard >= 0.2
    assert result.is_suspicious


def test_small_alterations_remain_suspicious():
    altered = (
        "Plagiarism detection tools compare academic documents to find copied content."
    )

    result = compare_texts(BASE_TEXT, altered)

    assert 0.5 <= result.cosine < 1.0
    assert 0.2 <= result.jaccard < 1.0
    assert result.is_suspicious


def test_partial_overlap_stays_below_thresholds():
    text_a = "The proposed system measures lexical similarity between academic papers."
    text_b = (
        "Semantic embeddings capture meaning, while lexical similarity counts "
        "shared words."
    )

    result = compare_texts(text_a, text_b)

    assert 0.0 < result.cosine < 0.5
    assert 0.0 < result.jaccard < 0.2
    assert not result.is_suspicious


def test_completely_different_texts_have_zero_similarity():
    text_a = "Quantum processors execute algorithms using entangled qubits."
    text_b = "Fresh bread requires flour, water, salt, and patient kneading."

    result = compare_texts(text_a, text_b)

    assert result.cosine == 0.0
    assert result.jaccard == 0.0
    assert not result.is_suspicious


def test_texts_without_relevant_tokens_have_zero_similarity():
    result = compare_texts("", "the of and to")

    assert result.cosine == 0.0
    assert result.jaccard == 0.0
    assert not result.is_suspicious


def test_thresholds_can_be_overridden_per_call():
    result = compare_texts(
        BASE_TEXT,
        BASE_TEXT,
        cosine_threshold=1.0,
        jaccard_threshold=1.0,
    )

    assert result.cosine_threshold == 1.0
    assert result.jaccard_threshold == 1.0
    assert result.is_suspicious


def test_default_thresholds_come_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "lexical_cosine_threshold", 0.9)
    monkeypatch.setattr(settings, "lexical_jaccard_threshold", 0.8)

    result = compare_texts(BASE_TEXT, BASE_TEXT)

    assert result.cosine_threshold == 0.9
    assert result.jaccard_threshold == 0.8


def test_compute_cosine_similarity_preprocesses_raw_text():
    score = compute_cosine_similarity("The COPIED text!", "the copied TEXT?")

    assert score == 1.0


def test_compute_jaccard_similarity_uses_token_sets():
    score = compute_jaccard_similarity(
        "copied text copied text", "copied text"
    )

    assert score == 1.0
