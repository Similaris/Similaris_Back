from pathlib import Path

from app.services.documents.docx_extractor import extract_docx_text
from app.services.documents.exceptions import UnsupportedDocumentTypeError
from app.services.documents.pdf_extractor import extract_pdf_text


def extract_document_text(content: bytes, filename: str) -> str:
    extension = Path(filename).suffix.lower()

    if extension == ".pdf":
        return extract_pdf_text(content)

    if extension == ".docx":
        return extract_docx_text(content)

    displayed_extension = extension or "sem extensão"
    raise UnsupportedDocumentTypeError(
        f"Formato de documento não suportado: {displayed_extension}. "
        "Use PDF ou DOCX."
    )
