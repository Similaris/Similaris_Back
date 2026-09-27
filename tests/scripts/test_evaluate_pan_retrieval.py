import pytest

from scripts.evaluate_pan_retrieval import RetrievalCounts, metrics


def test_retrieval_metrics_are_calculated_from_ground_truth_hits():
    result = metrics(RetrievalCounts(cases=4, predictions=8, hits=2, reciprocal_rank=1.5))

    assert result["precision_at_n"] == 0.25
    assert result["recall_at_n"] == 0.5
    assert result["f1_at_n"] == pytest.approx(1 / 3, abs=1e-6)
    assert result["mean_reciprocal_rank"] == 0.375
