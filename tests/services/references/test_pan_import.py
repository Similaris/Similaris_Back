import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models
from app.core.database import Base
from app.models.references import ReferenceDocument, ReferenceSegment
from app.services.analysis import segment_service
from app.services.references.pan_corpus import PanCorpusError
from app.services.references.pan_import import import_pan_corpus


@pytest.fixture
def sessions():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine)
    engine.dispose()


def test_imports_only_english_sources_with_original_offsets(
    sessions, corpus_dir, write_pan_document,
):
    text = "  The ocean.\r\n\r\nBlue whales swim.  "
    write_pan_document("source-document00001.txt", text)
    write_pan_document("source-document00002.txt", language="de")
    write_pan_document("suspicious-document00001.txt")
    result = import_pan_corpus(sessions, corpus_dir, max_words=2)
    assert (result.imported, result.reused) == (1, 0)
    with sessions() as db:
        documents = list(db.scalars(select(ReferenceDocument)))
        assert len(documents) == 1
        assert documents[0].language == "en"
        assert documents[0].corpus_id == "source-document00001.txt"
        assert not documents[0].file_path.startswith(str(corpus_dir))
        segments = documents[0].segments
        assert len(segments) == result.segments
        assert segments[0].text_clean == "ocean"
        for segment in segments:
            assert text[segment.start_offset:segment.end_offset] == segment.text_original


def test_reimport_preserves_ids_without_segmenting_again(
    sessions, corpus_dir, write_pan_document, monkeypatch,
):
    write_pan_document("source-document00001.txt")
    first = import_pan_corpus(sessions, corpus_dir)
    with sessions() as db:
        ids = list(db.scalars(select(ReferenceSegment.id)))

    def unexpected(*args):
        raise AssertionError("Document already prepared")

    monkeypatch.setattr(segment_service, "segment_text_with_offsets", unexpected)
    second = import_pan_corpus(sessions, corpus_dir)
    assert (second.imported, second.reused, second.segments) == (0, 1, first.segments)
    with sessions() as db:
        assert list(db.scalars(select(ReferenceSegment.id))) == ids


def test_deterministic_subset_can_be_extended(sessions, corpus_dir, write_pan_document):
    write_pan_document("source-document00002.txt")
    write_pan_document("source-document00001.txt")
    assert import_pan_corpus(sessions, corpus_dir, limit=1).imported == 1
    result = import_pan_corpus(sessions, corpus_dir, limit=2)
    assert (result.imported, result.reused) == (1, 1)


def test_changed_content_does_not_replace_existing_references(
    sessions, corpus_dir, write_pan_document,
):
    write_pan_document("source-document00001.txt", "Original ocean text.")
    import_pan_corpus(sessions, corpus_dir)
    write_pan_document("source-document00001.txt", "A changed forest document.")
    with pytest.raises(PanCorpusError, match="outro conteudo"):
        import_pan_corpus(sessions, corpus_dir)
    with sessions() as db:
        assert db.scalar(select(ReferenceSegment)).text_original == "Original ocean text."


def test_changed_segmentation_does_not_silently_reuse_references(
    sessions, corpus_dir, write_pan_document,
):
    write_pan_document("source-document00001.txt")
    import_pan_corpus(sessions, corpus_dir, max_words=10)
    with pytest.raises(PanCorpusError, match="pre-processamento"):
        import_pan_corpus(sessions, corpus_dir, max_words=3)


def test_interrupted_import_keeps_completed_documents_and_can_resume(
    sessions, corpus_dir, write_pan_document,
):
    write_pan_document("source-document00001.txt")
    bad = write_pan_document("source-document00002.txt")
    bad.with_suffix(".txt").write_bytes(b"Damaged.")
    with pytest.raises(PanCorpusError, match="MD5"):
        import_pan_corpus(sessions, corpus_dir)
    with sessions() as db:
        assert len(list(db.scalars(select(ReferenceDocument)))) == 1
    write_pan_document("source-document00002.txt")
    result = import_pan_corpus(sessions, corpus_dir)
    assert (result.imported, result.reused) == (1, 1)


def test_no_english_sources_is_reported(sessions, corpus_dir, write_pan_document):
    write_pan_document("source-document00001.txt", language="es")
    with pytest.raises(PanCorpusError, match="Nenhum documento fonte em ingles"):
        import_pan_corpus(sessions, corpus_dir)


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"max_words": 0}])
def test_invalid_limits_are_rejected(sessions, corpus_dir, kwargs):
    with pytest.raises(ValueError, match="maior que zero"):
        import_pan_corpus(sessions, corpus_dir, **kwargs)
