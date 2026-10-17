# Developer hooks

Debug and cheat features found in the retail build, and how they are gated. Addresses are for the patch0 `eboot.bin` (`file_offset = vaddr + 0x4000`). Nothing here has been tested on hardware yet unless stated.

## Entitlement "key files"

The script docs talk about "key files", but these are actually **PSN add-on entitlement labels**. A DRM thread (`0x1158a0`) queries each label at boot and stores a one-byte flag in the DRM object (global pointer `0x27c7020`, vtable `0x1eeb700`). A label counts as owned when the add-on status is 0 or 4.

| Label | Flag byte | Meaning |
|---|---|---|
| `ANDEBUGXXXXXXXXX` | 0x1a | Debug mode (`is_debug_enabled`) |
| `ANSTAGEXXXXXXXXX` | 0x1b | Stage mode (`is_stage_enabled`) |
| `ANWEAPONHACK0001` | 0x21 | Loot and equip all three classes' primary weapons |
| `ANVORTEXGRENADE1` | 0x22 | Vortex grenade |
| `ANSPHEREGUN00001` | 0x28 | Collapser (`sphere_gun`) |
| `ANLASERGUN000001` | 0x29 | Devastator (`laser_gun`) |
| `ANALLWEAPONS0001` | 0x2d | Bundle; ORed into the weapon checks above |
| `ANBULLETCOLOR001` / `002` / `003` | 0x1d / 0x1e / 0x1f | Bullet colours |
| `ANBULLETCOLORPKG` | 0x20 | Bullet colour pack |
| `ANSUITPAINT00001` / `002` / `003` | 0x25 / 0x26 / 0x27 | Suit paints |
| `ANSUITPAINTPKG01` | 0x2e | Suit paint pack |
| `ANSTARTLEVEL0015` | 0x23 | Start at level 15 |
| `ANLEVEL15HEALER1` / `TANK001` / `NINJA01` | 0x2a / 0x2b / 0x2c | Per-class level 15 |
| `ANCOMMSMSGPACK01` | 0x24 | Comms message pack |

Flag `0x19` is set from a different system call before the label checks. It's not identified yet (possibly the SKU/trial flag).

### Getter functions

| Script function | Address | Bytes | Logic |
|---|---|---|---|
| `is_master_release` | `0xe85d0` | — | Hard-coded `true` |
| `is_debug_enabled` | `0x1156e0` (file `0x1196e0`) | `8a 47 1a c3` | `return flag[0x1a]` |
| `is_stage_enabled` | `0x1156f0` (file `0x1196f0`) | `8a 47 1b c3` | `return flag[0x1b]` |
| `is_weapon_hack_enabled` | `0x115750` (file `0x119750`) | `80 7f 21 00 b0 01 74 01 c3 …` | `flag[0x21] \|\| flag[0x2d]` |

### Patch: force debug mode (verified statically, untested on console)

```
0x1156e0: 8a 47 1a c3  ->  b0 01 c3 90   ; mov al, 1 ; ret ; nop
```

Patch address `0x5156e0` (0x400000 + vaddr) for APP_VER 01.07. The original bytes are unique in the eboot and differ in 1.00. Packaged for ps-patch-system as [`patches/xml_orbis/CUSA04181.xml`](../patches/xml_orbis/CUSA04181.xml).

Verified call paths, all through the DRM vtable (`0x1eeb700`), so the one patch covers them:
- Script `is_debug_enabled` (`0xe85f0`) calls vtable `+0x28` = `0x1156e0`.
- Native main loop (`0x1169a0`): at `0x116ab0` it checks vtable `+0x18` (flag `0x18`, set once the DRM object is initialised, so normally true) and `+0x28`. When both are true it creates a USB keyboard reader and keys `0x60`/`0x61` call `0x111870(-1/+1)`, which **cycles the game language** through an 18-entry table (`0x177220` applies it). At `0x116e81` it gates another debug-only block.

The same `b0 01 c3` approach works for the other getters. Stage mode (`0x1156f0`) is left out on purpose: `ANSTAGEXXXXXXXXX` may point the game at staging servers.

## Debug keyboard controls (decoded from `Debug.Debug_Keys`)

`Game_Startup` (`spawn_first_stage_systems`, bytecode `0x1a5f9e`) spawns `Debug.Debug_Keys` **only when `is_debug_enabled()` is true**. With the debug patch, it starts with every level. It reads a **USB keyboard** (`keyboard_new`). The eboot links `libSceIme`, the retail keyboard API, so a keyboard plugged into the console should work. Keys are ignored while the comments manager is in its `ACTIVE` (typing) state.

Decoded statically with `tools/research/stated.py`; untested on console. Modifiers come from stack analysis: `Handle Keys` pushes Shift, Ctrl, Alt and branches on them.

**No modifier**

| Key | Action (`debug_events` field) |
|---|---|
| Q | God mode toggle (`player_toggle_god_mode`) |
| W | Demigod mode toggle |
| E | Alien debug monitor toggle |
| R | Aliens can't see you (toggle `aliens_toggle_sight`) |
| F | Aliens can't hear you (toggle `aliens_toggle_hearing`) |
| Y | Wallhack toggle |
| O | Teleport player (`player_teleport`) |
| K | Kill all enemies |
| T | Kill your own character (`player_should_die`) |
| S | Mute / unmute sound and music |
| Tab | Toggle AI player (bot takes over) |
| + | Collect grenade |
| G | Weapon flashlight toggle |
| 0 | Weapon supercharge |
| D (hold / release) | Shooting debugger start / shoot |
| I / U (hold) | Kill spot lights / point lights |
| 5 / 6 | Cycle decal / spawn decal |
| 7 / 8 | Spawn particle `AnExplosion` / `Steam1` |
| Numpad + | Collect credits |
| Numpad − | Cycle player colour |
| Numpad 7 / 4 | Camera FOV up / down |
| Numpad 8 / 5 | Camera distance down / up |
| Numpad 9 / 6 | Camera angle up / down |
| Numpad 0 | Free debug camera on/off (sets tweakable `cameras__primary_camera__force_debug_camera`) |
| Insert (debug camera on) | Teleport the player to the debug camera |

Spawn keys: hold to start, release to spawn (`player_start_spawning_object` → `player_spawn_object`). Z Popcorn (xenohuman), X Brute, C Soldier Shooter, V Scout, B Arch-Vile, N Blob, M Brute 2, comma Creeper, L Popcorn (xenoproto), P point light, H Pewpew 2.

**Shift held**

| Key | Action |
|---|---|
| Shift+Q | Debug cubemap |
| Shift+T | Checkpoint now |
| Shift+A | Get aggro |
| Shift+Tab | Reset playtime |

Shift spawn table: Z Popcorn, X Popcorn (bomb), C Brute (homing), L Popcorn (leaperproto), V Mini-360 (beam), B Behavior Tester, N Blob Ball, M Blob Big, R Random Spawner, E Mist effect.

**Ctrl held**

| Key | Action |
|---|---|
| Ctrl+T | Restart the level at your position (`restart_level_here`) |
| Ctrl+Q | Redraw cubemap |
| Ctrl+R | Print the `movie_recording_mode` tweakable |
| Ctrl+Numpad 0–9 | Send `control0`–`control9` activation messages to SMs registered via `debug_register_id` |

**Native (game code):** F7 / F8 cycle the game language (`0x116ab0` → `0x111870`).

### On-screen debug overlay (F1 / F2 / F3)

The engine has a **debug overlay** made of pages ("subsystems") owned by the subsystem manager (global `0x27c9808`, vtable `0x1ef4528`). Decoded statically; untested on console.

**How it's enabled.** At startup the main-loop state handler `0x116de0` checks `is_debug_enabled()` (`0x116e81`). If true, it allocates a debug buffer (manager `+0x10`) and sets the manager's debug flag (manager `+0x20(1)` → `[mgr+8] = 1`). The manager's per-frame update (`0x2d66d0`) only handles keys while that flag is set. It reads a **USB keyboard** (`[mgr+0x18]`, created through the input factory like the F7/F8 keyboard).

**Keys** (only when no Alt/Shift/Ctrl is held):

| Overlay state | Key | Effect |
|---|---|---|
| Hidden | **F1** | Show the overlay on the current page |
| Hidden | **F2** | Show the overlay and jump to the **GUI** page (id 0xF, the debug button menu) |
| Shown | F1 | Hide the overlay |
| Shown | F2 / F3 | Previous / next page |

When the overlay is hidden or debug is off, the current page is disabled every frame. That's why the GUI page "starts disabled".

**Pages** (subsystem vtables found by their shared base methods `0x2d97b0`/`0x2d97c0`; `id` from vtable `+0x30`, name from `+0x38`):

| Page | id |
|---|---|
| GUI | 0xF |
| NGParticles | 0xD |
| Debug log | 2 |
| Scripting | 1 |
| Statistics | 1 |
| Tweakables | −2 |
| Safe area | −1 |
| Artist Adjustments, Controller stats, GFX Mem Alloc, Performance, Render Stats | (computed) |

**GUI page (the debug menu).** `Debug.Debug_Keys` fills it via `debug_gui_button` with categories **Loot** (weapon rarity / perk condition / perk effect override cyclers, spawn weapon pickup, UFO key, Dreadnought key, loot box, xenoflower, colour pack, core), **Player** (ChangeClass, ShowStats, SpawnVehicle, SwapWeaponModel, FallDownTest, …), **Hazards** (spawn turrets, mortar flowers, shield generators, acid pool, exploding car, …), **Badges** (mission end zones, score/kills/damage/complete) and **Activate** (kill_all_players, toggle_thirdperson, registered debug ids). The GUI subsystem (constructor `0x2dd200`, global `0x27fe9a8`, update `0x2dd550`) navigates with **Up/Down** (row), **Left/Right** (column) and **Space** (press). Per-button hotkeys would work even while hidden, but none are assigned.

The perk-override cyclers only offer `on_enemy_hit`, `on_enemy_hit_melee`, `on_player_hit` and `chain_lightning_target`, `knockdown_target`, `boomerang_at_target`, `cluster_shell_from_target`: the same 7 seen in saves. The other conditions/effects are probably cut.

### Engine key codes

From the key-name table built at `0x4271a0` (code = index): 0–9 → `0`–`9`, 10–35 → `a`–`z`, 36 shift, 37 l_shift, 38 r_shift, 39 control, 40 l_control, 41 r_control, 42 alt, 43 l_alt, 44 r_alt, 45 capslock, 46 numlock, 47 scroll, 48 enter, 49 space, 50 tab, 51 backspace, 52 insert, 53 home, 54 delete, 55 end, 56 up, 57 down, 58 left, 59 right, 60 pgup, 61 pgdown, 62–71 numpad_0–9, 72 numpad_plus, 73 numpad_minus, 74 numpad_multiply, 75 numpad_divide, 76 numpad_enter, 77 numpad_decimal, 78 escape, 79 pause, 80 break, 81 print, 82 asterisk, 83 slash, 84 minus, 85 plus, 86 point, 87 comma, 88 colon, 89 semicolon, 90–101 f1–f12.

## Other debug and cheat state machines

| State machine | States / notes |
|---|---|
| `AN:Menu:Screens:Campaign_Select:Armor:cheat_code` | Cheat code entry on the armor/class select screen |
| `AN:Menu:Screens:Gear:cheat0rz_plaz0rz` | Sub-states `cheat` and `0wn3d` |
| `AN:Menu:Screens:Upgrade_Armor:New:cheat` | Cheat in armor upgrade screen |
| `AN:Player:Player_Character:Debug_Stuff` | `Cheats`, `cheat_badges`; consumes the `debug_events` flags above |
| `AN:Menu:Manager:Init:test_mode` | Automated soak test mode |

The `[CHEAT ACTIVE]%s%s` string is shown in the talents menu when a cheat is active.

### Menu-data cheat messages

Handled by the menu data / inventory code, so likely useful for the save editor as well:

- `resource_cheat` (logs "resource_cheat, adding:")
- `blueprint_cheat`, `partial_unlock_cheat`
- `colorset_cheat`, `bulletcolor_cheat`, `suitpaint_cheat`
- `cheat_mission`, `cheat_complete_mission`, `cheat_rewards`, `cheat_new_bounties`
- `add_item`

## Native tweakables and overlays

- A tweakables UI (`[F5] Save all modified tweakables`, `[DEL] Reset tweakable to default`). Scripts can read and write tweakables by `Folder__name`.
- Profiler overlays toggled with function keys: CPU stats (F7), heap stats (F6), Stated stats (F8), memory context (F5), graph modes and CSV dump.
- Scripts can create a keyboard reader (`keyboard_new`, `keyboard_is_down`, keys including `f1`–`f12`). PS4 accepts USB keyboards, so these may be reachable once debug mode is enabled.
- A debug GUI page API: `debug_gui_add_category`, `debug_gui_button`.

Interesting gameplay tweakables:

- `an__gameplay__perks__rarity_override`, `an__gameplay__perks__condition_override`, `an__gameplay__perks__effect_override`
- `an__gameplay__player_weapon_damage_multiplier`, `an__gameplay__player_fire_rate_multiplier`
- `an__gameplay__player_level_override`
- `an__gameplay__modifiers__*` (enemy speed, damage, no rush, no melee, …)

## Stated bytecode

Disassembler: `tools/research/stated.py` (`list`, `sm NAME`, `at OFFSET`, `calls FN`, `strings TEXT`). Format details are in its docstring:

- 71 opcodes (`Reserve` … `RefPut`); names from the eboot's pointer table at `0x1effd50`, operand sizes from the codegen walker's jump table at `0x17b6f30`. Stack machine: `Get n` copies the nth value from the top, `PushBlock L; Jmp F` is a call with continuation `L`, `Adjust 0xKKRR` keeps KK values and removes RR beneath them.
- `PushString` u16 = string id; `Store*`/`Self*` u32 = MD5 key hash (resolved through the string table's hash column); `CallExt` s16 = native function index (`STAD+0x0C` table: name string id, arg count, return count); jumps are u32 offsets from the bytecode start.
- 695 state machines, 10,644 code entries; 96% of states are named from STDD.

## Open questions

- What each overlay page shows and how its own controls work (e.g. editing Tweakables).
- The cheat-code sequences in `Campaign_Select:Armor:cheat_code` and `Gear:cheat0rz_plaz0rz` (now disassemblable with `tools/research/stated.py`). Controller buttons are mapped by name (`controller_map_button(name, "x360_l3")` etc.); the `ps3_*`/`x360_*` code strings are in the `STAD` string pool near `AN.Menu.Input`.
- What the debug-only block at `0x116e81` does.
