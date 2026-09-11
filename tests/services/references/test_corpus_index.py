import hashlib
import json

import numpy as np
import pytest
from scipy import sparse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models
from app.core.database import Base
from app.models.references import ReferenceDocument, ReferenceSegment
from app.repositories.references import ReferenceRepository
from app.services.analysis import semantic_similarity
from app.services.references.corpus_index import (
    CorpusIndexError,
    load_corpus_index,
    prepare_corpus_index,
    reference_fingerprint,
    reference_segment_signature,
)


@pytest.fixture
def repository():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        repository = ReferenceRepository(db)
        with db.begin():
            texts = ["Ocean current.", "Mountain current.", "Forest climate."]
            repository.add(
                ReferenceDocument(
                    title="Source", source="pan-pc-11",
                    corpus_id="source-document00001.txt",
                    content_sha256=hashlib.sha256(" ".join(texts).encode()).hexdigest(),
                    import_signature="a" * 64,
                ),
                [
                    ReferenceSegment(
                        position=index, text_original=text,
                        text_clean=text.lower().replace(".", ""),
                        start_offset=(index - 1) * 20,
                        end_offset=(index - 1) * 20 + len(text),
                    )
                    for index, text in enumerate(texts, start=1)
                ],
            )
        yield repository
    engine.dispose()


@pytest.fixture
def encoded_batches(monkeypatch):
    calls = []

    def encode(texts):
        calls.append(texts)
        rows = np.array(
            [[len(text), len(text.split()), 1] for text in texts],
            dtype=np.float32,
        )
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)

    monkeypatch.setattr(semantic_similarity, "generate_embeddings", encode)
    return calls


def test_prepares_aligned_sparse_and_semantic_artifacts(
    repository, tmp_path, encoded_batches
):
    result = prepare_corpus_index(repository, tmp_path, batch_size=2)
    index = load_corpus_index(tmp_path, reference_fingerprint(repository)[0])

    assert (result.documents, result.segments, result.reused) == (1, 3, False)
    assert [len(batch) for batch in encoded_batches] == [2, 1]
    assert encoded_batches[0][0] == "Ocean current."
    assert index.segment_ids.tolist() == [row.id for row in repository.iter_segments()]
    assert index.lexical.shape[0] == index.semantic.shape[0] == 3
    assert isinstance(index.semantic, np.memmap)
    query = index.vectorizer.transform(["ocean current"])
    np.testing.assert_allclose(query.toarray(), index.lexical[0].toarray(), atol=1e-6)
    np.testing.assert_allclose(np.linalg.norm(index.semantic, axis=1), 1, atol=1e-6)


def test_second_preparation_reuses_cache_without_generating_embeddings(
    repository, tmp_path, encoded_batches
):
    first = prepare_corpus_index(repository, tmp_path)
    second = prepare_corpus_index(repository, tmp_path)
    assert second.reused
    assert first.directory == second.directory
    assert len(encoded_batches) == 1


def test_changed_reference_requires_a_new_generation(
    repository, tmp_path, encoded_batches
):
    first = prepare_corpus_index(repository, tmp_path)
    row = next(repository.iter_segments())
    row.text_clean = "new prepared text"
    row.reference_document.import_signature = "b" * 64
    repository.db.commit()
    current_fingerprint = reference_fingerprint(repository)[0]
    with pytest.raises(CorpusIndexError, match="desatualizado"):
        load_corpus_index(tmp_path, current_fingerprint)
    second = prepare_corpus_index(repository, tmp_path)
    assert not second.reused
    assert first.directory != second.directory
    assert len(encoded_batches) == 2


def test_different_model_invalidates_cache(
    repository, tmp_path, encoded_batches, monkeypatch
):
    prepare_corpus_index(repository, tmp_path)
    monkeypatch.setattr(semantic_similarity.settings, "semantic_model_name", "another-model")
    with pytest.raises(CorpusIndexError, match="incompativel"):
        load_corpus_index(tmp_path)
    assert not prepare_corpus_index(repository, tmp_path).reused
    assert len(encoded_batches) == 2


def test_corrupted_cache_is_not_silently_used(repository, tmp_path, encoded_batches):
    first = prepare_corpus_index(repository, tmp_path)
    (first.directory / "idf.npy").write_bytes(b"corrupted")
    with pytest.raises(CorpusIndexError, match="corrompido"):
        prepare_corpus_index(repository, tmp_path)
    with pytest.raises(CorpusIndexError, match="corrompido"):
        load_corpus_index(tmp_path)
    assert len(encoded_batches) == 1
    assert not prepare_corpus_index(repository, tmp_path, rebuild=True).reused


def test_failed_rebuild_keeps_previous_index(
    repository, tmp_path, encoded_batches, monkeypatch
):
    first = prepare_corpus_index(repository, tmp_path)
    pointer = (tmp_path / "current.json").read_bytes()

    def fail(texts):
        raise semantic_similarity.EmbeddingGenerationError("encoder unavailable")

    monkeypatch.setattr(semantic_similarity, "generate_embeddings", fail)
    with pytest.raises(semantic_similarity.EmbeddingGenerationError):
        prepare_corpus_index(repository, tmp_path, rebuild=True)
    assert (tmp_path / "current.json").read_bytes() == pointer
    assert first.directory.exists()
    assert not list(tmp_path.glob(".building-*"))
    assert load_corpus_index(tmp_path).semantic.shape == (3, 3)


def test_invalid_embeddings_are_not_published(
    repository, tmp_path, encoded_batches, monkeypatch
):
    monkeypatch.setattr(
        semantic_similarity, "generate_embeddings",
        lambda texts: np.zeros((len(texts), 3), dtype=np.float32),
    )
    with pytest.raises(CorpusIndexError, match="embeddings invalidos"):
        prepare_corpus_index(repository, tmp_path)
    assert not (tmp_path / "current.json").exists()


def test_empty_reference_database_is_rejected(tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with pytest.raises(CorpusIndexError, match="Importe documentos"):
            prepare_corpus_index(ReferenceRepository(db), tmp_path)
    engine.dispose()


def test_invalid_generation_path_is_rejected(tmp_path):
    (tmp_path / "current.json").write_text(
        json.dumps({"generation": "..\\somewhere"}), encoding="utf-8"
    )
    with pytest.raises(CorpusIndexError, match="Ponteiro"):
        load_corpus_index(tmp_path)


def test_batch_size_must_be_positive(repository, tmp_path):
    with pytest.raises(ValueError, match="batch_size"):
        prepare_corpus_index(repository, tmp_path, batch_size=0)


def test_fingerprint_can_capture_signatures_without_changing_existing_identity(repository):
    previous = reference_fingerprint(repository)
    signatures = {}
    captured = reference_fingerprint(repository, on_segment=signatures.__setitem__)

    assert captured == previous
    assert signatures == {
        segment.id: reference_segment_signature(segment)
        for segment in repository.iter_segments()
    }


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0.0, 2.0])
def test_invalid_semantic_vectors_are_rejected_even_with_matching_hashes(
    repository, tmp_path, encoded_batches, refresh_artifact_hash, value,
):
    preparation = prepare_corpus_index(repository, tmp_path)
    filename = "semantic.npy"
    vectors = np.load(preparation.directory / filename)
    vectors[0] = value
    np.save(preparation.directory / filename, vectors, allow_pickle=False)
    refresh_artifact_hash(preparation.directory, filename)

    with pytest.raises(CorpusIndexError, match="Embeddings"):
        load_corpus_index(tmp_path)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 2.0])
def test_invalid_lexical_vectors_are_rejected_even_with_matching_hashes(
    repository, tmp_path, encoded_batches, refresh_artifact_hash, value,
):
    preparation = prepare_corpus_index(repository, tmp_path)
    filename = "lexical.npz"
    matrix = sparse.load_npz(preparation.directory / filename).tocsr()
    matrix.data[0] = value
    sparse.save_npz(preparation.directory / filename, matrix)
    refresh_artifact_hash(preparation.directory, filename)

    with pytest.raises(CorpusIndexError, match="lexicais"):
        load_corpus_index(tmp_path)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0.0, -0.1])
def test_invalid_idf_values_are_rejected(
    repository, tmp_path, encoded_batches, refresh_artifact_hash, value,
):
    preparation = prepare_corpus_index(repository, tmp_path)
    filename = "idf.npy"
    idf = np.load(preparation.directory / filename)
    idf[0] = value
    np.save(preparation.directory / filename, idf, allow_pickle=False)
    refresh_artifact_hash(preparation.directory, filename)

    with pytest.raises(CorpusIndexError, match="invalidos"):
        load_corpus_index(tmp_path)


def test_malformed_pointer_reports_the_file(tmp_path):
    (tmp_path / "current.json").write_text("{invalid", encoding="utf-8")
    with pytest.raises(CorpusIndexError, match="current.json"):
        load_corpus_index(tmp_path)


def test_missing_pointer_reports_the_file(tmp_path):
    with pytest.raises(CorpusIndexError, match="current.json"):
        load_corpus_index(tmp_path)
