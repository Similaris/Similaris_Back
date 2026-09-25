from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
from numpy.typing import NDArray

from app.core.config import settings
from app.models.references import ReferenceSegment
from app.repositories.references.reference_repository import (
    REFERENCE_BATCH_SIZE,
    ReferenceRepository,
)
from app.services.analysis import semantic_similarity
from app.services.analysis.lexical_similarity import compute_jaccard_from_tokens
from app.services.analysis.text_preprocessing import preprocess_text
from app.services.references.corpus_index import (
    CorpusIndex,
    CorpusIndexError,
    load_corpus_index,
    reference_fingerprint,
    reference_segment_signature,
)
from app.services.references.search_contracts import (
    ReferenceDocumentMatch,
    ReferenceMatch,
    ReferenceSearchOptions,
    ReferenceSearchResult,
    ReferenceSegmentMatch,
    SearchMode,
)

SEMANTIC_BATCH_SIZE = 4096


@dataclass(frozen=True, slots=True)
class _Candidate:
    row: int
    document: ReferenceDocumentMatch
    segment: ReferenceSegmentMatch
    tokens: frozenset[str]


def _checked_scores(scores: NDArray[np.float64], minimum: float) -> NDArray[np.float64]:
    if (
        not np.all(np.isfinite(scores))
        or np.any(scores < minimum - 1e-3)
        or np.any(scores > 1.0 + 1e-3)
    ):
        raise CorpusIndexError("A comparacao produziu scores invalidos.")
    return np.clip(scores, minimum, 1.0)


class ReferenceSearchService:
    """Busca em um snapshot offline; revalide entre documentos/lotes."""

    def __init__(
        self, repository: ReferenceRepository, index_dir: Path | str | None = None
    ):
        self.repository = repository
        self.index_dir = Path(
            settings.reference_index_dir if index_dir is None else index_dir
        )
        self._index: CorpusIndex | None = None
        self._signatures: dict[int, bytes] = {}
        self._model_name: str | None = None
        self._cached_query_text: str | None = None
        self._cached_query_embedding: NDArray[np.float32] | None = None
        self.revalidate()

    def revalidate(self) -> None:
        """Reabre o indice e valida a base; uma falha invalida a instancia."""
        self._index = None
        self._signatures = {}
        self._cached_query_text = None
        self._cached_query_embedding = None
        signatures: dict[int, bytes] = {}
        fingerprint, rows, _ = reference_fingerprint(
            self.repository, on_segment=signatures.__setitem__
        )
        index = load_corpus_index(self.index_dir, expected_fingerprint=fingerprint)
        ids = np.fromiter(signatures, dtype=np.int64)
        if len(signatures) != rows or not np.array_equal(ids, index.segment_ids):
            raise CorpusIndexError("Alinhamento dos segmentos do indice diverge do banco.")
        self._signatures = signatures
        self._model_name = settings.semantic_model_name
        self._index = index

    def search(
        self,
        text_original: str,
        *,
        mode: SearchMode | None = None,
        top_n: int | None = None,
        lexical_cosine_threshold: float | None = None,
        lexical_jaccard_threshold: float | None = None,
        semantic_threshold: float | None = None,
    ) -> ReferenceSearchResult:
        started = perf_counter()
        if not isinstance(text_original, str):
            raise TypeError("text_original deve ser uma string.")
        if not text_original.strip():
            raise ValueError("text_original nao pode ser vazio.")
        options = ReferenceSearchOptions.from_overrides(
            mode=mode, top_n=top_n,
            lexical_cosine_threshold=lexical_cosine_threshold,
            lexical_jaccard_threshold=lexical_jaccard_threshold,
            semantic_threshold=semantic_threshold,
        )
        index = self._index
        if index is None:
            raise CorpusIndexError("Snapshot de busca invalido; revalide a instancia.")
        if settings.semantic_model_name != self._model_name:
            self._index = None
            raise CorpusIndexError("O modelo mudou; revalide o indice antes de consultar.")

        clean_query = preprocess_text(text_original)
        query_tokens = frozenset(clean_query.split())
        lexical_query = index.vectorizer.transform([clean_query])
        # Somente o vetor de scores (N x 1) e denso, nunca a matriz TF-IDF.
        lexical_scores = _checked_scores(
            np.asarray((index.lexical @ lexical_query.T).toarray(), dtype=np.float64).ravel(),
            0.0,
        )
        embedding = self._query_embedding(text_original, index)

        semantic_scores = None
        if options.mode == "semantic":
            semantic_scores = self._semantic_scores(index, embedding)
            eligible = np.flatnonzero(semantic_scores >= options.semantic_threshold)
            ranking_scores = semantic_scores
        else:
            eligible = np.flatnonzero(lexical_scores >= options.lexical_cosine_threshold)
            ranking_scores = lexical_scores
        ordering = np.lexsort((index.segment_ids[eligible], -ranking_scores[eligible]))
        ranked_rows = eligible[ordering]
        if options.mode == "semantic":
            ranked_rows = ranked_rows[: options.top_n]

        selected: list[tuple[_Candidate, float]] = []
        for start in range(0, len(ranked_rows), REFERENCE_BATCH_SIZE):
            batch = ranked_rows[start : start + REFERENCE_BATCH_SIZE]
            for candidate in self._candidates(index, batch):
                jaccard = compute_jaccard_from_tokens(query_tokens, candidate.tokens)
                if options.mode == "lexical" and jaccard < options.lexical_jaccard_threshold:
                    continue
                selected.append((candidate, jaccard))
                if len(selected) == options.top_n:
                    break
            if len(selected) == options.top_n:
                break

        selected_rows = np.fromiter((candidate.row for candidate, _ in selected), dtype=np.intp)
        selected_semantic = (
            self._semantic_scores(index, embedding, selected_rows)
            if semantic_scores is None else semantic_scores[selected_rows]
        )
        matches = tuple(
            ReferenceMatch(
                source_document=candidate.document,
                source_segment=candidate.segment,
                lexical_score=float(lexical_scores[candidate.row]),
                semantic_score=float(semantic_score),
                jaccard_score=jaccard,
            )
            for (candidate, jaccard), semantic_score in zip(
                selected, selected_semantic, strict=True
            )
        )
        return ReferenceSearchResult(
            options=options,
            index_fingerprint=index.fingerprint,
            matches=matches,
            comparison_ms=(perf_counter() - started) * 1000,
        )

    def _query_embedding(
        self, text_original: str, index: CorpusIndex
    ) -> NDArray[np.float32]:
        if (
            self._cached_query_text == text_original
            and self._cached_query_embedding is not None
        ):
            return self._cached_query_embedding
        try:
            embedding = np.asarray(
                semantic_similarity.generate_embedding(text_original), dtype=np.float32
            )
        except (TypeError, ValueError) as error:
            raise semantic_similarity.EmbeddingGenerationError(
                "O embedding da consulta deve conter numeros."
            ) from error
        if (
            embedding.ndim != 1
            or embedding.shape[0] != index.semantic.shape[1]
            or not np.all(np.isfinite(embedding))
            or not np.isclose(
                np.linalg.norm(embedding.astype(np.float64)), 1.0, rtol=0, atol=1e-4
            )
        ):
            raise semantic_similarity.EmbeddingGenerationError(
                "O embedding da consulta deve ser finito, normalizado e compativel com o indice."
            )
        self._cached_query_text = text_original
        self._cached_query_embedding = embedding
        return embedding

    @staticmethod
    def _semantic_scores(
        index: CorpusIndex,
        embedding: NDArray[np.float32],
        rows: NDArray[np.intp] | None = None,
    ) -> NDArray[np.float64]:
        count = index.semantic.shape[0] if rows is None else len(rows)
        scores = np.empty(count, dtype=np.float64)
        for start in range(0, count, SEMANTIC_BATCH_SIZE):
            end = start + SEMANTIC_BATCH_SIZE
            batch = index.semantic[start:end] if rows is None else index.semantic[rows[start:end]]
            scores[start:end] = batch @ embedding
        return _checked_scores(scores, -1.0)

    def _candidates(
        self, index: CorpusIndex, rows: NDArray[np.intp]
    ) -> list[_Candidate]:
        ids = [int(index.segment_ids[row]) for row in rows]
        segments = self.repository.get_segments_by_ids(ids)
        by_id = {segment.id: segment for segment in segments}
        if len(segments) != len(ids) or set(by_id) != set(ids):
            self._index = None
            raise CorpusIndexError("Referencias ausentes ou divergentes do snapshot de busca.")
        return [
            self._candidate(by_id[segment_id], int(row))
            for segment_id, row in zip(ids, rows, strict=True)
        ]

    def _candidate(self, segment: ReferenceSegment, row: int) -> _Candidate:
        try:
            signature = reference_segment_signature(segment)
        except CorpusIndexError:
            self._index = None
            raise
        if signature != self._signatures[segment.id]:
            self._index = None
            raise CorpusIndexError("Referencia alterada; revalide o snapshot de busca.")
        document = segment.reference_document
        corpus_id = document.corpus_id
        start = segment.start_offset
        end = segment.end_offset
        text_clean = segment.text_clean
        if corpus_id is None or start is None or end is None or text_clean is None:
            self._index = None
            raise CorpusIndexError("Metadados da referencia incompletos.")
        return _Candidate(
            row=row,
            document=ReferenceDocumentMatch(
                id=document.id, corpus_id=corpus_id, source=document.source,
                language=document.language, title=document.title,
            ),
            segment=ReferenceSegmentMatch(
                id=segment.id, position=segment.position,
                start_offset=start, end_offset=end, text_original=segment.text_original,
            ),
            tokens=frozenset(text_clean.split()),
        )
