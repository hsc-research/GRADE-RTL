from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


class RunVerificationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunVerificationError(f"cannot parse {path}") from exc
    if not isinstance(value, dict):
        raise RunVerificationError(f"expected a JSON object in {path}")
    return value


def verify_run(
    run_dir: Path,
    *,
    require_paper_eligible: bool = False,
    require_paper_result: bool = False,
) -> list[str]:
    run_dir = run_dir.resolve()
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        raise RunVerificationError(f"missing run manifest: {manifest_path}")
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != 2:
        raise RunVerificationError(
            "run manifest must use schema_version 2; rerun with GRADE-RTL v1.1.0+"
        )

    mode = manifest.get("execution_mode")
    origin = manifest.get("response_origin")
    fixture = manifest.get("test_fixture")
    provider_eligible = manifest.get("provider_paper_eligible")
    tool_mode = manifest.get("tool_mode")
    result_eligible = manifest.get("paper_result_eligible")
    paper_result = manifest.get("paper_result")
    provider = manifest.get("provider")
    model = manifest.get("model")
    designs = manifest.get("designs")
    expected_eligible = bool(provider_eligible and not fixture and tool_mode == "real")

    if mode not in {"fixture", "replay", "live"}:
        raise RunVerificationError(f"invalid execution_mode: {mode!r}")
    if tool_mode not in {"real", "stub"}:
        raise RunVerificationError(f"invalid tool_mode: {tool_mode!r}")
    if result_eligible is not expected_eligible:
        raise RunVerificationError(
            f"paper_result_eligible={result_eligible!r}, expected {expected_eligible!r}"
        )
    if not isinstance(paper_result, bool):
        raise RunVerificationError("paper_result must be a Boolean")
    if not isinstance(provider, str) or not provider:
        raise RunVerificationError("run manifest is missing provider")
    if not isinstance(model, str) or not model:
        raise RunVerificationError("run manifest is missing model")
    if not isinstance(designs, list) or not designs or not all(
        isinstance(item, str) and item for item in designs
    ):
        raise RunVerificationError("run manifest must list at least one design")
    if len(designs) != len(set(designs)):
        raise RunVerificationError("run manifest contains duplicate designs")
    if paper_result and not expected_eligible:
        raise RunVerificationError(
            "run is marked paper_result=true but its provenance/tools are not eligible"
        )

    expected_origin = {
        "fixture": "synthetic_fixture",
        "replay": "recorded_live",
        "live": "live",
    }[mode]
    if origin != expected_origin:
        raise RunVerificationError(
            f"response_origin={origin!r}, expected {expected_origin!r} for mode {mode}"
        )
    if mode == "fixture" and (fixture is not True or provider_eligible is not False):
        raise RunVerificationError(
            "fixture mode must be marked test_fixture and not provider-paper-eligible"
        )
    if mode in {"replay", "live"} and fixture is True:
        raise RunVerificationError(f"{mode} mode may not be marked as a test fixture")

    attempts = 0
    attempt_designs: set[str] = set()
    for metadata_path in sorted(run_dir.glob("*/attempt_*/generation_metadata.json")):
        metadata = load_json(metadata_path)
        design_name = metadata_path.parent.parent.name
        attempt_designs.add(design_name)
        if metadata.get("provider") != provider:
            raise RunVerificationError(f"provider mismatch in {metadata_path}")
        if metadata.get("model") != model:
            raise RunVerificationError(f"model mismatch in {metadata_path}")
        if metadata.get("execution_mode") != mode:
            raise RunVerificationError(f"mode mismatch in {metadata_path}")
        if metadata.get("response_origin") != origin:
            raise RunVerificationError(f"origin mismatch in {metadata_path}")
        if metadata.get("test_fixture") != fixture:
            raise RunVerificationError(f"fixture flag mismatch in {metadata_path}")
        if metadata.get("tool_mode") != tool_mode:
            raise RunVerificationError(f"tool mode mismatch in {metadata_path}")
        if metadata.get("paper_result_eligible") is not expected_eligible:
            raise RunVerificationError(f"paper eligibility mismatch in {metadata_path}")
        attempt_dir = metadata_path.parent
        for field, filename in (
            ("prompt_sha256", "prompt.txt"),
            ("raw_response_sha256", "raw_response.txt"),
        ):
            target = attempt_dir / filename
            if not target.is_file() or metadata.get(field) != sha256_file(target):
                raise RunVerificationError(f"hash mismatch for {target}")
        rtl_hash = metadata.get("rtl_sha256")
        rtl_path = attempt_dir / "candidate.v"
        if rtl_hash is not None:
            if not rtl_path.is_file() or rtl_hash != sha256_file(rtl_path):
                raise RunVerificationError(f"hash mismatch for {rtl_path}")
        attempts += 1
    if attempts == 0:
        raise RunVerificationError(f"no attempt metadata found in {run_dir}")
    if attempt_designs != set(designs):
        raise RunVerificationError(
            f"attempt design set {sorted(attempt_designs)!r} does not match manifest "
            f"{sorted(designs)!r}"
        )
    for filename in ("attempts.json", "results.csv", "metrics.json", "metrics.txt"):
        if not (run_dir / filename).is_file():
            raise RunVerificationError(f"missing run output: {run_dir / filename}")
    if require_paper_eligible and not expected_eligible:
        raise RunVerificationError(
            f"run is not paper-eligible: mode={mode}, origin={origin}, tool_mode={tool_mode}"
        )
    if require_paper_result and not paper_result:
        raise RunVerificationError("run is eligible but was not created with --paper-run")

    return [
        f"mode={mode}",
        f"origin={origin}",
        f"tool_mode={tool_mode}",
        f"paper_result_eligible={str(expected_eligible).lower()}",
        f"paper_result={str(paper_result).lower()}",
        f"attempts_verified={attempts}",
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify GRADE-RTL run provenance and hashes")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--require-paper-eligible", action="store_true")
    parser.add_argument("--require-paper-result", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        lines = verify_run(
            args.run_dir,
            require_paper_eligible=args.require_paper_eligible or args.require_paper_result,
            require_paper_result=args.require_paper_result,
        )
    except RunVerificationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("GRADE-RTL run verification: PASS")
    for line in lines:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
