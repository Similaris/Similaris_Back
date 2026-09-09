import hashlib
from xml.etree import ElementTree

import pytest

from app.services.references.pan_corpus import (
    PanCorpusError,
    iter_documents,
    read_annotations,
    read_content,
    read_metadata,
)


def test_reads_pan_metadata_and_preserves_original_bytes(write_pan_document):
    original = "\ufeff  The ocean.\r\n\r\nBlue whales swim.  "
    path = write_pan_document("source-document00001.txt", original)
    document = read_metadata(path, "source")
    text, digest = read_content(document)
    assert document.reference == "source-document00001.txt"
    assert document.language == "en"
    assert text == original
    assert digest == hashlib.sha256(original.encode("utf-8")).hexdigest()


def test_source_and_suspicious_documents_are_kept_separate(corpus_dir, write_pan_document):
    write_pan_document("source-document00002.txt")
    write_pan_document("source-document00001.txt")
    write_pan_document("suspicious-document00001.txt")
    assert [doc.reference for doc in iter_documents(corpus_dir, "source")] == [
        "source-document00001.txt", "source-document00002.txt",
    ]
    assert len(list(iter_documents(corpus_dir, "suspicious"))) == 1


def test_outer_root_selects_external_corpus_not_intrinsic(corpus_dir, write_pan_document):
    path = write_pan_document("suspicious-document00001.txt")
    intrinsic = corpus_dir.parent / "intrinsic-detection-corpus"
    intrinsic.mkdir()
    (intrinsic / path.name).write_bytes(path.read_bytes())
    (intrinsic / path.with_suffix(".txt").name).write_bytes(path.with_suffix(".txt").read_bytes())
    documents = list(iter_documents(corpus_dir.parent, "suspicious"))
    assert len(documents) == 1
    assert documents[0].metadata_path == path


def test_reads_external_and_source_less_ground_truth(write_pan_document):
    attributes = {
        "this_offset": "2", "this_length": "10",
        "source_reference": "source-document00001.txt",
        "source_offset": "7", "source_length": "11",
        "source_language": "en", "this_language": "en", "obfuscation": "low",
    }
    path = write_pan_document(
        "suspicious-document00001.txt",
        annotations=[attributes, {"this_offset": "20", "this_length": "5"}],
    )
    annotations = read_annotations(read_metadata(path, "suspicious"))
    assert annotations[0].source_reference == "source-document00001.txt"
    assert annotations[0].this_offset == 2
    assert annotations[0].source_length == 11
    assert annotations[0].attributes["obfuscation"] == "low"
    assert annotations[1].source_reference is None
    assert annotations[1].source_offset is None


@pytest.mark.parametrize("language", ["", " "])
def test_missing_language_is_not_guessed(write_pan_document, language):
    path = write_pan_document("source-document00001.txt", language=language)
    with pytest.raises(PanCorpusError, match="Idioma ausente"):
        read_metadata(path, "source")


def test_missing_text_is_reported(write_pan_document):
    path = write_pan_document("source-document00001.txt")
    path.with_suffix(".txt").unlink()
    with pytest.raises(PanCorpusError, match="Texto ausente"):
        read_metadata(path, "source")


def test_changed_download_is_rejected(write_pan_document):
    path = write_pan_document("source-document00001.txt")
    path.with_suffix(".txt").write_bytes(b"Changed.")
    with pytest.raises(PanCorpusError, match="MD5 divergente"):
        read_content(read_metadata(path, "source"))


def test_pan_hash_without_leading_zeroes_is_validated(write_pan_document):
    text = next(
        f"An ocean sample {index}."
        for index in range(1000)
        if hashlib.md5(
            f"An ocean sample {index}.".encode(), usedforsecurity=False,
        ).hexdigest().startswith("0")
    )
    path = write_pan_document("source-document00001.txt", text)
    tree = ElementTree.parse(path)
    checksum = tree.find("./feature[@name='md5Hash']")
    checksum.set("value", checksum.get("value").lstrip("0"))
    tree.write(path, encoding="utf-8")
    assert read_content(read_metadata(path, "source"))[0] == text


@pytest.mark.parametrize("reference", ["../escape.txt", "suspicious-document00001.txt"])
def test_invalid_reference_is_rejected(write_pan_document, reference):
    path = write_pan_document("source-document00001.txt")
    tree = ElementTree.parse(path)
    tree.getroot().set("reference", reference)
    tree.write(path, encoding="utf-8")
    with pytest.raises(PanCorpusError, match="Identificador"):
        read_metadata(path, "source")


def test_duplicate_corpus_copies_are_rejected(corpus_dir, write_pan_document):
    path = write_pan_document("source-document00001.txt")
    duplicate = corpus_dir / "another-copy"
    duplicate.mkdir()
    (duplicate / path.name).write_bytes(path.read_bytes())
    (duplicate / path.with_suffix(".txt").name).write_bytes(path.with_suffix(".txt").read_bytes())
    with pytest.raises(PanCorpusError, match="duplicada"):
        list(iter_documents(corpus_dir, "source"))


@pytest.mark.parametrize("attributes", [
    {"this_offset": "-1", "this_length": "5"},
    {"this_offset": "0", "this_length": "-1"},
    {"this_offset": "x", "this_length": "5"},
    {"this_offset": "0", "this_length": "5", "source_reference": "source-document00001.txt"},
])
def test_invalid_annotation_offsets_are_rejected(write_pan_document, attributes):
    path = write_pan_document("suspicious-document00001.txt", annotations=[attributes])
    with pytest.raises(PanCorpusError, match="ground truth"):
        read_annotations(read_metadata(path, "suspicious"))


def test_zero_length_annotations_from_pan_are_preserved(write_pan_document):
    path = write_pan_document(
        "suspicious-document00001.txt",
        annotations=[{
            "this_offset": "0", "this_length": "0",
            "source_reference": "source-document00001.txt",
            "source_offset": "0", "source_length": "0",
        }],
    )
    annotation = read_annotations(read_metadata(path, "suspicious"))[0]
    assert annotation.this_length == annotation.source_length == 0


def test_invalid_xml_has_a_clear_error(tmp_path):
    path = tmp_path / "source-document00001.xml"
    path.write_text("<document>", encoding="utf-8")
    with pytest.raises(PanCorpusError, match="XML invalido"):
        read_metadata(path, "source")


def test_empty_corpus_is_not_a_success(corpus_dir):
    with pytest.raises(PanCorpusError, match="Nenhum XML"):
        list(iter_documents(corpus_dir, "source"))
