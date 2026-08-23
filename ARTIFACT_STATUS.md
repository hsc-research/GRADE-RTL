# Artifact Scope and Status

This package is a **GRADE-RTL framework and aggregate-results release**, not a complete raw-data archive for every experiment in the associated paper.

Included:

- staged P/C/E/M/F evaluation code;
- explicit fixture, replay, and live response modes;
- provenance and hash validation for replayed genuine responses;
- paper-result eligibility gates separating response origin from EDA-tool mode;
- three author-created smoke-test designs and synthetic fixtures;
- unit tests, tool-stub orchestration tests, and real-tool CI integration tests;
- aggregate within-K coverage data transcribed from the manuscript;
- scripts that recompute aggregate front-end metrics from that table;
- generic Yosys synthesis and a credential-free Cadence Genus template.

Not included because they were not present in the source archive supplied for this release preparation:

- raw responses and attempt logs for all nine models and ten paper designs;
- the ten complete benchmark prompts and trusted RTL trees;
- raw FPGA projects/reports;
- proprietary ASIC libraries, licenses, or remote-server configuration;
- raw Genus/Innovus reports used for the paper tables.

Fixture responses are synthetic tests and are never paper data. Replay mode accepts only provenance-enabled live/replay runs or bundles exported from live runs that passed the paper-result gate. `llm-rtl-verify-run` and the run manifest expose the response origin, tool mode, hashes, and paper-result status.

Do not claim that this package independently reproduces every paper number until the missing assets are added with their licenses and provenance. `paper_artifact_manifest.json` records the present scope explicitly.
