# Artifact Scope and Status

This public-ready package is a **framework release**, not a complete raw-data
archive for every result in the associated paper.

Included:

- staged P/C/E/M/F evaluation code;
- provider adapters and deterministic mock mode;
- three author-created smoke-test designs;
- unit and integration tests;
- aggregate within-K coverage data transcribed from the manuscript;
- scripts that recompute the aggregate front-end metrics from that table;
- generic Yosys synthesis and a credential-free Cadence Genus template.

Not included because they were not present in the source archive supplied for
this audit:

- raw responses and attempt logs for all nine models and ten paper designs;
- the ten complete benchmark prompts and trusted RTL trees;
- raw FPGA projects/reports;
- proprietary ASIC libraries, licenses, or remote-server configuration;
- raw Genus/Innovus reports used for the paper tables.

Do not claim that this package independently reproduces every paper number until
those assets are added with their licenses and provenance. The release verifier
checks framework integrity; `paper_artifact_manifest.json` records the present
scope explicitly.
