from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models.analysis import AnalysisResult
from app.models.references import ReferenceSegment

if TYPE_CHECKING:
    from app.services.analysis.hybrid_contracts import DocumentAnalysis


def _decimal_score(value: float) -> Decimal:
    return Decimal(str(round(value, 4)))


class AnalysisResultRepository:
    def __init__(self, db: Session):
        self.db = db

    def replace_for_document(
        self, document_id: int, analysis: DocumentAnalysis
    ) -> list[AnalysisResult]:
        self.db.execute(
            delete(AnalysisResult).where(AnalysisResult.document_id == document_id)
        )
        results = [
            AnalysisResult(
                document_id=document_id,
                segment_id=segment.segment_id,
                reference_segment_id=match.reference_segment.id,
                lexical_cosine=_decimal_score(match.tfidf_score),
                lexical_jaccard=_decimal_score(match.jaccard_score),
                semantic_cosine=_decimal_score(match.semantic_score),
                lexical_score=_decimal_score(match.lexical_score),
                final_score=_decimal_score(match.final_score),
                plagiarism_type=match.classification.value,
                is_suspicious=match.is_suspicious,
            )
            for segment in analysis.segments
            for match in segment.matches
        ]
        self.db.add_all(results)
        self.db.commit()
        return results

    def delete_by_document(self, document_id: int) -> None:
        self.db.execute(
            delete(AnalysisResult).where(AnalysisResult.document_id == document_id)
        )
        self.db.commit()

    def list_by_document(self, document_id: int) -> list[AnalysisResult]:
        statement = (
            select(AnalysisResult)
            .options(
                joinedload(AnalysisResult.reference_segment).joinedload(
                    ReferenceSegment.reference_document
                )
            )
            .where(AnalysisResult.document_id == document_id)
            .order_by(
                AnalysisResult.segment_id,
                AnalysisResult.final_score.desc(),
                AnalysisResult.semantic_cosine.desc(),
                AnalysisResult.reference_segment_id,
            )
        )
        return list(self.db.scalars(statement))
