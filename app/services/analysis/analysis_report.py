from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.analysis import AnalysisResult, Document
from app.repositories.analysis import AnalysisResultRepository, SegmentRepository
from app.services.analysis.hybrid_analysis import HybridScoreCalculator
from app.services.analysis.hybrid_contracts import (
    DocumentAnalysis,
    HybridMatch,
    SegmentAnalysis,
    SimilarityClassification,
)
from app.services.references.search_contracts import (
    ReferenceDocumentMatch,
    ReferenceSegmentMatch,
)


class AnalysisReportService:
    """Reconstrói o contrato público a partir dos resultados persistidos."""

    def __init__(
        self,
        db: Session,
        segment_repository: SegmentRepository | None = None,
        result_repository: AnalysisResultRepository | None = None,
    ):
        self.segment_repository = segment_repository or SegmentRepository(db)
        self.result_repository = result_repository or AnalysisResultRepository(db)
        self.score_calculator = HybridScoreCalculator()

    def build_document_analysis(self, document: Document) -> DocumentAnalysis:
        segments = self.segment_repository.list_by_document(document.id)
        stored_results = self.result_repository.list_by_document(document.id)
        by_segment: dict[int, list[AnalysisResult]] = defaultdict(list)
        for result in stored_results:
            by_segment[result.segment_id].append(result)

        analyses = tuple(
            self._segment_analysis(segment.id, segment.text_original, by_segment[segment.id])
            for segment in segments
        )
        total_segments = len(analyses)
        suspicious_segments = sum(analysis.is_suspicious for analysis in analyses)
        overall_score = (
            sum(analysis.segment_score for analysis in analyses) / total_segments
            if total_segments
            else 0.0
        )
        suspicious_percentage = (
            suspicious_segments / total_segments if total_segments else 0.0
        )
        analyzed_segments = (
            total_segments if document.status == "concluido" else len(by_segment)
        )
        return DocumentAnalysis(
            document_id=document.id,
            total_segments=total_segments,
            analyzed_segments=analyzed_segments,
            suspicious_segments=suspicious_segments,
            segments=analyses,
            overall_score=overall_score,
            suspicious_segment_percentage=suspicious_percentage,
            lexical_ms=document.lexical_ms or 0,
            semantic_ms=document.semantic_ms or 0,
            reference_fingerprint=document.reference_fingerprint,
        )

    def _segment_analysis(
        self, segment_id: int, text: str, results: list[AnalysisResult]
    ) -> SegmentAnalysis:
        matches = tuple(self._match(result) for result in results)
        best_match = matches[0] if matches else None
        segment_score = best_match.final_score if best_match else 0.0
        return SegmentAnalysis(
            segment_id=segment_id,
            text=text,
            matches=matches,
            best_match=best_match,
            segment_score=segment_score,
            classification=(
                best_match.classification
                if best_match else SimilarityClassification.LOW
            ),
            is_suspicious=any(result.is_suspicious for result in results),
        )

    def _match(self, result: AnalysisResult) -> HybridMatch:
        reference_segment = result.reference_segment
        reference_document = reference_segment.reference_document
        tfidf_score = float(result.lexical_cosine or 0)
        jaccard_score = float(result.lexical_jaccard or 0)
        semantic_score = float(result.semantic_cosine or 0)
        lexical_score = (
            float(result.lexical_score)
            if result.lexical_score is not None
            else self.score_calculator.lexical_score(tfidf_score, jaccard_score)
        )
        final_score = float(result.final_score)
        try:
            classification = SimilarityClassification(result.plagiarism_type)
        except ValueError:
            classification = self.score_calculator.classify(final_score)
        return HybridMatch(
            reference_document=ReferenceDocumentMatch(
                id=reference_document.id,
                corpus_id=reference_document.corpus_id or str(reference_document.id),
                source=reference_document.source,
                language=reference_document.language,
                title=reference_document.title,
            ),
            reference_segment=ReferenceSegmentMatch(
                id=reference_segment.id,
                position=reference_segment.position,
                start_offset=reference_segment.start_offset or 0,
                end_offset=reference_segment.end_offset or 0,
                text_original=reference_segment.text_original,
            ),
            tfidf_score=tfidf_score,
            jaccard_score=jaccard_score,
            semantic_score=semantic_score,
            lexical_score=lexical_score,
            final_score=final_score,
            classification=classification,
            is_suspicious=result.is_suspicious,
        )
