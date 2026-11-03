import os
from pathlib import Path
import re
import tempfile
import unittest
from dataclasses import replace

import combiner


def sample(number, offsets, tools=(1, 2)):
    lines = ["%", f"O{number}", *[
        f"(T{tool} DIA=0.375 RADIUS=0.1875 ZMIN=0.1 - END MILL)"
        for tool in tools
    ], *combiner.STARTUP]
    for index, tool in enumerate(tools):
        lines += [f"(OP T{tool})"]
        if index:
            lines.append("M09")
        lines += [f"T{tool} M06", "S2000 M03", "M08", "G17 G90 G94"]
        for offset in offsets:
            lines += [offset, "G00 X1. Y1.", f"G43 Z1. H{tool:02d}", "G01 Z0. F10.",
                      "G00 Z1.", "G49", "G28 G91 Z0.", "G90"]
        lines += [combiner.BREAK, combiner.BREAK_NOTE, "M05", "G49", "G28 G91 Z0.", "G90"]
    lines += ["G53 G00 X-7.5 Y0.", "M30", "%"]
    return "\n".join(lines) + "\n"


def path_sequences(text):
    """Extract work-offset machining blocks independently from the combiner."""
    tool = None
    offset = None
    current = []
    paths = {}

    def finish():
        nonlocal current
        if offset is not None:
            while current and (current[-1] in {"G49", "G28 G91 Z0.", "G90"} or
                               re.fullmatch(r"S\d+(?:\.\d+)? M0?3", current[-1])):
                current.pop()
            key = (tool, offset)
            if key in paths:
                raise AssertionError(f"Duplicate path: {key}")
            paths[key] = current
        current = []

    for line in text.splitlines():
        if line.strip().upper() == combiner.BREAK:
            finish()
            offset = None
            continue
        command = combiner.code(line)
        change = combiner.TOOL_CHANGE.fullmatch(command)
        if change:
            finish()
            offset = None
            tool = int(change.group(1))
            continue
        if combiner.OFFSET.fullmatch(command):
            finish()
            offset = command
            current = [command]
        elif offset is not None and command:
            current.append(command)
    finish()
    return paths


class CombinerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.load = self.root / "load.nc"
        self.unload = self.root / "unload.nc"
        self.load.write_text(sample(1001, combiner.LOAD_OFFSETS), encoding="ascii")
        self.unload.write_text(sample(3001, combiner.UNLOAD_OFFSETS), encoding="ascii")

    def programs(self):
        return (combiner.parse_program(self.load, combiner.LOAD_OFFSETS),
                combiner.parse_program(self.unload, combiner.UNLOAD_OFFSETS))

    def test_combine_preserves_source_paths_and_tool_changes(self):
        load, unload = self.programs()
        result = combiner.combine(load, unload, 1234)
        expected = path_sequences(self.load.read_text()) | path_sequences(self.unload.read_text())
        self.assertEqual(expected, path_sequences(result))
        self.assertEqual(re.findall(r"(?m)^T\d+ M06\r?$", result), ["T1 M06\r", "T2 M06\r"])
        self.assertEqual(result.count("M30"), 1)

    def test_rejects_bad_tool_description(self):
        self.unload.write_text(self.unload.read_text().replace("DIA=0.375", "DIA=0.5", 1))
        with self.assertRaisesRegex(combiner.ProgramError, "descriptions differ"):
            combiner.combine(*self.programs(), 1234)

    def test_rejects_unknown_g_code_and_mismatched_offset(self):
        for old, new, error in [
            ("G01 Z0. F10.", "G65 P123", "unsupported"),
            ("G43 Z1. H01", "G43 Z1. H02", "offset approach"),
            ("G54 P8", "G54 P9", "work offsets"),
            ("G00 X1. Y1.", "X1. Y1.", "offset approach"),
            ("G28 G91 Z0.\nG90\nG59", "G90\nG90\nG59", "expected retract"),
        ]:
            with self.subTest(new=new):
                original = self.unload.read_text()
                self.unload.write_text(original.replace(old, new, 1))
                with self.assertRaisesRegex(combiner.ProgramError, error):
                    combiner.parse_program(self.unload, combiner.UNLOAD_OFFSETS)
                self.unload.write_text(original)

    def test_rejects_conflicting_tool_order(self):
        load, unload = self.programs()
        unload = replace(unload, sections=tuple(reversed(unload.sections)))
        with self.assertRaisesRegex(combiner.ProgramError, "conflicting tool orders"):
            combiner.combine(load, unload, 1234)

    def test_orders_tools_used_by_only_one_part(self):
        self.load.write_text(sample(1001, combiner.LOAD_OFFSETS, (1, 4, 5)))
        self.unload.write_text(sample(3001, combiner.UNLOAD_OFFSETS, (1, 2, 4)))
        load, unload = self.programs()
        self.assertEqual(combiner.tool_order(load, unload), [1, 2, 4, 5])
        result = combiner.combine(load, unload, 1234)
        expected = path_sequences(self.load.read_text()) | path_sequences(self.unload.read_text())
        self.assertEqual(expected, path_sequences(result))

    def test_does_not_overwrite_existing_files(self):
        output = self.root / "existing.nc"
        output.write_text("KEEP")
        with self.assertRaises(combiner.ProgramError):
            combiner.create_file(self.load, self.unload, output, 1234)
        self.assertEqual(output.read_text(), "KEEP")
        with self.assertRaises(combiner.ProgramError):
            combiner.create_file(self.load, self.unload, self.load, 1234)

    def test_no_output_on_validation_failure(self):
        self.unload.write_text(self.unload.read_text().replace("G54 P8", "G54 P9", 1))
        output = self.root / "new.nc"
        with self.assertRaises(combiner.ProgramError):
            combiner.create_file(self.load, self.unload, output, 1234)
        self.assertFalse(output.exists())

    @unittest.skipUnless(os.environ.get("SYNTEC_SAMPLE_DIR"), "Set SYNTEC_SAMPLE_DIR to test the supplied production examples.")
    def test_production_reference_all_machining_blocks(self):
        folder = Path(os.environ["SYNTEC_SAMPLE_DIR"])
        load = combiner.parse_program(folder / "1001.nc", combiner.LOAD_OFFSETS)
        unload = combiner.parse_program(folder / "3001.nc", combiner.UNLOAD_OFFSETS)
        combined = combiner.combine(load, unload, 9006)
        actual = path_sequences(combined)
        reference = path_sequences((folder / "2001.nc").read_text(encoding="ascii"))
        self.assertEqual(24, len(actual))
        self.assertEqual(reference, actual)
        self.assertEqual(re.findall(r"(?m)^T\d+ M06\r?$", combined),
                         ["T1 M06\r", "T2 M06\r", "T4 M06\r"])
        lines = combined.splitlines()
        loading_tools = {section.tool for section in load.sections}
        for role, program in (("LOAD", load), ("UNLOAD", unload)):
            for section in program.sections:
                marker = f"({role} T{section.tool} SOURCE SECTION)"
                start = lines.index(marker) + 1
                expected = list(section.prefix) + list(
                    section.lines[1:] if role == "UNLOAD" and section.tool in loading_tools
                    else section.lines
                )
                self.assertEqual(expected, lines[start:start + len(expected)], marker)


if __name__ == "__main__":
    unittest.main()
