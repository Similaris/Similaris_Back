from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import nltk
from nltk.corpus import stopwords

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_LINE_BREAK_HYPHEN = re.compile(r"(?<=\w)-[ \t]*\r?\n[ \t]*(?=\w)")


def _ensure_stopwords_corpus() -> None:
    """Garante que o corpus de stopwords do NLTK está disponível localmente."""
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        nltk.download("stopwords", quiet=True)


@lru_cache(maxsize=1)
def get_english_stopwords() -> frozenset[str]:
    """Retorna o conjunto de stopwords em inglês do NLTK."""
    _ensure_stopwords_corpus()
    return frozenset(stopwords.words("english"))


def tokenize(text: str) -> list[str]:
    """Normaliza Unicode e extrai tokens sem pontuação.

    Hífens inseridos por quebra de linha em PDFs são removidos somente na via
    lexical. O texto original e seus offsets permanecem intactos.
    """
    normalized = unicodedata.normalize("NFKC", text or "").replace("\u00ad", "")
    normalized = _LINE_BREAK_HYPHEN.sub("", normalized).casefold()
    return _TOKEN.findall(normalized)


def preprocess_tokens(text: str) -> list[str]:
    """Tokeniza o texto e remove as stopwords em inglês."""
    english_stopwords = get_english_stopwords()
    return [token for token in tokenize(text) if token not in english_stopwords]


def preprocess_text(text: str) -> str:
    """Aplica o pré-processamento lexical completo e retorna o texto limpo.

    Etapas: minúsculas, tokenização, remoção de pontuação e de stopwords
    em inglês (idioma do corpus de validação PAN-PC-11). O resultado
    alimenta o campo ``text_clean`` dos segmentos e a vetorização TF-IDF;
    o texto original deve ser mantido separado.
    """
    return " ".join(preprocess_tokens(text))
