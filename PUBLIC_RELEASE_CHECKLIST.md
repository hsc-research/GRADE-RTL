# Public Release Checklist

## Completed in GRADE-RTL v1.1.1

- [x] Removed hardcoded credentials, private hosts, license paths, remote passwords, and password automation.
- [x] Separated response origin (`fixture`, `live`, `replay`) from EDA tool mode (`real`, `stub`).
- [x] Enforced that fixture data and tool-stub runs can never be marked as paper results.
- [x] Added paper-result gating and run-manifest/hash verification.
- [x] Added provenance-checked replay of full runs and exported replay bundles.
- [x] Added `llm-rtl-doctor` and explicit mode-selection documentation.
- [x] Fixed the real-Yosys `No latch inferred ...` false positive that caused the GitHub Actions failure.
- [x] Added regression tests for negative and positive latch messages and exact fixture attempt counts.
- [x] Added CLI tests for fixture, live-orchestration, and replay mode.
- [x] Added replay-export, replay-bundle, prompt-hash, response-hash, and source-run verification tests.
- [x] Ran the Python test suite three consecutive times: **69 passed, 1 real-tool test skipped** each time.
- [x] Recomputed aggregate manuscript metrics and matched the committed JSON exactly.
- [x] Documented the provenance and MIT license of every bundled RTL file.
- [x] Documented the limited artifact scope in `ARTIFACT_STATUS.md` and the machine-readable manifest.
- [x] Added security, contribution, migration, mode, and verification documentation.
- [x] Verified Python syntax, JSON, TOML, GitHub Actions YAML, and internal Markdown links.
- [x] Verified the package entry points and source-tree compatibility commands.
- [x] Added checksum generation and strict public-release verification.

## Author actions required before public visibility

- [ ] Rotate any credential that appeared in an earlier repository revision.
- [ ] Publish this clean tree from a fresh repository or a demonstrably scrubbed history.
- [ ] Push privately and confirm every GitHub Actions matrix job passes on Python 3.10 and 3.12.
- [ ] Confirm the GitHub Actions real-tool integration test passes with Icarus Verilog and Yosys.
- [ ] Run at least one intended live provider privately and inspect the saved provenance metadata.
- [ ] Exercise any authorized Cadence flow privately; never commit proprietary paths or license details.
- [ ] Do not describe this release as a complete raw paper artifact unless the missing paper assets are added and the manifest is revised.

## Final commands before a release tag

```bash
python -m pip install -e '.[dev]'
llm-rtl-doctor --require-tools
pytest -q -p no:cacheprovider
python scripts/verify_repository.py --require-tools --smoke
python scripts/generate_checksums.py
python scripts/verify_repository.py --public-release
```

The last two commands must complete with zero errors. A public paper run must also pass:

```bash
llm-rtl-verify-run --require-paper-result results/RUN_ID
```
