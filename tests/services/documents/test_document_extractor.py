import pytest

from app.services.documents import (
    UnsupportedDocumentTypeError,
    extract_document_text,
)
from app.services.documents import document_extractor


def test_extract_document_text_routes_pdf_case_insensitively(monkeypatch):
    monkeypatch.setattr(
        document_extractor,
        "extract_pdf_text",
        lambda content: f"pdf:{content.decode()}",
    )

    result = extract_document_text(b"conteudo", "TRABALHO.PDF")

    assert result == "pdf:conteudo"


def test_extract_document_text_routes_docx_case_insensitively(monkeypatch):
    monkeypatch.setattr(
        document_extractor,
        "extract_docx_text",
        lambda content: f"docx:{content.decode()}",
    )

    result = extract_document_text(b"conteudo", "TRABALHO.DOCX")

    assert result == "docx:conteudo"


def test_extract_document_text_rejects_unsupported_extension():
    with pytest.raises(UnsupportedDocumentTypeError, match=r"\.txt"):
        extract_document_text(b"conteudo", "trabalho.txt")


def test_extract_document_text_rejects_filename_without_extension():
    with pytest.raises(UnsupportedDocumentTypeError, match="sem extensão"):
        extract_document_text(b"conteudo", "trabalho")
