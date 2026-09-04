from unittest.mock import Mock

import numpy as np
import pytest

from app.services.analysis import semantic_similarity
from app.services.analysis.semantic_similarity import (
    compare_embeddings,
    compare_semantic,
    generate_embedding,
    generate_embeddings,
)

BASE_TEXT = "The student submitted the final assignment."
SIMPLE_PARAPHRASE = "The learner delivered the completed coursework."
EXTENDED_PARAPHRASE = (
    "After finishing the required coursework, the learner handed it in for grading."
)
UNRELATED_TEXT = "Volcanoes release magma from beneath the Earth's crust."


@pytest.fixture(scope="module")
def semantic_scores() -> dict[str, float]:
    return {
        "identical": compare_semantic(BASE_TEXT, BASE_TEXT),
        "simple_paraphrase": compare_semantic(BASE_TEXT, SIMPLE_PARAPHRASE),
        "extended_paraphrase": compare_semantic(BASE_TEXT, EXTENDED_PARAPHRASE),
        "unrelated": compare_semantic(BASE_TEXT, UNRELATED_TEXT),
    }


def test_identical_texts_have_very_high_similarity(
    semantic_scores: dict[str, float],
):
    assert semantic_scores["identical"] > 0.99


def test_simple_paraphrase_is_more_similar_than_unrelated_text(
    semantic_scores: dict[str, float],
):
    assert semantic_scores["simple_paraphrase"] > semantic_scores["unrelated"]


def test_paraphrase_with_larger_changes_preserves_semantic_relation(
    semantic_scores: dict[str, float],
):
    assert semantic_scores["extended_paraphrase"] > semantic_scores["unrelated"]


def test_unrelated_text_has_considerably_lower_similarity(
    semantic_scores: dict[str, float],
):
    assert (
        semantic_scores["simple_paraphrase"] - semantic_scores["unrelated"]
        > 0.2
    )


def test_generate_embedding_returns_one_vector():
    embedding = generate_embedding(BASE_TEXT)

    assert embedding.ndim == 1
    assert embedding.size > 0


def test_generate_embeddings_processes_all_texts_in_one_batch(monkeypatch):
    model = Mock()
    model.encode.return_value = np.ones((3, 4), dtype=np.float32)
    monkeypatch.setattr(semantic_similarity, "get_model", lambda: model)
    texts = ["text one", "text two", "text three"]

    embeddings = generate_embeddings(texts)

    assert embeddings.shape == (3, 4)
    model.encode.assert_called_once_with(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )


def test_compare_embeddings_accepts_precomputed_embeddings():
    same_direction = compare_embeddings([1.0, 0.0], np.array([2.0, 0.0]))
    orthogonal = compare_embeddings([1.0, 0.0], [0.0, 1.0])

    assert same_direction == pytest.approx(1.0)
    assert orthogonal == pytest.approx(0.0)


@pytest.mark.parametrize("text", ["", "   "])
def test_generate_embedding_rejects_empty_text(text: str, monkeypatch):
    model_loader = Mock(side_effect=AssertionError("modelo não deveria ser carregado"))
    monkeypatch.setattr(semantic_similarity, "get_model", model_loader)

    with pytest.raises(ValueError, match="não pode ser vazio"):
        generate_embedding(text)

    model_loader.assert_not_called()


def test_generate_embeddings_rejects_empty_list(monkeypatch):
    model_loader = Mock(side_effect=AssertionError("modelo não deveria ser carregado"))
    monkeypatch.setattr(semantic_similarity, "get_model", model_loader)

    with pytest.raises(ValueError, match="lista vazia"):
        generate_embeddings([])

    model_loader.assert_not_called()


def test_generate_embeddings_identifies_invalid_item(monkeypatch):
    model_loader = Mock(side_effect=AssertionError("modelo não deveria ser carregado"))
    monkeypatch.setattr(semantic_similarity, "get_model", model_loader)

    with pytest.raises(ValueError, match=r"texts\[1\]"):
        generate_embeddings(["valid text", "  "])

    model_loader.assert_not_called()


def test_get_model_reuses_a_single_instance(monkeypatch):
    model = Mock()
    model_factory = Mock(return_value=model)
    semantic_similarity._load_model.cache_clear()
    monkeypatch.setattr(semantic_similarity, "SentenceTransformer", model_factory)

    try:
        first = semantic_similarity.get_model()
        second = semantic_similarity.get_model()
    finally:
        semantic_similarity._load_model.cache_clear()

    assert first is second
    model_factory.assert_called_once_with(
        semantic_similarity.settings.semantic_model_name
    )
