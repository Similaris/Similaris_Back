from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.analysis import Batch, Document, Segment
from app.models.references import ReferenceDocument, ReferenceSegment
from app.repositories.analysis import AnalysisResultRepository
from app.services.analysis.analysis_report import AnalysisReportService
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


def test_persists_idempotent_hybrid_results_and_rebuilds_document_report():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()

    batch = Batch(status="processando")
    document = Document(
        batch=batch,
        filename="paper.pdf",
        file_type="pdf",
        file_path="paper.pdf",
        status="concluido",
        lexical_ms=12,
        semantic_ms=34,
    )
    segment = Segment(
        document=document,
        position=1,
        text_original="Submitted text",
        text_clean="submitted text",
    )
    reference_document = ReferenceDocument(
        title="Reference",
        source="pan-pc-11",
        language="en",
        corpus_id="source-document00001.txt",
    )
    reference_segment = ReferenceSegment(
        reference_document=reference_document,
        position=1,
        start_offset=0,
        end_offset=14,
        text_original="Reference text",
        text_clean="reference text",
    )
    db.add_all([batch, document, segment, reference_document, reference_segment])
    db.commit()

    match = HybridMatch(
        reference_document=ReferenceDocumentMatch(
            id=reference_document.id,
            corpus_id=reference_document.corpus_id,
            source=reference_document.source,
            language=reference_document.language,
            title=reference_document.title,
        ),
        reference_segment=ReferenceSegmentMatch(
            id=reference_segment.id,
            position=1,
            start_offset=0,
            end_offset=14,
            text_original="Reference text",
        ),
        tfidf_score=0.82,
        jaccard_score=0.63,
        semantic_score=0.91,
        lexical_score=0.763,
        final_score=0.8365,
        classification=SimilarityClassification.VERY_HIGH,
        is_suspicious=True,
    )
    segment_analysis = SegmentAnalysis(
        segment_id=segment.id,
        text=segment.text_original,
        matches=(match,),
        best_match=match,
        segment_score=match.final_score,
        classification=match.classification,
        is_suspicious=True,
    )
    analysis = DocumentAnalysis(
        document_id=document.id,
        total_segments=1,
        analyzed_segments=1,
        suspicious_segments=1,
        segments=(segment_analysis,),
        overall_score=match.final_score,
        suspicious_segment_percentage=1.0,
        lexical_ms=12,
        semantic_ms=34,
    )

    repository = AnalysisResultRepository(db)
    repository.replace_for_document(document.id, analysis)
    repository.replace_for_document(document.id, analysis)

    stored = repository.list_by_document(document.id)
    assert len(stored) == 1
    assert float(stored[0].lexical_score) == 0.763
    assert stored[0].plagiarism_type == "VERY_HIGH"
    assert stored[0].is_suspicious is True

    report = AnalysisReportService(db).build_document_analysis(document)
    assert report.total_segments == report.analyzed_segments == 1
    assert report.suspicious_segments == 1
    assert report.overall_score == 0.8365
    assert report.suspicious_segment_percentage == 1.0
    assert report.lexical_ms == 12
    assert report.semantic_ms == 34
    assert report.segments[0].best_match.reference_segment.id == reference_segment.id
    db.close()
    engine.dispose()
