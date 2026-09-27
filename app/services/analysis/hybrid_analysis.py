from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.models.analysis import Document, Segment
from app.repositories.analysis import SegmentRepository
from app.repositories.references import ReferenceRepository
from app.services.analysis.hybrid_contracts import (
    DocumentAnalysis,
    HybridAnalysisOptions,
    HybridMatch,
    SegmentAnalysis,
    SimilarityClassification,
)
from app.services.references.reference_search import ReferenceSearchService
from app.services.references.search_contracts import (
    ReferenceDocumentMatch,
    ReferenceMatch,
    ReferenceSearchResult,
    ReferenceSegmentMatch,
    SearchMode,
)


class _ReferenceSearcher(Protocol):
    def search(
        self, text_original: str, *, mode: SearchMode
    ) -> ReferenceSearchResult: ...


class _SegmentReader(Protocol):
    def list_by_document(self, document_id: int) -> list[Segment]: ...


def _clamp_score(score: float) -> float:
    return min(max(float(score), 0.0), 1.0)


class HybridScoreCalculator:
    def __init__(self, options: HybridAnalysisOptions | None = None):
        self.options = options or HybridAnalysisOptions()

    def lexical_score(self, tfidf_score: float, jaccard_score: float) -> float:
        return _clamp_score(
            self.options.tfidf_weight * _clamp_score(tfidf_score)
            + self.options.jaccard_weight * _clamp_score(jaccard_score)
        )

    def final_score(self, lexical_score: float, semantic_score: float) -> float:
        return _clamp_score(
            self.options.lexical_weight * _clamp_score(lexical_score)
            + self.options.semantic_weight * _clamp_score(semantic_score)
        )

    def classify(self, score: float) -> SimilarityClassification:
        score = _clamp_score(score)
        if score >= self.options.very_high_threshold:
            return SimilarityClassification.VERY_HIGH
        if score >= self.options.high_threshold:
            return SimilarityClassification.HIGH
        if score >= self.options.moderate_threshold:
            return SimilarityClassification.MODERATE
        return SimilarityClassification.LOW

    def is_suspicious(
        self,
        *,
        tfidf_score: float,
        jaccard_score: float,
        semantic_score: float,
        final_score: float,
    ) -> bool:
        return (
            final_score >= self.options.suspicious_final_threshold
            or semantic_score >= self.options.suspicious_semantic_threshold
            or (
                tfidf_score >= self.options.suspicious_tfidf_threshold
                and jaccard_score >= self.options.suspicious_jaccard_threshold
            )
        )


@dataclass(frozen=True, slots=True)
class _MergedCandidate:
    reference_document: ReferenceDocumentMatch
    reference_segment: ReferenceSegmentMatch
    tfidf_score: float
    jaccard_score: float
    semantic_score: float


@dataclass(frozen=True, slots=True)
class _SegmentExecution:
    analysis: SegmentAnalysis
    lexical_ms: float
    semantic_ms: float
    reference_fingerprint: str


def _merge_candidates(
    result_groups: Iterable[Iterable[ReferenceMatch]],
) -> tuple[_MergedCandidate, ...]:
    """Une resultados pelo ID da referencia, mantendo uma metrica por par."""
    merged: dict[int, _MergedCandidate] = {}
    for matches in result_groups:
        for match in matches:
            reference_id = match.source_segment.id
            current = merged.get(reference_id)
            if current is None:
                merged[reference_id] = _MergedCandidate(
                    reference_document=match.source_document,
                    reference_segment=match.source_segment,
                    tfidf_score=match.lexical_score,
                    jaccard_score=match.jaccard_score,
                    semantic_score=match.semantic_score,
                )
                continue
            merged[reference_id] = _MergedCandidate(
                reference_document=current.reference_document,
                reference_segment=current.reference_segment,
                tfidf_score=max(current.tfidf_score, match.lexical_score),
                jaccard_score=max(current.jaccard_score, match.jaccard_score),
                semantic_score=max(current.semantic_score, match.semantic_score),
            )
    return tuple(merged.values())


class HybridAnalysisService:
    """Orquestra a analise hibrida em memoria, sem persistir resultados."""

    def __init__(
        self,
        db: Session | None = None,
        *,
        reference_search: _ReferenceSearcher | None = None,
        segment_repository: _SegmentReader | None = None,
        options: HybridAnalysisOptions | None = None,
    ):
        if reference_search is None or segment_repository is None:
            if db is None:
                raise ValueError(
                    "db e obrigatorio quando as dependencias nao sao fornecidas."
                )
            reference_search = reference_search or ReferenceSearchService(
                ReferenceRepository(db)
            )
            segment_repository = segment_repository or SegmentRepository(db)
        self.reference_search = reference_search
        self.segment_repository = segment_repository
        self.options = options or HybridAnalysisOptions()
        self.score_calculator = HybridScoreCalculator(self.options)

    def analyze_document(self, document: Document) -> DocumentAnalysis:
        if document.id is None:
            raise ValueError("O documento deve estar persistido antes da analise.")
        segments = self.segment_repository.list_by_document(document.id)
        executions = tuple(self._analyze_segment(segment) for segment in segments)
        analyses = tuple(execution.analysis for execution in executions)
        suspicious_segments = sum(analysis.is_suspicious for analysis in analyses)
        total_segments = len(analyses)
        overall_score = (
            sum(analysis.segment_score for analysis in analyses) / total_segments
            if total_segments
            else 0.0
        )
        suspicious_percentage = (
            suspicious_segments / total_segments if total_segments else 0.0
        )
        return DocumentAnalysis(
            document_id=document.id,
            total_segments=total_segments,
            analyzed_segments=total_segments,
            suspicious_segments=suspicious_segments,
            segments=analyses,
            overall_score=_clamp_score(overall_score),
            suspicious_segment_percentage=_clamp_score(suspicious_percentage),
            lexical_ms=round(sum(execution.lexical_ms for execution in executions)),
            semantic_ms=round(sum(execution.semantic_ms for execution in executions)),
            reference_fingerprint=(
                executions[0].reference_fingerprint if executions else None
            ),
        )

    def _analyze_segment(self, segment: Segment) -> _SegmentExecution:
        lexical_result = self.reference_search.search(
            segment.text_original, mode="lexical"
        )
        semantic_result = self.reference_search.search(
            segment.text_original, mode="semantic"
        )
        if lexical_result.index_fingerprint != semantic_result.index_fingerprint:
            raise RuntimeError("O indice de referencia mudou durante a analise.")
        candidates = _merge_candidates(
            (lexical_result.matches, semantic_result.matches)
        )
        matches = sorted(
            (self._build_match(candidate) for candidate in candidates),
            key=lambda match: (
                -match.final_score,
                -match.semantic_score,
                match.reference_segment.id,
            ),
        )[: self.options.top_n]
        best_match = matches[0] if matches else None
        segment_score = best_match.final_score if best_match else 0.0
        return _SegmentExecution(
            analysis=SegmentAnalysis(
                segment_id=segment.id,
                text=segment.text_original,
                matches=tuple(matches),
                best_match=best_match,
                segment_score=segment_score,
                classification=self.score_calculator.classify(segment_score),
                is_suspicious=any(match.is_suspicious for match in matches),
            ),
            lexical_ms=lexical_result.comparison_ms,
            semantic_ms=semantic_result.comparison_ms,
            reference_fingerprint=lexical_result.index_fingerprint,
        )

    def _build_match(self, candidate: _MergedCandidate) -> HybridMatch:
        tfidf_score = _clamp_score(candidate.tfidf_score)
        jaccard_score = _clamp_score(candidate.jaccard_score)
        semantic_score = _clamp_score(candidate.semantic_score)
        lexical_score = self.score_calculator.lexical_score(
            tfidf_score, jaccard_score
        )
        final_score = self.score_calculator.final_score(
            lexical_score, semantic_score
        )
        return HybridMatch(
            reference_document=candidate.reference_document,
            reference_segment=candidate.reference_segment,
            tfidf_score=tfidf_score,
            jaccard_score=jaccard_score,
            semantic_score=semantic_score,
            lexical_score=lexical_score,
            final_score=final_score,
            classification=self.score_calculator.classify(final_score),
            is_suspicious=self.score_calculator.is_suspicious(
                tfidf_score=tfidf_score,
                jaccard_score=jaccard_score,
                semantic_score=semantic_score,
                final_score=final_score,
            ),
        )
