# Changelog

## 1.1.1 - 2026-08-23

- Clarified and documented fixture, live, and replay execution with exact commands.
- Added `llm-rtl-doctor` for repository and real-tool environment checks.
- Added source-tree bootstrapping so tests and compatibility scripts work before installation.
- Added replay-bundle export/replay regression coverage and environment-doctor tests.
- Fixed the real-Yosys `No latch inferred ...` false positive that caused the GitHub Actions second-attempt failure.
- Added CI checks for the mode guide and real-tool environment.
- Required explicit `--design` or `--all` selection to prevent accidental billable live runs.
- Added provider preflight checks before output creation or model calls.
- Strengthened direct-run and replay-bundle provenance, prompt, response, model, and provider checks.
- Added archived prompt text to exported replay bundles and verified source runs before export.

## 1.1.0 - 2026-08-23

- Added explicit fixture, replay, and live response modes.
- Renamed public-facing mock terminology to synthetic fixtures while retaining a legacy alias.
- Added provenance-checked replay of full run directories and exported replay bundles.
- Added paper-result gating, run-manifest schema version 2, and run provenance verification.
- Renamed temporary fake EDA executables to tool stubs and documented their test-only role.
- Added default fixture responses and stronger attempt-count assertions so CI failures identify stage regressions instead of missing fixture files.
- Fixed the real-Yosys `No latch inferred ...` false positive and added regression coverage.

## 1.0.1 - 2026-08-23

- Fixed a real-Yosys false positive in Module Completeness: the parser no longer treats `No latch inferred ...` as an inferred-latch failure.
- Added regression tests for both `No latch inferred ...` and true `Latch inferred ...` messages.

## 1.0.0 - 2026-07-26

- Replaced hardcoded credentials and private infrastructure with environment-based configuration.
- Separated P/C/E/M/F front-end evaluation from optional synthesis.
- Added exact interface comparison against trusted reference RTL.
- Added deterministic module-completeness rules and Yosys structural checks.
- Added bounded, first-failure-directed prompt refinement without manual RTL edits.
- Added E2E@1, E2E@K, SEY@K, ETS, TTFP, conditional-yield, and failure-share calculations.
- Added isolated run directories, metadata hashes, fixture examples, tests, CI, and release verification.
- Hardened provider endpoints, error handling, seed reporting, and secret-safe metadata.
- Updated Hugging Face support to the OpenAI-compatible inference router and made the OpenAI token-limit field configurable.
- Added primitive-gate completeness handling, preflight EDA-tool validation, duplicate-design rejection, and path/symlink containment checks.
- Added aggregate manuscript metric recomputation, public-release manifests, checksums, and an explicit artifact-scope statement.
