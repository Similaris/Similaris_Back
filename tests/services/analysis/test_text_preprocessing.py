from app.services.analysis.text_preprocessing import (
    get_english_stopwords,
    preprocess_text,
    preprocess_tokens,
    tokenize,
)


def test_tokenize_converts_to_lowercase():
    assert tokenize("Plagiarism DETECTION System") == [
        "plagiarism",
        "detection",
        "system",
    ]


def test_tokenize_removes_punctuation_and_symbols():
    text = "Hello, world! (test): plagiarism; 100%._"

    assert tokenize(text) == ["hello", "world", "test", "plagiarism", "100"]


def test_tokenize_handles_empty_and_none_text():
    assert tokenize("") == []
    assert tokenize(None) == []
    assert tokenize(" \n\t ") == []


def test_preprocess_tokens_removes_english_stopwords():
    text = "The detection of plagiarism in the papers that were submitted"

    assert preprocess_tokens(text) == [
        "detection",
        "plagiarism",
        "papers",
        "submitted",
    ]


def test_preprocess_text_returns_clean_joined_text():
    text = "The student copied the original text without any citation!"

    assert preprocess_text(text) == "student copied original text without citation"


def test_preprocess_text_with_only_stopwords_returns_empty():
    assert preprocess_text("the of a an that and to in for") == ""


def test_get_english_stopwords_contains_common_words():
    stopwords_set = get_english_stopwords()

    assert {"the", "of", "and", "that"} <= stopwords_set
    assert "plagiarism" not in stopwords_set
