from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .utils import validate_module_name

_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_$]*"


class VerilogParseError(ValueError):
    """Raised when a Verilog structure cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class Port:
    name: str
    direction: str
    width: int | str
    signed: bool = False

    def normalized(self) -> tuple[str, int | str, bool]:
        return self.direction, self.width, self.signed


@dataclass(frozen=True, slots=True)
class ModuleSpan:
    name: str
    start: int
    end: int
    text: str


def mask_comments_and_strings(text: str) -> str:
    """Mask comments and strings while preserving length and newlines."""
    output = list(text)
    state = "code"
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if char == "/" and nxt == "/":
                output[index] = output[index + 1] = " "
                index += 2
                state = "line_comment"
                continue
            if char == "/" and nxt == "*":
                output[index] = output[index + 1] = " "
                index += 2
                state = "block_comment"
                continue
            if char == '"':
                output[index] = " "
                index += 1
                state = "string"
                continue
        elif state == "line_comment":
            if char == "\n":
                state = "code"
            else:
                output[index] = " "
        elif state == "block_comment":
            if char == "*" and nxt == "/":
                output[index] = output[index + 1] = " "
                index += 2
                state = "code"
                continue
            if char != "\n":
                output[index] = " "
        elif state == "string":
            if char == "\\" and index + 1 < len(text):
                output[index] = output[index + 1] = " "
                index += 2
                continue
            if char == '"':
                output[index] = " "
                state = "code"
            elif char != "\n":
                output[index] = " "
        index += 1
    return "".join(output)


def mask_strings_only(text: str) -> str:
    output = list(text)
    in_string = False
    index = 0
    while index < len(text):
        char = text[index]
        if not in_string and char == '"':
            output[index] = " "
            in_string = True
        elif in_string:
            if char == "\\" and index + 1 < len(text):
                output[index] = output[index + 1] = " "
                index += 1
            elif char == '"':
                output[index] = " "
                in_string = False
            elif char != "\n":
                output[index] = " "
        index += 1
    return "".join(output)


def _find_matching(text: str, start: int, opening: str = "(", closing: str = ")") -> int:
    if start >= len(text) or text[start] != opening:
        raise VerilogParseError(f"Expected {opening!r} at offset {start}")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    raise VerilogParseError(f"Unmatched {opening!r} at offset {start}")


def split_top_level(text: str, separator: str = ",") -> list[str]:
    result: list[str] = []
    start = 0
    depths = {"(": 0, "[": 0, "{": 0}
    pairs = {")": "(", "]": "[", "}": "{"}
    for index, char in enumerate(text):
        if char in depths:
            depths[char] += 1
        elif char in pairs:
            key = pairs[char]
            depths[key] = max(0, depths[key] - 1)
        elif char == separator and all(depth == 0 for depth in depths.values()):
            result.append(text[start:index])
            start = index + 1
    result.append(text[start:])
    return result


def module_spans(text: str) -> list[ModuleSpan]:
    masked = mask_comments_and_strings(text)
    token_pattern = re.compile(r"\b(module|endmodule)\b")
    modules: list[ModuleSpan] = []
    open_module: tuple[str, int] | None = None
    for match in token_pattern.finditer(masked):
        token = match.group(1)
        if token == "module":
            if open_module is not None:
                raise VerilogParseError("Nested or unterminated module declaration")
            tail = masked[match.end() :]
            name_match = re.match(
                rf"\s*(?:(?:automatic|static)\s+)?({_IDENTIFIER})", tail
            )
            if not name_match:
                raise VerilogParseError("Module declaration has no valid identifier")
            name = name_match.group(1)
            open_module = (name, match.start())
        elif open_module is None:
            raise VerilogParseError("endmodule appears before module")
        else:
            name, start = open_module
            end = match.end()
            modules.append(ModuleSpan(name=name, start=start, end=end, text=text[start:end]))
            open_module = None
    if open_module is not None:
        raise VerilogParseError(f"Module {open_module[0]!r} is missing endmodule")
    return modules


def extract_modules(text: str) -> str | None:
    try:
        spans = module_spans(text)
    except VerilogParseError:
        return None
    if not spans:
        return None
    return "\n\n".join(span.text.strip() for span in spans) + "\n"


def module_names(text: str) -> list[str]:
    return [span.name for span in module_spans(text)]


def detect_top_module(text: str, expected: str | None = None) -> str | None:
    try:
        spans = module_spans(text)
    except VerilogParseError:
        return None
    names = [span.name for span in spans]
    if expected:
        return expected if expected in names else None
    if not names:
        return None
    masked = mask_comments_and_strings(text)
    instantiated: set[str] = set()
    for module_name in names:
        pattern = re.compile(
            rf"\b{re.escape(module_name)}\b\s*(?:#\s*\([^;]*?\)\s*)?"
            rf"{_IDENTIFIER}\s*\(",
            re.DOTALL,
        )
        for match in pattern.finditer(masked):
            prefix = masked[max(0, match.start() - 12) : match.start()]
            if re.search(r"\bmodule\s*$", prefix):
                continue
            instantiated.add(module_name)
            break
    candidates = [name for name in names if name not in instantiated]
    return candidates[0] if len(candidates) == 1 else (candidates[-1] if candidates else names[-1])


def _module_span(text: str, module_name: str) -> ModuleSpan:
    validate_module_name(module_name)
    for span in module_spans(text):
        if span.name == module_name:
            return span
    raise VerilogParseError(f"Module {module_name!r} not found")


def _normalize_width(range_text: str | None) -> int | str:
    if not range_text:
        return 1
    compact = re.sub(r"\s+", "", range_text)
    literal = re.fullmatch(r"\[(-?\d+):(-?\d+)\]", compact)
    if literal:
        return abs(int(literal.group(1)) - int(literal.group(2))) + 1
    return compact


def _strip_decl_tokens(segment: str) -> tuple[str, str | None, bool, str]:
    direction_match = re.search(r"\b(input|output|inout)\b", segment)
    direction = direction_match.group(1) if direction_match else ""
    range_match = re.search(r"\[[^\]]+\]", segment)
    range_text = range_match.group(0) if range_match else None
    signed = bool(re.search(r"\bsigned\b", segment))
    cleaned = segment
    cleaned = re.sub(r"\(\*.*?\*\)", " ", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\b(input|output|inout|wire|reg|logic|signed|unsigned|var)\b", " ", cleaned)
    cleaned = re.sub(r"\[[^\]]+\]", " ", cleaned)
    cleaned = cleaned.split("=", 1)[0]
    return direction, range_text, signed, cleaned


def parse_interface(text: str, module_name: str) -> dict[str, Port]:
    span = _module_span(text, module_name)
    masked = mask_comments_and_strings(span.text)
    declaration = re.search(
        rf"\bmodule\s+(?:(?:automatic|static)\s+)?{re.escape(module_name)}\b",
        masked,
    )
    if not declaration:
        raise VerilogParseError(f"Malformed declaration for module {module_name!r}")
    cursor = declaration.end()
    while cursor < len(masked) and masked[cursor].isspace():
        cursor += 1
    if cursor < len(masked) and masked[cursor] == "#":
        cursor += 1
        while cursor < len(masked) and masked[cursor].isspace():
            cursor += 1
        if cursor >= len(masked) or masked[cursor] != "(":
            raise VerilogParseError("Malformed parameter list")
        cursor = _find_matching(masked, cursor) + 1
        while cursor < len(masked) and masked[cursor].isspace():
            cursor += 1
    if cursor >= len(masked) or masked[cursor] != "(":
        raise VerilogParseError("Malformed module port list")
    close = _find_matching(masked, cursor)
    header = span.text[cursor + 1 : close]
    masked_header = masked[cursor + 1 : close]
    ports: dict[str, Port] = {}

    ansi = bool(re.search(r"\b(input|output|inout)\b", masked_header))
    if ansi:
        direction = ""
        range_text: str | None = None
        signed = False
        original_segments = split_top_level(header)
        masked_segments = split_top_level(masked_header)
        for original, masked_segment in zip(original_segments, masked_segments, strict=True):
            new_direction, new_range, new_signed, cleaned = _strip_decl_tokens(masked_segment)
            if new_direction:
                direction = new_direction
                range_text = new_range
                signed = new_signed
            elif new_range is not None:
                range_text = new_range
                signed = new_signed or signed
            if not direction:
                continue
            identifiers = re.findall(_IDENTIFIER, cleaned)
            if not identifiers:
                identifiers = re.findall(_IDENTIFIER, original.split("=", 1)[0])
                identifiers = [
                    item
                    for item in identifiers
                    if item not in {"input", "output", "inout", "wire", "reg", "logic", "signed", "unsigned", "var"}
                ]
            if not identifiers:
                raise VerilogParseError(f"Could not parse port segment: {original!r}")
            name = identifiers[-1]
            if name in ports:
                raise VerilogParseError(f"Duplicate port {name!r}")
            ports[name] = Port(name, direction, _normalize_width(range_text), signed)
    else:
        header_names = [name for name in re.findall(_IDENTIFIER, masked_header)]
        body = span.text[close + 1 :]
        masked_body = masked[close + 1 :]
        declarations: dict[str, Port] = {}
        for match in re.finditer(r"\b(input|output|inout)\b([^;]*);", masked_body, re.DOTALL):
            statement = match.group(0)
            direction, range_text, signed, cleaned = _strip_decl_tokens(statement)
            for name_part in split_top_level(cleaned):
                identifiers = re.findall(_IDENTIFIER, name_part.split("=", 1)[0])
                if not identifiers:
                    continue
                name = identifiers[-1]
                declarations[name] = Port(name, direction, _normalize_width(range_text), signed)
        for name in header_names:
            if name not in declarations:
                raise VerilogParseError(f"Port {name!r} has no input/output/inout declaration")
            ports[name] = declarations[name]
    if not ports:
        raise VerilogParseError(f"No ports found for module {module_name!r}")
    return ports


def compare_interfaces(
    candidate: dict[str, Port],
    reference: dict[str, Port],
    aliases: dict[str, str] | None = None,
) -> list[str]:
    aliases = aliases or {}
    mapped: dict[str, Port] = {}
    issues: list[str] = []
    for name, port in candidate.items():
        mapped_name = aliases.get(name, name)
        if mapped_name in mapped:
            issues.append(f"multiple candidate ports map to {mapped_name!r}")
            continue
        mapped[mapped_name] = Port(mapped_name, port.direction, port.width, port.signed)
    missing = sorted(set(reference) - set(mapped))
    extra = sorted(set(mapped) - set(reference))
    if missing:
        issues.append("missing ports: " + ", ".join(missing))
    if extra:
        issues.append("unexpected ports: " + ", ".join(extra))
    for name in sorted(set(reference) & set(mapped)):
        expected = reference[name]
        actual = mapped[name]
        if actual.direction != expected.direction:
            issues.append(
                f"port {name}: direction {actual.direction!r} != {expected.direction!r}"
            )
        if actual.width != expected.width:
            issues.append(f"port {name}: width {actual.width!r} != {expected.width!r}")
        if actual.signed != expected.signed:
            issues.append(f"port {name}: signedness differs")
    return issues


def completeness_issues(
    text: str,
    top_module: str,
    *,
    require_case_default: bool = False,
) -> list[str]:
    issues: list[str] = []
    strings_masked = mask_strings_only(text)
    masked = mask_comments_and_strings(text)
    try:
        span = _module_span(text, top_module)
        ports = parse_interface(text, top_module)
    except VerilogParseError as exc:
        return [str(exc)]

    if re.search(r"\b(TODO|FIXME|TBD|XXX|PLACEHOLDER)\b", strings_masked, re.IGNORECASE):
        issues.append("placeholder marker found")
    if re.search(r"\(\*\s*blackbox\b", masked, re.IGNORECASE):
        issues.append("black-box module detected")
    if re.search(r"\balways(?:_comb|_ff|_latch)?\s*(?:@\s*\([^)]*\))?\s*begin\s*end\b", masked, re.DOTALL):
        issues.append("empty always block")
    if require_case_default:
        for case_match in re.finditer(r"\bcase[xz]?\b", masked):
            end_match = re.search(r"\bendcase\b", masked[case_match.end() :])
            if end_match:
                case_body = masked[case_match.end() : case_match.end() + end_match.start()]
                if not re.search(r"\bdefault\s*:", case_body):
                    issues.append("case statement lacks default branch")
                    break

    module_masked = mask_comments_and_strings(span.text)
    primitive_gate = (
        r"(?:and|nand|or|nor|xor|xnor|buf|not|bufif0|bufif1|"
        r"notif0|notif1|cmos|rcmos|nmos|pmos|rnmos|rpmos|tran|"
        r"rtran|tranif0|tranif1|rtranif0|rtranif1|pullup|pulldown)"
    )
    has_behavior = bool(
        re.search(r"\bassign\b|\balways(?:_comb|_ff|_latch)?\b", module_masked)
        or re.search(rf"\b{primitive_gate}\b\s*(?:{_IDENTIFIER}\s*)?\(", module_masked)
    )
    module_name_set = set(module_names(text))
    for child in module_name_set - {top_module}:
        if re.search(rf"\b{re.escape(child)}\b\s*(?:#\s*\([^;]*\)\s*)?{_IDENTIFIER}\s*\(", module_masked, re.DOTALL):
            has_behavior = True
    if not has_behavior:
        issues.append("no executable logic or child-module instance found")

    for name, port in ports.items():
        if port.direction not in {"output", "inout"}:
            continue
        escaped = re.escape(name)
        lhs_pattern = (
            rf"(?:\bassign\s+)?(?:"
            rf"\{{[^;=]*\b{escaped}\b[^;=]*\}}"
            rf"|\b{escaped}\b(?:\s*\[[^\]]+\])?"
            rf")\s*(?:<=|=(?!=))"
        )
        driven = bool(
            re.search(lhs_pattern, module_masked, re.DOTALL)
            or re.search(rf"\.\s*{_IDENTIFIER}\s*\(\s*{escaped}\s*\)", module_masked)
            or re.search(
                rf"\b{primitive_gate}\b\s*(?:{_IDENTIFIER}\s*)?\(\s*{escaped}\b",
                module_masked,
            )
        )
        if not driven:
            issues.append(f"output {name!r} appears undriven")
    return sorted(set(issues))


def iter_module_texts(text: str) -> Iterable[tuple[str, str]]:
    for span in module_spans(text):
        yield span.name, span.text
