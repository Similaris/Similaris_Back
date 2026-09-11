import json
from dataclasses import FrozenInstanceError, asdict

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.services.references.search_contracts import (
    ReferenceDocumentMatch,
    ReferenceMatch,
    ReferenceSearchOptions,
    ReferenceSearchResult,
    ReferenceSegmentMatch,
)


def test_search_defaults_follow_current_settings(monkeypatch):
    monkeypatch.setattr(settings, "reference_search_mode", "lexical")
    monkeypatch.setattr(settings, "reference_search_top_n", 9)
    monkeypatch.setattr(settings, "reference_search_semantic_threshold", -0.25)
    monkeypatch.setattr(settings, "lexical_cosine_threshold", 0.6)
    monkeypatch.setattr(settings, "lexical_jaccard_threshold", 0.3)

    options = ReferenceSearchOptions()

    assert options.mode == "lexical"
    assert options.top_n == 9
    assert options.semantic_threshold == -0.25
    assert options.lexical_cosine_threshold == 0.6
    assert options.lexical_jaccard_threshold == 0.3


def test_overrides_share_the_same_defaults_as_direct_options(monkeypatch):
    monkeypatch.setattr(settings, "reference_search_top_n", 9)
    assert ReferenceSearchOptions.from_overrides() == ReferenceSearchOptions()
    options = ReferenceSearchOptions.from_overrides(
        mode="lexical", top_n=2, semantic_threshold=-1,
        lexical_cosine_threshold=0, lexical_jaccard_threshold=1,
    )
    assert options == ReferenceSearchOptions(
        mode="lexical", top_n=2, semantic_threshold=-1,
        lexical_cosine_threshold=0, lexical_jaccard_threshold=1,
    )


def test_invalid_overrides_are_validated():
    with pytest.raises(TypeError, match="top_n"):
        ReferenceSearchOptions.from_overrides(top_n=True)


@pytest.mark.parametrize("top_n", [True, False, 1.0, "5", None])
def test_top_n_requires_an_integer(top_n):
    with pytest.raises(TypeError, match="top_n"):
        ReferenceSearchOptions(top_n=top_n)


@pytest.mark.parametrize("top_n", [0, -1])
def test_top_n_must_be_positive(top_n):
    with pytest.raises(ValueError, match="top_n"):
        ReferenceSearchOptions(top_n=top_n)


@pytest.mark.parametrize(
    "name", ["lexical_cosine_threshold", "lexical_jaccard_threshold", "semantic_threshold"]
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 1.01, -1.01])
def test_thresholds_must_be_finite_and_in_range(name, value):
    with pytest.raises(ValueError, match=name):
        ReferenceSearchOptions(**{name: value})


@pytest.mark.parametrize("name", ["lexical_cosine_threshold", "lexical_jaccard_threshold"])
def test_lexical_thresholds_do_not_accept_negatives(name):
    with pytest.raises(ValueError, match=name):
        ReferenceSearchOptions(**{name: -0.01})


@pytest.mark.parametrize(
    "name", ["lexical_cosine_threshold", "lexical_jaccard_threshold", "semantic_threshold"]
)
@pytest.mark.parametrize("value", [True, False, "0.5", None])
def test_thresholds_reject_non_numeric_values(name, value):
    with pytest.raises(TypeError, match=name):
        ReferenceSearchOptions(**{name: value})


@pytest.mark.parametrize("semantic_threshold", [-1.0, 0.0, 1.0])
@pytest.mark.parametrize("lexical_threshold", [0.0, 1.0])
def test_threshold_boundaries_are_accepted(semantic_threshold, lexical_threshold):
    options = ReferenceSearchOptions(
        semantic_threshold=semantic_threshold,
        lexical_cosine_threshold=lexical_threshold,
        lexical_jaccard_threshold=lexical_threshold,
        top_n=1,
    )
    assert options.semantic_threshold == semantic_threshold


@pytest.mark.parametrize("mode", ["hybrid", "", "Semantic"])
def test_unknown_modes_are_rejected(mode):
    with pytest.raises(ValueError, match="mode"):
        ReferenceSearchOptions(mode=mode)


@pytest.mark.parametrize("mode", [None, 1, False])
def test_mode_requires_a_string(mode):
    with pytest.raises(TypeError, match="mode"):
        ReferenceSearchOptions(mode=mode)


def test_settings_read_search_configuration_from_environment(monkeypatch):
    monkeypatch.setenv("REFERENCE_SEARCH_MODE", "lexical")
    monkeypatch.setenv("REFERENCE_SEARCH_TOP_N", "7")
    monkeypatch.setenv("REFERENCE_SEARCH_SEMANTIC_THRESHOLD", "-0.4")
    configured = Settings(_env_file=None)

    assert configured.reference_search_mode == "lexical"
    assert configured.reference_search_top_n == 7
    assert configured.reference_search_semantic_threshold == -0.4


@pytest.mark.parametrize(
    "name,value",
    [
        ("reference_search_mode", "hybrid"),
        ("reference_search_top_n", 0),
        ("reference_search_top_n", 1.5),
        ("reference_search_semantic_threshold", 1.01),
        ("reference_search_semantic_threshold", -1.01),
        ("reference_search_semantic_threshold", float("nan")),
    ],
)
def test_invalid_search_settings_are_rejected(name, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


def test_result_is_immutable_and_serializable_without_orm_objects():
    options = ReferenceSearchOptions()
    match = ReferenceMatch(
        source_document=ReferenceDocumentMatch(
            id=3, corpus_id="source-document00003.txt",
            source="pan-pc-11", language="en", title="A source",
        ),
        source_segment=ReferenceSegmentMatch(
            id=11, position=2, start_offset=20, end_offset=32,
            text_original="Source text.",
        ),
        lexical_score=1.0, semantic_score=-0.2, jaccard_score=1.0,
    )
    result = ReferenceSearchResult(
        options=options, index_fingerprint="a" * 64,
        matches=(match,), comparison_ms=12.5,
    )
    decoded = json.loads(json.dumps(asdict(result), allow_nan=False))

    assert decoded["options"]["mode"] == "semantic"
    assert decoded["matches"][0]["source_document"]["id"] == 3
    assert decoded["matches"][0]["source_segment"]["text_original"] == "Source text."
    assert decoded["matches"][0]["semantic_score"] == -0.2
    assert decoded["comparison_ms"] == 12.5
    with pytest.raises(FrozenInstanceError):
        result.comparison_ms = 0
