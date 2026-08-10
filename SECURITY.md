# Security Policy

## Secrets

Never commit API keys, passwords, private hostnames, SSH passwords, private
keys, foundry-library paths, or license-server details. Provider credentials are
read only from environment variables. The optional Cadence template contains no
credentials or institution-specific paths.

Use key-based SSH with strict host-key verification for any remote proprietary
flow. Password automation and `StrictHostKeyChecking=no` are intentionally not
supported.

If credentials were ever committed to a previous private or public revision,
rotate them before publishing a cleaned repository. Removing a secret from the
latest commit does not remove it from Git history.

## Reporting

Report suspected vulnerabilities privately to the corresponding author before
opening a public issue. Do not include live credentials or private infrastructure
information in a report.
