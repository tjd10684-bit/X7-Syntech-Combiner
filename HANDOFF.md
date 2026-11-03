# Project handoff: Syntec program combiner

Last updated: 2026-11-03

## What problem this solves

The user runs a SYIL X7 mill with a Syntec controller. Parts require two
operations across eight fixture locations:

| Work offsets | Use |
| --- | --- |
| G54, G55, G56, G57 | Four Op 1 locations |
| G58, G59, G54 P7, G54 P8 | Four Op 2 locations |

At the start of a batch, the Op 2 fixtures are empty. At the end, the Op 1
fixtures are empty. The goal is to finish the previous part's Op 2 while
starting a different part's Op 1, reducing idle fixture cycles without
incurring the many extra tool changes of running each part to completion.

The machine is intentionally air-gapped; programs are transferred by USB.
The jobs share a tool list, but the operator must confirm the actual installed
tools and offsets match for each pair of programs. Avoid solutions requiring
network access or extensive editing on the machine control.

## Chosen approach

An offline Windows application takes two complete CAM-posted programs:

1. A loading program containing the new part's Op 1 toolpaths.
2. An unloading program containing the previous part's Op 2 toolpaths.

It outputs one flat NC program, organized by tool, rather than requiring a
master program and many subprogram files on the control. For shared tools,
the loading section runs before the unloading section, and the second tool
change is removed. Source-specific speeds, offsets, approaches, and other
commands are retained. The app preserves each input's tool order and rejects
conflicting orders.

The generated program retains each source section's stop and retract, then
restarts for the next section. Consequently it can differ from a CAM-posted
combined program at transitions, even where machining blocks match.

**Do not use the previous O9000-O9005/O9999 master/subprogram templates.**
They were incomplete, applied incorrect assumptions about shared paths, and
are excluded from the repository. An earlier suggestion that cutter
compensation itself was the cause of the workflow problem was not established.

## Current implementation

- [combiner.py](./combiner.py): parsing, validation, grouping, file creation,
  and command-line interface.
- [qt_gui.py](./qt_gui.py): PySide6 Qt interface, file browsing and drag/drop,
  confirmation checkbox, and messages. Changing or unsuccessfully dropping an
  input clears the tool confirmation; invalid drops also clear that field.
- [test_combiner.py](./test_combiner.py): parser and output regression tests,
  including an optional comparison with the user's sample files.
- [test_qt_gui.py](./test_qt_gui.py): optional GUI, drag/drop, and validation
  tests.
- [README.md](./README.md): operator instructions, supported input format,
  safety checks, installation, testing, and EXE build instructions.

The parser intentionally supports only the observed inch-mode post format,
the eight offsets above, one section per tool, a restricted set of G/M codes,
and particular startup, approach, retract, and tool-break marker blocks.
Shared tool descriptions must match except for `ZMIN`; physical tool
compatibility cannot be inferred from that text. Unsupported structures are
rejected instead of guessed. It is not a general G-code parser or simulator.
The source programs and output files are not overwritten.

## What has been tested

The supplied matched example set was `1001.nc` (loading), `3001.nc`
(unloading), and `2001.nc` (CAM-posted production reference for the same
part). These names may be reused for other jobs; do not assume files with
these names are the same examples. The production files are local only and
are not in this public repository.

- The reference test compared 24 tool/offset machining sequences: T1, T2,
  and T4 across all eight offsets. The sequences matched after normalization
  and removal of boundary retract/spindle commands for comparison.
- Separate tests check that the combined output preserves source sections
  except for the intentionally removed duplicate tool-change lines.
- The standalone EXE was launched on the development Windows machine, driven
  through the GUI, and produced output byte-for-byte identical to the Python
  implementation for that sample pair. The source and Qt tests also passed.
- The user visually reviewed an earlier combined output and said it looked
  promising, but stated that considerable machine verification is still
  needed. No machine-side dry run, production cut, or test on a second PC
  has been reported.
- A comparison using two different parts has not been validated against a
  known-good combined CAM reference. The user originally supplied a pair
  from different parts, but the matched reference test used the later
  same-part example set.

These tests do **not** prove transitions, machine clearance, physical tooling,
modal interactions, or the generated program are safe. Follow the independent
verification, simulation, and cautious dry-run guidance in the README before
cutting.

## Work on another computer

The repository is
<https://github.com/tjd10684-bit/X7-Syntech-Combiner>. Clone or pull it on the
other development computer. `*.nc`, old templates, `.venv`, and build output
are intentionally ignored; arrange access to any sample programs separately.
Do not publish customer or production files without permission.

For source development, use Windows with Python 3.10 or later, run
`Setup Combiner.cmd`, and launch `Start Combiner.cmd`. For an EXE build,
install `requirements-build.txt` in the local environment and run
`Build EXE.cmd`. The script refuses to overwrite an existing EXE. The
standalone EXE from this session was built locally as
`dist\SyntecCombiner.exe`; it is not in Git or a GitHub release. Copy it
separately or build a new one. It is unsigned and has only been tested on the
development machine.

To run tests on Windows PowerShell:

```powershell
$env:SYNTEC_GUI_TESTS = '1'
$env:SYNTEC_SAMPLE_DIR = 'C:\path\to\matched\samples'
.\.venv\Scripts\python.exe -m unittest -v test_combiner test_qt_gui
```

Omit `SYNTEC_SAMPLE_DIR` if the private matched examples are unavailable; the
production-reference comparison will be skipped. Omit `SYNTEC_GUI_TESTS` to
skip GUI tests.

## Next steps

1. Obtain the user's results from testing the EXE on the other Windows PC.
2. Support the user's independent simulation and careful machine-side
   verification of the generated transitions and fixture/tool setup.
3. If the user supplies additional posts or real cross-part transition
   examples, add focused tests before expanding the supported format. Do not
   loosen parser checks or declare a file safe merely to accept more inputs.
