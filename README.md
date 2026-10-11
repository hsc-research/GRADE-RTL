# GRADE-RTL

**Generated RTL Assessment through Design-flow Evaluation**

GRADE-RTL evaluates LLM-generated Verilog/SystemVerilog through five ordered
front-end checks: **Port Signature → Compilation → Elaboration → Module
Completeness → Functional Equivalence** (P/C/E/M/F). It records prompts,
responses, candidate RTL, tool logs, stage outcomes, and refinement metrics.
Synthesis is a separate, optional step.

> **Release scope:** this repository contains the evaluation framework, three
> author-created synthetic smoke designs, and aggregate results for an earlier
> **ten-design, nine-model** study. It does not include all study prompts,
> reference RTL, model responses, attempt logs, or FPGA/ASIC reports. The smoke
> examples test the software; they are not model-performance evidence. See
> [Artifact status](ARTIFACT_STATUS.md) and the
> [machine-readable manifest](paper_artifact_manifest.json).

<p align="center">
  <img src="evaluation_flow.png"
       alt="GRADE-RTL flow: input preparation, RTL generation, staged validation, bounded refinement, metrics, and separate implementation evidence"
       width="100%">
</p>

## Start here

- [Installation](#installation): set up Python and EDA tools
- [Fixture quick start](#fixture-quick-start): run without a model or API key
- [Choose a response mode](#choose-a-response-mode): fixture, live, or replay
- [Verification](#verification): check the committed release and run artifacts
- [Project layout](#project-layout): find code, examples, and study aggregates
- [Limits and reproducibility](#limits-and-reproducibility): understand what a result establishes

## Installation

Requirements: **Python 3.10+**, **Icarus Verilog** (`iverilog`), and **Yosys** on
`PATH`. The commands below use a Unix shell and run from the repository root.
Use the Python and EDA modules provided by your HPC environment when applicable.

On Ubuntu/Debian, install the OS dependencies if needed:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv iverilog yosys
```

Clone the repository, select the revision you intend to evaluate, and install
it into a virtual environment:

```bash
git clone https://github.com/hsc-research/GRADE-RTL.git
cd GRADE-RTL
# If needed: git checkout <branch, tag, or commit>
python3 --version                     # must be 3.10 or newer
python3 -m venv .venv
source .venv/bin/activate
python scripts/generate_checksums.py --check
python -m pip install -e '.[dev]'
llm-rtl-doctor --require-tools
```

The checksum command checks the existing receipt without changing it. Investigate
an unexpected mismatch before proceeding. A receipt establishes file consistency;
it does not authenticate an author or protect against replacement of both files
and receipt.

Activate the same environment in each new terminal:

```bash
cd /path/to/GRADE-RTL
source .venv/bin/activate
```

Cloning or pulling does not install the console commands. If `llm-rtl-eval` is
not found, check `which python`, activate the environment, and rerun the editable
installation. If Python is too old, create the environment with an available
3.10+ interpreter instead of changing `requires-python`.

For source-tree use after installing dependencies:

```bash
PYTHONPATH=src python -m llm_rtl_eval.cli --help
PYTHONPATH=src python -m llm_rtl_eval.doctor --require-tools
```

## Fixture quick start

This run makes **no model/API call**. It evaluates deterministic synthetic RTL
with real Icarus Verilog and Yosys:

```bash
llm-rtl-eval --mode fixture --all --k 3 --run-id fixture-smoke
llm-rtl-verify-run results/fixture-smoke
cat results/fixture-smoke/metrics.txt
```

Expected behavior:

- `priority_encoder` and `ripple_carry_adder` pass on attempt 1
- `half_adder` fails its first port check and passes on attempt 2
- E2E@1 = 2/3; E2E@3 = 1; SEY@3 = 1
- The manifest identifies `synthetic_fixture` responses and a non-paper run

`--k 3` means at most **three total attempts**, or two refinements after the
initial attempt. Use a new `--run-id` for another run; existing output is
protected unless `--overwrite` is supplied. List available designs with
`llm-rtl-eval --list-designs`.

## Choose a response mode

Response source and EDA-tool mode are separate. Fixture data remain synthetic
even when checked by real EDA tools; short-lived tool stubs are used only in
orchestration tests.

| Mode | Response source | New model call? | Intended use |
|---|---|---:|---|
| `fixture` | Bundled synthetic RTL | No | Installation, regression tests, and CI |
| `live` | A local model or provider API | Yes | Collect new model responses |
| `replay` | Archived live/replay responses with consistency metadata | No | Re-evaluate recorded responses |

Use `--mode` explicitly. The legacy `--provider mock` spelling maps to fixture
mode. Live generation requires an explicit `--design` selection or `--all`.
The [mode guide](MODES.md) provides further details; the CLI also supports
`llm-rtl-eval --describe-modes`.

### Live generation

Live API calls may incur provider charges. Configure credentials privately in
the environment and select an exact model identifier. `.env.example` documents
the variables; GRADE-RTL does not automatically load `.env` files.

| Provider | Credential variable | Model variable or `--model` |
|---|---|---|
| `ollama` | None for localhost | `OLLAMA_MODEL` |
| `openai` | `OPENAI_API_KEY` | `OPENAI_MODEL` |
| `deepseek` | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` |
| `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` |
| `gemini` | `GEMINI_API_KEY` | `GEMINI_MODEL` |
| `huggingface` | `HF_TOKEN` or `HF_API_KEY` | `HF_MODEL` |

For example, after setting `OPENAI_API_KEY` securely:

```bash
export OPENAI_MODEL='EXACT_MODEL_IDENTIFIER'
llm-rtl-doctor --require-tools --provider openai --model "$OPENAI_MODEL"
llm-rtl-eval \
  --mode live --provider openai --model "$OPENAI_MODEL" \
  --design half_adder --k 3 \
  --temperature 0 --top-p 1 --seed 7 \
  --run-id live-half-adder --paper-run
llm-rtl-verify-run --require-paper-result results/live-half-adder
```

The doctor performs local configuration checks without calling a model.
Supported sampling options vary by provider and model; inspect saved metadata
and verify compatibility with the chosen model. A fixed seed or zero temperature
does not guarantee identical responses from a changing hosted service.

**What the paper-result gate means:** `--paper-run` marks an eligible live/replay
run as intended for research use and rejects fixture/stub runs. The run verifier
checks recorded flags, provider/model consistency, and prompt/response/candidate
hashes. Passing this gate is not a certificate of scientific validity, complete
provenance, or correctness. Authors must validate the specification, trusted
reference, proof assumptions, supported RTL semantics, and underlying evidence.

### Replay an archived run

Replay makes no model call. It requires a provenance-enabled source run or an
exported bundle; synthetic fixture runs cannot be presented as genuine responses.

```bash
llm-rtl-eval \
  --mode replay --replay-source results/live-half-adder \
  --design half_adder --k 3 --run-id replay-half-adder --paper-run
llm-rtl-verify-run --require-paper-result results/replay-half-adder
```

Keep the source prompts and evaluation configuration. Prompt/response hashes
are checked. Changed tool outcomes or diagnostics can alter a refinement prompt
and stop replay with a mismatch rather than silently evaluating a different
interaction.

To export a source run that passes the paper-result gate:

```bash
python scripts/export_replay.py \
  results/live-half-adder replay_bundles/live-half-adder
```

Use that bundle directory as `--replay-source`. Review provider responses for
sensitive content before sharing. Hash consistency does not authenticate the
external provider; see [Security](SECURITY.md).

## Evaluation and metrics

| Check | Implementation |
|---|---|
| P: Port Signature | Compare the configured top module's port names, directions, widths, and signedness with the reference |
| C: Compilation | Compile with Icarus Verilog, warnings, and `default_nettype none` |
| E: Elaboration | Run Yosys `hierarchy -check` for the configured top |
| M: Module Completeness | Apply source heuristics and Yosys `proc; opt; check -assert` |
| F: Functional Equivalence | Normalize and flatten reference/candidate, then run `equiv_simple`, bounded induction, and `equiv_status -assert` |

Evaluation stops at the earliest failed check. Refinement appends that check's
message and a stage-specific instruction to the base prompt; the framework does
not hand-edit RTL. A proof timeout or inconclusive result counts as **not proven**
and fails F, which does not by itself establish a functional counterexample.

The scorecard reports:

- Within-budget stage coverage and conditional yields between adjacent checks
- **E2E@1 / E2E@K:** full success initially / within K total attempts
- **SEY@K:** at least one attempt passes compilation and elaboration, an operational
  eligibility proxy that does not itself run synthesis or establish timing closure
- **ETS / TTFP:** refinements and cumulative elapsed attempt time to first success,
  averaged over solved designs
- First-failure and operational root-cause shares among unsolved designs, using
  the attempt reaching the greatest stage depth (earliest attempt on ties)

These are feedback-dependent attempts, not independent samples for a pass@k
estimator. Source definitions are in [metrics.py](src/llm_rtl_eval/metrics.py).

## Output and project layout

```text
results/RUN/
├── run_manifest.json
├── attempts.json
├── results.csv
├── metrics.json / metrics.txt
└── DESIGN/attempt_N/
    ├── prompt.txt / raw_response.txt
    ├── candidate.v                  # when extraction succeeds
    ├── generation_metadata.json
    ├── attempt_result.json
    └── stage scripts and logs       # for checks that were reached
```

<a id="project-layout"></a>

| Path | Purpose |
|---|---|
| `src/llm_rtl_eval/` | CLI, provider adapters, parser, staged runner, metrics, doctor, and run verifier |
| `designs.json` | Three bundled smoke-design configurations |
| `prompts/`, `reference/` | Smoke prompts and author-created reference RTL |
| `fixtures/llm_outputs/` | Synthetic responses used in tests |
| `tests/` | Unit, orchestration, replay, checksum, and real-tool smoke tests |
| `paper_results/` | Earlier ten-design aggregate CSV, JSON, and recomputation script |
| `scripts/` | Repository/checksum checks, replay export, and synthesis entry points |
| `synthesis/` | Credential-free Genus template for authorized environments |

### Add a design

1. Add a fixed prompt under `prompts/` and trusted RTL under `reference/DESIGN/`.
2. Add a `designs.json` entry with prompt/reference paths, `top_module`,
   `reference_top`, and `language` (`verilog` or `systemverilog`).
3. Set optional `require_case_default` and `port_aliases` only when appropriate
   for the evaluation contract.
4. Add synthetic `attempt_N.v` or `default.v` responses only if fixture testing
   is needed. Preserve third-party licenses and update
   [Third-party licenses](THIRD_PARTY_LICENSES.md).

## Verification

Check the committed receipt and run the tests and real-tool smoke gate:

```bash
python scripts/generate_checksums.py --check
pytest -q -p no:cacheprovider
python scripts/verify_repository.py --public-release --require-tools --smoke
```

The smoke gate reruns the suite and evaluates the three synthetic examples.
GitHub Actions uses Python 3.10 and 3.12 with Icarus Verilog and Yosys. CI checks
the **committed** checksum receipt without regenerating it, so stale, missing,
or unlisted release files fail verification.

After intentional source or documentation changes, authors regenerate the
receipt, review the changes, and commit it with the files it covers:

```bash
python scripts/generate_checksums.py
python scripts/generate_checksums.py --check
python scripts/verify_repository.py --public-release --require-tools --smoke
```

Do not regenerate a receipt merely to hide an unexplained mismatch. See the
[release checklist](PUBLIC_RELEASE_CHECKLIST.md) and [migration notes](MIGRATION.md).
The [verification report](VERIFICATION_REPORT.md) records the earlier release
preparation environment; a new run should retain its own tool versions and logs.

**YoWASP note:** its runtime remaps `/tmp`. If absolute pytest temporary paths
cannot be opened by Yosys, set `TMPDIR` to a writable directory outside `/tmp`
and outside the release source tree, then rerun the tests. Native Yosys does not
need this workaround.

## Synthesis

Generic Yosys synthesis is available separately:

```bash
python scripts/synthesize.py \
  results/fixture-smoke/half_adder/attempt_2/candidate.v \
  --top half_adder --output results/fixture-smoke/half_adder/generic_synthesis
```

This produces a technology-independent netlist and statistics. It does not
reproduce foundry-specific ASIC PPA or FPGA implementation reports.
[synthesis/genus_template.tcl](synthesis/genus_template.tcl) is a starting point
for an authorized Cadence environment. Supply and record the appropriate timing,
I/O, library/corner, and power-activity setup for your experiment; the template
alone does not specify the study's complete implementation flow.

## Limits and reproducibility

- **Study data:** `paper_results/coverage_within_k.csv` contains 90 aggregate
  outcomes (ten designs × nine model labels), transcribed from an earlier
  manuscript. `python paper_results/recompute_aggregate_metrics.py` recomputes
  the corresponding stage rates, conditional yields, E2E@K, SEY@K, and failure
  shares. This checks aggregate arithmetic, not the underlying experiments.
  E2E@1, ETS, TTFP, complete model outputs, and FPGA/ASIC tables require the missing
  raw assets. Do not use these aggregates as evidence for an expanded study.
- **RTL coverage:** port parsing and completeness rules are purpose-built
  heuristics. The released integration examples are small combinational designs;
  validate unsupported language constructs, sequential/reset semantics, memories,
  and larger hierarchies before relying on a new benchmark.
- **Proof scope:** equivalence is relative to the reference and configured proof
  model. A successful gate does not establish that the reference implements an
  independently correct specification.
- **Run provenance:** existing hashes do not bind all reference/configuration
  files, tool scripts/logs, stage outcomes, and aggregate outputs into a complete
  immutable experiment record. The verifier does not independently recompute
  the run's metrics from a fully validated attempt history. Retain these inputs
  and check their relationships before making publication claims.
- **Environment:** hosted models and unpinned tool/dependency versions can change.
  Record exact model identifiers, source revisions, settings, tool versions,
  benchmark licenses, and proof/implementation constraints for each study.

## License, citation, and contributions

Framework code and bundled author-created smoke RTL are [MIT licensed](LICENSE).
Third-party tools, provider services, and separately added benchmark RTL retain
their own terms. See [CITATION.cff](CITATION.cff),
[CONTRIBUTING.md](CONTRIBUTING.md), and [SECURITY.md](SECURITY.md). Never commit
provider credentials, private infrastructure details, or proprietary libraries.
