from io import BytesIO
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from app.services.documents.exceptions import (
    EmptyDocumentError,
    InvalidDocumentError,
)


def extract_docx_text(content: bytes) -> str:
    """Extract DOCX paragraphs while preserving their original order."""
    if not content:
        raise EmptyDocumentError("O arquivo DOCX está vazio.")

    try:
        document = Document(BytesIO(content))
    except (PackageNotFoundError, BadZipFile, KeyError, ValueError) as exc:
        raise InvalidDocumentError("Não foi possível ler o arquivo DOCX.") from exc

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]
    text = "\n\n".join(paragraphs)

    if not text:
        raise EmptyDocumentError("O DOCX não contém texto extraível.")

    return text
