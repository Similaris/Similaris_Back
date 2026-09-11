"""Busca na referencia preparada: python -m scripts.search_references --help."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from scripts.prepare_pan_corpus import positive_integer

if TYPE_CHECKING:
    from app.services.references.search_contracts import ReferenceSearchResult


class ReferenceSearchCommandError(RuntimeError):
    """Falha semantica apresentada pela CLI sem alterar o contrato do servico."""


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recupera segmentos da referencia PAN inglesa ja preparada."
    )
    query = parser.add_mutually_exclusive_group(required=True)
    query.add_argument("--text", help="Texto original de um segmento.")
    query.add_argument("--text-file", type=Path, help="Arquivo UTF-8 com um segmento.")
    parser.add_argument("--mode", choices=("semantic", "lexical"))
    parser.add_argument("--top-n", type=positive_integer)
    parser.add_argument("--lexical-cosine-threshold", type=float)
    parser.add_argument("--lexical-jaccard-threshold", type=float)
    parser.add_argument("--semantic-threshold", type=float)
    parser.add_argument("--database-url", help="Banco correspondente ao indice.")
    parser.add_argument("--index-dir", type=Path, help="Diretorio do indice preparado.")
    return parser


def _read_only_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if not url.database or url.database == ":memory:":
            raise ValueError("A busca exige um arquivo SQLite existente e preparado.")
        if url.query.get("uri") == "true":
            if not url.database.startswith("file:"):
                raise ValueError("Uma URI SQLite deve iniciar com file:.")
        else:
            database_path = Path(url.database)
            if not database_path.is_file():
                raise ValueError(f"Banco SQLite inexistente: {database_path}.")
            url = url.set(database=database_path.resolve().as_uri())
        url = url.update_query_dict({"mode": "ro", "uri": "true"})
    return create_engine(url)


def _search(arguments: argparse.Namespace) -> ReferenceSearchResult:
    text = (
        arguments.text if arguments.text is not None
        else arguments.text_file.read_text(encoding="utf-8")
    )
    if not text.strip():
        raise ValueError("O texto do segmento nao pode ser vazio.")
    if arguments.database_url:
        os.environ["DATABASE_URL"] = arguments.database_url

    import app.models
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.repositories.references import ReferenceRepository
    from app.services.analysis.semantic_similarity import SemanticSimilarityError
    from app.services.references.reference_search import ReferenceSearchService
    from app.services.references.search_contracts import ReferenceSearchOptions

    options = ReferenceSearchOptions.from_overrides(
        mode=arguments.mode, top_n=arguments.top_n,
        lexical_cosine_threshold=arguments.lexical_cosine_threshold,
        lexical_jaccard_threshold=arguments.lexical_jaccard_threshold,
        semantic_threshold=arguments.semantic_threshold,
    )
    engine = _read_only_engine(arguments.database_url or settings.database_url)
    try:
        with Session(engine, autoflush=False) as db:
            service = ReferenceSearchService(ReferenceRepository(db), arguments.index_dir)
            return service.search(
                text, mode=options.mode, top_n=options.top_n,
                lexical_cosine_threshold=options.lexical_cosine_threshold,
                lexical_jaccard_threshold=options.lexical_jaccard_threshold,
                semantic_threshold=options.semantic_threshold,
            )
    except SemanticSimilarityError as error:
        raise ReferenceSearchCommandError(str(error)) from error
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> None:
    parser = create_parser()
    arguments = parser.parse_args(argv)
    try:
        result = _search(arguments)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
            for item in error.errors(include_input=False, include_context=False)
        )
        parser.exit(1, f"Configuracao da busca invalida: {details}\n")
    except SQLAlchemyError as error:
        parser.exit(
            1,
            f"Falha ao consultar o banco de referencias ({type(error).__name__}). "
            "Confira a conexao, o caminho SQLite e as migrations da base escolhida.\n",
        )
    except (OSError, ValueError, ReferenceSearchCommandError) as error:
        parser.exit(1, f"Busca de referencias: {error}\n")
    print(json.dumps(asdict(result), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
