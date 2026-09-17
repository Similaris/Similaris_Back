from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from app.core.config import settings
from app.services.references.search_contracts import (
    ReferenceDocumentMatch,
    ReferenceSegmentMatch,
)


class SimilarityClassification(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


def _validate_unit_interval(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} deve ser um numero.")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} deve ser finito e estar entre 0.0 e 1.0.")


@dataclass(frozen=True, slots=True)
class HybridAnalysisOptions:
    """Politica configuravel de pontuacao e classificacao hibrida."""

    tfidf_weight: float = field(default_factory=lambda: settings.hybrid_tfidf_weight)
    jaccard_weight: float = field(
        default_factory=lambda: settings.hybrid_jaccard_weight
    )
    lexical_weight: float = field(
        default_factory=lambda: settings.hybrid_lexical_weight
    )
    semantic_weight: float = field(
        default_factory=lambda: settings.hybrid_semantic_weight
    )
    moderate_threshold: float = field(
        default_factory=lambda: settings.hybrid_classification_moderate_threshold
    )
    high_threshold: float = field(
        default_factory=lambda: settings.hybrid_classification_high_threshold
    )
    very_high_threshold: float = field(
        default_factory=lambda: settings.hybrid_classification_very_high_threshold
    )
    suspicious_final_threshold: float = field(
        default_factory=lambda: settings.hybrid_suspicious_final_threshold
    )
    suspicious_semantic_threshold: float = field(
        default_factory=lambda: settings.hybrid_suspicious_semantic_threshold
    )
    suspicious_tfidf_threshold: float = field(
        default_factory=lambda: settings.hybrid_suspicious_tfidf_threshold
    )
    suspicious_jaccard_threshold: float = field(
        default_factory=lambda: settings.hybrid_suspicious_jaccard_threshold
    )
    top_n: int = field(default_factory=lambda: settings.hybrid_top_n)

    def __post_init__(self) -> None:
        unit_values = {
            "tfidf_weight": self.tfidf_weight,
            "jaccard_weight": self.jaccard_weight,
            "lexical_weight": self.lexical_weight,
            "semantic_weight": self.semantic_weight,
            "moderate_threshold": self.moderate_threshold,
            "high_threshold": self.high_threshold,
            "very_high_threshold": self.very_high_threshold,
            "suspicious_final_threshold": self.suspicious_final_threshold,
            "suspicious_semantic_threshold": self.suspicious_semantic_threshold,
            "suspicious_tfidf_threshold": self.suspicious_tfidf_threshold,
            "suspicious_jaccard_threshold": self.suspicious_jaccard_threshold,
        }
        for name, value in unit_values.items():
            _validate_unit_interval(name, value)
        if not math.isclose(self.tfidf_weight + self.jaccard_weight, 1.0):
            raise ValueError("Os pesos de TF-IDF e Jaccard devem somar 1.0.")
        if not math.isclose(self.lexical_weight + self.semantic_weight, 1.0):
            raise ValueError("Os pesos lexical e semantico devem somar 1.0.")
        if not (
            self.moderate_threshold
            <= self.high_threshold
            <= self.very_high_threshold
        ):
            raise ValueError("Os thresholds de classificacao devem ser crescentes.")
        if type(self.top_n) is not int or self.top_n < 1:
            raise ValueError("top_n deve ser um inteiro positivo.")


@dataclass(frozen=True, slots=True)
class HybridMatch:
    reference_document: ReferenceDocumentMatch
    reference_segment: ReferenceSegmentMatch
    tfidf_score: float
    jaccard_score: float
    semantic_score: float
    lexical_score: float
    final_score: float
    classification: SimilarityClassification
    is_suspicious: bool


@dataclass(frozen=True, slots=True)
class SegmentAnalysis:
    segment_id: int
    text: str
    matches: tuple[HybridMatch, ...]
    best_match: HybridMatch | None
    segment_score: float
    classification: SimilarityClassification
    is_suspicious: bool


@dataclass(frozen=True, slots=True)
class DocumentAnalysis:
    document_id: int
    total_segments: int
    analyzed_segments: int
    suspicious_segments: int
    segments: tuple[SegmentAnalysis, ...]
    overall_score: float
    suspicious_segment_percentage: float
    lexical_ms: int = 0
    semantic_ms: int = 0
