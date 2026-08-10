# Public Release Checklist

## Completed in this release archive

- [x] Removed hardcoded credentials, private hosts, license paths, and remote passwords.
- [x] Removed password automation and disabled-host-verification behavior.
- [x] Scanned the clean tree for common secret and unsafe-code patterns.
- [x] Ran the Python test suite three consecutive times: 45 passed, 1 real-tool test skipped each time.
- [x] Recomputed aggregate manuscript metrics and matched the committed JSON exactly.
- [x] Documented the provenance and MIT license of every bundled RTL file.
- [x] Documented the limited artifact scope in `ARTIFACT_STATUS.md`.
- [x] Added a machine-readable public manifest.
- [x] Added a security policy, contribution policy, and verification report.
- [x] Generated `SHA256SUMS` as the final in-tree release step.
- [x] Ran `python scripts/verify_repository.py --public-release` successfully.

## Author actions required before public visibility

- [ ] Rotate any credentials that appeared in earlier repository revisions.
- [ ] Publish this clean tree from a fresh repository or a verified scrubbed history.
- [ ] Push privately and confirm GitHub Actions passes on all configured Python versions.
- [ ] Confirm the CI real-tool smoke run passes with Icarus Verilog and Yosys.
- [ ] Exercise any intended real provider and authorized Cadence environment privately.
- [ ] Do not describe this release as a complete raw paper artifact unless the missing assets are added and the manifest is revised.

## If upgrading to a complete paper artifact

Add, with licenses and provenance:

- all ten benchmark prompts and trusted RTL trees;
- every model/design/attempt raw response and extracted RTL;
- refinement prompts and normalized failure logs;
- exact provider model identifiers, access dates, decoding settings, and seeds;
- raw FPGA scripts, constraints, and reports;
- raw Genus/Innovus scripts and reports, excluding proprietary libraries;
- data-generation scripts for every table and figure;
- a manifest linking each manuscript value to released raw inputs.
