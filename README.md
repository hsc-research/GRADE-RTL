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

## Framework overview

<p align="center">
  <img src="evaluation_flow.png"
       alt="GRADE-RTL framework: input preparation, RTL generation, five-stage front-end validation, bounded refinement, robustness metrics, and FPGA/ASIC implementation evidence"
       width="100%">
</p>

GRADE-RTL keeps two decisions separate:

1. **Response source:** `fixture`, `live`, or `replay`.
2. **EDA-tool mode:** real Icarus Verilog/Yosys, or test-only tool stubs.

Fixture responses are synthetic and can never become paper data. Live runs call
a genuine model. Replay runs re-evaluate provenance-checked responses captured
from a genuine live run. Paper-result verification requires live/replay responses
and real EDA tools.

### Which mode should I use?

| Goal | Mode | Model/API call? | Paper-result eligible? |
|---|---|---:|---:|
| Check installation, CI, stages, refinement, and metrics | `fixture` | No | No |
| Collect a new response from a local or API model | `live` | Yes | Yes, after strict verification |
| Re-evaluate an archived genuine response | `replay` | No | Yes, when provenance passes |

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

## Installation and first-time setup

GRADE-RTL requires:

- Python 3.10 or newer;
- Icarus Verilog (`iverilog`);
- Yosys.

`git clone` or `git pull` updates the source code but does **not** install the
Python command-line tools. The package must be installed into a Python 3.10+
environment before `llm-rtl-eval` becomes available.

### 1. Clone the repository

```bash
git clone https://github.com/hsc-research/GRADE-RTL.git
cd GRADE-RTL
```

### 2. Confirm the Python version

```bash
python3 --version
```

The version must be 3.10 or newer. Do not lower `requires-python` in
`pyproject.toml` merely to install under Python 3.9; the source targets Python
3.10 features.

Check whether a suitable interpreter is already available:

```bash
for p in python3.12 python3.11 python3.10; do
  if command -v "$p" >/dev/null 2>&1; then
    echo "Found: $(command -v "$p")"
    "$p" --version
  fi
done
```

On a module-based university or HPC server, inspect available Python modules:

```bash
module spider python 2>&1
module avail python 2>&1
```

Load the exact Python 3.10+ module shown by the server, for example:

```bash
module load python/3.11   # example only; use the name listed on your server
python3 --version
```

A Conda environment is also suitable:

```bash
conda create -p "$PWD/.grade-rtl-env" python=3.11 pip -y
conda activate "$PWD/.grade-rtl-env"
```

### 3. Create and activate a virtual environment

Use the selected Python 3.10+ executable explicitly. For example:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python --version
```

On Ubuntu/Debian, install the virtual-environment and EDA packages first when
needed:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv iverilog yosys
```

### 4. Install GRADE-RTL

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
hash -r
```

Confirm that the console commands were created inside the active environment:

```bash
which llm-rtl-eval
llm-rtl-eval --help
llm-rtl-eval --describe-modes
```

`which llm-rtl-eval` should resolve to a path under `.venv/bin/` or the active
Conda environment.

### 5. Verify the repository and real EDA tools

```bash
llm-rtl-doctor --require-tools
```

A successful check reports real Icarus Verilog and Yosys, the configured design
count, and the fixture directory. You can also inspect the tools directly:

```bash
which iverilog
iverilog -V
which yosys
yosys -V
```

Without installing the package, source-tree commands remain available:

```bash
PYTHONPATH=src python -m llm_rtl_eval.doctor --require-tools
PYTHONPATH=src python -m llm_rtl_eval.cli --describe-modes
```

### Every new terminal session

Activate the same environment before using the commands:

```bash
cd /path/to/GRADE-RTL
source .venv/bin/activate
```

If a Python module was required to create `.venv`, load that module first in
each new shell when your server does not preserve the interpreter path.

### Common installation problems

#### `llm-rtl-eval: command not found`

The package was not installed successfully, or the environment is not active.
Run:

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
hash -r
which llm-rtl-eval
```

#### `requires a different Python: 3.9 ... not in '>=3.10'`

The virtual environment was created with Python 3.9. Remove it and recreate it
with a newer interpreter:

```bash
deactivate 2>/dev/null || true
rm -rf .venv
python3.11 -m venv .venv   # or python3.10 / python3.12
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
```

#### `No module named venv`

Install the OS package that provides `venv`, or use Conda:

```bash
sudo apt-get install -y python3-venv
```

#### Icarus Verilog or Yosys is missing

Install or load the real tools before running validation:

```bash
sudo apt-get install -y iverilog yosys
# or, on a module-based system:
module avail iverilog yosys
```

#### The checkout does not recognize `--mode`

Confirm that the expected release is checked out:

```bash
grep '^version' pyproject.toml
grep -n -- '--mode' src/llm_rtl_eval/cli.py
git status
git pull --ff-only
```

Then reinstall the editable package so the command reflects the updated source:

```bash
python -m pip install -e '.[dev]'
hash -r
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
