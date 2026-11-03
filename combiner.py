"""Conservative offline combiner for the supplied Syntec CAM post format."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys


class ProgramError(ValueError):
    pass


WORD = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))")
TOOL_CHANGE = re.compile(r"T(\d+)\s+M0?6", re.I)
OFFSET = re.compile(r"G(54|55|56|57|58|59)(?:\s+P([78]))?", re.I)
TOOL_INFO = re.compile(r"\(T(\d+)\s+(.+)\)", re.I)
ALLOWED_G = {0, 1, 2, 3, 17, 18, 19, 28, 40, 41, 43, 49, 54, 55, 56, 57, 58, 59, 90, 91, 94}
ALLOWED_M = {3, 5, 8, 9}
STARTUP = ["G90 G94 G17 G49 G40 G80", "G70", "G28 G91 Z0.", "G90"]
BREAK = "(TOOL BREAK CONTROL)"
BREAK_NOTE = "(NO TOOL BREAK CONTROL AVAILABLE IN PIONEER MARCO)"
END_COMMANDS = ("M05", "G49", "G28 G91 Z0.", "G90")
LOAD_OFFSETS = ("G54", "G55", "G56", "G57")
UNLOAD_OFFSETS = ("G58", "G59", "G54 P7", "G54 P8")


def code(line: str) -> str:
    """Strip ordinary, non-nested parenthesized comments and normalize spaces."""
    clean = re.sub(r"\([^()]*\)", "", line).strip().upper()
    if "(" in clean or ")" in clean:
        raise ProgramError(f"Unsupported comment: {line!r}")
    return " ".join(clean.split())


def words(line: str) -> list[tuple[str, str]]:
    compact = code(line).replace(" ", "")
    matches = list(WORD.finditer(compact))
    if "".join(match.group(0) for match in matches) != compact:
        raise ProgramError(f"Unsupported or malformed command: {line!r}")
    return [(match.group(1), match.group(2)) for match in matches]


def g_or_m_number(value: str) -> int:
    number = float(value)
    if not number.is_integer():
        raise ProgramError(f"Unsupported decimal G or M code: {value}")
    return int(number)


def normalized_metadata(text: str) -> str:
    # ZMIN describes a path, not the physical tool.
    text = re.sub(r"\bZMIN\s*=\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)", "", text, flags=re.I)
    return " ".join(text.upper().split())


@dataclass(frozen=True)
class Section:
    tool: int
    prefix: tuple[str, ...]
    lines: tuple[str, ...]
    offsets: tuple[str, ...]


@dataclass(frozen=True)
class Program:
    path: Path
    number: int
    title: str
    startup: tuple[str, ...]
    footer: tuple[str, ...]
    tools: dict[int, str]
    sections: tuple[Section, ...]


def parse_program(path: Path, expected_offsets: tuple[str, ...]) -> Program:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ProgramError(f"Cannot read {path}: {exc}") from exc
    if len(lines) < 10 or lines[0].strip() != "%" or lines[-1].strip() != "%":
        raise ProgramError(f"{path.name}: expected a percent-delimited program.")
    match = re.fullmatch(r"O(\d{1,4})\s*(\([^()]*\))?", lines[1].strip(), re.I)
    if not match:
        raise ProgramError(f"{path.name}: expected an O number on the second line.")
    number = int(match.group(1))
    if not 1 <= number <= 9999:
        raise ProgramError(f"{path.name}: invalid O number.")
    title = match.group(2) or ""

    positions = [i for i, line in enumerate(lines) if TOOL_CHANGE.fullmatch(code(line))]
    if not positions:
        raise ProgramError(f"{path.name}: no supported tool changes found.")
    first = positions[0]
    initial_commands = [code(line) for line in lines[2:first] if code(line)]
    if initial_commands != STARTUP:
        raise ProgramError(f"{path.name}: startup differs from the supported inch-mode post.")

    tools: dict[int, str] = {}
    for line in lines[2:first]:
        info = TOOL_INFO.fullmatch(line.strip())
        if info:
            tool = int(info.group(1))
            if tool in tools:
                raise ProgramError(f"{path.name}: duplicate T{tool} description.")
            tools[tool] = normalized_metadata(info.group(2))

    sections: list[Section] = []
    previous_end = first
    first_prefix = tuple(line for line in lines[2:first] if line.strip().startswith("(")
                         and not TOOL_INFO.fullmatch(line.strip())
                         and not re.match(r"\((FILE NAME|POSTED ON|POST PROC|POST VERS)\b", line.strip(), re.I))
    for index, start in enumerate(positions):
        change = TOOL_CHANGE.fullmatch(code(lines[start]))
        assert change is not None
        tool = int(change.group(1))
        if tool not in tools or not tools[tool]:
            raise ProgramError(f"{path.name}: missing description for T{tool}.")
        if any(section.tool == tool for section in sections):
            raise ProgramError(f"{path.name}: T{tool} is used in more than one tool section.")
        if index == 0:
            prefix = first_prefix
        else:
            prefix = tuple(lines[previous_end:start])
            if any(code(line) not in ("", "M09") for line in prefix):
                raise ProgramError(f"{path.name}: unexpected commands before T{tool}.")
        limit = positions[index + 1] if index + 1 < len(positions) else len(lines) - 1
        markers = [i for i in range(start, limit) if lines[i].strip().upper() == BREAK]
        if len(markers) != 1:
            raise ProgramError(f"{path.name}: T{tool} must have exactly one tool-break marker.")
        marker = markers[0]
        if marker + 1 >= limit or lines[marker + 1].strip().upper() != BREAK_NOTE:
            raise ProgramError(f"{path.name}: T{tool} has an unsupported tool-break block.")
        cursor = marker + 2
        end_codes: list[str] = []
        while cursor < limit and len(end_codes) < 4:
            value = code(lines[cursor])
            if value and value != "M09":
                end_codes.append(value)
            cursor += 1
        if tuple(end_codes) != END_COMMANDS:
            raise ProgramError(f"{path.name}: T{tool} lacks the expected spindle stop and Z retract.")
        section_lines = tuple(lines[start:cursor])
        body = section_lines[1:marker - start]
        commands = [code(line) for line in body if code(line)]
        if len(commands) < 4 or not re.fullmatch(r"S\d+(?:\.\d+)? M0?3", commands[0]):
            raise ProgramError(f"{path.name}: T{tool} must start with an explicit spindle speed.")
        if commands[1:3] != ["M08", "G17 G90 G94"]:
            raise ProgramError(f"{path.name}: T{tool} lacks the expected coolant and modal setup.")
        offset_indices = [i for i, command in enumerate(commands) if OFFSET.fullmatch(command)]
        for offset_index, position in enumerate(offset_indices):
            number_pattern = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
            if position + 2 >= len(commands) or not re.fullmatch(
                rf"G0?0 X{number_pattern} Y{number_pattern}", commands[position + 1]
            ) or not re.fullmatch(
                rf"G43 Z{number_pattern} H0*{tool}", commands[position + 2]
            ):
                raise ProgramError(f"{path.name}: T{tool} has an unsupported offset approach.")
            if offset_index:
                before = commands[:position]
                if before and re.fullmatch(r"S\d+(?:\.\d+)? M0?3", before[-1]):
                    before = before[:-1]
                if before[-3:] != ["G49", "G28 G91 Z0.", "G90"]:
                    raise ProgramError(f"{path.name}: T{tool} lacks the expected retract before an offset change.")
        offsets: list[str] = []
        comp = False
        seen_offset = False
        length_comp = False
        for line in body:
            command = code(line)
            if not command:
                continue
            match_offset = OFFSET.fullmatch(command)
            if match_offset:
                offset = f"G{match_offset.group(1)}"
                if match_offset.group(2):
                    if offset != "G54":
                        raise ProgramError(f"{path.name}: invalid extended work offset.")
                    offset += f" P{match_offset.group(2)}"
                if seen_offset and (not length_comp or comp):
                    raise ProgramError(f"{path.name}: T{tool} missing G43 or has active cutter compensation at an offset change.")
                offsets.append(offset)
                seen_offset, length_comp = True, False
                continue
            parsed = words(line)
            g_codes = [g_or_m_number(value) for letter, value in parsed if letter == "G"]
            h_values = [value for letter, value in parsed if letter == "H"]
            if 28 in g_codes and command != "G28 G91 Z0.":
                raise ProgramError(f"{path.name}: unsupported G28 move in T{tool}.")
            if h_values and (43 not in g_codes or len(h_values) != 1):
                raise ProgramError(f"{path.name}: unsupported H word in T{tool}.")
            if 43 in g_codes and (len(h_values) != 1 or not h_values[0].isdigit() or int(h_values[0]) != tool):
                raise ProgramError(f"{path.name}: T{tool} G43 must use matching H{tool}.")
            for letter, value in parsed:
                if letter not in "GMXYZIJKFRSDH":
                    raise ProgramError(f"{path.name}: unsupported {letter} word in T{tool}.")
                if letter == "G":
                    g = g_or_m_number(value)
                    if g not in ALLOWED_G:
                        raise ProgramError(f"{path.name}: unsupported G{value} in T{tool}.")
                    if g in {54, 55, 56, 57, 58, 59}:
                        raise ProgramError(f"{path.name}: work offsets must occupy their own line.")
                    if g == 41:
                        comp = True
                    elif g == 40:
                        comp = False
                    elif g == 43:
                        length_comp = True
                elif letter == "M" and g_or_m_number(value) not in ALLOWED_M:
                    raise ProgramError(f"{path.name}: unsupported M{value} in T{tool}.")
            if not seen_offset and any(letter in "XYZ" for letter, _ in parsed):
                raise ProgramError(f"{path.name}: motion before the first offset in T{tool}.")
        if tuple(offsets) != expected_offsets or not length_comp:
            raise ProgramError(f"{path.name}: T{tool} has unexpected offsets or missing G43.")
        if comp:
            raise ProgramError(f"{path.name}: cutter compensation remains active at T{tool} end.")
        sections.append(Section(tool, prefix, section_lines, tuple(offsets)))
        previous_end = cursor

    footer = tuple(line for line in lines[previous_end:] if code(line) or line.strip() == "%")
    if len(footer) != 3 or not re.fullmatch(r"G53 G0?0 X[+-]?(?:\d+(?:\.\d*)?|\.\d+) Y[+-]?(?:\d+(?:\.\d*)?|\.\d+)", code(footer[0])) or code(footer[1]) != "M30" or footer[2].strip() != "%":
        raise ProgramError(f"{path.name}: unsupported program footer.")
    return Program(path, number, title, tuple(STARTUP), footer, tools, tuple(sections))


def tool_order(load: Program, unload: Program) -> list[int]:
    sequences = [[section.tool for section in p.sections] for p in (load, unload)]
    order = list(dict.fromkeys(sequences[0] + sequences[1]))
    edges = {tool: set() for tool in order}
    for sequence in sequences:
        for a, b in zip(sequence, sequence[1:]):
            edges[a].add(b)
    result: list[int] = []
    while len(result) < len(order):
        ready = [t for t in order if t not in result and not any(t in edges[other] for other in order if other not in result)]
        if not ready:
            raise ProgramError("The two programs require conflicting tool orders; cannot safely group tools.")
        result.append(ready[0])
    return result


def combine(load: Program, unload: Program, output_number: int) -> str:
    if not 1 <= output_number <= 9999 or output_number in (load.number, unload.number):
        raise ProgramError("Choose a new O number from 1 to 9999, different from both inputs.")
    if load.path.resolve() == unload.path.resolve():
        raise ProgramError("Loading and unloading must be different source files.")
    if load.startup != unload.startup or tuple(map(code, load.footer)) != tuple(map(code, unload.footer)):
        raise ProgramError("Startup or final park blocks differ; cannot safely choose one.")
    load_sections = {section.tool: section for section in load.sections}
    unload_sections = {section.tool: section for section in unload.sections}
    order = tool_order(load, unload)
    for tool in set(load_sections) & set(unload_sections):
        if load.tools[tool] != unload.tools[tool]:
            raise ProgramError(f"T{tool} descriptions differ beyond ZMIN; verify the physical tools and post data.")

    result = ["%", f"O{output_number:04d} (COMBINED PROGRAM VERIFY BEFORE USE)",
              "(GENERATED FILE REQUIRES SIMULATION AND DRY RUN)",
              f"(LOADING SOURCE O{load.number:04d} {load.title.strip('()')})",
              f"(UNLOADING SOURCE O{unload.number:04d} {unload.title.strip('()')})"]
    for tool in order:
        if tool in load.tools:
            result.append(f"(LOAD T{tool} {load.tools[tool]})")
        if tool in unload.tools:
            result.append(f"(UNLOAD T{tool} {unload.tools[tool]})")
    result.extend(load.startup)
    for tool in order:
        for role, section in (("LOAD", load_sections.get(tool)), ("UNLOAD", unload_sections.get(tool))):
            if section is None:
                continue
            result.extend(("", f"({role} T{tool} SOURCE SECTION)", *section.prefix))
            if role == "UNLOAD" and tool in load_sections:
                result.extend(section.lines[1:])
            else:
                result.extend(section.lines)
    result.extend(load.footer)
    return "\r\n".join(result) + "\r\n"


def create_file(load_path: Path, unload_path: Path, output_path: Path, number: int) -> tuple[Program, Program, list[int]]:
    if output_path.resolve() in (load_path.resolve(), unload_path.resolve()):
        raise ProgramError("Output must not overwrite an input file.")
    load = parse_program(load_path, LOAD_OFFSETS)
    unload = parse_program(unload_path, UNLOAD_OFFSETS)
    text = combine(load, unload, number)
    created = False
    try:
        with output_path.open("x", encoding="ascii", newline="") as output:
            created = True
            output.write(text)
    except (OSError, UnicodeError) as exc:
        if created:
            try:
                output_path.unlink()
            except OSError as cleanup:
                raise ProgramError(f"Output failed and the incomplete file could not be removed: {output_path}: {cleanup}") from exc
        raise ProgramError(f"Cannot create output file: {exc}") from exc
    return load, unload, tool_order(load, unload)


def gui() -> None:
    try:
        from qt_gui import run_gui
    except ModuleNotFoundError as exc:
        if exc.name and (exc.name == "PySide6" or exc.name.startswith("PySide6.")):
            raise SystemExit("PySide6 is missing. Run Setup Combiner.cmd, then start the combiner again.") from exc
        raise
    run_gui(create_file, ProgramError)


def main() -> int:
    if len(sys.argv) == 1:
        gui()
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load", required=True, type=Path)
    parser.add_argument("--unload", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--number", required=True, type=int)
    parser.add_argument("--confirm-tools", required=True, action="store_true",
                        help="Confirm shared physical tools and offsets match.")
    args = parser.parse_args()
    try:
        _, _, order = create_file(args.load, args.unload, args.output, args.number)
    except ProgramError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("Created:", args.output, "| Tool order:", ", ".join(f"T{t}" for t in order))
    print("Verify tool setup and offsets, simulate, and dry run before cutting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
