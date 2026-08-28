class DocumentExtractionError(Exception):
    """Base error raised when document text extraction fails."""


class InvalidDocumentError(DocumentExtractionError):
    """Raised when the document cannot be opened or decoded."""


class EmptyDocumentError(DocumentExtractionError):
    """Raised when the document has no extractable text."""


class UnsupportedDocumentTypeError(DocumentExtractionError):
    """Raised when no extractor exists for the document extension."""


class UploadValidationError(Exception):
    """Base error raised when an upload request is invalid."""


class EmptyUploadError(UploadValidationError):
    """Raised when the upload request has no files."""


class FileTooLargeError(UploadValidationError):
    """Raised when an uploaded file exceeds the size limit."""
