from io import BytesIO

import pytest
from docx import Document

from app.services.documents import (
    EmptyDocumentError,
    InvalidDocumentError,
    extract_docx_text,
)


def build_docx(*paragraphs: str) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)

    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def test_extract_docx_text_preserves_paragraph_order():
    content = build_docx("primeiro paragrafo", "segundo paragrafo")

    result = extract_docx_text(content)

    assert result == "primeiro paragrafo\n\nsegundo paragrafo"


def test_extract_docx_text_rejects_empty_file():
    with pytest.raises(EmptyDocumentError, match="arquivo DOCX está vazio"):
        extract_docx_text(b"")


def test_extract_docx_text_rejects_corrupted_file():
    with pytest.raises(InvalidDocumentError, match="Não foi possível ler"):
        extract_docx_text(b"conteudo que nao representa um docx")


def test_extract_docx_text_rejects_document_without_text():
    content = build_docx()

    with pytest.raises(EmptyDocumentError, match="não contém texto extraível"):
        extract_docx_text(content)
