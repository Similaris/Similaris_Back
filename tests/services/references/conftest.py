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
