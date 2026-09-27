"""Avalia a recuperação híbrida contra o ground truth externo da PAN-PC-11."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.references.pan_corpus import (
    external_corpus_directory,
    iter_documents,
    read_annotations,
    read_content,
)


@dataclass(frozen=True)
class RetrievalCounts:
    cases: int = 0
    predictions: int = 0
    hits: int = 0
    reciprocal_rank: float = 0.0


def metrics(counts: RetrievalCounts) -> dict[str, float | int]:
    precision = counts.hits / counts.predictions if counts.predictions else 0.0
    recall = counts.hits / counts.cases if counts.cases else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "cases": counts.cases,
        "predictions": counts.predictions,
        "hits": counts.hits,
        "precision_at_n": round(precision, 6),
        "recall_at_n": round(recall, 6),
        "f1_at_n": round(f1, 6),
        "mean_reciprocal_rank": round(
            counts.reciprocal_rank / counts.cases if counts.cases else 0.0, 6
        ),
    }


def positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Use um inteiro maior que zero.")
    return number


def evaluate(corpus_dir: Path, database_url: str, index_dir: Path, limit: int | None) -> dict:
    os.environ["DATABASE_URL"] = database_url
    from app.repositories.references import ReferenceRepository
    from app.services.analysis.hybrid_analysis import HybridScoreCalculator
    from app.services.references.reference_search import ReferenceSearchService

    engine = create_engine(database_url)
    counts = RetrievalCounts()
    skipped_missing_source = 0
    calculator = HybridScoreCalculator()
    try:
        with Session(engine) as db:
            repository = ReferenceRepository(db)
            search = ReferenceSearchService(repository, index_dir)
            available_sources = {
                segment.reference_document.corpus_id
                for segment in repository.iter_segments()
                if segment.reference_document.corpus_id
            }
            for document in iter_documents(external_corpus_directory(corpus_dir), "suspicious"):
                if document.language != "en":
                    continue
                text, _ = read_content(document)
                for annotation in read_annotations(document):
                    source = annotation.source_reference
                    if source is None or source not in available_sources:
                        skipped_missing_source += 1
                        continue
                    query = text[
                        annotation.this_offset : annotation.this_offset + annotation.this_length
                    ]
                    if not query.strip():
                        continue
                    lexical = search.search(query, mode="lexical")
                    semantic = search.search(query, mode="semantic")
                    by_segment = {}
                    for match in (*lexical.matches, *semantic.matches):
                        previous = by_segment.get(match.source_segment.id)
                        if previous is None:
                            by_segment[match.source_segment.id] = match
                        else:
                            match = type(match)(
                                source_document=match.source_document,
                                source_segment=match.source_segment,
                                lexical_score=max(previous.lexical_score, match.lexical_score),
                                semantic_score=max(previous.semantic_score, match.semantic_score),
                                jaccard_score=max(previous.jaccard_score, match.jaccard_score),
                            )
                            by_segment[match.source_segment.id] = match
                    ranked = sorted(
                        by_segment.values(),
                        key=lambda match: calculator.final_score(
                            calculator.lexical_score(
                                match.lexical_score, match.jaccard_score
                            ),
                            match.semantic_score,
                        ),
                        reverse=True,
                    )[: calculator.options.top_n]
                    predicted = []
                    for match in ranked:
                        if match.source_document.corpus_id not in predicted:
                            predicted.append(match.source_document.corpus_id)
                    hit = source in predicted
                    rank = predicted.index(source) + 1 if hit else 0
                    counts = RetrievalCounts(
                        cases=counts.cases + 1,
                        predictions=counts.predictions + len(predicted),
                        hits=counts.hits + int(hit),
                        reciprocal_rank=counts.reciprocal_rank + (1 / rank if rank else 0),
                    )
                    if limit is not None and counts.cases >= limit:
                        return {
                            **metrics(counts),
                            "skipped_missing_source": skipped_missing_source,
                            "top_n": calculator.options.top_n,
                        }
    finally:
        engine.dispose()
    return {
        **metrics(counts),
        "skipped_missing_source": skipped_missing_source,
        "top_n": calculator.options.top_n,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--limit", type=positive_integer)
    arguments = parser.parse_args()
    os.environ["DATABASE_URL"] = arguments.database_url
    result = evaluate(
        arguments.corpus_dir,
        arguments.database_url,
        arguments.index_dir,
        arguments.limit,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
