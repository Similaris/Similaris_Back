from unittest.mock import Mock

import numpy as np
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import create_engine, delete, update
from sqlalchemy.orm import Session

import app.models
from app.core.config import settings
from app.core.database import Base
from app.models.references import ReferenceDocument, ReferenceSegment
from app.repositories.references import ReferenceRepository
from app.services.analysis import lexical_similarity, semantic_similarity
from app.services.analysis.text_preprocessing import preprocess_text
from app.services.references import reference_search
from app.services.references.corpus_index import CorpusIndexError, prepare_corpus_index
from app.services.references.reference_search import ReferenceSearchService


@pytest.fixture
def service(search_corpus):
    return ReferenceSearchService(search_corpus.repository, search_corpus.index_dir)


def match_ids(result):
    return [match.source_segment.id for match in result.matches]


@pytest.mark.parametrize("mode", ["lexical", "semantic"])
def test_exact_match_returns_original_source_metadata_and_all_scores(
    service, search_corpus, mode,
):
    result = service.search(search_corpus.query, mode=mode, top_n=1)
    match = result.matches[0]

    assert result.options.mode == mode
    assert result.options.top_n == 1
    assert len(result.index_fingerprint) == 64
    assert np.isfinite(result.comparison_ms) and result.comparison_ms >= 0
    assert match.source_document.id == 1
    assert match.source_document.corpus_id == "source-document00001.txt"
    assert match.source_document.title == "First source"
    assert match.source_document.source == "pan-pc-11"
    assert match.source_document.language == "en"
    assert match.source_segment.id == 7
    assert match.source_segment.position == 1
    assert match.source_segment.start_offset == 0
    assert match.source_segment.end_offset == len(search_corpus.query)
    assert match.source_segment.text_original == search_corpus.query
    assert match.lexical_score == pytest.approx(1.0)
    assert match.semantic_score == pytest.approx(1.0)
    assert match.jaccard_score == 1.0
    search_corpus.query_encoder.assert_called_once_with(search_corpus.query)


def test_semantic_mode_does_not_gate_candidates_by_lexical_overlap(service, search_corpus):
    result = service.search(
        search_corpus.query,
        lexical_cosine_threshold=1.0,
        lexical_jaccard_threshold=1.0,
    )
    matches = {match.source_segment.id: match for match in result.matches}

    assert result.options.mode == "semantic"
    assert result.options.top_n == 5
    assert match_ids(result) == [7, 40, 81, 215]
    assert matches[81].semantic_score == pytest.approx(0.8)
    assert matches[81].lexical_score == matches[81].jaccard_score == 0


def test_lexical_mode_uses_and_filter_without_semantic_threshold(service, search_corpus):
    result = service.search(
        search_corpus.query, mode="lexical", semantic_threshold=1.0
    )

    assert match_ids(result) == [7, 40, 12]
    assert result.matches[-1].semantic_score == -1.0
    assert result.matches[-1].jaccard_score == pytest.approx(3 / 5)
    assert all(match.lexical_score >= 0.5 for match in result.matches)


@pytest.mark.parametrize("mode", ["lexical", "semantic"])
def test_equal_scores_use_segment_id_not_index_or_sql_order(service, search_corpus, mode):
    assert service._index.segment_ids.tolist() == [7, 81, 103, 215, 40, 12]
    assert match_ids(service.search(search_corpus.query, mode=mode, top_n=2)) == [7, 40]


def test_ranked_results_are_mapped_back_from_different_sql_order(
    service, search_corpus, monkeypatch,
):
    original = search_corpus.repository.get_segments_by_ids
    reader = Mock(side_effect=lambda ids: list(reversed(original(ids))))
    monkeypatch.setattr(search_corpus.repository, "get_segments_by_ids", reader)

    result = service.search(search_corpus.paraphrase, top_n=3)

    assert match_ids(result) == [81, 7, 40]
    assert result.matches[0].source_segment.position == 2
    assert result.matches[0].source_segment.start_offset == 200
    assert result.matches[0].source_segment.text_original == search_corpus.paraphrase
    assert result.matches[-1].source_document.id == 2
    reader.assert_called_once_with([81, 7, 40])


@pytest.mark.parametrize("query_name,expected_id", [("oov", 103), ("stopwords", 215)])
def test_zero_lexical_query_still_retrieves_semantically(
    service, search_corpus, query_name, expected_id,
):
    text = getattr(search_corpus, query_name)
    result = service.search(text, top_n=1)

    assert match_ids(result) == [expected_id]
    assert result.matches[0].lexical_score == result.matches[0].jaccard_score == 0
    assert result.matches[0].semantic_score == pytest.approx(1.0)
    assert service.search(text, mode="lexical").matches == ()


def test_semantic_cosine_supports_negative_scores_and_thresholds(service, search_corpus):
    all_scores = service.search(search_corpus.query, semantic_threshold=-1.0, top_n=20)
    non_negative = service.search(search_corpus.query, semantic_threshold=0, top_n=20)

    assert match_ids(all_scores) == [7, 40, 81, 215, 103, 12]
    assert all_scores.matches[-1].semantic_score == -1.0
    assert match_ids(non_negative) == [7, 40, 81, 215, 103]


def test_semantic_threshold_is_inclusive_without_rounding_to_float32(
    service, search_corpus,
):
    baseline = service.search(search_corpus.query, top_n=20)
    score = next(match.semantic_score for match in baseline.matches if match.source_segment.id == 81)
    at_boundary = service.search(search_corpus.query, semantic_threshold=score)
    above_boundary = service.search(
        search_corpus.query, semantic_threshold=float(np.nextafter(score, np.inf))
    )

    assert 81 in match_ids(at_boundary)
    assert 81 not in match_ids(above_boundary)


def test_lexical_threshold_is_inclusive_without_rounding_to_float32(service, search_corpus):
    baseline = service.search(search_corpus.query, mode="lexical")
    score = next(match.lexical_score for match in baseline.matches if match.source_segment.id == 12)
    at_boundary = service.search(
        search_corpus.query, mode="lexical", lexical_cosine_threshold=score
    )
    above_boundary = service.search(
        search_corpus.query, mode="lexical",
        lexical_cosine_threshold=float(np.nextafter(score, np.inf)),
    )

    assert 12 in match_ids(at_boundary)
    assert 12 not in match_ids(above_boundary)


def test_jaccard_threshold_is_inclusive_without_rounding(service, search_corpus):
    assert 12 in match_ids(service.search(
        search_corpus.query, mode="lexical", lexical_jaccard_threshold=3 / 5,
    ))
    assert 12 not in match_ids(service.search(
        search_corpus.query, mode="lexical",
        lexical_jaccard_threshold=float(np.nextafter(3 / 5, np.inf)),
    ))


def test_lexical_ranking_continues_after_jaccard_rejection_in_earlier_batch(
    search_corpus, monkeypatch,
):
    query = "cosmos orbital orbit"
    high_cosine = (query + " ") * 30 + " ".join(f"noise{index}" for index in range(10))
    eligible_text = "cosmos orbital"
    for text in (query, high_cosine, eligible_text):
        search_corpus.vectors[text] = np.array([1, 0, 0], dtype=np.float32)
    search_corpus.repository.add(
        ReferenceDocument(
            id=3, title="Threshold source", source="pan-pc-11", language="en",
            corpus_id="source-document00003.txt", content_sha256="c" * 64,
            import_signature="b" * 64,
        ),
        [
            ReferenceSegment(
                id=segment_id, position=position, start_offset=0,
                end_offset=len(text), text_original=text, text_clean=preprocess_text(text),
            )
            for position, (segment_id, text) in enumerate(
                [(600, high_cosine), (610, eligible_text)], start=1
            )
        ],
    )
    search_corpus.repository.db.commit()
    prepare_corpus_index(search_corpus.repository, search_corpus.index_dir, rebuild=True)
    service = ReferenceSearchService(search_corpus.repository, search_corpus.index_dir)
    reader = Mock(wraps=search_corpus.repository.get_segments_by_ids)
    monkeypatch.setattr(search_corpus.repository, "get_segments_by_ids", reader)
    monkeypatch.setattr(reference_search, "REFERENCE_BATCH_SIZE", 1)

    result = service.search(
        query, mode="lexical", top_n=1,
        lexical_cosine_threshold=0.1, lexical_jaccard_threshold=0.5,
    )

    assert match_ids(result) == [610]
    assert [call.args[0] for call in reader.call_args_list] == [[600], [610]]
    assert result.matches[0].jaccard_score == pytest.approx(2 / 3)


def test_semantic_scoring_can_use_small_blocks(service, search_corpus, monkeypatch):
    monkeypatch.setattr(reference_search, "SEMANTIC_BATCH_SIZE", 2)
    assert match_ids(service.search(search_corpus.query, top_n=20)) == [7, 40, 81, 215]
    lexical = service.search(search_corpus.query, mode="lexical")
    assert [match.semantic_score for match in lexical.matches] == [1, 1, -1]


def test_top_n_is_a_limit_not_a_required_number_of_matches(service, search_corpus):
    assert len(service.search(search_corpus.query, top_n=1).matches) == 1
    assert len(service.search(search_corpus.query, top_n=1000).matches) == 4
    assert service.search(search_corpus.unmatched, semantic_threshold=0.99).matches == ()


@pytest.mark.parametrize("text", ["", " ", "\n\t"])
def test_empty_query_is_an_error_not_empty_matches(service, search_corpus, text):
    with pytest.raises(ValueError, match="text_original"):
        service.search(text)
    search_corpus.query_encoder.assert_not_called()


@pytest.mark.parametrize("text", [None, 42, True, [], b"text"])
def test_query_type_is_validated(service, search_corpus, text):
    with pytest.raises(TypeError, match="text_original"):
        service.search(text)
    search_corpus.query_encoder.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [
        {"top_n": 0}, {"top_n": -1}, {"top_n": True}, {"top_n": 1.5},
        {"mode": "hybrid"}, {"lexical_cosine_threshold": -0.1},
        {"lexical_jaccard_threshold": float("nan")},
        {"semantic_threshold": float("inf")}, {"semantic_threshold": -1.1},
    ],
)
def test_invalid_search_overrides_fail_before_generating_embeddings(
    service, search_corpus, overrides,
):
    with pytest.raises((TypeError, ValueError)):
        service.search(search_corpus.query, **overrides)
    search_corpus.query_encoder.assert_not_called()


@pytest.mark.parametrize(
    "embedding",
    [
        np.zeros(3), np.ones(3), np.ones(4), np.ones((1, 3)), np.array([]),
        np.array([float("nan"), 0, 1]), np.array([float("inf"), 0, 1]), ["invalid"],
    ],
)
def test_invalid_query_embeddings_are_rejected(service, search_corpus, embedding):
    search_corpus.query_encoder.side_effect = None
    search_corpus.query_encoder.return_value = embedding
    with pytest.raises(semantic_similarity.EmbeddingGenerationError, match="embedding"):
        service.search(search_corpus.query)


def test_model_failure_is_not_converted_to_empty_matches(service, search_corpus):
    search_corpus.query_encoder.side_effect = semantic_similarity.SemanticModelLoadError(
        "model unavailable"
    )
    with pytest.raises(semantic_similarity.SemanticModelLoadError, match="unavailable"):
        service.search(search_corpus.query)


def test_index_and_fingerprint_are_reused_and_tfidf_is_never_refitted(
    search_corpus, monkeypatch,
):
    load = Mock(wraps=reference_search.load_corpus_index)
    fingerprint = Mock(wraps=reference_search.reference_fingerprint)
    monkeypatch.setattr(reference_search, "load_corpus_index", load)
    monkeypatch.setattr(reference_search, "reference_fingerprint", fingerprint)
    no_fit = Mock(side_effect=AssertionError("TF-IDF must not be refitted by search"))
    monkeypatch.setattr(TfidfVectorizer, "fit", no_fit)
    monkeypatch.setattr(TfidfVectorizer, "fit_transform", no_fit)
    search_corpus.reference_encoder.reset_mock()
    search_corpus.reference_encoder.side_effect = AssertionError("No reference embeddings")
    service = ReferenceSearchService(search_corpus.repository, search_corpus.index_dir)
    index = service._index
    transform = Mock(wraps=index.vectorizer.transform)
    monkeypatch.setattr(index.vectorizer, "transform", transform)

    service.search(search_corpus.query)
    service.search(search_corpus.query, mode="lexical")

    assert isinstance(index.semantic, np.memmap)
    assert service._index is index
    assert load.call_count == fingerprint.call_count == 1
    assert transform.call_count == 2
    assert transform.call_args.args == (["orchard fruit trees"],)
    assert search_corpus.query_encoder.call_count == 2
    search_corpus.reference_encoder.assert_not_called()
    no_fit.assert_not_called()
    service.revalidate()
    assert load.call_count == fingerprint.call_count == 2


def test_only_the_query_is_preprocessed_for_lexical_metrics(
    service, search_corpus, monkeypatch,
):
    preprocess = Mock(wraps=reference_search.preprocess_text)
    monkeypatch.setattr(reference_search, "preprocess_text", preprocess)
    monkeypatch.setattr(
        lexical_similarity, "preprocess_tokens",
        Mock(side_effect=AssertionError("Stored reference tokens must be reused")),
    )

    result = service.search(search_corpus.query)

    preprocess.assert_called_once_with(search_corpus.query)
    search_corpus.query_encoder.assert_called_once_with(search_corpus.query)
    assert result.matches[0].jaccard_score == 1.0


def test_missing_index_is_an_error(search_corpus, tmp_path):
    with pytest.raises(CorpusIndexError, match="current.json"):
        ReferenceSearchService(search_corpus.repository, tmp_path / "missing")


def test_empty_reference_database_is_an_error(search_corpus):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            with pytest.raises(CorpusIndexError, match="Importe documentos"):
                ReferenceSearchService(ReferenceRepository(db), search_corpus.index_dir)
    finally:
        engine.dispose()


def test_different_database_fingerprint_is_rejected(search_corpus):
    search_corpus.repository.db.execute(
        update(ReferenceDocument).values(import_signature="c" * 64)
    )
    search_corpus.repository.db.commit()

    with pytest.raises(CorpusIndexError, match="desatualizado"):
        ReferenceSearchService(search_corpus.repository, search_corpus.index_dir)


def test_model_incompatible_index_is_rejected(search_corpus, monkeypatch):
    monkeypatch.setattr(settings, "semantic_model_name", "another-model")
    with pytest.raises(CorpusIndexError, match="incompativel"):
        ReferenceSearchService(search_corpus.repository, search_corpus.index_dir)


def test_model_change_after_opening_invalidates_search(service, search_corpus, monkeypatch):
    monkeypatch.setattr(settings, "semantic_model_name", "another-model")
    with pytest.raises(CorpusIndexError, match="modelo mudou"):
        service.search(search_corpus.query)
    search_corpus.query_encoder.assert_not_called()


def test_corruption_does_not_become_a_successful_empty_search(search_corpus):
    (search_corpus.generation / "lexical.npz").write_bytes(b"corrupted")
    with pytest.raises(CorpusIndexError, match="corrompido"):
        ReferenceSearchService(search_corpus.repository, search_corpus.index_dir)


def test_segment_id_alignment_is_checked_even_with_valid_artifact_hash(
    search_corpus, refresh_artifact_hash,
):
    filename = "segment_ids.npy"
    ids = np.load(search_corpus.generation / filename)
    np.save(search_corpus.generation / filename, ids[::-1], allow_pickle=False)
    refresh_artifact_hash(search_corpus.generation, filename)

    with pytest.raises(CorpusIndexError, match="Alinhamento"):
        ReferenceSearchService(search_corpus.repository, search_corpus.index_dir)


def test_missing_candidate_invalidates_the_snapshot(service, search_corpus):
    search_corpus.repository.db.execute(delete(ReferenceSegment).where(ReferenceSegment.id == 7))
    search_corpus.repository.db.commit()
    with pytest.raises(CorpusIndexError, match="ausentes"):
        service.search(search_corpus.query, top_n=1)
    with pytest.raises(CorpusIndexError, match="Snapshot"):
        service.search(search_corpus.unmatched, semantic_threshold=1)


@pytest.mark.parametrize(
    "changes",
    [
        {"text_clean": "modified"},
        {"text_original": "Modified original.", "end_offset": 18},
        {"start_offset": 1},
        {"text_clean": None},
    ],
)
def test_changed_or_incomplete_candidate_is_an_error(service, search_corpus, changes):
    search_corpus.repository.db.execute(
        update(ReferenceSegment)
        .where(ReferenceSegment.id == 7)
        .values(**changes)
        .execution_options(synchronize_session=False)
    )
    search_corpus.repository.db.commit()

    with pytest.raises(CorpusIndexError):
        service.search(search_corpus.query, top_n=1)
    assert service._index is None


def test_failed_revalidation_cannot_fall_back_to_old_snapshot(service, search_corpus):
    search_corpus.repository.db.execute(
        update(ReferenceSegment)
        .where(ReferenceSegment.id == 81)
        .values(text_clean="changed outside the selected candidates")
        .execution_options(synchronize_session=False)
    )
    search_corpus.repository.db.commit()
    with pytest.raises(CorpusIndexError, match="desatualizado"):
        service.revalidate()
    with pytest.raises(CorpusIndexError, match="Snapshot"):
        service.search(search_corpus.query)


def test_revalidation_accepts_a_new_compatible_generation(service, search_corpus):
    previous = service._index
    prepare_corpus_index(search_corpus.repository, search_corpus.index_dir, rebuild=True)
    service.revalidate()

    assert service._index is not previous
    assert service._index.fingerprint == previous.fingerprint
    assert match_ids(service.search(search_corpus.query, top_n=1)) == [7]
