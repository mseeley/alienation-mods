# Alienation (CUSA04181) — project context

Reverse-engineering the PS5-dumped PS4 build of Housemarque's *Alienation* for two goals:

1. A **save editor** for weapons, cores, equipment and armor sets (done: `tools/save-editor-gui.py` / `tools/save-editor-cli.py`).
2. A **[ps-patch-system](https://github.com/illusionyy/ps-patch-system) patch** for framerate/resolution and other tweaks (`patches/xml_orbis/CUSA04181.xml`).

Start with the [root README](../README.md) (doc index), [docs/file-formats.md](../docs/file-formats.md) (address conventions) and [tools/README.md](../tools/README.md). Reuse what's documented there instead of re-deriving it.

## Rules

- **`dumps/` and `savegames/` are read-only.** `dumps/` is the reference copy of the user's purchased game (`chmod -R a-w`, so "Permission denied" there is expected, don't work around it). `savegames/` is *not* locked and the tools no longer guard either folder: the user wants this to be my responsibility, not the app's. Every output path (`-o`, test scripts, GUI tests) goes to the scratchpad or `edits/`; test against copies of saves. Never run relocated copies of the tools (e.g. from /tmp) with outputs pointing at these folders, and never use them as targets for negative tests.
- **GUI tests: always set `SAVE_EDITOR_SETTINGS=<scratchpad>/test-settings.ini`.** Otherwise QSettings('alienation', 'save-editor') writes the user's real prefs (`~/Library/Preferences/com.alienation.save-editor.plist`). `QSettings.setPath`/`setDefaultFormat` do not redirect it. Compare `defaults read com.alienation.save-editor` before/after if in doubt.
- **Save editor UX is for novices.** UI, YAML plans and help text use plain game-facing words (plates/suit/visor/accent, colour, glow, metallic, shine), never internals (x/y/z/w, smoothness, shader slot names). Internals live in `docs/` and code comments. Breaking plan-format changes are fine; keep a clear error with a rename hint for old keys. Help text that worked: say what the setting does in everyday terms, what you see at low vs high values, and what game-made items use. Scale words under numbers worked; arrows between paired numbers read as ranges, so avoid them.
- **Surface developer hooks.** During any RE work, look for and report debug menus, key combos, cheat flags, tweakables, entitlement "key files" and how they're gated (`is_master_release`, `is_debug_enabled`, key-file checks). See [docs/developer-hooks.md](../docs/developer-hooks.md).
- Only claim something works on hardware if the user confirmed it on console; otherwise say "untested".

## Layout

| Path | What |
|---|---|
| `dumps/` | Game dump, app0 + patch0. **Use patch0 files.** Read-only. |
| `savegames/` | Save exports. Read-only. `CUSA04181_sdimg_savedata` = user's own; decrypted CUSA00062 saves `Alienation Platinum Save/CUSA00062` and `alienation-eu-231382` (same format). |
| `edits/<name>/CUSA04181_sdimg_savedata/` | Save editor output. |
| `tools/` | User-run save editor at root; shared code `tools/lib/` (`gamedata.py` = ALL game-derived data (names, tables, limits; keep any new game data here, not in saveedit/GUI), `saveedit.py` checks/builders, `savedata.py` save format, `common.py` paths + stream/eboot helpers, `GAME_DIR` → dumps/); RE scripts `tools/research/` (stream_catalog, stream_extract, xref, disasm, `stated.py` Stated disassembler, `gcn_disasm.py` GFX7 shader disassembler, raw `savedata.py`). Venv: `tools/.venv`. |
| `tools/example-recipes/` | Commented YAML plans. `10_max_smg_boomerang.yaml` = console-confirmed maxed SMG. |
| `recipes/` | User's own recipes (e.g. `synthspeed-suit.yaml`, keep). Git-ignored: personal, not for the repo. The console test recipes and raw screenshots/saves were deleted; their results are recorded in docs/armor.md. |
| `patches/xml_orbis/CUSA04181.xml` | ps-patch-system patch (AppVer 01.07; patch addr = 0x400000 + vaddr). |
| `docs/` | All findings: file-formats, weapons-and-cores, armor, developer-hooks, cheat-codes, framerate, resolution, intro-videos, platform-windows, ark-missions, save-editor. |

## Key facts (details in docs/)

- Engine "Sasquatch". Gameplay = **Stated** state machines compiled to bytecode (STAD record; debug names in STDD). Render pipeline = plain-text Lua in SCRI records. Script constants live in `stream.dat`, so XML patches can't reach them directly — except via the loader-hook technique below.
- eboot (patch0): **vaddr = file_off − 0x4000**. Save thread 0x460710, load 0x45ff90, crc32 0x129b70, inflate 0x131190, deflate 0x131290, Stated loader 0x3dad40.
- `stream.dat`: 64-byte-aligned records, id = file_offset/0x40, zlib payloads; manifest at id 0. STAD 0x124af99, STDD 0x1255d46.
- `savedata.dat`: "AYE!" magic, crc32 over [8, 0x14+len), uncompressed tagged-value payload; keys = first LE u32 of MD5(name.upper()). Solved; `dump → apply` is byte-identical, selftest rebuilds 274/274 items.
- Save gotchas: weapon/armor level 30 = `upgrade_level` 29 (0-based). Installed core tuple level is 0-based 0–5 — **writing 6 crashed the game**. Inventory core names are 1-based (`core1_6`). `active_weapons = [nil, heavy, primary, secondary]`; only primary is class-bound. Caps: 10 weapons per slot type + 10 items; hero level cap 300.
- Script-constant patching from XML: hook the Stated loader at 0x3dae06 (r12 = writable STAD payload) → code cave rewrites bytes with a value guard. Used by "Fast weapon scrapping"; reusable. A dead-function scan found 2288 unreferenced functions usable as caves.

## Status

**Patch entries** (`patches/xml_orbis/CUSA04181.xml`):

| Entry | Status |
|---|---|
| Enable debug mode (`is_debug_enabled` 0x1156e0 → `b0 01 c3 90`) | Works on console. Debug UI needs a **USB keyboard** (F1 overlay, F2/F3 pages; key map in docs/developer-hooks.md). No controller combo exists. |
| 60 FPS | v1.0 works on console (feels slightly faster). v1.1 (extra 1/30 → 1/60 fixes for rotors/hologram/rain) untested; typewriter text and intro-video smoothness unexplained. |
| Resolution 720p | Untested. |
| Skip intro videos | Untested. |
| Fast weapon scrapping v1.1 | Untested. |
| 1440p/2160p/supersampling | **Removed at the user's request**: all booted but crashed once combat started (undiagnosed). Analysis kept in docs/resolution.md. Don't re-add without a diagnosed fix. |

**Not shipped:** forcing `is_platform_windows` true (breaks enemies/player/menus because dev-only tweakables are missing in retail; see docs/platform-windows.md).

**Save editor:** done. Armor colours/glow confirmed in the gear menu; custom perk effect values and >2 effects per colour set still untested. Which gun part each weapon tint area paints is unknown.

## Next directions (user wants these; offer when asked "what's next")

1. **Test never-seen perks:** 8 conditions / 10 effects exist in data but never drop. First console test: `staying_still` → `bonus_weapon_damage`. Expect little: the devs' own debug perk cyclers only offer the 3 conditions / 4 effects seen in saves.
2. **Resolution/framerate**, continued: 60 FPS v1.1 follow-ups; resolution only with a diagnosed combat crash.
3. **stream.dat script patching** (deferred by the user): repack `stream.dat` with edited Stated bytecode and load it via a GoldHEN file-redirect plugin. First target: drop the Windows-only check on the Bounties debug cheat (0x37de3c, see docs/cheat-codes.md). Worth it as a general mod capability more than for cheats.
