# Contributing

1. Create a feature branch.
2. Do not add third-party RTL without its license and provenance.
3. Do not commit generated `results/` directories or credentials.
4. Run `pytest -q` and `python scripts/verify_repository.py` before proposing a change.
5. Changes to stage semantics or metric definitions must include tests and a
   corresponding README update.

Code should support Python 3.10 or newer and remain import-safe: importing a
module must not contact a provider, invoke an EDA tool, or modify files.
