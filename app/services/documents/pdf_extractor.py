import pymupdf

from app.services.documents.exceptions import (
    EmptyDocumentError,
    InvalidDocumentError,
)


def extract_pdf_text(content: bytes) -> str:
    """Extract text from every PDF page while preserving page order."""
    if not content:
        raise EmptyDocumentError("O arquivo PDF está vazio.")

    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise InvalidDocumentError("PDF protegido por senha não é suportado.")

            text = "\n".join(page.get_text("text") for page in document).strip()
    except InvalidDocumentError:
        raise
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise InvalidDocumentError("Não foi possível ler o arquivo PDF.") from exc

    if not text:
        raise EmptyDocumentError("O PDF não contém texto extraível.")

    return text
