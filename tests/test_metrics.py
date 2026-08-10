from __future__ import annotations

import pytest

from llm_rtl_eval.metrics import aggregate_metrics, summarize_design
from llm_rtl_eval.models import AttemptResult, StageResult


def make_attempt(
    design: str,
    attempt: int,
    passed_depth: int,
    *,
    elapsed: float = 1.0,
) -> AttemptResult:
    order = ["P", "C", "E", "M", "F"]
    stages = {}
    for index, stage in enumerate(order):
        if index < passed_depth:
            status = "PASS"
        elif index == passed_depth:
            status = "FAIL"
        else:
            status = "SKIP"
        stages[stage] = StageResult(stage, status)  # type: ignore[arg-type]
    first_failure = None if passed_depth == 5 else order[passed_depth]
    cause = {
        "P": "compiler",
        "C": "compiler",
        "E": "not-elaborated",
        "M": "partial_module",
        "F": "functional_mismatch",
        None: None,
    }[first_failure]
    return AttemptResult(
        design=design,
        attempt=attempt,
        provider="mock",
        model="mock",
        elapsed_seconds=elapsed,
        stages=stages,
        first_failure=first_failure,
        root_cause=cause,
        prompt_path="prompt.txt",
        raw_response_path="raw.txt",
        rtl_path="candidate.v",
        metadata_path="metadata.json",
    )


def test_summary_recovers_on_attempt_two() -> None:
    summary = summarize_design(
        [make_attempt("d", 1, 0, elapsed=1.0), make_attempt("d", 2, 5, elapsed=2.0)],
        k=3,
    )
    assert summary.e2e_at_1 == 0
    assert summary.e2e_at_k == 1
    assert summary.sey_at_k == 1
    assert summary.first_success_attempt == 2
    assert summary.edits_to_success == 1
    assert summary.time_to_first_pass == 3.0
    assert summary.first_failure is None


def test_unsolved_summary_uses_deepest_attempt() -> None:
    summary = summarize_design(
        [make_attempt("d", 1, 1), make_attempt("d", 2, 3), make_attempt("d", 3, 2)],
        k=3,
    )
    assert summary.selected_attempt == 2
    assert summary.first_failure == "M"
    assert summary.root_cause == "partial_module"
    assert summary.sey_at_k == 1
    assert summary.e2e_at_k == 0


def test_aggregate_metrics_obey_metric_order() -> None:
    solved_first = summarize_design([make_attempt("a", 1, 5)], k=3)
    solved_second = summarize_design([make_attempt("b", 1, 0), make_attempt("b", 2, 5)], k=3)
    unsolved = summarize_design([make_attempt("c", 1, 3)], k=3)
    metrics = aggregate_metrics([solved_first, solved_second, unsolved])
    assert metrics.e2e_at_1 == pytest.approx(1 / 3)
    assert metrics.e2e_at_k == pytest.approx(2 / 3)
    assert metrics.sey_at_k == 1.0
    assert metrics.ets == pytest.approx(0.5)
    assert metrics.ttfp_seconds == pytest.approx(1.5)
    assert metrics.first_failure_shares["M"] == 1.0


def test_invalid_nonmonotonic_stage_flags_are_rejected() -> None:
    attempt = make_attempt("bad", 1, 2)
    attempt.stages["M"] = StageResult("M", "PASS")
    with pytest.raises(ValueError, match="not monotonic"):
        summarize_design([attempt], k=3)


def test_summary_rejects_duplicate_attempt_indices() -> None:
    first = make_attempt("d", 1, 5)
    duplicate = make_attempt("d", 1, 5)
    with pytest.raises(ValueError, match="unique"):
        summarize_design([first, duplicate], k=3)


def test_summary_rejects_nonconsecutive_attempt_indices() -> None:
    first = make_attempt("d", 1, 0)
    third = make_attempt("d", 3, 5)
    with pytest.raises(ValueError, match="consecutive"):
        summarize_design([first, third], k=3)
