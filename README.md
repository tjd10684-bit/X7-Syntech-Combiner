# Offline Syntec program combiner

For project history, testing context, and development on another machine, see
[HANDOFF.md](./HANDOFF.md).

**Experimental:** do not run old O9000 through O9005 and O9999 templates
from an earlier approach. They are incomplete and do not represent the two
different operation paths in the production programs. They are excluded from
this repository.

The combiner makes a new, flat NC file from an Op 1 loading program and an
Op 2 unloading program. It runs locally on Windows and needs no network access.
It preserves the source tool sections and their original commands, grouping
matching tool numbers while preserving each source program's tool order.
The Op 1 section is placed before the Op 2 section for each shared tool.

## Before every use

This software is **not a G-code simulator or a machine safety verifier**. It
has only been checked against the supplied post examples; other programs may
be rejected and are not automatically safe if accepted. Even source programs
that ran safely by themselves can interact differently when combined.

An experienced operator must independently verify:

- The selected files and part revisions, fixture setup, work offsets, and
  stock or parts in all eight locations.
- That every shared tool number really is the same installed physical tool
  with suitable length and diameter offsets for both parts. The program
  compares tool descriptions but cannot check what is in the machine.
- Tool sequence, tool clearances, speeds, coolant, safe retracts, changes in
  modal state, and final machine-coordinate park position.
- The complete combined toolpath and the transitions between the two source
  sections using an appropriate simulator or backplot.
- A controlled, single-block dry run at safe settings, with no cutting and
  safe clearance, following the machine's established procedures.

Stop if any step is uncertain. Do not rely on this tool to detect collisions,
bad offsets, post errors, or all controller-specific modal behavior.

## Windows executable

The standalone `SyntecCombiner.exe` is built in `dist`. Copy that single file
to a compatible 64-bit Windows computer and double-click it; Python, Qt, and
VS Code are not required on that computer. It runs offline. Windows may warn
about an unsigned executable. Verify the file's origin before running it;
do not bypass security policies.

To build it from source on Windows with Python 3.10 or later:

1. Run `Setup Combiner.cmd`.
2. Run `.venv\Scripts\python.exe -m pip install -r requirements-build.txt`.
3. Run `Build EXE.cmd`. The result is `dist\SyntecCombiner.exe`.

The executable and build environment are not stored in Git. Building uses
PyInstaller and PySide6 Essentials; review their applicable licenses and
redistribution requirements before redistributing a build.

## Use from source

Requires Python 3.10 or later and PySide6 Essentials on the Windows computer preparing
programs. Double-click `Setup Combiner.cmd` once to create a project-local
environment and install dependencies (this setup needs internet access).
Then double-click `Start Combiner.cmd` to use the Qt interface. Setup is
already complete on the computer where this version was created.
On a different computer, copy the application files without the `.venv`
folder and run `Setup Combiner.cmd` there; virtual environments are not
portable between computers.

The application itself runs offline, and the mill remains air-gapped.
Alternatively, install `requirements.txt` in a Python environment and run
`python combiner.py`. The command-line mode does not require Qt.

## Preparing a combined program

1. Drag the loading file onto the Loading / Op 1 field, or select it with
   Browse. It must use G54, G55, G56, and G57.
2. Drag the unloading file onto the Unloading / Op 2 field, or select it
   with Browse. It must use G58, G59, G54 P7, and G54 P8.
3. Choose a **new** output filename and an unused, non-reserved O number.
   The O number must differ from the two input program numbers; also check
   for conflicts with programs already on the controller.
4. Confirm the shared physical tools and offsets match and create the file.
   The program refuses to overwrite an existing output or either input.
5. Complete all verification above before copying the file to USB.

Drop one existing file at a time onto the appropriate input field. The output
field still uses Browse or a typed path. If drag-and-drop is unavailable,
use Browse; the programs are validated in the same way either way. An invalid
drop clears that input field. Changing either input clears the tool
confirmation, so it must be checked again for the newly selected files.

Each source section retains its stop, length-comp cancellation, Z reference
return, spindle startup, coolant and modal setup. For a tool used in both
files, only the second `T... M06` line is removed. Thus there are additional
stop/restart and retract blocks between the two sections, compared with a
native combined CAM post. These transitions need particular attention.

## Supported input and limitations

This first version accepts the exact inch-mode startup and final park format
seen in the examples, the specified four offsets per source and tool, one
section per tool, matching T/H numbers and a restricted set of G/M commands.
It requires the post's tool-break comments and expected end-of-tool retract.
Each offset must use the observed XY rapid and G43 approach, and consecutive
offsets must have the observed G49/G28/G90 retract sequence.
Tool descriptions for shared tool numbers must match apart from `ZMIN`.
Contradictory tool orders, incompatible park positions, unsupported
commands, different units, and other unexpected structures are rejected.
It does not support macros, subprogram calls, canned cycles, arbitrary posts,
different fixture layouts, or incomplete loading/unloading sets.

There is no automatic tool renumbering, unit conversion, fixture mapping,
tool-geometry verification, or material/process dependency analysis. A
successful check is not an approval to machine. The tool does not modify
the input files.

## Command line

```text
python combiner.py --load 1001.nc --unload 3001.nc --output combined.nc --number 1234 --confirm-tools
```

`--confirm-tools` means the operator has verified shared physical tools and
offsets. Choose your own unused O number; `1234` is only an example.

## Testing

Run `.venv\Scripts\python.exe -m unittest -v test_combiner test_qt_gui`.
Set `SYNTEC_GUI_TESTS=1` to exercise the Qt interface. To also compare against the three
supplied examples, set `SYNTEC_SAMPLE_DIR` to the directory containing
`1001.nc`, `3001.nc`, and `2001.nc` before running the tests. The reference
comparison checks the ordered machining blocks for all 24 tool/offset pairs;
it does not establish machine safety or prove the added transitions match
the original production file.
