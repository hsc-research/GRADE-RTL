# Contributing

1. Create a feature branch.
2. Do not add third-party RTL without its license and provenance.
3. Do not commit generated `results/` directories or credentials.
4. Run `llm-rtl-doctor --require-tools`, `pytest -q`, and `python scripts/verify_repository.py --require-tools --smoke` before proposing a change.
5. Changes to stage semantics or metric definitions must include tests and a
   corresponding README update.

Code should support Python 3.10 or newer and remain import-safe: importing a
module must not contact a provider, invoke an EDA tool, or modify files.


## Response-mode and provenance rules

- Synthetic test data belongs only under `fixtures/llm_outputs/` and must use
  fixture mode.
- Replay inputs must originate from a provenance-enabled live run or a bundle
  produced by `scripts/export_replay.py`.
- Never mark fixture data or tool-stub runs as paper results.
- Changes to mode, provenance, or paper-result gating require dedicated tests and
  updates to `README.md` and `MODES.md`.
