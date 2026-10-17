# Alienation tools

The savegame editor: add, replace and remove weapons, equipment and armor sets, and set resources, on a PS4
ALIENATION savegame. Full guide: [docs/save-editor.md](../docs/save-editor.md).

## Getting started

You need Python 3.10 or newer (`python3 --version`). Run everything from the project folder, not from `tools/`.

1. Create the Python environment in `tools/.venv` and install the dependencies into it:

   ```bash
   python3 -m venv tools/.venv
   tools/.venv/bin/pip install -r tools/requirements.txt
   ```

   This installs everything in [requirements.txt](requirements.txt) in one go: PyYAML (both editors), ruamel.yaml and
   PySide6 (desktop editor) and capstone (`research/disasm.py` only). Nothing is installed system-wide.

2. Check it works:

   ```bash
   tools/.venv/bin/python tools/save-editor-cli.py --help
   ```

3. Open the desktop editor:

   ```bash
   tools/.venv/bin/python tools/save-editor-gui.py
   ```

   Optional, macOS: build `Alienation Savegame Editor.app` so it opens with a double-click (rerun after moving the
   project folder, and once on each new machine):

   ```bash
   tools/.venv/bin/python tools/make-save-editor-app.py
   ```

On a new machine, repeat step 1 rather than copying `tools/.venv` across: a venv only works where it was created.
Upgrading Python? Delete `tools/.venv` and repeat step 1.

The save editor needs only a savegame folder (`CUSA04181_sdimg_savedata`). The `research/` scripts also need the game
dump at `dumps/CUSA04181-patch0_ALIENATION/` (`eboot.bin`, `stream.dat`), and cache what they build in `tools/.cache/`.

## What's here

| What you run | Purpose |
| --- | --- |
| `save-editor-gui.py` | The desktop editor (needs PySide6 and ruamel.yaml) |
| `make-save-editor-app.py` | Builds `Alienation Savegame Editor.app` (macOS) so the desktop editor opens with a double-click |
| `save-editor-cli.py` | The same editor on the command line, driven by YAML recipes (needs PyYAML) |
| `example-recipes/` | Ready-to-use recipes, each commented ([example-recipes/README.md](example-recipes/README.md)) |

Everything else here is support:

| Folder | Contents |
| --- | --- |
| `lib/` | Shared code, not run directly: `gamedata.py` (all game-derived data: item names, number tables, limits), `saveedit.py` (the editor's checks and item builders), `savedata.py` (save format), `common.py` (game data access, project paths) |
| `research/` | Reverse-engineering scripts for the game files (disassemblers, `stream.dat` tools, a raw save inspector). See [research/README.md](research/README.md) |
| `.venv/`, `.cache/` | The Python environment and the key-name cache built from the game data |

## Command line

```bash
tools/.venv/bin/python tools/save-editor-cli.py show SAVE
tools/.venv/bin/python tools/save-editor-cli.py apply SAVE tools/example-recipes/10_max_smg_boomerang.yaml --slot 0 -o edits/NAME/CUSA04181_sdimg_savedata
```

`save-editor-cli.py` and `save-editor-gui.py` refuse to overwrite the save they read from.
