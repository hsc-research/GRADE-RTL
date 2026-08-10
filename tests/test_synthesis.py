from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_rtl_eval import synthesis


def test_generic_synthesis_script_uses_tee_for_stat_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rtl = tmp_path / "top.v"
    rtl.write_text("module top(input wire a, output wire y); assign y=a; endmodule\n", encoding="utf-8")
    output = tmp_path / "out"

    monkeypatch.setattr(synthesis.shutil, "which", lambda _: "/usr/bin/yosys")

    def fake_run(argv, *, cwd, timeout):
        script_path = Path(argv[-1])
        script = script_path.read_text(encoding="utf-8")
        assert "tee -q -o" in script
        assert "stat -json" in script
        assert "stat -json " not in script
        (output / "netlist.v").write_text("module top; endmodule\n", encoding="utf-8")
        (output / "stat.json").write_text(json.dumps({"modules": {}}), encoding="utf-8")
        return 0, "ok"

    monkeypatch.setattr(synthesis, "run_command", fake_run)
    result = synthesis.run_generic_yosys_synthesis(
        rtl, top_module="top", output_dir=output
    )
    assert result["status"] == "PASS"


def test_generic_synthesis_rejects_invalid_top(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rtl = tmp_path / "top.v"
    rtl.write_text("module top; endmodule\n", encoding="utf-8")
    monkeypatch.setattr(synthesis.shutil, "which", lambda _: "/usr/bin/yosys")
    with pytest.raises(ValueError, match="Invalid Verilog module name"):
        synthesis.run_generic_yosys_synthesis(
            rtl, top_module="bad;top", output_dir=tmp_path / "out"
        )


def test_generic_synthesis_refuses_nonempty_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rtl = tmp_path / "top.v"
    rtl.write_text("module top; endmodule\n", encoding="utf-8")
    output = tmp_path / "out"
    output.mkdir()
    (output / "old.txt").write_text("old", encoding="utf-8")
    monkeypatch.setattr(synthesis.shutil, "which", lambda _: "/usr/bin/yosys")
    with pytest.raises(FileExistsError, match="not empty"):
        synthesis.run_generic_yosys_synthesis(
            rtl, top_module="top", output_dir=output
        )
