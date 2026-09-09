from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

DocumentKind = Literal["source", "suspicious"]


class PanCorpusError(ValueError):
    """Corpus incompleto ou metadados inconsistentes."""


@dataclass(frozen=True)
class PanDocument:
    reference: str
    language: str
    title: str
    text_path: Path
    metadata_path: Path
    md5: str | None


@dataclass(frozen=True)
class PlagiarismAnnotation:
    suspicious_reference: str
    this_offset: int
    this_length: int
    source_reference: str | None
    source_offset: int | None
    source_length: int | None
    attributes: dict[str, str]


def _xml(path: Path) -> ElementTree.Element:
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as error:
        raise PanCorpusError(f"XML invalido: {path}: {error}") from error
    if root.tag != "document":
        raise PanCorpusError(f"Raiz XML inesperada em {path}.")
    return root


def _reference(value: str | None, kind: DocumentKind) -> str:
    if value is None or not re.fullmatch(rf"{kind}-document\d+\.txt", value):
        raise PanCorpusError(f"Identificador de documento {kind} invalido: {value!r}.")
    return value


def read_metadata(path: Path, kind: DocumentKind) -> PanDocument:
    root = _xml(path)
    reference = _reference(root.get("reference"), kind)
    if path.with_suffix(".txt").name != reference:
        raise PanCorpusError(f"Nome do XML difere da referencia: {path}.")
    about = root.find("./feature[@name='about']")
    language = about.get("lang", "").strip().lower() if about is not None else ""
    if not language:
        raise PanCorpusError(f"Idioma ausente nos metadados: {path}.")
    title = about.get("title", reference) if about is not None else reference
    checksum = root.find("./feature[@name='md5Hash']")
    md5 = checksum.get("value") if checksum is not None else None
    if checksum is not None and (
        md5 is None or not re.fullmatch(r"[0-9a-fA-F]{1,32}", md5)
    ):
        raise PanCorpusError(f"MD5 invalido nos metadados: {path}.")
    text_path = path.with_suffix(".txt")
    if not text_path.is_file():
        raise PanCorpusError(f"Texto ausente: {text_path}.")
    return PanDocument(reference, language, title, text_path, path, md5)


def external_corpus_directory(directory: Path) -> Path:
    if not directory.is_dir():
        raise PanCorpusError(f"Diretorio do corpus inexistente: {directory}.")
    for root in (directory, directory / "pan-plagiarism-corpus-2011"):
        external = root / "external-detection-corpus"
        if external.is_dir():
            return external
    return directory


def iter_documents(directory: Path, kind: DocumentKind) -> Iterator[PanDocument]:
    if kind not in ("source", "suspicious"):
        raise ValueError("kind deve ser source ou suspicious.")
    directory = external_corpus_directory(directory)
    paths = sorted(directory.rglob(f"{kind}-document*.xml"))
    if not paths:
        raise PanCorpusError(f"Nenhum XML de documentos {kind} em {directory}.")
    seen: set[str] = set()
    for path in paths:
        document = read_metadata(path, kind)
        if document.reference in seen:
            raise PanCorpusError(
                f"Referencia duplicada no corpus: {document.reference}. "
                "Use somente uma copia do corpus externo."
            )
        seen.add(document.reference)
        yield document


def read_content(document: PanDocument) -> tuple[str, str]:
    content = document.text_path.read_bytes()
    if document.md5 is not None:
        actual = hashlib.md5(content, usedforsecurity=False).hexdigest()
        # O PAN serializa o digest como inteiro hexadecimal, sem zeros iniciais.
        if actual != document.md5.lower().zfill(32):
            raise PanCorpusError(f"MD5 divergente: {document.text_path}.")
    try:
        # Nao normalizar CRLF/BOM: os offsets do ground truth usam o original.
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PanCorpusError(f"Texto nao e UTF-8: {document.text_path}.") from error
    if not text.strip():
        raise PanCorpusError(f"Documento vazio: {document.text_path}.")
    return text, hashlib.sha256(content).hexdigest()


def _integer(attributes: dict[str, str], name: str, minimum: int) -> int:
    try:
        value = int(attributes[name])
    except (KeyError, ValueError) as error:
        raise PanCorpusError(f"Atributo de ground truth invalido: {name}.") from error
    if value < minimum:
        raise PanCorpusError(f"Atributo de ground truth fora do limite: {name}.")
    return value


def read_annotations(document: PanDocument) -> list[PlagiarismAnnotation]:
    _reference(document.reference, "suspicious")
    result = []
    for feature in _xml(document.metadata_path).findall("./feature[@name='plagiarism']"):
        attributes = dict(feature.attrib)
        source = attributes.get("source_reference")
        if source is not None:
            _reference(source, "source")
        result.append(
            PlagiarismAnnotation(
                suspicious_reference=document.reference,
                this_offset=_integer(attributes, "this_offset", 0),
                this_length=_integer(attributes, "this_length", 0),
                source_reference=source,
                source_offset=_integer(attributes, "source_offset", 0) if source else None,
                source_length=_integer(attributes, "source_length", 0) if source else None,
                attributes=attributes,
            )
        )
    return result
