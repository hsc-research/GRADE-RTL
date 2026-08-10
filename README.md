# LLM-for-RTL Evaluation Framework

A reproducible, failure-localizing framework for evaluating Verilog RTL generated
by large language models. Each candidate passes through five front-end stages:

```text
Port Signature (P) -> Compilation (C) -> Elaboration (E)
                    -> Module Completeness (M) -> Functional Equivalence (F)
```

Synthesis is intentionally separate from the correctness scorecard. A candidate
is **synthesis-eligible** after passing Compilation and Elaboration, but it is
counted as end-to-end correct only after passing all five stages.

## Release scope

This release contains the evaluation framework, three author-created smoke-test
designs, tests, CI, aggregate manuscript coverage data, generic Yosys synthesis,
and a credential-free Cadence Genus template. It does not contain proprietary
libraries or every raw paper experiment. Read [ARTIFACT_STATUS.md](ARTIFACT_STATUS.md)
before describing the package as a complete paper artifact.

## Why this version is safe to publish

- no API keys, SSH passwords, private hostnames, or institution-specific paths;
- no `sshpass`, disabled TLS verification, or disabled SSH host verification;
- import-safe modules: importing the package performs no network or EDA action;
- isolated run directories with explicit overwrite protection;
- every attempt preserves the prompt, raw response, extracted RTL, logs,
  metadata, hashes, and stage outcome;
- deterministic mock mode for offline testing;
- repository verifier and GitHub Actions workflow.

If credentials were committed in any earlier repository revision, rotate them
and publish this tree from a clean Git history. See [SECURITY.md](SECURITY.md).

## Requirements

- Python 3.10 or newer
- Icarus Verilog (`iverilog`)
- Yosys
- `requests`

Ubuntu/Debian example:

```bash
sudo apt-get update
sudo apt-get install -y iverilog yosys python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

For an offline environment with build dependencies already installed:

```bash
python -m pip install -e . --no-build-isolation
```

## Quick start: deterministic smoke test

The bundled mock run intentionally makes `half_adder` fail its first interface
check and recover on attempt 2. The other two designs pass on attempt 1.

```bash
llm-rtl-eval --provider mock --all --k 3 --run-id smoke
```

Expected aggregate behavior:

```text
E2E@1 = 2/3
E2E@3 = 3/3
SEY@3 = 3/3
```

Outputs are written to:

```text
results/smoke/
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

## Running a real provider

Copy `.env.example` to a private shell configuration and export only the
variables for the chosen provider. Never commit `.env`.

OpenAI-compatible example:

```bash
export OPENAI_API_KEY='...'
export OPENAI_MODEL='EXACT_MODEL_IDENTIFIER'
llm-rtl-eval \
  --provider openai \
  --model "$OPENAI_MODEL" \
  --design half_adder \
  --k 3 \
  --temperature 0 \
  --top-p 1 \
  --seed 7 \
  --run-id openai-half-adder
```

Supported adapters:

- `mock`
- `ollama`
- `openai`
- `deepseek`
- `anthropic`
- `gemini`
- `huggingface`

Provider metadata records the exact requested model, endpoint, sampling controls,
seed request, whether the provider accepted the seed, provider-reported model and
usage fields when returned, tool versions, and content hashes. API keys are never
written to results. The deterministic mock provider records a requested seed but
correctly marks it as not applied.

The OpenAI adapter defaults to the current `max_completion_tokens` field; set
`OPENAI_TOKEN_FIELD=max_tokens` only for a compatible endpoint that requires the
legacy field. The Hugging Face adapter uses the OpenAI-compatible inference router
at `https://router.huggingface.co/v1/chat/completions` and accepts `HF_TOKEN` (or
`HF_API_KEY` as a compatibility alias).

Plain HTTP is rejected for remote provider endpoints, embedded credentials and
credential-bearing query parameters are rejected, and provider error bodies are
not copied into logs. Plain HTTP is allowed only for localhost, enabling a local
Ollama server.

## Adding a design

1. Add a fixed prompt under `prompts/`.
2. Add trusted reference RTL under `reference/DESIGN/`.
3. Add an entry to `designs.json`.
4. Optionally add deterministic mock responses under
   `mock_responses/DESIGN/attempt_N.v`.
5. Preserve any third-party RTL license and update
   `THIRD_PARTY_LICENSES.md`.

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

Port names, directions, widths, and signedness are compared against the trusted
reference. If a benchmark intentionally permits different candidate port names,
provide an explicit `port_aliases` mapping in `designs.json`; aliases are never
inferred automatically.

## Stage semantics

### P: Port Signature

- extracts complete modules from the model response;
- requires the configured top module;
- compares candidate and reference port names, directions, widths, and
  signedness;
- rejects missing, extra, duplicated, or incompatible ports.

### C: Compilation

- invokes Icarus Verilog with the configured language generation;
- wraps the candidate with `` `default_nettype none``;
- enables warnings, including implicit-net diagnostics.

### E: Elaboration

- invokes Yosys `hierarchy -check` using the configured top module;
- rejects missing submodules, unresolved hierarchy, and invalid parameters.

### M: Module Completeness

- deterministic static rules detect placeholders, empty logic, undriven
  outputs, malformed modules, empty procedural blocks, and optional missing
  `default` branches;
- Yosys `proc; opt; check -assert` detects structural problems;
- the full rules are implemented in `src/llm_rtl_eval/parsing.py` and
  `src/llm_rtl_eval/stages.py`.

### F: Functional Equivalence

- reference and candidate designs are normalized separately in Yosys;
- both are flattened and copied into an equivalence miter;
- `equiv_simple`, bounded induction, and `equiv_status -assert` are run;
- a disproved, timed-out, or inconclusive proof is a failure.

The configured induction depth is stored in the attempt result. Users evaluating
stateful designs should validate that the chosen Yosys proof strategy matches
the claims in their paper.

## Bounded refinement

Refinement is driven by the earliest failing stage. Each later prompt contains a
compact diagnostic and a stage-specific clarification. The framework does not
edit RTL by hand, provide a direct code patch, or change target functionality.
The original prompt file remains unchanged; every attempt receives its own
snapshot.

`K=3` is the default fixed interaction budget, not a claim of universal
optimality. Increase it only when the experimental question explicitly concerns
larger agentic repair budgets.

## Metrics

For each design, stage flags indicate whether that stage was passed by at least
one attempt within the budget. The framework reports:

- stage-wise P/C/E/M/F pass rates;
- conditional yields `C|P`, `E|C`, `M|E`, and `F|M`;
- `E2E@1`: full success on attempt 1;
- `E2E@K`: full success within K attempts;
- `SEY@K`: at least one attempt passes C and E;
- ETS: refinements before first success;
- TTFP: cumulative wall-clock seconds to first success;
- first-failure and root-cause shares among unsolved designs.

The implementation checks that:

```text
E2E@1 <= E2E@K <= SEY@K
```

## Synthesis

Synthesis is not a sixth front-end correctness stage.

Generic technology-independent Yosys synthesis:

```bash
python scripts/synthesize.py \
  results/smoke/half_adder/attempt_2/candidate.v \
  --top half_adder \
  --output results/smoke/half_adder/generic_synthesis
```

`synthesis/genus_template.tcl` is a credential-free starting point for an
authorized Cadence environment. It relies on environment variables and does not
include foundry paths, licenses, remote credentials, or private hostnames.

## Aggregate manuscript data

`paper_results/coverage_within_k.csv` and
`paper_results/recompute_aggregate_metrics.py` reproduce the aggregate within-K
stage rates, conditional yields, E2E@K, SEY@K, and first-failure shares shown in
the manuscript coverage table.

They cannot reproduce E2E@1, ETS, or TTFP because the supplied source archive did
not contain raw attempt-level logs. This limitation is explicit to prevent
accidental fabrication of those quantities.

## Verification

Run unit and mock-integration tests:

```bash
pytest -q
```

Run the repository hygiene check:

```bash
python scripts/verify_repository.py
```

With Icarus Verilog and Yosys installed, run the real-tool smoke test:

```bash
python scripts/verify_repository.py --require-tools --smoke
```

GitHub Actions repeats syntax, tests, security scanning, aggregate-paper metric
recomputation, and real-tool smoke evaluation on a clean runner. Before making a
release public, confirm the private workflow passes on every configured Python
version, then generate `SHA256SUMS` and run the public-release verifier.

## Verification scope

The bundled aggregate manuscript CSV reproduces only within-budget stage rates,
conditional yields, E2E@K, SEY@K, and first-failure shares. It cannot recover
E2E@1, ETS, TTFP, raw FPGA/ASIC reports, or individual LLM outputs because those
assets were absent from the archive supplied for this release audit. See
[ARTIFACT_STATUS.md](ARTIFACT_STATUS.md) and
[VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).

## Citation and license

See `CITATION.cff`. Framework code and bundled smoke RTL are MIT licensed.
Third-party EDA tools, provider services, and any separately added benchmark RTL
remain under their own licenses and terms.
