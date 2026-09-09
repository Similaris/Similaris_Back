from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.references import ReferenceDocument, ReferenceSegment
from app.repositories.references import ReferenceRepository
from app.services.analysis import segment_service, text_preprocessing
from app.services.references.pan_corpus import (
    PanCorpusError,
    external_corpus_directory,
    iter_documents,
    read_content,
)


@dataclass(frozen=True)
class ImportSummary:
    imported: int
    reused: int
    segments: int


def import_signature(max_words: int) -> str:
    sources = [
        Path(module.__file__).read_text(encoding="utf-8")
        for module in (segment_service, text_preprocessing)
    ]
    configuration = {
        "format_version": 1,
        "max_words": max_words,
        "pipeline_sha256": hashlib.sha256("\n".join(sources).encode("utf-8")).hexdigest(),
        "stopwords": sorted(text_preprocessing.get_english_stopwords()),
    }
    return hashlib.sha256(
        json.dumps(configuration, sort_keys=True).encode("utf-8")
    ).hexdigest()


def import_pan_corpus(
    sessions: sessionmaker[Session],
    directory: Path,
    limit: int | None = 100,
    max_words: int | None = None,
) -> ImportSummary:
    if limit is not None and limit < 1:
        raise ValueError("limit deve ser maior que zero.")
    max_words = settings.segment_max_words if max_words is None else max_words
    if max_words < 1:
        raise ValueError("max_words deve ser maior que zero.")
    directory = external_corpus_directory(directory)
    signature = import_signature(max_words)
    imported = reused = total_segments = 0

    for metadata in iter_documents(directory, "source"):
        if metadata.language != "en":
            continue
        text, content_sha256 = read_content(metadata)
        with sessions.begin() as db:
            repository = ReferenceRepository(db)
            existing = repository.get_by_corpus_id("pan-pc-11", metadata.reference)
            if existing is not None:
                if (
                    existing.content_sha256 != content_sha256
                    or existing.import_signature != signature
                    or existing.language != "en"
                    or not existing.segments
                ):
                    raise PanCorpusError(
                        f"Referencia {metadata.reference} ja existe com outro conteudo "
                        "ou pre-processamento. Use uma base separada para outra "
                        "configuracao; referencias existentes nao serao substituidas."
                    )
                total_segments += len(existing.segments)
                reused += 1
            else:
                slices = segment_service.segment_text_with_offsets(text, max_words)
                segments = [
                    ReferenceSegment(
                        position=position,
                        start_offset=piece.start_offset,
                        end_offset=piece.end_offset,
                        text_original=piece.text,
                        text_clean=text_preprocessing.preprocess_text(piece.text),
                    )
                    for position, piece in enumerate(slices, start=1)
                ]
                file_path = metadata.text_path.relative_to(directory).as_posix()
                if len(metadata.title) > 500 or len(file_path) > 500:
                    raise PanCorpusError(f"Metadados excedem 500 caracteres: {metadata.reference}.")
                repository.add(
                    ReferenceDocument(
                        source="pan-pc-11",
                        corpus_id=metadata.reference,
                        title=metadata.title,
                        language="en",
                        file_path=file_path,
                        content_sha256=content_sha256,
                        import_signature=signature,
                    ),
                    segments,
                )
                imported += 1
                total_segments += len(segments)
        if limit is not None and imported + reused >= limit:
            break
    if imported + reused == 0:
        raise PanCorpusError("Nenhum documento fonte em ingles encontrado.")
    return ImportSummary(imported, reused, total_segments)
