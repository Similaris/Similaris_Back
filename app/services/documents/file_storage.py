from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from app.core.config import settings


def compute_content_hash(content: bytes) -> str:
    """Calcula o hash SHA-256 do conteúdo do arquivo."""
    return hashlib.sha256(content).hexdigest()


def store_document_file(content: bytes, filename: str, batch_id: int) -> str:
    """Grava o arquivo enviado no diretório de uploads e retorna o caminho.

    O arquivo é salvo em ``{upload_dir}/{batch_id}/{uuid}{extensão}`` para
    evitar colisões de nome entre uploads distintos.
    """
    extension = Path(filename).suffix.lower()
    target_dir = Path(settings.upload_dir) / str(batch_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / f"{uuid.uuid4().hex}{extension}"
    target_path.write_bytes(content)
    return target_path.as_posix()
