from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

import numpy as np
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer, util

from app.core.config import settings

Embedding = NDArray[np.float32]
EmbeddingMatrix = NDArray[np.float32]
EmbeddingInput = Embedding | Sequence[float]


class SemanticSimilarityError(RuntimeError):
    """Erro base do motor de similaridade semântica."""


class SemanticModelLoadError(SemanticSimilarityError):
    """Indica que o modelo semântico não pôde ser carregado."""


class EmbeddingGenerationError(SemanticSimilarityError):
    """Indica que o modelo não pôde gerar os embeddings solicitados."""


@lru_cache(maxsize=1)
def _load_model(model_name: str) -> SentenceTransformer:
    try:
        return SentenceTransformer(model_name)
    except Exception as exc:
        raise SemanticModelLoadError(
            f"Não foi possível carregar o modelo semântico '{model_name}'."
        ) from exc


def get_model() -> SentenceTransformer:
    """Retorna a instância reutilizável do modelo SBERT configurado."""
    return _load_model(settings.semantic_model_name)


def _validate_text(text: str, field_name: str) -> None:
    if not isinstance(text, str):
        raise TypeError(f"{field_name} deve ser uma string")
    if not text.strip():
        raise ValueError(f"{field_name} não pode ser vazio")


def generate_embedding(text: str) -> Embedding:
    """Gera o embedding normalizado de um texto original."""
    _validate_text(text, "text")

    try:
        embedding = get_model().encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except SemanticSimilarityError:
        raise
    except Exception as exc:
        raise EmbeddingGenerationError(
            "Não foi possível gerar o embedding do texto."
        ) from exc

    return np.asarray(embedding, dtype=np.float32)


def generate_embeddings(texts: list[str]) -> EmbeddingMatrix:
    """Gera embeddings normalizados em lote para textos originais."""
    if not isinstance(texts, list):
        raise TypeError("texts deve ser uma lista de strings")
    if not texts:
        raise ValueError("texts não pode ser uma lista vazia")
    for index, text in enumerate(texts):
        _validate_text(text, f"texts[{index}]")

    try:
        embeddings = get_model().encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except SemanticSimilarityError:
        raise
    except Exception as exc:
        raise EmbeddingGenerationError(
            "Não foi possível gerar os embeddings dos textos."
        ) from exc

    return np.asarray(embeddings, dtype=np.float32)


def _validate_embedding(
    embedding: EmbeddingInput,
    field_name: str,
) -> Embedding:
    try:
        array = np.asarray(embedding, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} deve conter apenas números") from exc

    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{field_name} deve ser um vetor unidimensional não vazio")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{field_name} deve conter apenas valores finitos")
    if not np.any(array):
        raise ValueError(f"{field_name} não pode ser um vetor nulo")
    return array


def compare_embeddings(
    embedding_a: EmbeddingInput,
    embedding_b: EmbeddingInput,
) -> float:
    """Calcula a similaridade de cosseno entre dois embeddings existentes."""
    validated_a = _validate_embedding(embedding_a, "embedding_a")
    validated_b = _validate_embedding(embedding_b, "embedding_b")
    if validated_a.shape != validated_b.shape:
        raise ValueError("os embeddings devem possuir a mesma dimensão")

    score = float(util.cos_sim(validated_a, validated_b).item())
    return min(max(score, -1.0), 1.0)


def compare_semantic(text_a: str, text_b: str) -> float:
    """Calcula a similaridade semântica entre dois textos originais."""
    _validate_text(text_a, "text_a")
    _validate_text(text_b, "text_b")
    embeddings = generate_embeddings([text_a, text_b])
    return compare_embeddings(embeddings[0], embeddings[1])
