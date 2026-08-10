from __future__ import annotations

from pathlib import Path

from llm_rtl_eval.models import DesignConfig
from llm_rtl_eval.stages import build_equivalence_script, classify_root_cause


def test_equivalence_script_contains_separate_gold_and_gate_designs(tmp_path: Path) -> None:
    ref = tmp_path / "ref.v"
    cand = tmp_path / "cand.v"
    ref.write_text("module r; endmodule", encoding="utf-8")
    cand.write_text("module c; endmodule", encoding="utf-8")
    config = DesignConfig(
        name="d",
        prompt="p",
        reference="r",
        top_module="c",
        reference_top="r",
    )
    script = build_equivalence_script(cand, [ref], config, induction_depth=7)
    assert "design -stash gold_design" in script
    assert "design -stash gate_design" in script
    assert "design -reset-vlog" in script
    assert "equiv_make gold gate equiv" in script
    assert "equiv_simple -seq 7" in script
    assert "equiv_induct -seq 7" in script
    assert "equiv_status -assert" in script


def test_root_cause_mapping() -> None:
    assert classify_root_cause("P") == "compiler"
    assert classify_root_cause("C") == "compiler"
    assert classify_root_cause("E") == "not-elaborated"
    assert classify_root_cause("M") == "partial_module"
    assert classify_root_cause("F") == "functional_mismatch"
