from pathlib import Path

from app.core.config import settings
from app.services.documents.file_storage import (
    compute_content_hash,
    store_document_file,
)


def test_compute_content_hash_returns_sha256_hex():
    assert compute_content_hash(b"similaris") == (
        "6ae51a74293787cab3975d28fecd18ca758b384cdc8650898ba5be69c8f77154"
    )


def test_store_document_file_writes_content_inside_batch_dir(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    stored_path = store_document_file(b"conteudo", "Trabalho Final.PDF", batch_id=7)

    stored_file = Path(stored_path)
    assert stored_file.read_bytes() == b"conteudo"
    assert stored_file.parent == tmp_path / "7"
    assert stored_file.suffix == ".pdf"


def test_store_document_file_generates_unique_names(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    first_path = store_document_file(b"a", "doc.docx", batch_id=1)
    second_path = store_document_file(b"b", "doc.docx", batch_id=1)

    assert first_path != second_path
    assert Path(first_path).read_bytes() == b"a"
    assert Path(second_path).read_bytes() == b"b"
