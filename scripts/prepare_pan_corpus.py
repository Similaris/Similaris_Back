"""Preparacao offline: python -m scripts.prepare_pan_corpus --help."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from app.services.references.pan_corpus import iter_documents, read_annotations


def positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Use um inteiro maior que zero.")
    return number


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preparacao offline da PAN-PC-11.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "import", "index", "prepare"):
        child = commands.add_parser(command)
        if command != "index":
            child.add_argument("--corpus-dir", type=Path, default=Path("data") / "pan-pc-11")
        if command == "inspect":
            child.add_argument("--ground-truth", action="store_true")
            continue
        child.add_argument("--database-url")
        child.add_argument(
            "--init-db", action="store_true",
            help="Cria tabelas apenas em um SQLite explicitamente selecionado.",
        )
        if command in ("import", "prepare"):
            selection = child.add_mutually_exclusive_group()
            selection.add_argument("--limit", type=positive_integer, default=100)
            selection.add_argument("--all", action="store_true")
            child.add_argument("--max-words", type=positive_integer)
        if command in ("index", "prepare"):
            child.add_argument("--index-dir", type=Path)
            child.add_argument("--batch-size", type=positive_integer, default=64)
            child.add_argument("--rebuild", action="store_true")
    return parser


def inspect_corpus(directory: Path, ground_truth: bool) -> dict:
    languages = Counter(document.language for document in iter_documents(directory, "source"))
    result = {"sources": sum(languages.values()), "source_languages": dict(languages)}
    if ground_truth:
        suspicious_languages: Counter[str] = Counter()
        cases = external = empty_spans = 0
        source_languages: Counter[str] = Counter()
        for document in iter_documents(directory, "suspicious"):
            suspicious_languages[document.language] += 1
            for annotation in read_annotations(document):
                cases += 1
                if annotation.this_length == 0 or annotation.source_length == 0:
                    empty_spans += 1
                if annotation.source_reference is not None:
                    external += 1
                    source_languages[annotation.attributes.get("source_language", "unknown")] += 1
        result["ground_truth"] = {
            "suspicious_documents": sum(suspicious_languages.values()),
            "suspicious_languages": dict(suspicious_languages),
            "annotations": cases,
            "external_annotations": external,
            "empty_span_annotations": empty_spans,
            "external_source_languages": dict(source_languages),
        }
    return result


def _database_command(arguments: argparse.Namespace) -> dict:
    if arguments.database_url:
        os.environ["DATABASE_URL"] = arguments.database_url

    import app.models
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.core.database import Base
    from app.repositories.references import ReferenceRepository
    from app.services.references.corpus_index import prepare_corpus_index
    from app.services.references.pan_import import import_pan_corpus

    url = arguments.database_url or settings.database_url
    engine = create_engine(url)
    sessions = sessionmaker(engine)
    try:
        if arguments.init_db:
            if not arguments.database_url or engine.dialect.name != "sqlite":
                raise ValueError("--init-db exige --database-url de um SQLite isolado.")
            if engine.url.database and engine.url.database != ":memory:":
                Path(engine.url.database).parent.mkdir(parents=True, exist_ok=True)
            Base.metadata.create_all(engine)
        result = {}
        if arguments.command in ("import", "prepare"):
            summary = import_pan_corpus(
                sessions,
                arguments.corpus_dir,
                limit=None if arguments.all else arguments.limit,
                max_words=arguments.max_words,
            )
            result["import"] = asdict(summary)
        if arguments.command in ("index", "prepare"):
            directory = arguments.index_dir or Path(settings.reference_index_dir)
            with sessions() as db:
                preparation = prepare_corpus_index(
                    ReferenceRepository(db), directory,
                    batch_size=arguments.batch_size, rebuild=arguments.rebuild,
                )
            result["index"] = {
                **asdict(preparation),
                "directory": str(preparation.directory),
                "model": settings.semantic_model_name,
            }
        return result
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> None:
    parser = create_parser()
    arguments = parser.parse_args(argv)
    started = perf_counter()
    try:
        if arguments.command == "inspect":
            result = inspect_corpus(arguments.corpus_dir, arguments.ground_truth)
        else:
            result = _database_command(arguments)
    except (OSError, ValueError) as error:
        parser.exit(1, f"PAN-PC-11: {error}\n")
    result["elapsed_seconds"] = round(perf_counter() - started, 3)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
