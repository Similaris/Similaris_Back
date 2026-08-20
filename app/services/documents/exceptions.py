class DocumentExtractionError(Exception):
    """Base error raised when document text extraction fails."""


class InvalidDocumentError(DocumentExtractionError):
    """Raised when the document cannot be opened or decoded."""


class EmptyDocumentError(DocumentExtractionError):
    """Raised when the document has no extractable text."""


class UnsupportedDocumentTypeError(DocumentExtractionError):
    """Raised when no extractor exists for the document extension."""
