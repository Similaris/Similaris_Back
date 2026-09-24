from __future__ import annotations

from pydantic import BaseModel

from app.models.analysis import Document
from app.services.analysis.hybrid_contracts import (
    DocumentAnalysis,
    HybridMatch,
    SegmentAnalysis,
    SimilarityClassification,
)


class ReferenceDocumentOut(BaseModel):
    id: int
    corpus_id: str
    source: str
    language: str
    title: str


class ReferenceSegmentOut(BaseModel):
    id: int
    position: int
    start_offset: int
    end_offset: int
    text_original: str


class HybridMatchOut(BaseModel):
    reference_document: ReferenceDocumentOut
    reference_segment: ReferenceSegmentOut
    tfidf_score: float
    jaccard_score: float
    semantic_score: float
    lexical_score: float
    final_score: float
    classification: SimilarityClassification
    is_suspicious: bool

    @classmethod
    def from_match(cls, match: HybridMatch) -> HybridMatchOut:
        return cls(
            reference_document=ReferenceDocumentOut(
                id=match.reference_document.id,
                corpus_id=match.reference_document.corpus_id,
                source=match.reference_document.source,
                language=match.reference_document.language,
                title=match.reference_document.title,
            ),
            reference_segment=ReferenceSegmentOut(
                id=match.reference_segment.id,
                position=match.reference_segment.position,
                start_offset=match.reference_segment.start_offset,
                end_offset=match.reference_segment.end_offset,
                text_original=match.reference_segment.text_original,
            ),
            tfidf_score=match.tfidf_score,
            jaccard_score=match.jaccard_score,
            semantic_score=match.semantic_score,
            lexical_score=match.lexical_score,
            final_score=match.final_score,
            classification=match.classification,
            is_suspicious=match.is_suspicious,
        )


class SegmentAnalysisOut(BaseModel):
    segment_id: int
    text: str
    matches: list[HybridMatchOut]
    best_match: HybridMatchOut | None
    segment_score: float
    classification: SimilarityClassification
    is_suspicious: bool

    @classmethod
    def from_analysis(cls, analysis: SegmentAnalysis) -> SegmentAnalysisOut:
        matches = [HybridMatchOut.from_match(match) for match in analysis.matches]
        return cls(
            segment_id=analysis.segment_id,
            text=analysis.text,
            matches=matches,
            best_match=(
                HybridMatchOut.from_match(analysis.best_match)
                if analysis.best_match else None
            ),
            segment_score=analysis.segment_score,
            classification=analysis.classification,
            is_suspicious=analysis.is_suspicious,
        )


class DocumentAnalysisOut(BaseModel):
    document_id: int
    filename: str
    status: str
    error_message: str | None
    total_segments: int
    analyzed_segments: int
    suspicious_segments: int
    overall_score: float
    suspicious_segment_percentage: float
    extraction_ms: int | None
    lexical_ms: int
    semantic_ms: int
    analysis_profile: dict | None
    reference_fingerprint: str | None
    segments: list[SegmentAnalysisOut]

    @classmethod
    def from_analysis(
        cls, document: Document, analysis: DocumentAnalysis
    ) -> DocumentAnalysisOut:
        return cls(
            document_id=document.id,
            filename=document.filename,
            status=document.status,
            error_message=document.error_message,
            total_segments=analysis.total_segments,
            analyzed_segments=analysis.analyzed_segments,
            suspicious_segments=analysis.suspicious_segments,
            overall_score=analysis.overall_score,
            suspicious_segment_percentage=analysis.suspicious_segment_percentage,
            extraction_ms=document.extraction_ms,
            lexical_ms=analysis.lexical_ms,
            semantic_ms=analysis.semantic_ms,
            analysis_profile=document.analysis_profile,
            reference_fingerprint=document.reference_fingerprint,
            segments=[
                SegmentAnalysisOut.from_analysis(segment)
                for segment in analysis.segments
            ],
        )


class BatchAnalysisOut(BaseModel):
    batch_id: int
    status: str
    documents: list[DocumentAnalysisOut]
