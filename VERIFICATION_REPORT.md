# Verification Report

## Release candidate

- Software: **LLM-for-RTL Evaluation Framework**
- Version: **1.0.0**
- Release scope: **framework and aggregate manuscript results**
- Verification date: **2026-07-26**

This report applies to the clean release tree containing the staged P/C/E/M/F
framework, three author-created smoke designs, unit tests, aggregate within-K
coverage data, generic Yosys synthesis support, and a credential-free Cadence
Genus template. It does not certify reproduction of every paper experiment; the
missing raw assets are listed in `ARTIFACT_STATUS.md` and
`paper_artifact_manifest.json`.

## Verification environment

- Operating system: Linux 6.12.13 x86_64, glibc 2.41
- Python: 3.13.5
- requests: 2.32.5
- pytest: 9.0.2
- Icarus Verilog: not available in this audit runtime
- Yosys: not available in this audit runtime

The GitHub Actions workflow installs Icarus Verilog and Yosys on a clean Ubuntu
runner and is the required final real-tool gate before the repository is made
public.

## Completed checks

### Source and repository hygiene

- Parsed every released Python file with the Python AST parser.
- Removed build directories, wheel metadata, bytecode, test caches, and generated
  result directories from the release tree.
- Scanned released text files for common API-key, private-key, cloud-token, and
  hardcoded-password patterns.
- Scanned executable Python, YAML, and Tcl sources for `shell=True`, `os.system`,
  `sshpass`, disabled TLS verification, and disabled SSH host verification.
- Confirmed that provider endpoints reject embedded credentials, credential-like
  query parameters, URL fragments, and non-HTTPS remote endpoints.
- Confirmed that provider failures do not copy remote response bodies or API keys
  into result logs.

### Automated test suite

The complete local test suite was run three consecutive times with bytecode and
pytest cache generation disabled:

```text
Run 1: 45 passed, 1 skipped
Run 2: 45 passed, 1 skipped
Run 3: 45 passed, 1 skipped
```

The single skipped test is the real Icarus-Verilog/Yosys integration test. It is
skipped only when either executable is absent.

The tests cover interface parsing, ANSI and non-ANSI Verilog, module extraction,
primitive-gate completeness, provider payload and response handling, seed
semantics, secure endpoint validation, output isolation, path traversal and
symlink containment, overwrite protection, metric consistency, refinement, and
synthesis-script generation.

### Manuscript aggregate data

`paper_results/recompute_aggregate_metrics.py` was run independently and its
output matched `paper_results/aggregate_metrics.json` exactly. The released CSV
and script reproduce within-budget stage rates, conditional yields, E2E@K,
SEY@K, and first-failure shares.

The supplied archive did not contain attempt-level paper logs, so the release
does not claim to reproduce paper E2E@1, ETS, TTFP, raw model outputs, or raw
FPGA/ASIC reports.

### Command-line and packaging checks

- CLI help rendered successfully.
- All three configured designs were loaded and listed successfully.
- Package metadata and entry points were exercised by the test suite.
- Built `llm_rtl_eval-1.0.0-py3-none-any.whl` successfully with SHA-256
  `79ad613d85fe3c4aebc2bcd1e39527870180bffcd55dc378301eeb1a995f4d76`.
- Installed that wheel in a temporary environment, rendered CLI help, and
  imported version `1.0.0` successfully.
- Removed all generated build directories and package metadata from the public
  source tree after the packaging check.

### Repository verifier

The non-tool verifier completed successfully with two expected warnings: Icarus
Verilog and Yosys were not installed in this audit runtime. The verifier checked
required files, source syntax, design assets, secret patterns, unsafe execution
patterns, release-tree cleanliness, citation metadata, the complete test suite,
and aggregate manuscript metric consistency.

### Release-archive validation

The final ZIP was tested with the archive integrity checker, extracted into a
fresh directory, and verified independently. All 58 in-tree checksum entries
matched; the extracted test suite again reported 45 passed and 1 real-tool test
skipped; the extracted public-release verifier passed with only the two expected
missing-tool warnings; and the extracted CLI listed all three bundled designs.

## Required author-side checks before public visibility

The following checks require the intended author infrastructure and cannot be
completed in this audit runtime:

1. Rotate any credential that appeared in earlier private repository revisions.
2. Publish from a fresh Git repository or a demonstrably scrubbed history.
3. Push the release privately and confirm every GitHub Actions matrix job passes,
   including the real Icarus-Verilog/Yosys smoke run.
4. Exercise at least one intended real LLM provider with a non-billable or
   carefully controlled test and inspect the saved metadata.
5. Exercise the authorized Cadence Genus environment with the provided template,
   using institution-specific paths only through private environment variables.
6. Confirm that any subsequently added benchmark RTL preserves its original
   license and provenance.

## Release decision

The tree is suitable for publication as a **framework-and-aggregate-results
release** after the author-side credential/history and real-tool CI gates above
pass. It must not be described as a complete raw-data reproduction package for
the ten-design, nine-model FPGA/ASIC study unless the missing assets are added
with licenses, provenance, and a revised manifest.
