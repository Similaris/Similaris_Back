from io import BytesIO

import pytest
from docx import Document as DocxBuilder
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import database
from app.core.config import settings
from app.core.database import Base
from app.models.analysis import Batch, Document, Segment
from app.services.documents.file_storage import store_document_file
from app.tasks.document_tasks import process_document


def build_docx(*paragraphs: str) -> bytes:
    document = DocxBuilder()
    for text in paragraphs:
        document.add_paragraph(text)

    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    # A task abre a própria sessão via app.core.database.SessionLocal;
    # aqui apontamos para o banco de teste.
    monkeypatch.setattr(database, "SessionLocal", factory)
    return factory


def test_process_document_task_runs_pipeline(session_factory):
    db = session_factory()
    batch = Batch(status="pendente")
    db.add(batch)
    db.commit()
    db.refresh(batch)

    content = build_docx("The student wrote an original academic paper.")
    file_path = store_document_file(content, "paper.docx", batch.id)
    document = Document(
        batch_id=batch.id,
        filename="paper.docx",
        file_type="docx",
        file_path=file_path,
        status="pendente",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    process_document(document.id)

    db.expire_all()
    assert document.status == "concluido"
    assert db.query(Segment).filter_by(document_id=document.id).count() > 0
    assert db.get(Batch, batch.id).status == "concluido"
    db.close()


def test_process_document_task_is_registered_with_stable_name():
    # O nome estável desacopla o roteamento das mensagens do caminho do módulo.
    assert process_document.name == "documents.process_document"
