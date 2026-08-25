from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings
from app.services.analysis.text_preprocessing import preprocess_text, preprocess_tokens


@dataclass(frozen=True, slots=True)
class LexicalSimilarityResult:
    """Resultado da comparação lexical entre dois textos."""

    cosine: float
    jaccard: float
    cosine_threshold: float
    jaccard_threshold: float
    exceeds_cosine: bool
    exceeds_jaccard: bool
    is_suspicious: bool


def _clamp_score(score: float) -> float:
    return round(min(max(score, 0.0), 1.0), 4)


def compute_cosine_similarity(text_a: str, text_b: str) -> float:
    """Calcula a similaridade do cosseno entre dois textos via TF-IDF.

    Os textos passam pelo pré-processamento lexical antes da vetorização.
    Textos sem tokens relevantes resultam em similaridade 0.0.
    """
    clean_a = preprocess_text(text_a)
    clean_b = preprocess_text(text_b)
    if not clean_a or not clean_b:
        return 0.0

    vectorizer = TfidfVectorizer(analyzer=str.split)
    tfidf_matrix = vectorizer.fit_transform([clean_a, clean_b])
    return _clamp_score(float(cosine_similarity(tfidf_matrix)[0, 1]))


def compute_jaccard_similarity(text_a: str, text_b: str) -> float:
    """Calcula o coeficiente de Jaccard entre os conjuntos de tokens.

    Os textos passam pelo pré-processamento lexical antes da comparação.
    Textos sem tokens relevantes resultam em similaridade 0.0.
    """
    tokens_a = set(preprocess_tokens(text_a))
    tokens_b = set(preprocess_tokens(text_b))
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return _clamp_score(len(intersection) / len(union))


def compare_texts(
    text_a: str,
    text_b: str,
    cosine_threshold: float | None = None,
    jaccard_threshold: float | None = None,
) -> LexicalSimilarityResult:
    """Compara dois textos e aplica os limiares de plágio literal.

    Segue a abordagem híbrida de AL-JIBORY e AL-TAMIMI (2021): Jaccard
    atua como filtro rápido (limiar 0.2) e o cosseno TF-IDF confirma a
    suspeita (limiar 0.5). O texto é considerado suspeito de plágio
    literal quando ambos os limiares são atingidos. Os limiares padrão
    vêm das configurações e podem ser sobrescritos por parâmetro.
    """
    resolved_cosine_threshold = (
        settings.lexical_cosine_threshold
        if cosine_threshold is None
        else cosine_threshold
    )
    resolved_jaccard_threshold = (
        settings.lexical_jaccard_threshold
        if jaccard_threshold is None
        else jaccard_threshold
    )

    cosine = compute_cosine_similarity(text_a, text_b)
    jaccard = compute_jaccard_similarity(text_a, text_b)
    exceeds_cosine = cosine >= resolved_cosine_threshold
    exceeds_jaccard = jaccard >= resolved_jaccard_threshold

    return LexicalSimilarityResult(
        cosine=cosine,
        jaccard=jaccard,
        cosine_threshold=resolved_cosine_threshold,
        jaccard_threshold=resolved_jaccard_threshold,
        exceeds_cosine=exceeds_cosine,
        exceeds_jaccard=exceeds_jaccard,
        is_suspicious=exceeds_cosine and exceeds_jaccard,
    )
