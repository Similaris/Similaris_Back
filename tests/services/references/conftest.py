import hashlib
from xml.etree import ElementTree

import pytest


@pytest.fixture
def corpus_dir(tmp_path):
    root = tmp_path / "external-detection-corpus"
    root.mkdir()
    return root


@pytest.fixture
def write_pan_document(corpus_dir):
    def write(reference, text="The ocean. Blue whales swim.", language="en", annotations=()):
        kind = reference.split("-")[0]
        directory = corpus_dir / f"{kind}-documents" / "part1"
        directory.mkdir(parents=True, exist_ok=True)
        content = text.encode("utf-8")
        (directory / reference).write_bytes(content)
        root = ElementTree.Element("document", reference=reference)
        ElementTree.SubElement(
            root, "feature", name="about", lang=language, title=reference,
        )
        ElementTree.SubElement(
            root, "feature", name="md5Hash",
            value=hashlib.md5(content, usedforsecurity=False).hexdigest(),
        )
        for attributes in annotations:
            ElementTree.SubElement(root, "feature", name="plagiarism", **attributes)
        metadata_path = (directory / reference).with_suffix(".xml")
        ElementTree.ElementTree(root).write(
            metadata_path, encoding="utf-8", xml_declaration=True,
        )
        return metadata_path

    return write


@pytest.fixture
def search_corpus(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    import numpy as np
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import app.models
    from app.core.database import Base
    from app.models.references import ReferenceDocument, ReferenceSegment
    from app.repositories.references import ReferenceRepository
    from app.services.analysis import semantic_similarity
    from app.services.analysis.text_preprocessing import preprocess_text
    from app.services.references.corpus_index import prepare_corpus_index

    query = "Orchard fruit trees."
    paraphrase = "Pomaceous harvest vegetation."
    extra = "Orchard fruit trees. Extra branches."
    unrelated = "Volcano magma ash."
    stopwords = "the and of to"
    oov = "xylophonicquartz"
    unmatched = "Unmatched query."
    vectors = {
        query: np.array([1, 0, 0], dtype=np.float32),
        paraphrase: np.array([0.8, 0.6, 0], dtype=np.float32),
        extra: np.array([-1, 0, 0], dtype=np.float32),
        unrelated: np.array([0, 0, 1], dtype=np.float32),
        stopwords: np.array([0.6, 0, 0.8], dtype=np.float32),
        oov: np.array([0, 0, 1], dtype=np.float32),
        unmatched: np.ones(3, dtype=np.float32) / np.sqrt(3),
    }
    reference_encoder = Mock(
        side_effect=lambda texts: np.stack([vectors[text] for text in texts])
    )
    query_encoder = Mock(side_effect=lambda text: vectors[text].copy())
    monkeypatch.setattr(semantic_similarity, "generate_embeddings", reference_encoder)
    monkeypatch.setattr(semantic_similarity, "generate_embedding", query_encoder)
    database_url = f"sqlite:///{tmp_path / 'search.sqlite3'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        repository = ReferenceRepository(db)
        with db.begin():
            for document_id, title, rows in [
                (2, "Second source", [(40, 1, query), (12, 2, extra)]),
                (1, "First source", [
                    (81, 2, paraphrase), (7, 1, query),
                    (103, 3, unrelated), (215, 4, stopwords),
                ]),
            ]:
                repository.add(
                    ReferenceDocument(
                        id=document_id, title=title, source="pan-pc-11", language="en",
                        corpus_id=f"source-document{document_id:05}.txt",
                        content_sha256=hashlib.sha256(
                            "\n".join(text for _, _, text in rows).encode()
                        ).hexdigest(),
                        import_signature="b" * 64,
                    ),
                    [
                        ReferenceSegment(
                            id=segment_id, position=position, text_original=text,
                            text_clean=preprocess_text(text),
                            start_offset=(position - 1) * 200,
                            end_offset=(position - 1) * 200 + len(text),
                        )
                        for segment_id, position, text in rows
                    ],
                )
        index_dir = tmp_path / "index"
        preparation = prepare_corpus_index(repository, index_dir, batch_size=2)
        yield SimpleNamespace(
            repository=repository, index_dir=index_dir, generation=preparation.directory,
            database_url=database_url, vectors=vectors, query=query, paraphrase=paraphrase,
            extra=extra, stopwords=stopwords, oov=oov, unmatched=unmatched,
            reference_encoder=reference_encoder, query_encoder=query_encoder,
        )
    engine.dispose()


@pytest.fixture
def refresh_artifact_hash():
    import json

    def refresh(generation, filename):
        path = generation / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["sha256"][filename] = hashlib.sha256(
            (generation / filename).read_bytes()
        ).hexdigest()
        path.write_text(json.dumps(manifest), encoding="utf-8")

    return refresh
