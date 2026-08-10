#!/usr/bin/env python3
"""Recompute manuscript aggregate metrics from coverage_within_k.csv.

The CSV contains one final within-budget outcome per model/design pair. It does
not contain attempt-level data and therefore cannot reproduce E2E@1, ETS, or
TTFP. Those quantities require the raw attempt logs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

STAGES = ("P", "C", "E", "M", "F")


def flags(outcome: str) -> dict[str, int]:
    if outcome == "PASS":
        return {stage: 1 for stage in STAGES}
    if outcome not in STAGES:
        raise ValueError(f"Invalid outcome: {outcome}")
    index = STAGES.index(outcome)
    return {stage: int(position < index) for position, stage in enumerate(STAGES)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("coverage_within_k.csv"),
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with args.csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grouped[row["model"]].append(row)

    result = {}
    for model, rows in grouped.items():
        stage_counts = Counter()
        failure_counts = Counter()
        for row in rows:
            outcome = row["outcome"]
            stage_counts.update(flags(outcome))
            if outcome != "PASS":
                failure_counts[outcome] += 1
        n = len(rows)
        rates = {stage: stage_counts[stage] / n for stage in STAGES}
        yields = {}
        for previous, current in zip(STAGES, STAGES[1:]):
            denominator = stage_counts[previous]
            yields[f"{current}|{previous}"] = (
                stage_counts[current] / denominator if denominator else 0.0
            )
        unsolved = sum(failure_counts.values())
        first_failure = {
            stage: failure_counts[stage] / unsolved if unsolved else 0.0
            for stage in STAGES
        }
        result[model] = {
            "designs": n,
            "stage_rates": rates,
            "conditional_yields": yields,
            "E2E@K": sum(row["outcome"] == "PASS" for row in rows) / n,
            "SEY@K": sum(flags(row["outcome"])["E"] for row in rows) / n,
            "first_failure_shares": first_failure,
        }

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
