# GRADE-RTL

**Generated RTL Assessment through Design-flow Evaluation**

GRADE-RTL evaluates LLM-generated Verilog/SystemVerilog through five ordered
front-end stages:

```text
P: Port Signature
C: Compilation
E: Elaboration
M: Module Completeness
F: Functional Equivalence
```

The framework preserves every prompt, response, extracted RTL candidate, tool
script, tool log, stage result, hash, and run manifest. Synthesis is optional
and is not treated as a sixth correctness stage.

> **Artifact scope.** This release contains the executable framework, three
> author-created smoke designs, tests, provider adapters, and aggregate
> within-budget manuscript data. It is not a complete raw archive for all
> paper experiments. See [ARTIFACT_STATUS.md](ARTIFACT_STATUS.md).

## Three response modes

GRADE-RTL makes the source of generated RTL explicit:

| Mode | Response source | Calls an LLM? | Paper-result eligible? |
|---|---|---:|---:|
| `fixture` | Synthetic deterministic test RTL | No | **No** |
| `replay` | Archived response from a provenance-checked live run | No | Only if the source run passed the paper-result gate |
| `live` | A new local/API LLM call | Yes | Yes, with real EDA tools and `--paper-run` |

The response mode is independent of the EDA tools. The normal CLI always uses
real Icarus Verilog and Yosys. Short-lived tool stubs exist only inside unit
tests to exercise Python orchestration; they cannot be marked as paper data.

Print the mode guide at any time:

```bash
llm-rtl-eval --describe-modes
```

A detailed explanation is available in [MODES.md](MODES.md).

Select the mode explicitly with `--mode`:

```text
fixture -> test the framework with synthetic RTL
live    -> call a real model and collect a new response
replay  -> rerun a previously recorded genuine response
```

The legacy `--provider mock` spelling remains accepted only for backwards
compatibility and is always treated as non-paper fixture data.

## Installation

Requirements:

- Python 3.10 or newer
- Icarus Verilog (`iverilog`)
- Yosys

Ubuntu/Debian example:

```bash
sudo apt-get update
sudo apt-get install -y iverilog yosys python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Verify the checkout before running an experiment:

```bash
llm-rtl-doctor --require-tools
```

A successful check reports real Icarus Verilog and Yosys, the configured
benchmark count, and the fixture directory. Without installation, the same
source-tree check can be run as:

```bash
PYTHONPATH=src python -m llm_rtl_eval.doctor --require-tools
```

## Quick start

GRADE-RTL requires an explicit `--design DESIGN` selection or `--all`; it never
starts live/provider calls for an implicit design set.

### 1. Fixture mode: deterministic smoke test

Fixture mode uses synthetic RTL in `fixtures/llm_outputs/`. It is designed for
CI and local verification and is never accepted as paper data.

```bash
llm-rtl-eval \
  --mode fixture \
  --all \
  --k 3 \
  --run-id fixture-smoke
```

Expected aggregate behavior:

```text
E2E@1 = 2/3
E2E@3 = 3/3
SEY@3 = 3/3
```

The intended attempt pattern is:

- `priority_encoder`: passes on attempt 1;
- `ripple_carry_adder`: passes on attempt 1;
- `half_adder`: fails its first interface check and passes on attempt 2.

Verify the run:

```bash
llm-rtl-verify-run results/fixture-smoke
```

The verifier will report `mode=fixture`, `origin=synthetic_fixture`, and
`paper_result_eligible=false`.

Legacy commands using `--provider mock` are accepted as fixture mode, but new
scripts should use `--mode fixture`.

### 2. Live mode: call an actual model

Export credentials privately; never commit `.env` or API keys.

```bash
export OPENAI_API_KEY='...'
export OPENAI_MODEL='EXACT_MODEL_IDENTIFIER'

llm-rtl-eval \
  --mode live \
  --provider openai \
  --model "$OPENAI_MODEL" \
  --design half_adder \
  --k 3 \
  --temperature 0 \
  --top-p 1 \
  --seed 7 \
  --run-id live-openai-half-adder \
  --paper-run
```

Supported live providers and their usual environment variables:

| Provider | Credential | Model setting | Optional endpoint setting |
|---|---|---|---|
| `ollama` | none for localhost | `OLLAMA_MODEL` or `--model` | `OLLAMA_HOST` |
| `openai` | `OPENAI_API_KEY` | `OPENAI_MODEL` or `--model` | `OPENAI_BASE_URL` |
| `deepseek` | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` or `--model` | `DEEPSEEK_BASE_URL` |
| `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` or `--model` | `ANTHROPIC_ENDPOINT` |
| `gemini` | `GEMINI_API_KEY` | `GEMINI_MODEL` or `--model` | `GEMINI_ENDPOINT` |
| `huggingface` | `HF_TOKEN` or `HF_API_KEY` | `HF_MODEL` or `--model` | `HF_ENDPOINT` |

Use exact model identifiers and keep credentials in the shell environment. The
`.env.example` file lists the supported variables, but GRADE-RTL does not load
or commit secrets automatically. Check a provider configuration without making
an API call:

```bash
llm-rtl-doctor --require-tools --provider openai --model EXACT_MODEL_IDENTIFIER
```

`--paper-run` is optional but recommended for a run intended to support a
publication. It is accepted only when the response source is live/replay and
real Icarus Verilog and Yosys are detected.

Verify a publication run strictly:

```bash
llm-rtl-verify-run \
  --require-paper-result \
  results/live-openai-half-adder
```

### 3. Replay mode: rerun a genuine archived response

Replay mode makes no model/API call. It re-evaluates the exact prompts and raw
responses from a prior provenance-enabled run.

Directly replay a completed run directory:

```bash
llm-rtl-eval \
  --mode replay \
  --replay-source results/live-openai-half-adder \
  --design half_adder \
  --k 3 \
  --run-id replay-openai-half-adder \
  --paper-run
```

The current prompts must hash-match the source prompts. Raw-response hashes and
provenance metadata are also checked before evaluation.

For a smaller shareable replay bundle, export a live run that passed the paper-result gate:

```bash
python scripts/export_replay.py \
  results/live-openai-half-adder \
  replay_bundles/openai-half-adder
```

Then replay it:

```bash
llm-rtl-eval \
  --mode replay \
  --replay-source replay_bundles/openai-half-adder \
  --design half_adder \
  --k 3 \
  --run-id replay-bundle-openai-half-adder \
  --paper-run
```

Fixture runs cannot be exported or replayed as genuine model data.

## How mode and provenance are detected

Every `results/RUN/run_manifest.json` records:

```json
{
  "execution_mode": "fixture | replay | live",
  "response_origin": "synthetic_fixture | recorded_live | live",
  "tool_mode": "stub | real",
  "provider_paper_eligible": true,
  "paper_result_eligible": true,
  "paper_result": true
}
```

Each attempt's `generation_metadata.json` repeats the mode/origin flags and
stores prompt, response, and RTL hashes. Use:

```bash
llm-rtl-verify-run results/RUN
```

A run can support paper results only when all of the following hold:

```text
execution_mode in {live, replay}
response_origin in {live, recorded_live}
test_fixture = false
tool_mode = real
paper_result_eligible = true
paper_result = true
```

## GitHub Actions troubleshooting

If the real-tool integration test requests an unexpected second fixture
attempt, inspect the previous attempt's `M_yosys.log` and first-failure field.
GRADE-RTL v1.1.1 fixes a previous false positive in which Yosys output
`No latch inferred ...` was misread as an inferred latch. The regression suite
now distinguishes positive and negative latch messages and asserts the expected
attempt count for every smoke design.

Run the same gates locally before pushing:

```bash
pytest -q -p no:cacheprovider
llm-rtl-doctor --require-tools
python scripts/verify_repository.py --require-tools --smoke
```

## Output structure

```text
results/RUN/
├── run_manifest.json
├── attempts.json
├── results.csv
├── metrics.json
├── metrics.txt
└── DESIGN/attempt_N/
    ├── prompt.txt
    ├── raw_response.txt
    ├── candidate.v
    ├── generation_metadata.json
    ├── attempt_result.json
    └── P/C/E/M/F scripts and logs
```

## Adding a design

1. Add a fixed prompt under `prompts/`.
2. Add trusted reference RTL under `reference/DESIGN/`.
3. Add an entry to `designs.json`.
4. For fixture testing only, add synthetic responses under
   `fixtures/llm_outputs/DESIGN/attempt_N.v` or `default.v`.
5. Preserve third-party RTL licenses and update `THIRD_PARTY_LICENSES.md`.

Example configuration:

```json
{
  "my_design": {
    "prompt": "prompts/my_design.txt",
    "reference": "reference/my_design",
    "top_module": "my_design",
    "reference_top": "my_design",
    "language": "verilog",
    "require_case_default": false,
    "description": "Short design description"
  }
}
```

## Stage semantics

### P: Port Signature

- extracts complete modules from the model response;
- requires the configured top module;
- compares candidate and reference port names, directions, widths, and signedness;
- rejects missing, extra, duplicated, or incompatible ports.

### C: Compilation

- invokes Icarus Verilog in the configured language mode;
- wraps the candidate with `` `default_nettype none``;
- enables warnings, including implicit-net diagnostics.

### E: Elaboration

- invokes Yosys `hierarchy -check` using the configured top module;
- rejects missing submodules, unresolved hierarchy, and invalid parameters.

### M: Module Completeness

- deterministic source rules detect placeholders, empty logic, undriven
  outputs, malformed modules, empty procedural blocks, and optional missing
  `default` branches;
- Yosys `proc; opt; check -assert` detects structural problems;
- the full rules are in `src/llm_rtl_eval/parsing.py` and
  `src/llm_rtl_eval/stages.py`.

### F: Functional Equivalence

- reference and candidate designs are normalized separately in Yosys;
- both are flattened and copied into an equivalence miter;
- `equiv_simple`, bounded induction, and `equiv_status -assert` are run;
- disproved, timed-out, or inconclusive proofs fail.

## Bounded refinement and metrics

Refinement is driven by the earliest failing stage. Later prompts contain a
compact diagnostic and a stage-specific clarification. The framework does not
edit RTL by hand, provide a direct code patch, or change target functionality.

`K=3` is the default total-attempt budget, not a universal optimum.

The framework reports:

- stage-wise P/C/E/M/F pass rates;
- conditional yields `C|P`, `E|C`, `M|E`, and `F|M`;
- `E2E@1`: full success on attempt 1;
- `E2E@K`: full success within K total attempts;
- `SEY@K`: at least one attempt passes C and E;
- ETS and TTFP;
- first-failure and root-cause shares among unsolved designs.

The implementation enforces:

```text
E2E@1 <= E2E@K <= SEY@K
```

## Synthesis

Synthesis is not a sixth front-end correctness stage.

Generic Yosys synthesis:

```bash
python scripts/synthesize.py \
  results/fixture-smoke/half_adder/attempt_2/candidate.v \
  --top half_adder \
  --output results/fixture-smoke/half_adder/generic_synthesis
```

`synthesis/genus_template.tcl` is a credential-free starting point for an
authorized Cadence environment. It contains no foundry paths, credentials, or
private hosts.

## Aggregate manuscript data

`paper_results/coverage_within_k.csv` and
`paper_results/recompute_aggregate_metrics.py` reproduce the aggregate within-K
stage rates, conditional yields, E2E@K, SEY@K, and first-failure shares included
in this framework-and-aggregate-results release.

They cannot reproduce E2E@1, ETS, TTFP, raw FPGA/ASIC reports, or individual LLM
outputs because those assets were absent from the source archive supplied for
this release. This limitation is explicit in [ARTIFACT_STATUS.md](ARTIFACT_STATUS.md).

## Verification

Run the complete Python test suite:

```bash
pytest -q
```

Run repository checks:

```bash
python scripts/verify_repository.py
```

With real tools, run the deterministic integration smoke test:

```bash
python scripts/verify_repository.py --require-tools --smoke
```

Before a public release:

```bash
python scripts/generate_checksums.py
python scripts/verify_repository.py --public-release --require-tools --smoke
```

GitHub Actions installs real Icarus Verilog and Yosys and runs all of these
checks on a clean runner.

## Security, citation, and license

- Never commit provider keys, `.env`, private hosts, or foundry paths.
- See [SECURITY.md](SECURITY.md) before publishing a repository derived from an
  older private tree.
- See `CITATION.cff` for citation metadata.
- Framework code and bundled smoke RTL are MIT licensed. Third-party tools,
  services, and separately added benchmark RTL retain their own terms.
