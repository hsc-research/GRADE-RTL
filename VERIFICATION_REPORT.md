# Verification Report

## Release candidate

- Software: **GRADE-RTL: Generated RTL Assessment through Design-flow Evaluation**
- Version: **1.1.1**
- Verification date: **2026-08-23**
- Release scope: **framework, smoke examples, tests, and aggregate manuscript results**

This report applies to the clean source tree containing the staged P/C/E/M/F framework, explicit fixture/live/replay modes, three author-created smoke designs, provider adapters, tests, aggregate within-budget coverage data, generic Yosys synthesis support, and a credential-free Cadence Genus template. It does not certify reproduction of every paper experiment; missing raw assets are listed in `ARTIFACT_STATUS.md` and `paper_artifact_manifest.json`.

## Verification environment

- Operating system: Linux 6.18.35 x86_64
- Python: 3.13.5
- requests: 2.32.5
- pytest: 9.0.2
- setuptools: 82.0.1
- wheel: 0.46.3
- Icarus Verilog: unavailable in this audit runtime
- Yosys: unavailable in this audit runtime

The GitHub Actions workflow installs Icarus Verilog and Yosys on clean Ubuntu runners using Python 3.10 and 3.12. That workflow is the final real-tool gate.

## Mode and provenance verification

The release distinguishes three response sources:

- **fixture**: synthetic deterministic test RTL; never paper eligible;
- **live**: a new response from an actual local/API model;
- **replay**: a previously recorded genuine response whose prompt/response hashes and run metadata are checked.

Response mode is independent of EDA tool mode. Tool stubs exist only inside Pytest and are automatically classified as `stub`. A paper result is accepted only when the response source is live or paper-gated replay, the tools are real, and the run was explicitly created with `--paper-run`.

## GitHub Actions failure addressed

The previous CI failure was caused by a Module Completeness parser that matched the substring `latch inferred` inside Yosys output `No latch inferred ...`. The design was incorrectly sent to attempt 2, where no attempt-specific fixture existed. Version 1.1.1 matches only a genuine positive `Latch inferred for signal ...` line. Regression tests cover both messages and assert the intended smoke attempt counts:

```text
priority_encoder   attempt 1 passes
ripple_carry_adder attempt 1 passes
half_adder         attempt 1 fails P, attempt 2 passes
```

Expected smoke metrics:

```text
E2E@1 = 2/3
E2E@3 = 1
SEY@3 = 1
```

## Automated test suite

The complete local suite was run three consecutive times with bytecode and Pytest cache generation disabled:

```text
Run 1: 69 passed, 1 skipped
Run 2: 69 passed, 1 skipped
Run 3: 69 passed, 1 skipped
```

The single skipped test requires real Icarus Verilog and Yosys. Tests cover:

- fixture, live-orchestration, and replay CLI selection;
- fixture/paper-result separation and real/stub tool classification;
- provider payloads, credentials, endpoint security, model identifiers, and seed reporting;
- replay source-run and bundle validation, prompt/response hashes, and export safety;
- ANSI and non-ANSI interface parsing, module extraction, hierarchy selection, and path containment;
- compilation, elaboration, completeness, equivalence-script generation, and Yosys latch-message parsing;
- bounded refinement, attempt ordering, E2E/SEY/ETS/TTFP calculations, and failure taxonomy;
- output isolation, overwrite protection, run manifests, run verification, and synthesis-script generation.

## Static and repository checks

The following completed successfully:

- Python AST parsing for all released Python files;
- JSON and TOML parsing;
- GitHub Actions YAML parsing;
- internal Markdown link checking;
- secret and unsafe-code scans;
- release-tree cache/build hygiene checks;
- design, prompt, reference, and fixture asset checks;
- release-version consistency across package, citation, and artifact metadata;
- aggregate manuscript metric recomputation.

## Packaging verification

The wheel `llm_rtl_eval-1.1.1-py3-none-any.whl` was built successfully with SHA-256:

```text
30615c8c85238e9ee732065f5cf5d9d5ae503116d1bb8181331424b64266bf81
```

It was installed into a new temporary environment. The installed package reported version `1.1.1`, rendered the mode guide, loaded all three designs, and completed the environment-doctor command.

The source archive was checked with the ZIP integrity tester, extracted into a new directory, and independently rerun. The extracted tree reported **69 passed, 1 real-tool test skipped**, and the strict public-release verifier passed with only the expected local warnings that Icarus Verilog and Yosys were unavailable.

## Limitations and required author-side checks

This runtime could not execute the real Icarus/Yosys integration test. Before public visibility, authors must:

1. push the release privately and confirm all GitHub Actions jobs pass;
2. inspect at least one live provider run and verify its metadata and hashes;
3. verify any authorized proprietary synthesis flow on the intended infrastructure;
4. rotate any credential that appeared in older history;
5. publish from a fresh or correctly scrubbed Git history.

## Release decision

The source is suitable for publication as a **framework-and-aggregate-results release** after the private GitHub Actions real-tool gate passes. It must not be described as a complete raw-data reproduction package for the ten-design, nine-model FPGA/ASIC paper study unless the missing assets are added with licenses, provenance, and a revised manifest.
