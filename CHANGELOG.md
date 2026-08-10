# Changelog

## 1.0.0 - 2026-07-26

- Replaced hardcoded credentials and private infrastructure with environment-based configuration.
- Separated P/C/E/M/F front-end evaluation from optional synthesis.
- Added exact interface comparison against trusted reference RTL.
- Added deterministic module-completeness rules and Yosys structural checks.
- Added bounded, first-failure-directed prompt refinement without manual RTL edits.
- Added E2E@1, E2E@K, SEY@K, ETS, TTFP, conditional-yield, and failure-share calculations.
- Added isolated run directories, metadata hashes, mock examples, tests, CI, and release verification.
- Hardened provider endpoints, error handling, seed reporting, and secret-safe metadata.
- Updated Hugging Face support to the OpenAI-compatible inference router and made the OpenAI token-limit field configurable.
- Added primitive-gate completeness handling, preflight EDA-tool validation, duplicate-design rejection, and path/symlink containment checks.
- Added aggregate manuscript metric recomputation, public-release manifests, checksums, and an explicit artifact-scope statement.
