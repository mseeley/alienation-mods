# Alienation research scripts

Scripts for poking at the CUSA04181 dump. They aren't part of the save editor (that's one level up, in
`tools/`); they share its `tools/lib/` code. They default to `dumps/CUSA04181-patch0_ALIENATION/` (treat
`dumps/` as read-only); pass `--stream` / `--eboot` to point elsewhere (e.g. the app0 files).

```bash
python3 -m venv tools/.venv && tools/.venv/bin/pip install -r tools/requirements.txt
```

| Script | Purpose |
| --- | --- |
| `stream_catalog.py` | Walk `stream.dat` from its manifests; count record types, list or bulk-extract a type |
| `stream_extract.py` | Extract one record by id and list its pointer fixups |
| `xref.py` | Find code in `eboot.bin` that references a string |
| `disasm.py` | Disassemble `eboot.bin` with string annotations (needs capstone) |
| `gcn_disasm.py` | Disassemble PS4 GPU shader code from `SHDR` records (LLVM can't do this GPU generation) |
| `stated.py` | Disassemble Stated gameplay bytecode (state machines, states, native calls, strings) |
| `savedata.py` | Low-level `savedata.dat` inspector: decode, dump the value tree, set raw values, export/import JSON |

Shared code they import (`tools/lib/`): `common.py` (`stream.dat` records, eboot helpers, project paths) and
`savedata.py` (the save format library, also used by the save editor).

## Formats

**stream.dat** — records aligned to 0x40; record id = file offset / 0x40. Header layout is
documented in `tools/lib/common.py` (`Stream`). Useful records:

| Id | Type | Contents |
| --- | --- | --- |
| `0x17c` | SCRM | Manifest of 40 SCRI records (plain-text Lua render pipeline) |
| `0x124af99` | STAD | Compiled Stated gameplay program + string table / localization |
| `0x1255d46` | STDD | Stated debug info (state machine and state names) |

**savedata.dat**

```
+0x00  "AYE!"
+0x04  u32 crc32 (zlib) over bytes [0x08, 0x14 + len)
+0x08  u32 0x14       data offset
+0x0C  u32 len
+0x10  u16 0x0401     not checked on load
+0x14  Stated value stream (uncompressed): version byte 1, then one tagged value
```

Table keys are the first little-endian u32 of `MD5(name.upper())`. The full tag table is in
`docs/file-formats.md`.

### Disassembling gameplay scripts

```bash
python3 tools/research/stated.py list Debug            # find state machines
python3 tools/research/stated.py sm Debug.Debug_Keys   # disassemble every state
python3 tools/research/stated.py calls is_debug_enabled
python3 tools/research/stated.py strings cheat
```

### Inspecting saves at the value level

For normal edits (weapons, equipment, armor sets, resources) use the save editor in `tools/`. This is for
looking at, or poking, the raw value tree:

```bash
python3 tools/research/savedata.py info    SAVE
python3 tools/research/savedata.py weapons SAVE
python3 tools/research/savedata.py cores   SAVE
python3 tools/research/savedata.py set     SAVE -o out/savedata.dat core4_3=50 metal4=999
python3 tools/research/savedata.py export  SAVE -o save.json     # edit, then:
python3 tools/research/savedata.py import  save.json --base SAVE -o out/savedata.dat
```

It refuses to overwrite the save it reads from. The first `tree`/`export` builds a key-name cache from the
game data in `tools/.cache/` (takes a few seconds).

## eboot addresses (patch0, vaddr = file offset - 0x4000)

| Address | Function |
| --- | --- |
| `0x45ff90` / `0x460710` | savedata load / save threads |
| `0x3b5f60` | header + CRC validation on load |
| `0x129b70` | crc32 |
| `0x131290` / `0x131190` | deflate / inflate wrappers |
| `0x283060`, `0x282f80` | Stated value deserialize (version byte check) |
| `0x3dafb0` | Stated value stream writer |
| `0x3b5b20` | `persistence_set_data` |
