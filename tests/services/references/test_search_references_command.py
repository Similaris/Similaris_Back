import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import create_engine, text, update
from sqlalchemy.exc import OperationalError

from app.core.database import Base
from app.models.references import ReferenceDocument
from app.services.analysis import semantic_similarity
from scripts import search_references


@pytest.fixture(autouse=True)
def database_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")


def arguments(search_corpus, *extra):
    return [
        "--text", search_corpus.query,
        "--database-url", search_corpus.database_url,
        "--index-dir", str(search_corpus.index_dir),
        *extra,
    ]


@pytest.mark.parametrize("mode", ["semantic", "lexical"])
def test_command_returns_json_with_sources_metrics_options_and_timing(
    search_corpus, capsys, mode,
):
    search_references.main(arguments(search_corpus, "--mode", mode, "--top-n", "1"))
    output = capsys.readouterr()
    result = json.loads(output.out)
    match = result["matches"][0]

    assert output.err == ""
    assert result["options"]["mode"] == mode
    assert result["options"]["top_n"] == 1
    assert result["comparison_ms"] >= 0
    assert len(result["index_fingerprint"]) == 64
    assert match["source_document"]["corpus_id"] == "source-document00001.txt"
    assert match["source_segment"]["id"] == 7
    assert match["source_segment"]["text_original"] == search_corpus.query
    assert match["lexical_score"] == pytest.approx(1)
    assert match["semantic_score"] == pytest.approx(1)
    assert match["jaccard_score"] == 1


def test_text_file_preserves_utf8_and_original_whitespace(
    search_corpus, tmp_path, capsys,
):
    original = "\ufeffCaf\u00e9, a\u00e7\u00e3o!\n"
    query_file = tmp_path / "query.txt"
    query_file.write_text(original, encoding="utf-8")
    search_corpus.query_encoder.side_effect = None
    search_corpus.query_encoder.return_value = np.array([1, 0, 0], dtype=np.float32)
    search_corpus.repository.db.execute(
        update(ReferenceDocument).where(ReferenceDocument.id == 1).values(title="\u00c1rvores")
    )
    search_corpus.repository.db.commit()

    search_references.main([
        "--text-file", str(query_file),
        "--database-url", search_corpus.database_url,
        "--index-dir", str(search_corpus.index_dir), "--top-n", "1",
    ])
    result = json.loads(capsys.readouterr().out)

    search_corpus.query_encoder.assert_called_once_with(original)
    assert result["matches"][0]["source_document"]["title"] == "\u00c1rvores"


def test_all_threshold_overrides_are_forwarded(search_corpus, capsys):
    search_references.main(arguments(
        search_corpus, "--top-n", "20", "--semantic-threshold", "-1",
        "--lexical-cosine-threshold", "1", "--lexical-jaccard-threshold", "1",
    ))
    result = json.loads(capsys.readouterr().out)

    assert result["options"]["semantic_threshold"] == -1
    assert result["options"]["lexical_cosine_threshold"] == 1
    assert result["options"]["lexical_jaccard_threshold"] == 1
    assert [match["source_segment"]["id"] for match in result["matches"]] == [7, 40, 81, 215, 103, 12]
    assert result["matches"][-1]["semantic_score"] == -1


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--text", "query", "--text-file", "query.txt"],
        ["--text", "query", "--mode", "hybrid"],
        ["--text", "query", "--top-n", "0"],
        ["--text", "query", "--top-n", "1.5"],
        ["--text", "query", "--init-db"],
    ],
)
def test_invalid_arguments_exit_before_database_access(argv, monkeypatch, capsys):
    reader = Mock(side_effect=AssertionError("Invalid arguments must not reach the database"))
    monkeypatch.setattr(search_references, "_read_only_engine", reader)

    with pytest.raises(SystemExit) as error:
        search_references.main(argv)
    assert error.value.code == 2
    assert capsys.readouterr().out == ""
    reader.assert_not_called()


@pytest.mark.parametrize(
    "extra",
    [
        ["--semantic-threshold", "nan"],
        ["--semantic-threshold", "-1.1"],
        ["--lexical-cosine-threshold", "inf"],
        ["--lexical-jaccard-threshold", "-0.1"],
    ],
)
def test_invalid_thresholds_fail_without_opening_the_database(extra, monkeypatch, capsys):
    reader = Mock(side_effect=AssertionError("Invalid thresholds must not open the database"))
    monkeypatch.setattr(search_references, "_read_only_engine", reader)

    with pytest.raises(SystemExit) as error:
        search_references.main(["--text", "query", *extra])
    assert error.value.code == 1
    assert "threshold" in capsys.readouterr().err
    reader.assert_not_called()


def test_empty_text_is_not_a_successful_empty_result(capsys):
    with pytest.raises(SystemExit) as error:
        search_references.main(["--text", " \n "])
    output = capsys.readouterr()
    assert error.value.code == 1
    assert output.out == ""
    assert "vazio" in output.err


def test_missing_query_file_reports_an_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        search_references.main(["--text-file", str(tmp_path / "missing.txt")])
    output = capsys.readouterr()
    assert error.value.code == 1
    assert output.out == ""
    assert "missing.txt" in output.err


def test_missing_sqlite_database_is_not_created(tmp_path, capsys):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(SystemExit) as error:
        search_references.main([
            "--text", "query", "--database-url", f"sqlite:///{path}",
        ])
    output = capsys.readouterr()
    assert error.value.code == 1
    assert output.out == ""
    assert "inexistente" in output.err
    assert not path.exists()


def test_sqlite_is_read_only_even_when_the_input_uri_requests_writes(search_corpus):
    from sqlalchemy.engine import make_url

    path = Path(make_url(search_corpus.database_url).database)
    url = make_url(search_corpus.database_url).set(
        database=path.resolve().as_uri(), query={"mode": "rw", "uri": "true"}
    )
    engine = search_references._read_only_engine(str(url))
    try:
        with engine.begin() as connection:
            assert connection.scalar(text("SELECT count(*) FROM reference_docs")) == 2
            with pytest.raises(OperationalError, match="readonly"):
                connection.execute(text("DELETE FROM reference_segments"))
    finally:
        engine.dispose()


def test_search_does_not_modify_database_or_index(search_corpus, capsys):
    from sqlalchemy.engine import make_url

    database_path = Path(make_url(search_corpus.database_url).database)
    paths = [database_path, search_corpus.index_dir / "current.json"]
    paths.extend(path for path in search_corpus.generation.iterdir() if path.is_file())
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

    search_references.main(arguments(search_corpus))
    capsys.readouterr()

    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths} == before


def test_empty_reference_database_exits_with_error(tmp_path, search_corpus, capsys):
    database_url = f"sqlite:///{tmp_path / 'empty.sqlite3'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()

    with pytest.raises(SystemExit) as error:
        search_references.main([
            "--text", search_corpus.query, "--database-url", database_url,
            "--index-dir", str(search_corpus.index_dir),
        ])
    output = capsys.readouterr()
    assert error.value.code == 1
    assert output.out == ""
    assert "Importe documentos" in output.err


def test_wrong_reference_identity_exits_with_error(search_corpus, capsys):
    search_corpus.repository.db.execute(
        update(ReferenceDocument).values(import_signature="c" * 64)
    )
    search_corpus.repository.db.commit()
    with pytest.raises(SystemExit) as error:
        search_references.main(arguments(search_corpus))
    output = capsys.readouterr()
    assert error.value.code == 1
    assert output.out == ""
    assert "desatualizado" in output.err


def test_missing_index_exits_with_error(search_corpus, tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        search_references.main(arguments(
            search_corpus, "--index-dir", str(tmp_path / "missing-index")
        ))
    output = capsys.readouterr()
    assert error.value.code == 1
    assert output.out == ""
    assert "current.json" in output.err


def test_semantic_failure_is_reported_without_a_success_payload(search_corpus, capsys):
    search_corpus.query_encoder.side_effect = semantic_similarity.SemanticModelLoadError(
        "model unavailable"
    )
    with pytest.raises(SystemExit) as error:
        search_references.main(arguments(search_corpus))
    output = capsys.readouterr()
    assert error.value.code == 1
    assert output.out == ""
    assert "model unavailable" in output.err


def test_database_error_does_not_print_sensitive_driver_details(monkeypatch, capsys):
    monkeypatch.setattr(
        search_references, "_read_only_engine",
        Mock(side_effect=OperationalError("SQL", {}, Exception("private-connection-data"))),
    )
    with pytest.raises(SystemExit) as error:
        search_references.main(["--text", "query"])
    output = capsys.readouterr()
    assert error.value.code == 1
    assert output.out == ""
    assert "OperationalError" in output.err
    assert "private-connection-data" not in output.err


def test_configuration_errors_do_not_print_input_values(monkeypatch, capsys):
    class Configuration(BaseModel):
        top_n: int

    with pytest.raises(ValidationError) as invalid:
        Configuration(top_n="private-configuration-data")
    monkeypatch.setattr(search_references, "_search", Mock(side_effect=invalid.value))

    with pytest.raises(SystemExit) as error:
        search_references.main(["--text", "query"])
    output = capsys.readouterr()
    assert error.value.code == 1
    assert "top_n" in output.err
    assert "private-configuration-data" not in output.err


def test_help_does_not_require_backend_configuration_or_a_model(tmp_path):
    environment = os.environ.copy()
    for key in ("DATABASE_URL", "REDIS_URL", "JWT_SECRET_KEY", "SECRET_KEY"):
        environment.pop(key, None)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[3])
    result = subprocess.run(
        [sys.executable, "-m", "scripts.search_references", "--help"],
        cwd=tmp_path, env=environment, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--mode" in result.stdout
    assert "--top-n" in result.stdout
