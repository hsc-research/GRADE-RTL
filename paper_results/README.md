# Aggregate Paper Results

`coverage_within_k.csv` is a machine-readable transcription of the final
within-budget coverage table used in the manuscript. Each entry is either
`PASS` or the earliest failed stage (`P`, `C`, `E`, `M`, or `F`).

Run:

```bash
python paper_results/recompute_aggregate_metrics.py \
  --output paper_results/aggregate_metrics.json
```

The script recomputes stage-wise rates, conditional yields, E2E@K, SEY@K,
and first-failure shares. It intentionally does **not** compute E2E@1, ETS, or
TTFP because the source archive did not include raw attempt-level logs. Do not
infer those metrics from the within-K table.

These aggregate files improve transparency but are not a substitute for the
raw model outputs, prompts, and tool logs listed as missing in
`ARTIFACT_STATUS.md`.
