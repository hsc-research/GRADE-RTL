#!/usr/bin/env python3
"""Export a completed live run into a provenance-checked replay bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

_SOURCE = Path(__file__).resolve().parents[1] / "src"
if str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))

from llm_rtl_eval.run_verifier import RunVerificationError, verify_run


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Completed results/RUN directory")
    parser.add_argument("output_dir", type=Path, help="New replay bundle directory")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    output = args.output_dir.resolve()
    if output == run_dir:
        print("error: replay output must differ from the source run", file=sys.stderr)
        return 2
    try:
        output.relative_to(run_dir)
    except ValueError:
        pass
    else:
        print("error: replay output may not be created inside the source run", file=sys.stderr)
        return 2
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        print(f"error: missing run manifest: {manifest_path}", file=sys.stderr)
        return 2
    try:
        verify_run(run_dir, require_paper_result=True)
    except RunVerificationError as exc:
        print(f"error: source run verification failed: {exc}", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("execution_mode") != "live":
        print("error: only genuine live runs may be exported for replay", file=sys.stderr)
        return 2
    if manifest.get("response_origin") != "live":
        print("error: source run does not declare live response origin", file=sys.stderr)
        return 2
    if manifest.get("test_fixture") is True:
        print("error: fixture runs cannot be exported as replay data", file=sys.stderr)
        return 2
    if manifest.get("paper_result_eligible") is not True:
        print(
            "error: source run is not paper-result eligible; verify that real EDA tools were used",
            file=sys.stderr,
        )
        return 2
    if manifest.get("paper_result") is not True:
        print(
            "error: source run was not created with --paper-run",
            file=sys.stderr,
        )
        return 2
    if output.exists():
        if not args.overwrite:
            print(f"error: output exists: {output}; use --overwrite", file=sys.stderr)
            return 2
        shutil.rmtree(output)
    output.mkdir(parents=True)

    replay_manifest = {
        "schema_version": 1,
        "origin": "recorded_live",
        "provider": manifest["provider"],
        "model": manifest["model"],
        "source_run_id": run_dir.name,
        "source_created_utc": manifest.get("created_utc"),
        "paper_eligible": True,
        "designs": manifest.get("designs", []),
        "refinement_budget": manifest.get("refinement_budget"),
        "source_tool_versions": manifest.get("tool_versions", {}),
    }
    (output / "replay_manifest.json").write_text(
        json.dumps(replay_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    exported = 0
    for design_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
        attempt_dirs = sorted(
            (path for path in design_dir.glob("attempt_*") if path.is_dir()),
            key=lambda path: int(path.name.split("_")[-1]),
        )
        if not attempt_dirs:
            continue
        target_design = output / design_dir.name
        target_design.mkdir()
        for attempt_dir in attempt_dirs:
            attempt = int(attempt_dir.name.split("_")[-1])
            prompt_path = attempt_dir / "prompt.txt"
            response_path = attempt_dir / "raw_response.txt"
            generation_path = attempt_dir / "generation_metadata.json"
            if not prompt_path.is_file() or not response_path.is_file() or not generation_path.is_file():
                print(f"error: incomplete attempt directory: {attempt_dir}", file=sys.stderr)
                return 2
            prompt = prompt_path.read_text(encoding="utf-8")
            response = response_path.read_text(encoding="utf-8")
            generation = json.loads(generation_path.read_text(encoding="utf-8"))
            if generation.get("execution_mode") != "live" or generation.get("test_fixture") is True:
                print(f"error: attempt is not a genuine live response: {attempt_dir}", file=sys.stderr)
                return 2
            target_prompt = target_design / f"attempt_{attempt}.prompt.txt"
            target_response = target_design / f"attempt_{attempt}.txt"
            target_meta = target_design / f"attempt_{attempt}.json"
            target_prompt.write_text(prompt, encoding="utf-8")
            target_response.write_text(response, encoding="utf-8")
            metadata = {
                "schema_version": 1,
                "origin": "recorded_live",
                "provider": manifest["provider"],
                "model": manifest["model"],
                "design": design_dir.name,
                "attempt": attempt,
                "paper_eligible": True,
                "source_run_id": run_dir.name,
                "source_response_id": generation.get("response_id"),
                "source_created_utc": manifest.get("created_utc"),
                "prompt_sha256": sha256_text(prompt),
                "response_sha256": sha256_text(response),
                "seed_requested": generation.get("seed_requested"),
                "seed_applied": generation.get("seed_applied", False),
                "temperature": generation.get("temperature"),
                "top_p": generation.get("top_p"),
                "max_tokens": generation.get("max_tokens"),
            }
            target_meta.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            exported += 1
    if exported == 0:
        print("error: no attempts were found in the source run", file=sys.stderr)
        return 2
    print(f"Exported {exported} recorded responses to {output}")
    print(
        "Replay with: llm-rtl-eval --mode replay "
        f"--replay-source {output} --all --k {manifest.get('refinement_budget', 3)} "
        f"--run-id replay-{run_dir.name} --paper-run"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
