import json

import numpy as np
import pytest

from app.services.analysis import semantic_similarity
from scripts.prepare_pan_corpus import main


def test_inspect_reports_languages_and_ground_truth(
    corpus_dir, write_pan_document, capsys,
):
    write_pan_document("source-document00001.txt")
    write_pan_document("source-document00002.txt", language="de")
    write_pan_document(
        "suspicious-document00001.txt",
        annotations=[{
            "this_offset": "0", "this_length": "5",
            "source_reference": "source-document00001.txt",
            "source_offset": "0", "source_length": "5", "source_language": "en",
        }],
    )
    main(["inspect", "--corpus-dir", str(corpus_dir), "--ground-truth"])
    result = json.loads(capsys.readouterr().out)
    assert result["sources"] == 2
    assert result["source_languages"] == {"en": 1, "de": 1}
    assert result["ground_truth"]["external_annotations"] == 1


def test_prepare_command_imports_then_reuses_persistent_data(
    corpus_dir, write_pan_document, tmp_path, capsys, monkeypatch,
):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    write_pan_document("source-document00001.txt")
    calls = []

    def encode(texts):
        calls.append(texts)
        rows = np.ones((len(texts), 4), dtype=np.float32)
        return rows / 2

    monkeypatch.setattr(semantic_similarity, "generate_embeddings", encode)
    arguments = [
        "prepare", "--corpus-dir", str(corpus_dir),
        "--database-url", f"sqlite:///{tmp_path / 'corpus.sqlite3'}",
        "--init-db", "--index-dir", str(tmp_path / "index"), "--limit", "1",
    ]
    main(arguments)
    first = json.loads(capsys.readouterr().out)
    main(arguments)
    second = json.loads(capsys.readouterr().out)
    assert first["import"]["imported"] == 1
    assert not first["index"]["reused"]
    assert second["import"]["reused"] == 1
    assert second["index"]["reused"]
    assert len(calls) == 1


def test_invalid_dataset_exits_with_error(corpus_dir, capsys):
    with pytest.raises(SystemExit) as error:
        main(["inspect", "--corpus-dir", str(corpus_dir)])
    assert error.value.code == 1
    assert "Nenhum XML" in capsys.readouterr().err


def test_all_and_limit_are_mutually_exclusive(capsys):
    with pytest.raises(SystemExit) as error:
        main(["import", "--all", "--limit", "20"])
    assert error.value.code == 2
