from __future__ import annotations

import pytest

from llm_rtl_eval.parsing import (
    Port,
    compare_interfaces,
    completeness_issues,
    detect_top_module,
    extract_modules,
    mask_comments_and_strings,
    module_names,
    parse_interface,
)


def test_mask_comments_and_strings_preserves_length_and_newlines() -> None:
    text = 'module x; // module fake\ninitial $display("endmodule"); /* module y */ endmodule\n'
    masked = mask_comments_and_strings(text)
    assert len(masked) == len(text)
    assert masked.count("\n") == text.count("\n")
    assert "fake" not in masked
    assert "module y" not in masked


def test_extract_modules_from_fenced_response() -> None:
    text = "Here is the RTL:\n```verilog\nmodule a(input x, output y); assign y=x; endmodule\n```"
    rtl = extract_modules(text)
    assert rtl is not None
    assert rtl.startswith("module a")
    assert rtl.rstrip().endswith("endmodule")


def test_extract_modules_ignores_tokens_in_comments_and_strings() -> None:
    text = '''
// module fake; endmodule
module real(input wire a, output wire y);
  initial $display("module ghost; endmodule");
  assign y = a;
endmodule
'''
    assert module_names(text) == ["real"]


def test_extract_modules_rejects_unterminated_module() -> None:
    assert extract_modules("module broken(input a, output y); assign y=a;") is None


def test_detect_top_module_from_instantiation_graph() -> None:
    text = '''
module child(input wire a, output wire y); assign y=a; endmodule
module top(input wire a, output wire y); child u_child(.a(a), .y(y)); endmodule
'''
    assert detect_top_module(text) == "top"
    assert detect_top_module(text, "child") == "child"


def test_parse_ansi_interface_with_carried_direction_and_width() -> None:
    text = '''
module sample(
  input wire signed [3:0] a, b,
  output reg [1:0] y,
  output valid
);
endmodule
'''
    ports = parse_interface(text, "sample")
    assert ports["a"] == Port("a", "input", 4, True)
    assert ports["b"] == Port("b", "input", 4, True)
    assert ports["y"] == Port("y", "output", 2, False)
    assert ports["valid"] == Port("valid", "output", 1, False)


def test_parse_non_ansi_interface() -> None:
    text = '''
module sample(a, b, y);
  input [7:0] a, b;
  output [8:0] y;
  assign y = a + b;
endmodule
'''
    ports = parse_interface(text, "sample")
    assert ports["a"].width == 8
    assert ports["b"].width == 8
    assert ports["y"].width == 9


def test_compare_interfaces_reports_missing_extra_and_width() -> None:
    candidate = {
        "a": Port("a", "input", 4),
        "z": Port("z", "output", 1),
    }
    reference = {
        "a": Port("a", "input", 8),
        "y": Port("y", "output", 1),
    }
    issues = compare_interfaces(candidate, reference)
    assert any("missing ports: y" in issue for issue in issues)
    assert any("unexpected ports: z" in issue for issue in issues)
    assert any("port a: width" in issue for issue in issues)


def test_compare_interfaces_supports_explicit_aliases() -> None:
    candidate = {"out_value": Port("out_value", "output", 1)}
    reference = {"y": Port("y", "output", 1)}
    assert compare_interfaces(candidate, reference, {"out_value": "y"}) == []


def test_completeness_ignores_placeholder_word_inside_string() -> None:
    text = '''
module sample(input wire a, output wire y);
  initial $display("TODO is documentation text");
  assign y = a;
endmodule
'''
    assert completeness_issues(text, "sample") == []


def test_completeness_catches_placeholder_comment_and_undriven_output() -> None:
    text = '''
module sample(input wire a, output wire y);
  // TODO: implement output
  wire internal = a;
endmodule
'''
    issues = completeness_issues(text, "sample")
    assert "placeholder marker found" in issues
    assert "output 'y' appears undriven" in issues


def test_completeness_case_default_policy() -> None:
    text = '''
module sample(input wire [1:0] a, output reg y);
  always @* begin
    case (a)
      2'b00: y = 1'b0;
      2'b01: y = 1'b1;
    endcase
  end
endmodule
'''
    assert "case statement lacks default branch" in completeness_issues(
        text, "sample", require_case_default=True
    )


def test_completeness_detects_output_driven_through_concatenation() -> None:
    text = '''
module sample(input wire a, input wire b, output wire sum, output wire carry);
  assign {carry, sum} = a + b;
endmodule
'''
    assert completeness_issues(text, "sample") == []


def test_multiple_modules_are_extracted_in_order() -> None:
    text = '''
module child(input wire a, output wire y); assign y = a; endmodule
module top(input wire a, output wire y); child u0(.a(a), .y(y)); endmodule
'''
    rtl = extract_modules(text)
    assert rtl is not None
    assert rtl.index("module child") < rtl.index("module top")


def test_completeness_accepts_primitive_gate_outputs() -> None:
    text = '''
module gate_half_adder(input wire a, input wire b, output wire sum, output wire carry);
  xor u_sum(sum, a, b);
  and u_carry(carry, a, b);
endmodule
'''
    assert completeness_issues(text, "gate_half_adder") == []
