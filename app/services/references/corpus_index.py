from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from itertools import islice
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from app.core.config import settings
from app.models.references import ReferenceSegment
from app.repositories.references import ReferenceRepository

ARTIFACTS = (
    "segment_ids.npy",
    "lexical.npz",
    "vocabulary.json",
    "idf.npy",
    "semantic.npy",
)
VALIDATION_BATCH_SIZE = 1024


class CorpusIndexError(ValueError):
    """Indice ausente, incompleto ou incompativel com a base/modelo."""


@dataclass(frozen=True)
class IndexPreparation:
    directory: Path
    documents: int
    segments: int
    reused: bool


@dataclass(frozen=True)
class CorpusIndex:
    segment_ids: NDArray[np.int64]
    lexical: sparse.csr_matrix
    semantic: NDArray[np.float32]
    vectorizer: TfidfVectorizer
    fingerprint: str


def _configuration() -> dict[str, str | int]:
    return {
        "format_version": 1,
        "model_name": settings.semantic_model_name,
        "sentence_transformers_version": version("sentence-transformers"),
        "sklearn_version": version("scikit-learn"),
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CorpusIndexError(
            f"Indice ausente ou ilegivel ({path.name}): {error}"
        ) from error


def _file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _segment_record(segment: ReferenceSegment) -> bytes:
    document = segment.reference_document
    if (
        not document.content_sha256
        or not document.import_signature
        or segment.text_clean is None
        or segment.start_offset is None
        or segment.end_offset is None
        or segment.start_offset < 0
        or segment.end_offset - segment.start_offset != len(segment.text_original)
    ):
        raise CorpusIndexError(
            f"Referencia {document.corpus_id} sem preparacao completa."
        )
    record = (
        segment.id, document.id, document.corpus_id,
        document.content_sha256, document.import_signature,
        segment.position, segment.start_offset, segment.end_offset,
        segment.text_original, segment.text_clean,
    )
    return json.dumps(record, ensure_ascii=True).encode("utf-8")


def reference_segment_signature(segment: ReferenceSegment) -> bytes:
    return hashlib.sha256(_segment_record(segment)).digest()


def reference_fingerprint(
    repository: ReferenceRepository,
    *,
    on_segment: Callable[[int, bytes], None] | None = None,
) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    count = 0
    documents: set[int] = set()
    for segment in repository.iter_segments():
        record = _segment_record(segment)
        digest.update(record)
        digest.update(b"\n")
        if on_segment is not None:
            on_segment(segment.id, hashlib.sha256(record).digest())
        documents.add(segment.reference_doc_id)
        count += 1
    if count == 0:
        raise CorpusIndexError("Importe documentos fonte em ingles antes de indexar.")
    return digest.hexdigest(), count, len(documents)


def _current_generation(directory: Path) -> Path:
    pointer = _read_json(directory / "current.json")
    if not isinstance(pointer, dict):
        raise CorpusIndexError("Ponteiro do indice invalido.")
    generation = pointer.get("generation")
    if not isinstance(generation, str) or not re.fullmatch(r"[0-9a-f]{32}", generation):
        raise CorpusIndexError("Ponteiro do indice invalido.")
    return directory / generation


def _manifest(generation: Path) -> dict:
    value = _read_json(generation / "manifest.json")
    if not isinstance(value, dict):
        raise CorpusIndexError("Manifesto do indice invalido.")
    return value


def _verify_artifacts(generation: Path, manifest: dict) -> None:
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(ARTIFACTS):
        raise CorpusIndexError("Manifesto de arquivos incompleto.")
    for filename in ARTIFACTS:
        path = generation / filename
        if not path.is_file() or _file_hash(path) != hashes[filename]:
            raise CorpusIndexError(f"Artefato ausente ou corrompido: {filename}.")


def _validate_vectors(lexical: sparse.csr_matrix, semantic: NDArray[np.float32]) -> None:
    try:
        lexical.check_format(full_check=True)
    except ValueError as error:
        raise CorpusIndexError("Estrutura da matriz lexical invalida.") from error
    if not np.issubdtype(lexical.dtype, np.floating):
        raise CorpusIndexError("Tipo da matriz lexical invalido.")

    for start in range(0, lexical.shape[0], VALIDATION_BATCH_SIZE):
        end = start + VALIDATION_BATCH_SIZE
        lexical_batch = lexical[start:end].astype(np.float64)
        if (
            not np.all(np.isfinite(lexical_batch.data))
            or np.any(lexical_batch.data < 0)
        ):
            raise CorpusIndexError("Vetores lexicais invalidos.")
        lexical_norms = np.sqrt(
            np.asarray(lexical_batch.multiply(lexical_batch).sum(axis=1)).ravel()
        )
        if not np.all(
            (lexical_norms == 0) | np.isclose(lexical_norms, 1.0, rtol=0, atol=1e-4)
        ):
            raise CorpusIndexError("Vetores lexicais nao normalizados.")

        semantic_batch = semantic[start:end]
        if not np.all(np.isfinite(semantic_batch)):
            raise CorpusIndexError("Embeddings do indice invalidos.")
        semantic_norms = np.linalg.norm(semantic_batch.astype(np.float64), axis=1)
        if not np.all(np.isclose(semantic_norms, 1.0, rtol=0, atol=1e-4)):
            raise CorpusIndexError("Embeddings do indice nao normalizados.")


def load_corpus_index(
    directory: Path, expected_fingerprint: str | None = None
) -> CorpusIndex:
    generation = _current_generation(directory)
    manifest = _manifest(generation)
    if any(manifest.get(key) != value for key, value in _configuration().items()):
        raise CorpusIndexError("Indice incompativel com o modelo ou as dependencias.")
    if (
        expected_fingerprint is not None
        and manifest.get("fingerprint") != expected_fingerprint
    ):
        raise CorpusIndexError("Indice desatualizado em relacao ao banco.")
    _verify_artifacts(generation, manifest)

    ids = np.load(generation / "segment_ids.npy", allow_pickle=False)
    lexical = sparse.load_npz(generation / "lexical.npz").tocsr()
    semantic = np.load(generation / "semantic.npy", allow_pickle=False, mmap_mode="r")
    vocabulary = _read_json(generation / "vocabulary.json")
    idf = np.load(generation / "idf.npy", allow_pickle=False)
    if (
        not isinstance(vocabulary, dict) or not vocabulary
        or any(not isinstance(term, str) for term in vocabulary)
        or any(type(index) is not int for index in vocabulary.values())
        or set(vocabulary.values()) != set(range(len(vocabulary)))
    ):
        raise CorpusIndexError("Vocabulario do indice invalido.")
    rows = manifest.get("segments")
    if (
        type(rows) is not int or rows < 1
        or ids.shape != (rows,) or ids.dtype != np.int64
        or semantic.ndim != 2 or semantic.shape[0] != rows
        or semantic.shape[1] < 1
        or semantic.shape[1] != manifest.get("dimensions")
        or semantic.dtype != np.float32
        or lexical.shape != (rows, len(vocabulary))
        or idf.shape != (len(vocabulary),)
        or not np.all(np.isfinite(idf))
        or np.any(idf <= 0)
        or len(set(ids.tolist())) != rows or np.any(ids < 1)
    ):
        raise CorpusIndexError("Dimensoes ou identificadores do indice invalidos.")

    vectorizer = TfidfVectorizer(analyzer=str.split, dtype=np.float32, vocabulary=vocabulary)
    vectorizer.idf_ = idf
    fingerprint = manifest.get("fingerprint")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise CorpusIndexError("Identidade do indice invalida.")
    _validate_vectors(lexical, semantic)
    return CorpusIndex(ids, lexical, semantic, vectorizer, fingerprint)


def _write_embeddings(
    path: Path, repository: ReferenceRepository, rows: int, batch_size: int
) -> int:
    from app.services.analysis.semantic_similarity import generate_embeddings

    iterator = iter(repository.iter_segments())
    dimensions = 0
    written = 0
    with path.open("wb") as stream:
        while batch := list(islice(iterator, batch_size)):
            embeddings = np.asarray(
                generate_embeddings([segment.text_original for segment in batch]),
                dtype=np.float32,
            )
            if (
                embeddings.ndim != 2 or embeddings.shape[0] != len(batch)
                or embeddings.shape[1] < 1 or not np.all(np.isfinite(embeddings))
                or not np.allclose(np.linalg.norm(embeddings, axis=1), 1.0, atol=1e-4)
            ):
                raise CorpusIndexError("SBERT retornou embeddings invalidos.")
            if dimensions == 0:
                dimensions = embeddings.shape[1]
                np.lib.format.write_array_header_2_0(
                    stream,
                    {
                        "descr": np.dtype(np.float32).str,
                        "fortran_order": False,
                        "shape": (rows, dimensions),
                    },
                )
            elif embeddings.shape[1] != dimensions:
                raise CorpusIndexError("A dimensao do modelo mudou durante a indexacao.")
            np.ascontiguousarray(embeddings).tofile(stream)
            written += len(batch)
    if written != rows:
        raise CorpusIndexError("A base mudou durante a geracao dos embeddings.")
    return dimensions


def prepare_corpus_index(
    repository: ReferenceRepository,
    directory: Path,
    batch_size: int = 64,
    rebuild: bool = False,
) -> IndexPreparation:
    if batch_size < 1:
        raise ValueError("batch_size deve ser maior que zero.")
    fingerprint, rows, documents = reference_fingerprint(repository)
    configuration = {
        **_configuration(),
        "fingerprint": fingerprint,
        "segments": rows,
        "documents": documents,
    }
    if (directory / "current.json").exists() and not rebuild:
        generation = _current_generation(directory)
        manifest = _manifest(generation)
        if all(manifest.get(key) == value for key, value in configuration.items()):
            _verify_artifacts(generation, manifest)
            return IndexPreparation(generation, documents, rows, reused=True)

    directory.mkdir(parents=True, exist_ok=True)
    generation_name = uuid4().hex
    generation = directory / generation_name
    with TemporaryDirectory(prefix=".building-", dir=directory) as temporary:
        staging = Path(temporary)
        ids = np.fromiter(
            (segment.id for segment in repository.iter_segments()), dtype=np.int64
        )
        vectorizer = TfidfVectorizer(analyzer=str.split, dtype=np.float32)
        lexical = vectorizer.fit_transform(
            segment.text_clean for segment in repository.iter_segments()
        )
        if ids.shape != (rows,) or lexical.shape[0] != rows:
            raise CorpusIndexError("A base mudou durante a vetorizacao lexical.")
        np.save(staging / "segment_ids.npy", ids, allow_pickle=False)
        sparse.save_npz(staging / "lexical.npz", lexical.tocsr())
        _write_json(
            staging / "vocabulary.json",
            {term: int(index) for term, index in vectorizer.vocabulary_.items()},
        )
        np.save(staging / "idf.npy", vectorizer.idf_, allow_pickle=False)
        dimensions = _write_embeddings(
            staging / "semantic.npy", repository, rows, batch_size
        )
        if reference_fingerprint(repository) != (fingerprint, rows, documents):
            raise CorpusIndexError("A base mudou durante a preparacao; execute novamente.")
        _write_json(
            staging / "manifest.json",
            {
                **configuration,
                "dimensions": dimensions,
                "sha256": {name: _file_hash(staging / name) for name in ARTIFACTS},
            },
        )
        staging.rename(generation)

    # Publica apenas geracoes completas; uma falha preserva o indice anterior.
    pointer = directory / f".current-{generation_name}.json"
    _write_json(pointer, {"generation": generation_name})
    pointer.replace(directory / "current.json")
    return IndexPreparation(generation, documents, rows, reused=False)
