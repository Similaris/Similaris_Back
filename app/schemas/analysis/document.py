from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    filename: str
    file_type: str
    status: str
    error_message: str | None = None
    created_at: datetime


class BatchUploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    status: str
    documents: list[DocumentOut]


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    position: int
    start_offset: int | None = None
    end_offset: int | None = None
    text_original: str
    text_clean: str | None = None
