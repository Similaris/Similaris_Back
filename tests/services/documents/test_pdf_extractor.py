import pymupdf
import pytest

from app.services.documents import (
    EmptyDocumentError,
    InvalidDocumentError,
    extract_pdf_text,
)


def build_pdf(*page_texts: str) -> bytes:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)

    content = document.tobytes()
    document.close()
    return content


def test_extract_pdf_text_preserves_page_order():
    content = build_pdf("primeira pagina", "segunda pagina")

    result = extract_pdf_text(content)

    assert result == "primeira pagina\n\nsegunda pagina"


def test_extract_pdf_text_rejects_empty_file():
    with pytest.raises(EmptyDocumentError, match="arquivo PDF está vazio"):
        extract_pdf_text(b"")


def test_extract_pdf_text_rejects_corrupted_file():
    with pytest.raises(InvalidDocumentError, match="Não foi possível ler"):
        extract_pdf_text(b"conteudo que nao representa um pdf")


def test_extract_pdf_text_rejects_pdf_without_text():
    content = build_pdf("")

    with pytest.raises(EmptyDocumentError, match="não contém texto extraível"):
        extract_pdf_text(content)


def test_extract_pdf_text_rejects_password_protected_pdf():
    document = pymupdf.open(stream=build_pdf("conteudo protegido"), filetype="pdf")
    protected_content = document.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="secret",
    )
    document.close()

    with pytest.raises(InvalidDocumentError, match="protegido por senha"):
        extract_pdf_text(protected_content)
