# Migrating to GRADE-RTL v1.1.1

## Why this update exists

Earlier releases exposed a `mock` provider name and a GitHub Actions integration
run could fail after Yosys printed `No latch inferred ...`. The parser matched
the substring `latch inferred` and incorrectly classified the design as an MC
failure, which triggered an unnecessary second fixture attempt. Version 1.1.1
matches only a genuine positive latch report and adds regression tests for both
messages.

## Command changes

Use an explicit response mode:

```bash
# Old, retained only as a deprecated alias
llm-rtl-eval --provider mock --all --k 3 --run-id smoke

# New
llm-rtl-eval --mode fixture --all --k 3 --run-id fixture-smoke
```

Fixture files now live under:

```text
fixtures/llm_outputs/
```

`mock_responses/` must not exist in a release tree.

## Before pushing to GitHub

```bash
python -m pip install -e '.[dev]'
llm-rtl-doctor --require-tools
pytest -q -p no:cacheprovider
python scripts/verify_repository.py --require-tools --smoke
python scripts/generate_checksums.py
python scripts/verify_repository.py --public-release
```

The expected real-tool smoke behavior is:

```text
priority_encoder   passes attempt 1
ripple_carry_adder passes attempt 1
half_adder         fails P on attempt 1 and passes attempt 2

E2E@1 = 2/3
E2E@3 = 1
SEY@3 = 1
```

## Mode meanings

- `fixture`: synthetic test RTL; never paper data.
- `live`: a new response from a real local/API model.
- `replay`: a previously recorded genuine live response with provenance and hash
  checks.

Independently, EDA tools are classified as `real` or `stub`. A paper result must
come from `live` or paper-gated `replay` mode, use real tools, and be created with
`--paper-run`.
