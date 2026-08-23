# Fixture, Replay, and Live Modes

GRADE-RTL separates the **source of the RTL response** from the **EDA tools used
to validate it**.

## Verify the environment first

```bash
llm-rtl-doctor --require-tools
```

The command verifies the repository configuration and confirms that the
executables on `PATH` are real Icarus Verilog and Yosys rather than test stubs.
Before a live run, it can also check provider credentials and the model setting
without making a model call:

```bash
llm-rtl-doctor --require-tools --provider openai --model EXACT_MODEL_IDENTIFIER
```

## Decision guide

Select exactly one response source with `--mode`:

- Choose **fixture** when testing the repository, CI, metrics, or refinement logic.
- Choose **live** when collecting a new response from a real model.
- Choose **replay** when re-running a previously recorded genuine response without
  paying for or depending on the model/API again.

## Mode 1: Fixture

Fixture mode reads synthetic deterministic RTL files from:

```text
fixtures/llm_outputs/DESIGN/attempt_N.v
```

Run:

```bash
llm-rtl-eval --mode fixture --all --k 3 --run-id fixture-smoke
```

Properties:

```text
execution_mode     = fixture
response_origin    = synthetic_fixture
test_fixture       = true
paper_result       = false
paper-result use   = forbidden
```

Fixture mode can use real Icarus/Yosys for an integration test, but the response
is still synthetic and is never paper data.

## Mode 2: Live

Live mode calls an actual model through a local runtime or API adapter.

Example:

```bash
export OPENAI_API_KEY='...'
llm-rtl-eval \
  --mode live \
  --provider openai \
  --model EXACT_MODEL_IDENTIFIER \
  --design half_adder \
  --k 3 \
  --run-id live-half-adder \
  --paper-run
```

Properties:

```text
execution_mode     = live
response_origin    = live
test_fixture       = false
paper_result       = true only when --paper-run is supplied
paper-result use   = allowed only with real Icarus/Yosys
```

The run stores the prompt, raw provider response, provider metadata, extracted
RTL, tool logs, and hashes.

## Mode 3: Replay

Replay mode reads archived genuine responses from either:

1. a full previous GRADE-RTL run containing `run_manifest.json`; or
2. a compact bundle created by `scripts/export_replay.py` containing
   `replay_manifest.json`, the archived prompts, raw responses, and per-attempt
   provenance metadata.

Direct replay:

```bash
llm-rtl-eval \
  --mode replay \
  --replay-source results/live-half-adder \
  --design half_adder \
  --k 3 \
  --run-id replay-half-adder \
  --paper-run
```

Replay validates:

- source mode and origin;
- source model/provider identity;
- prompt SHA-256;
- raw-response SHA-256;
- fixture exclusion;
- source paper-result certification when `--paper-run` is requested.

Properties:

```text
execution_mode     = replay
response_origin    = recorded_live
test_fixture       = false
paper-result use   = allowed only if source and target runs pass the paper-result gate
```

## EDA tool modes

The three response modes above do not describe the EDA tools.

| Tool mode | Meaning | Paper use |
|---|---|---:|
| `real` | Real `iverilog` and `yosys` executables | Allowed with live/replay |
| `stub` | Temporary test scripts created inside Pytest | Forbidden |

The normal `llm-rtl-eval` CLI requires real EDA executables. Tool stubs are used
only by unit tests and are automatically detected from their path/version text.

## Selection summary

```bash
# Synthetic, deterministic framework test
llm-rtl-eval --mode fixture --all --k 3 --run-id fixture-smoke

# New genuine model response
llm-rtl-eval --mode live --provider PROVIDER --model MODEL \
  --design DESIGN --k 3 --run-id LIVE_RUN --paper-run

# Re-evaluate a genuine archived response
llm-rtl-eval --mode replay --replay-source SOURCE_RUN_OR_BUNDLE \
  --design DESIGN --k 3 --run-id REPLAY_RUN --paper-run
```

`--paper-run` does not make a run genuine by itself. It activates a strict gate:
fixture responses and tool stubs are rejected, while replay additionally
requires a source run that passed the paper-result gate.

## Verify any run

```bash
llm-rtl-verify-run results/RUN
```

For a paper result:

```bash
llm-rtl-verify-run --require-paper-result results/RUN
```

A valid paper result must report:

```text
mode in {live, replay}
origin in {live, recorded_live}
tool_mode=real
paper_result_eligible=true
paper_result=true
```

## Common errors

### `No fixture response for DESIGN attempt N`

The evaluator requested another refinement attempt, but no `attempt_N.v` or
`default.v` fixture exists. Add the intended fixture or investigate why the
previous attempt unexpectedly failed. Do not use fixture responses for paper
experiments.

### `Replay prompt mismatch`

The current prompt differs from the prompt used in the source run. Restore the
same prompt/configuration or collect a new live response.

### `Synthetic fixture runs cannot be marked as paper results`

Remove `--paper-run` or switch to live/replay mode.

### `Paper runs require real Icarus Verilog and Yosys`

Install the actual EDA tools and ensure test-stub directories are not first in
`PATH`.
