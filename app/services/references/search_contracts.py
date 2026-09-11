from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import settings

SearchMode = Literal["semantic", "lexical"]


def _validate_threshold(name: str, value: float, minimum: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} deve ser um numero.")
    if not minimum <= value <= 1.0 or not math.isfinite(value):
        raise ValueError(f"{name} deve ser finito e estar entre {minimum} e 1.0.")


@dataclass(frozen=True, slots=True)
class ReferenceSearchOptions:
    mode: SearchMode = field(default_factory=lambda: settings.reference_search_mode)
    top_n: int = field(default_factory=lambda: settings.reference_search_top_n)
    lexical_cosine_threshold: float = field(
        default_factory=lambda: settings.lexical_cosine_threshold
    )
    lexical_jaccard_threshold: float = field(
        default_factory=lambda: settings.lexical_jaccard_threshold
    )
    semantic_threshold: float = field(
        default_factory=lambda: settings.reference_search_semantic_threshold
    )

    @classmethod
    def from_overrides(
        cls,
        *,
        mode: SearchMode | None = None,
        top_n: int | None = None,
        lexical_cosine_threshold: float | None = None,
        lexical_jaccard_threshold: float | None = None,
        semantic_threshold: float | None = None,
    ) -> ReferenceSearchOptions:
        return cls(
            mode=settings.reference_search_mode if mode is None else mode,
            top_n=settings.reference_search_top_n if top_n is None else top_n,
            lexical_cosine_threshold=(
                settings.lexical_cosine_threshold
                if lexical_cosine_threshold is None else lexical_cosine_threshold
            ),
            lexical_jaccard_threshold=(
                settings.lexical_jaccard_threshold
                if lexical_jaccard_threshold is None else lexical_jaccard_threshold
            ),
            semantic_threshold=(
                settings.reference_search_semantic_threshold
                if semantic_threshold is None else semantic_threshold
            ),
        )

    def __post_init__(self) -> None:
        if not isinstance(self.mode, str):
            raise TypeError("mode deve ser uma string.")
        if self.mode not in ("semantic", "lexical"):
            raise ValueError("mode deve ser 'semantic' ou 'lexical'.")
        if type(self.top_n) is not int:
            raise TypeError("top_n deve ser um inteiro positivo.")
        if self.top_n < 1:
            raise ValueError("top_n deve ser um inteiro positivo.")
        _validate_threshold("lexical_cosine_threshold", self.lexical_cosine_threshold, 0.0)
        _validate_threshold("lexical_jaccard_threshold", self.lexical_jaccard_threshold, 0.0)
        _validate_threshold("semantic_threshold", self.semantic_threshold, -1.0)


@dataclass(frozen=True, slots=True)
class ReferenceDocumentMatch:
    id: int
    corpus_id: str
    source: str
    language: str
    title: str


@dataclass(frozen=True, slots=True)
class ReferenceSegmentMatch:
    id: int
    position: int
    start_offset: int
    end_offset: int
    text_original: str


@dataclass(frozen=True, slots=True)
class ReferenceMatch:
    source_document: ReferenceDocumentMatch
    source_segment: ReferenceSegmentMatch
    lexical_score: float
    semantic_score: float
    jaccard_score: float


@dataclass(frozen=True, slots=True)
class ReferenceSearchResult:
    options: ReferenceSearchOptions
    index_fingerprint: str
    matches: tuple[ReferenceMatch, ...]
    comparison_ms: float
