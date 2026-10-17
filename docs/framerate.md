# Frame rate

Static analysis of the patch0 eboot (APP_VER 01.07) and the Stated scripts. Patch: "60 FPS" in [`patches/xml_orbis/CUSA04181.xml`](../patches/xml_orbis/CUSA04181.xml). **Console test (2026-10-10, patch 1.0): works; play feels slightly faster, no blockers. 1.1 also fixes the remaining hard-coded 1/30 steps (below).**

## Current behaviour

| Where | Target | Set by |
|---|---|---|
| Boot | 59.94 | native, `0x1162ef` (constant at `0x176cfc0`) |
| Splash / boot menu, menus, loading screens | 59.94, max frame skip 0 | scripts at bytecode `0x3c730a`, `0x2730f8`, `0x267047` |
| **Gameplay** | **29.97, max frame skip 0** | game startup script at bytecode `0xce0d`, plus the menu-to-game transition at `0x25ffd3` |

So the game renders at **30 fps in levels** and 60 fps in menus.

## How the timing works

- `engine_set_fps(fps)` (native `0x378080`) calls the engine timing object (global `0x27c9800`, method `+0x18` = `0x154980`). That stores `fps` at `+8`, the logic step `1/fps` at `+0xc`, and calls `+0x28` (`0x1549b0`).
- `+0x28` notifies the display (global `0x27b7ee0`, vtable `+0x40` = `0x3014d0`). The display computes `interval = clamp(round(1 / (fps × refresh_period)) − 1, 0, 2)` and calls **`sceVideoOutSetFlipRate`** (0 = 60 Hz, 1 = 30 Hz, 2 = 20 Hz). The TV refresh period is `1/59.94` (`0x2fff37`); in VR mode it's 1/119.88 or 1/89.91.
- The main loop (`Game_Runner`, `0x154680`) advances game logic in steps of `1/fps` (`0x154110`). With max frame skip 0 there's one step per displayed frame, so game speed equals displayed fps ÷ target fps: when the console can't keep up, the game slows down.
- Render-side time (effects, particles, shader timers; `0x27b6170` → `0x211050`) advances by a **fixed 1/30 s per frame** when the tweakable `sasquatch__fixed_render_frame_rate` is on (default on; registered at `0x154ddb`, constant `0x1773f58`, read only at `0x15474b`). Otherwise it uses the measured frame time.

## Would 60 fps make the game run faster?

**Game logic: no.** The logic step is derived from the target fps, so 60 steps of 1/59.94 s cover the same game time as 30 steps of 1/29.97 s. The menus already run this way at 60.

**Render-side effects: yes, unless fixed.** The fixed render step stays 1/30 per frame, so anything driven by it would run at double speed at 60 fps. The patch changes that constant to 1/60.

**Below 60:** because max frame skip is 0, any frame the console can't deliver in time slows the game proportionally (the same behaviour the 30 fps game has below 30).

## The patch

| Address (patch / vaddr) | Original | New | Purpose |
|---|---|---|---|
| `0x7780a1` / `0x3780a1` | `75 06` | `90 90` | Drop the int/float argument branch in `engine_set_fps` |
| `0x7780a3` / `0x3780a3` | `c5 f9 6e c0 eb 13 48 ba 00 00` | `c5 fa 10 05 15 4f 3f 01 eb 0f` | `vmovss xmm0, [0x176cfc0]` (59.94), `jmp 0x3780bc` (the setter) |
| `0x1b73f58` / `0x1773f58` | `89 88 08 3d` (1/30) | `89 88 88 3c` (1/60) | Fixed render time step |

Every script call (all pass floats) now sets 59.94, so menus are unchanged and gameplay targets 60 Hz.

## Other hard-coded 1/30 steps (patch 1.1)

Console testing of 1.0 (2026-10-11) reported helicopter rotors that looked too fast, a typewriter text effect running about twice as fast, and less smooth intro videos. A byte-level scan for every code reference to a 1/30 float found these. Each constant is read by exactly one instruction.

| Constant | Reader | What it is | Patch 1.1 |
|---|---|---|---|
| `0x1773f58` | `0x15474b` | Game_Runner fixed render time step | 1/60 (already in 1.0) |
| `0x176d5c0` (vec4) | `0x119111` | Hologram shader phases (`shader__hologram__phase_speed_x/y/z`, `noise_speed`) += speed × 1/30 per frame | 1/60 |
| `0x17306d8` | `0xeb9e` | Render animation phase += (1/30) / period per frame | 1/60 |
| `0x1731558` | `0x1700a` | Weather/rain render node: per-frame count = rate × 1/30 | 1/60 |
| `0x17b2248` | `0x3fc59a` | Stated network sync timer `+= 1/30` per frame (compared against send/timeout thresholds) | 1/60 |
| `0x46fb65` (reads `0x17b7b50`) | | Fixed 30 Hz tick: `timer -= dt`, reload `+= 1/30` | Unchanged; already frame-rate independent |
| `0x173150c` | `0x15dc4` | Debug performance overlay: frame ms ÷ 30 for a bar | Unchanged; display scale |
| `0x173157c` | `0x17a45` | Rain wetness shader constants (setting × 1/30) | Unchanged; unit conversion, not a per-frame step |
| `0x1c5103c` | `0x10506a8` | Havok Behavior: fallback time step when given 0 | Unchanged |

Because the patch forces 59.94 in every state (boot, menus, gameplay and the ending cutscene), the true per-frame step is always 1/60, so constant replacement is exact.

What the 1.0 reports turned out to be:

- **Helicopter rotors:** the scripts are time-based (`AN.Objects.Miscellanea.Mission_End_Helicopter`, `Super_Mission_End_Zone`: `phase += delta_t × speed`). `main_rotor_speed` = 4.3 rev/s (258 RPM, a real Black Hawk's rate) and `tail_rotor_speed` = 19.83 rev/s (props at `0x587891`, `0x58de10`). At 30 fps the four-blade main rotor advances 0.14 rev per frame, close to the half-blade (0.125 rev) point, so it strobes and looks slower than it is. At 60 fps (0.07 rev per frame) the real speed is visible. Not a timing bug; slowing it would mean changing those script constants.
- **Typewriter text:** the native `Progress_Text_Effect` (`0x321550`: `progress += dt × speed`) is time-based in itself. No script-driven per-frame reveal was found. Not yet located; the hologram shader (now fixed) is a candidate if the text is holographic.
- **Intro videos:** `AV_Player_Orbis` decodes on the AvPlayer clock and reads no engine time, and the boot, intro, title and story videos play in states that were already 59.94 before the patch. No mechanism found.

## Script audit: frame-rate dependence

All 1,927,908 Stated instructions were scanned. A linear decode of the whole 6 MB bytecode stays in sync, so the scan covers code the state walker misses. Timing is overwhelmingly time-based: `delta_t` is called 1,747 times and `time_in_state` 1,218 times, and no frame-counter native exists. Four frame-dependent patterns were searched for:

| Pattern | Sites | Verdict |
|---|---|---|
| `x = x ± const` with no `delta_t` | 956 | Almost all are per-event counters (hits, shots, waves, kills, menu indices). No frame-counted gameplay timer found |
| `rand()` compared each update | 289 | Mostly one-off or per-event. Per-update ones are listed below |
| Constant-factor `lerp` (smoothing) | 579 | Converges about twice as fast at 60 fps. Gameplay-relevant ones are listed below |
| `x = x × c` decay | 13 | Per-hit damage handling (`health × 0.97`/`0.501` in damage-message loops), plus cosmetic pickup drift |

What changes at 60 fps (none of it can be fixed with an eboot XML patch, because scripts live in `stream.dat`):

- **Player aim:** `aim_dir` turns 20% toward the stick each update (`Player_Character` `Aim_and_shoot`, `0x1dcac3`), so aiming feels **snappier**.
- **Enemy turning and look direction:** constant-factor smoothing (e.g. Creeper `angular_dir_3d_lerp 0.4`, `0x357c41`) makes enemies turn toward targets faster.
- **Enemy aggro memory:** `damage_interest` decays 2% per update (`0x27b869` and the equivalent in each enemy type), so enemies may switch targets sooner.
- **Horde spawning:** `Massive_Horde_Spawner` spawns at most 40 spawners per frame (`0x33b7be`), so big waves finish appearing faster. Wave size is the same.
- **Leash/despawn check:** each alien's 10%-per-update chance to check distance (`Generic_Update:Update`, e.g. Brute `0x28441a`) runs twice as often. Far-away aliens get recycled after about 0.17 s instead of 0.33 s. Not noticeable.
- **Idle patrol "ponder"** (`rand() < ponder_chance`) happens more often. Cosmetic.
- **Cosmetic:** light flicker, `Area_Damage` and flamethrower particle randomness, falling mine acceleration (`Shell_Mine`, `0x306ac1`), pickup drift and merging (`Alien_Resource`), aim/visual smoothing, and stuck detection averaging.
- **`Player_AI`** (the bot that drives your character in debug/soak tests) has per-update random behaviour. Not used in normal play.

The search is heuristic: it covers the common idioms, not every possible frame dependence. Watch enemy aggression and turning in playtests.

## Not yet done

- A frame-skip option (`engine_set_max_frame_skip`), which would keep game speed correct when the console drops below 60, at the cost of judder.
