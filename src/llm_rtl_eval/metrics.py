from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .models import AttemptResult, RunMetrics, STAGE_ORDER


@dataclass(slots=True)
class DesignSummary:
    design: str
    attempts: int
    selected_attempt: int
    selected_depth: int
    stage_pass_within_k: dict[str, int]
    e2e_at_1: int
    e2e_at_k: int
    sey_at_k: int
    first_success_attempt: int | None
    edits_to_success: int | None
    time_to_first_pass: float | None
    first_failure: str | None
    root_cause: str | None

    def to_row(self, k: int) -> dict[str, str | int | float]:
        row: dict[str, str | int | float] = {
            "design": self.design,
            "attempts": self.attempts,
            "selected_attempt": self.selected_attempt,
            "selected_depth": self.selected_depth,
            "E2E@1": self.e2e_at_1,
            f"E2E@{k}": self.e2e_at_k,
            f"SEY@{k}": self.sey_at_k,
            "A_i": self.first_success_attempt or "",
            "ETS": self.edits_to_success if self.edits_to_success is not None else "",
            "TTFP_seconds": (
                round(self.time_to_first_pass, 6)
                if self.time_to_first_pass is not None
                else ""
            ),
            "First_Failure": self.first_failure or "None",
            "Root_Cause": self.root_cause or "None",
        }
        row.update({stage: self.stage_pass_within_k[stage] for stage in STAGE_ORDER})
        return row


def summarize_design(attempts: list[AttemptResult], *, k: int) -> DesignSummary:
    if not attempts:
        raise ValueError("A design summary requires at least one attempt")
    attempts = sorted(attempts, key=lambda item: item.attempt)
    attempt_ids = [item.attempt for item in attempts]
    if len(attempt_ids) != len(set(attempt_ids)):
        raise ValueError("Attempt indices must be unique")
    if attempt_ids != list(range(1, len(attempts) + 1)):
        raise ValueError("Attempts must be consecutive and start at 1")
    if len(attempts) > k:
        raise ValueError("Number of attempts exceeds the configured refinement budget")
    if len({item.design for item in attempts}) != 1:
        raise ValueError("All attempts in a design summary must have the same design")
    if any(item.attempt < 1 or item.attempt > k for item in attempts):
        raise ValueError("Attempt index is outside the configured refinement budget")
    first_success = next((item for item in attempts if item.full_success), None)
    selected = first_success or max(attempts, key=lambda item: (item.depth, -item.attempt))
    stage_pass = {
        stage: int(any(item.stages.get(stage) and item.stages[stage].passed for item in attempts))
        for stage in STAGE_ORDER
    }
    cumulative_time = 0.0
    time_to_first_pass: float | None = None
    for item in attempts:
        cumulative_time += item.elapsed_seconds
        if first_success is not None and item.attempt == first_success.attempt:
            time_to_first_pass = cumulative_time
            break
    summary = DesignSummary(
        design=attempts[0].design,
        attempts=len(attempts),
        selected_attempt=selected.attempt,
        selected_depth=selected.depth,
        stage_pass_within_k=stage_pass,
        e2e_at_1=int(attempts[0].full_success),
        e2e_at_k=int(first_success is not None),
        sey_at_k=int(any(item.synthesis_eligible for item in attempts)),
        first_success_attempt=first_success.attempt if first_success else None,
        edits_to_success=(first_success.attempt - 1) if first_success else None,
        time_to_first_pass=time_to_first_pass,
        first_failure=None if first_success else selected.first_failure,
        root_cause=None if first_success else selected.root_cause,
    )
    validate_design_summary(summary)
    return summary


def validate_design_summary(summary: DesignSummary) -> None:
    values = [summary.stage_pass_within_k[stage] for stage in STAGE_ORDER]
    if any(value not in {0, 1} for value in values):
        raise ValueError(f"Stage flags must be binary for {summary.design}")
    if any(later > earlier for earlier, later in zip(values, values[1:])):
        raise ValueError(
            f"Stage flags are not monotonic for {summary.design}: {summary.stage_pass_within_k}"
        )
    if not (summary.e2e_at_1 <= summary.e2e_at_k <= summary.sey_at_k):
        raise ValueError(
            f"Expected E2E@1 <= E2E@K <= SEY@K for {summary.design}"
        )
    if summary.e2e_at_k and summary.stage_pass_within_k["F"] != 1:
        raise ValueError(f"Solved design {summary.design} must pass FE")
    if summary.sey_at_k and not (
        summary.stage_pass_within_k["C"] and summary.stage_pass_within_k["E"]
    ):
        raise ValueError(f"SEY design {summary.design} must pass C and E")
    if summary.e2e_at_k:
        if summary.first_failure is not None or summary.root_cause is not None:
            raise ValueError(f"Solved design {summary.design} may not have a final failure label")
    elif summary.first_failure not in STAGE_ORDER:
        raise ValueError(f"Unsolved design {summary.design} needs a valid first-failure stage")


def aggregate_metrics(summaries: Iterable[DesignSummary]) -> RunMetrics:
    summaries = list(summaries)
    if not summaries:
        raise ValueError("Cannot compute metrics for an empty run")
    count = len(summaries)
    stage_totals = {
        stage: sum(summary.stage_pass_within_k[stage] for summary in summaries)
        for stage in STAGE_ORDER
    }
    stage_rates = {stage: stage_totals[stage] / count for stage in STAGE_ORDER}
    conditional_yields: dict[str, float] = {}
    for previous, current in zip(STAGE_ORDER, STAGE_ORDER[1:]):
        denominator = stage_totals[previous]
        conditional_yields[f"{current}|{previous}"] = (
            stage_totals[current] / denominator if denominator else 0.0
        )
    solved = [summary for summary in summaries if summary.e2e_at_k]
    unsolved = [summary for summary in summaries if not summary.e2e_at_k]
    failure_counter = Counter(summary.first_failure for summary in unsolved)
    cause_counter = Counter(summary.root_cause for summary in unsolved)
    failure_shares = {
        stage: failure_counter[stage] / len(unsolved) if unsolved else 0.0
        for stage in STAGE_ORDER
    }
    cause_labels = ("compiler", "not-elaborated", "partial_module", "functional_mismatch")
    cause_shares = {
        label: cause_counter[label] / len(unsolved) if unsolved else 0.0
        for label in cause_labels
    }
    metrics = RunMetrics(
        designs=count,
        stage_rates=stage_rates,
        conditional_yields=conditional_yields,
        e2e_at_1=sum(summary.e2e_at_1 for summary in summaries) / count,
        e2e_at_k=sum(summary.e2e_at_k for summary in summaries) / count,
        sey_at_k=sum(summary.sey_at_k for summary in summaries) / count,
        ets=(
            sum(summary.edits_to_success or 0 for summary in solved) / len(solved)
            if solved
            else None
        ),
        ttfp_seconds=(
            sum(summary.time_to_first_pass or 0.0 for summary in solved) / len(solved)
            if solved
            else None
        ),
        unsolved=len(unsolved),
        first_failure_shares=failure_shares,
        root_cause_shares=cause_shares,
    )
    if not metrics.e2e_at_1 <= metrics.e2e_at_k <= metrics.sey_at_k:
        raise ValueError("Aggregate metrics violate E2E@1 <= E2E@K <= SEY@K")
    return metrics
