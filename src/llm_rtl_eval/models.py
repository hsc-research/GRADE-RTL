from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

StageName = Literal["P", "C", "E", "M", "F"]
StageStatus = Literal["PASS", "FAIL", "SKIP", "ERROR"]

STAGE_ORDER: tuple[StageName, ...] = ("P", "C", "E", "M", "F")


@dataclass(slots=True)
class StageResult:
    stage: StageName
    status: StageStatus
    message: str = ""
    log_path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


@dataclass(slots=True)
class AttemptResult:
    design: str
    attempt: int
    provider: str
    model: str
    elapsed_seconds: float
    stages: dict[str, StageResult]
    first_failure: str | None
    root_cause: str | None
    prompt_path: str
    raw_response_path: str
    rtl_path: str | None
    metadata_path: str
    synthesis: dict[str, Any] | None = None

    @property
    def full_success(self) -> bool:
        return all(self.stages.get(stage) and self.stages[stage].passed for stage in STAGE_ORDER)

    @property
    def synthesis_eligible(self) -> bool:
        return bool(
            self.stages.get("C")
            and self.stages["C"].passed
            and self.stages.get("E")
            and self.stages["E"].passed
        )

    @property
    def depth(self) -> int:
        """Number of consecutive stages passed from the start of the flow."""
        depth = 0
        for stage in STAGE_ORDER:
            result = self.stages.get(stage)
            if result is None or not result.passed:
                break
            depth += 1
        return depth

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["full_success"] = self.full_success
        data["synthesis_eligible"] = self.synthesis_eligible
        data["depth"] = self.depth
        return data


@dataclass(slots=True)
class DesignConfig:
    name: str
    prompt: str
    reference: str
    top_module: str
    reference_top: str | None = None
    language: Literal["verilog", "systemverilog"] = "verilog"
    require_case_default: bool = False
    port_aliases: dict[str, str] = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_mapping(cls, name: str, value: dict[str, Any]) -> "DesignConfig":
        if not isinstance(value, dict):
            raise TypeError(f"Design {name!r} must map to an object")
        return cls(
            name=name,
            prompt=str(value.get("prompt", f"prompts/{name}.txt")),
            reference=str(value.get("reference", f"reference/{name}")),
            top_module=str(value.get("top_module", name)),
            reference_top=(
                str(value["reference_top"])
                if value.get("reference_top") is not None
                else None
            ),
            language=str(value.get("language", "verilog")),  # type: ignore[arg-type]
            require_case_default=bool(value.get("require_case_default", False)),
            port_aliases=dict(value.get("port_aliases", {})),
            description=str(value.get("description", "")),
        )


@dataclass(slots=True)
class RunMetrics:
    designs: int
    stage_rates: dict[str, float]
    conditional_yields: dict[str, float]
    e2e_at_1: float
    e2e_at_k: float
    sey_at_k: float
    ets: float | None
    ttfp_seconds: float | None
    unsolved: int
    first_failure_shares: dict[str, float]
    root_cause_shares: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def path_to_posix(path: Path | None) -> str | None:
    return path.as_posix() if path is not None else None


def attempt_from_dict(data: dict[str, Any]) -> AttemptResult:
    stages = {
        name: StageResult(
            stage=value["stage"],
            status=value["status"],
            message=value.get("message", ""),
            log_path=value.get("log_path"),
            details=dict(value.get("details", {})),
        )
        for name, value in dict(data["stages"]).items()
    }
    return AttemptResult(
        design=str(data["design"]),
        attempt=int(data["attempt"]),
        provider=str(data["provider"]),
        model=str(data["model"]),
        elapsed_seconds=float(data["elapsed_seconds"]),
        stages=stages,
        first_failure=data.get("first_failure"),
        root_cause=data.get("root_cause"),
        prompt_path=str(data["prompt_path"]),
        raw_response_path=str(data["raw_response_path"]),
        rtl_path=data.get("rtl_path"),
        metadata_path=str(data["metadata_path"]),
        synthesis=data.get("synthesis"),
    )
