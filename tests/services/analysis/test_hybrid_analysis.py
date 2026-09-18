from unittest.mock import Mock

import pytest

from app.models.analysis import Document, Segment
from app.services.analysis.hybrid_analysis import (
    HybridAnalysisService,
    HybridScoreCalculator,
)
from app.services.analysis.hybrid_contracts import (
    HybridAnalysisOptions,
    SimilarityClassification,
)
from app.services.references.search_contracts import (
    ReferenceDocumentMatch,
    ReferenceMatch,
    ReferenceSearchOptions,
    ReferenceSearchResult,
    ReferenceSegmentMatch,
)


def reference_match(
    reference_id: int,
    *,
    tfidf: float,
    jaccard: float,
    semantic: float,
    document_id: int = 10,
) -> ReferenceMatch:
    return ReferenceMatch(
        source_document=ReferenceDocumentMatch(
            id=document_id,
            corpus_id=f"source-{document_id}.txt",
            source="pan-pc-11",
            language="en",
            title=f"Source {document_id}",
        ),
        source_segment=ReferenceSegmentMatch(
            id=reference_id,
            position=reference_id,
            start_offset=0,
            end_offset=20,
            text_original=f"Reference {reference_id}",
        ),
        lexical_score=tfidf,
        jaccard_score=jaccard,
        semantic_score=semantic,
    )


def search_result(*matches: ReferenceMatch) -> ReferenceSearchResult:
    return ReferenceSearchResult(
        options=ReferenceSearchOptions(),
        index_fingerprint="a" * 64,
        matches=matches,
        comparison_ms=1.0,
    )


def build_service(
    responses: dict[tuple[str, str], ReferenceSearchResult],
    segments: list[Segment],
    *,
    options: HybridAnalysisOptions | None = None,
) -> tuple[HybridAnalysisService, Mock]:
    search = Mock()
    search.search.side_effect = lambda text, *, mode: responses[(text, mode)]
    segment_repository = Mock()
    segment_repository.list_by_document.return_value = segments
    service = HybridAnalysisService(
        reference_search=search,
        segment_repository=segment_repository,
        options=options,
    )
    return service, search


def document(document_id: int = 1) -> Document:
    return Document(
        id=document_id,
        batch_id=1,
        filename="submission.pdf",
        file_type="pdf",
        file_path="submission.pdf",
    )


def segment(segment_id: int, text: str) -> Segment:
    return Segment(
        id=segment_id,
        document_id=1,
        position=segment_id,
        text_original=text,
        text_clean=text.lower(),
    )


def test_combines_all_scores_only_for_the_same_reference_pair():
    source = segment(12, "Submitted segment")
    lexical_match = reference_match(
        101, tfidf=0.82, jaccard=0.63, semantic=0.91
    )
    other_semantic_match = reference_match(
        202, tfidf=0.1, jaccard=0.2, semantic=0.95
    )
    service, _ = build_service(
        {
            (source.text_original, "lexical"): search_result(lexical_match),
            (source.text_original, "semantic"): search_result(other_semantic_match),
        },
        [source],
    )

    result = service.analyze_document(document())
    matches = {match.reference_segment.id: match for match in result.segments[0].matches}

    assert set(matches) == {101, 202}
    assert matches[101].tfidf_score == 0.82
    assert matches[101].jaccard_score == 0.63
    assert matches[101].semantic_score == 0.91
    assert matches[101].lexical_score == pytest.approx(0.763)
    assert matches[101].final_score == pytest.approx(0.8365)
    assert matches[202].semantic_score == 0.95
    assert matches[202].tfidf_score == 0.1


def test_unites_lexical_only_and_semantic_only_candidates():
    source = segment(1, "Query")
    lexical_only = reference_match(11, tfidf=0.9, jaccard=0.7, semantic=0.2)
    semantic_only = reference_match(22, tfidf=0.1, jaccard=0.0, semantic=0.9)
    service, search = build_service(
        {
            (source.text_original, "lexical"): search_result(lexical_only),
            (source.text_original, "semantic"): search_result(semantic_only),
        },
        [source],
    )

    result = service.analyze_document(document())

    assert {match.reference_segment.id for match in result.segments[0].matches} == {
        11,
        22,
    }
    assert [call.kwargs["mode"] for call in search.search.call_args_list] == [
        "lexical",
        "semantic",
    ]


def test_duplicate_candidate_is_consolidated_once():
    source = segment(1, "Query")
    lexical_version = reference_match(11, tfidf=0.8, jaccard=0.5, semantic=0.4)
    semantic_version = reference_match(11, tfidf=0.8, jaccard=0.5, semantic=0.9)
    service, _ = build_service(
        {
            (source.text_original, "lexical"): search_result(lexical_version),
            (source.text_original, "semantic"): search_result(semantic_version),
        },
        [source],
    )

    matches = service.analyze_document(document()).segments[0].matches

    assert len(matches) == 1
    assert matches[0].reference_segment.id == 11
    assert matches[0].tfidf_score == 0.8
    assert matches[0].semantic_score == 0.9


def test_score_calculator_uses_configured_weights_and_clamps_scores():
    calculator = HybridScoreCalculator(
        HybridAnalysisOptions(
            tfidf_weight=0.6,
            jaccard_weight=0.4,
            lexical_weight=0.25,
            semantic_weight=0.75,
        )
    )

    lexical_score = calculator.lexical_score(0.82, 0.63)
    final_score = calculator.final_score(lexical_score, 0.91)

    assert lexical_score == pytest.approx(0.6 * 0.82 + 0.4 * 0.63)
    assert final_score == pytest.approx(0.25 * lexical_score + 0.75 * 0.91)
    assert calculator.final_score(2.0, -1.0) == 0.25


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.39, SimilarityClassification.LOW),
        (0.40, SimilarityClassification.MODERATE),
        (0.60, SimilarityClassification.HIGH),
        (0.80, SimilarityClassification.VERY_HIGH),
    ],
)
def test_classifies_boundary_scores(score, expected):
    assert HybridScoreCalculator().classify(score) == expected


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ({"tfidf_score": 0.1, "jaccard_score": 0.1, "semantic_score": 0.1,
          "final_score": 0.6}, True),
        ({"tfidf_score": 0.1, "jaccard_score": 0.1, "semantic_score": 0.8,
          "final_score": 0.4}, True),
        ({"tfidf_score": 0.7, "jaccard_score": 0.5, "semantic_score": 0.1,
          "final_score": 0.4}, True),
        ({"tfidf_score": 0.7, "jaccard_score": 0.49, "semantic_score": 0.1,
          "final_score": 0.4}, False),
    ],
)
def test_applies_configurable_suspicion_rule(scores, expected):
    assert HybridScoreCalculator().is_suspicious(**scores) is expected


def test_orders_matches_by_final_then_semantic_and_applies_top_n():
    source = segment(1, "Query")
    options = HybridAnalysisOptions(top_n=2)
    lower = reference_match(1, tfidf=0.2, jaccard=0.2, semantic=0.2)
    lexical_tie = reference_match(2, tfidf=0.8, jaccard=0.8, semantic=0.0)
    semantic_tie = reference_match(3, tfidf=0.0, jaccard=0.0, semantic=0.8)
    service, _ = build_service(
        {
            (source.text_original, "lexical"): search_result(lower, lexical_tie),
            (source.text_original, "semantic"): search_result(semantic_tie),
        },
        [source],
        options=options,
    )

    matches = service.analyze_document(document()).segments[0].matches

    assert [match.reference_segment.id for match in matches] == [3, 2]
    assert matches[0].final_score == pytest.approx(matches[1].final_score)


def test_segment_without_matches_has_zero_score_and_low_classification():
    source = segment(1, "No match")
    service, _ = build_service(
        {
            (source.text_original, "lexical"): search_result(),
            (source.text_original, "semantic"): search_result(),
        },
        [source],
    )

    analysis = service.analyze_document(document()).segments[0]

    assert analysis.matches == ()
    assert analysis.best_match is None
    assert analysis.segment_score == 0.0
    assert analysis.classification == SimilarityClassification.LOW
    assert analysis.is_suspicious is False


def test_document_scores_use_best_match_per_segment_and_suspicious_ratio():
    matched = segment(1, "Matched")
    unmatched = segment(2, "Unmatched")
    best = reference_match(10, tfidf=0.8, jaccard=0.8, semantic=0.8)
    service, _ = build_service(
        {
            (matched.text_original, "lexical"): search_result(best),
            (matched.text_original, "semantic"): search_result(best),
            (unmatched.text_original, "lexical"): search_result(),
            (unmatched.text_original, "semantic"): search_result(),
        },
        [matched, unmatched],
    )

    result = service.analyze_document(document(42))

    assert result.document_id == 42
    assert result.total_segments == result.analyzed_segments == 2
    assert result.segments[0].segment_score == pytest.approx(0.8)
    assert result.suspicious_segments == 1
    assert result.overall_score == pytest.approx(0.4)
    assert result.suspicious_segment_percentage == pytest.approx(0.5)


def test_document_without_segments_has_zero_aggregates():
    service, search = build_service({}, [])

    result = service.analyze_document(document())

    assert result.total_segments == result.analyzed_segments == 0
    assert result.segments == ()
    assert result.overall_score == 0.0
    assert result.suspicious_segment_percentage == 0.0
    search.search.assert_not_called()
