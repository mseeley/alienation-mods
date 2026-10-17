# Cheat codes

Hidden cheat inputs in the menu and player scripts. Each entry gives the exact input, the gate, what it does, and the bytecode offsets it was read from. Offsets are bytecode offsets in the `STAD` record (`python3 tools/research/stated.py at OFFSET`). Everything here was decoded statically. **None of it has been tested on console yet.**

The short version: **only one code works on a retail game without the debug patch**, and it is cosmetic. Every code that grants resources, items or unlocks is gated by `is_debug_enabled()`, which returns false unless you own the `ANDEBUGXXXXXXXXX` entitlement or apply the patch in [developer-hooks.md](developer-hooks.md#patch-force-debug-mode-verified-statically-untested-on-console). Most of them are gated twice: once by the screen that sends the cheat message, and again by `AN.Menu.Data` when it receives it.

## Input names

Menu screens read buttons through `AN.Menu.Input`, which every screen gets from `AN.Menu.Manager` (`0x25b14e`). Its `update` state (`0x5d3fd`) fills these fields every frame:

| Field | Meaning |
|---|---|
| `pad_up` / `pad_down` / `pad_left` / `pad_right` | D-pad **pressed this frame** (`controller_was_pressed`). The sticks are separate fields (`lx`, `ly`, …) and do not count |
| `triangle`, `square`, `cross`, `circle`, `l2`, `l3`, `select`, … | Pressed this frame |
| `square_down`, `cross_down`, … | Held |

The DualShock 4 has no Select button. `select` is probably the touchpad click (**unverified**).

## Summary

| Cheat | Where | Input | Gate | Effect |
|---|---|---|---|---|
| Konami suit colours | Class select (new game) | ↑ ↑ ↓ ↓ ← → ← → on the D-pad | **None** | Pink/orange colour scheme on the class preview model |
| Free skill points | Class skills screen | L3 (toggle) | Debug | +100 skill points to spend |
| Resource +100 | Resources screen | Triangle | Debug | +100 of the highlighted resource |
| Unlock missions | Missions world map | Hold Square for over 1 s (toggle) | Debug | Every mission's prerequisites count as met |
| Partial mission unlock | Missions world map | Tap Square (toggle) | Debug | Missions flagged `partial_unlock_cheat` count as unlocked |
| Mission rewards | Missions world map or mission list | L2 | Debug | Grants the focused mission's reward list |
| Complete mission | Mission list | Select | Debug | Marks the focused story mission completed |
| New bounties | Bounties screen | Triangle | Debug **and Windows only** | Rerolls the bounty board. Can't fire on PS4 |
| Gear screen keys | Gear screen | USB keyboard `0` `1` `2` `3` `b` `a` `c` `p` | Debug | Credits, cores, bullet colours, blueprints, colour set, suit paints. **Probably dead code** (see below) |
| Badges | Debug menu (F-key overlay GUI) | `Badges` buttons | Debug | Sets end-of-mission badge flags |

## Class select: Konami code (no gate)

`AN:Menu:Screens:Campaign_Select:Armor:cheat_code` at `0x30ac5c`. This state has no debug, master-release or entitlement check. It runs on the class (armor) selection screen, which you reach from New Game and when joining co-op.

**Input:** D-pad **Up, Up, Down, Down, Left, Right, Left, Right**. Other buttons are ignored. A wrong D-pad direction resets the sequence to step 0.

| Step (`cheat_code_index`) | Expected | Branch offset |
|---|---|---|
| 0 | Up | `0x30ad2b` |
| 1 | Up | `0x30ad97` |
| 2 | Down | `0x30ae03` |
| 3 | Down | `0x30ae6f` |
| 4 | Left | `0x30aedb` |
| 5 | Right | `0x30af47` |
| 6 | Left | `0x30afb3` |
| 7 | Right → fire | `0x30b186` → `0x30afc9` |

**Effect** (`0x30afc9`): builds an 8-entry `color_override` and applies it to the preview character with `scene_set_mesh_rendering_opts`:

| Mask | RGBA |
|---|---|
| `user_colormask_non` | 1.0, 0.1, 0.3, 0 (hot pink) |
| `user_colormask_pri` | 0.2, 0.0, 0.1, 0 (dark maroon) |
| `user_colormask_sec` | 0.7, 0.1, 0.4, 0 (pink) |
| `user_colormask_tri` | 1.0, 0.5, 0.0, 0 (orange) |
| `*_mat` (non/pri/sec/tri) | (0,1,0.6,0.2), (0,1,0.6,0.4), (0,1,0.3,0.2), (0,1,1,0) |

`Armor:focus` keeps using the override when you switch class (`0x30c160` → `0x30c57d`). It's cleared by cycling colours with Square (`Armor:color`, `0x30a790`) or by backing out (`0x30a70f`).

It looks **preview-only**. `Armor:select` (`0x30ec0f`) saves only `color_offset`, the normal Square colour choice, and `start_level` never reads `color_override`. So the in-game suit probably stays the normal colour (**unverified**).

## Class skills screen: +100 skill points (debug)

`AN:Menu:Screens:Upgrade_Armor:New:cheat` at `0x2a554a`. `Upgrade_Armor` is the class skill/talent screen (its guide box is `Menu_Talents`).

- **Gate:** `is_debug_enabled()` at `0x2a554c`. Without it the state just exits.
- **Input:** **L3** toggles it (`input.l3`, `0x2a5584`).
- **Effect:** sets `cheat_points = 100`, or removes it if already set. The available-points calculation (`0x29eeed`) starts from `cheat_points` instead of 0 (`0x29f21b`), so you get 100 extra points. The guide text gets a `[CHEAT ACTIVE]` prefix (`0x2a02a3`).
- Upgrades bought with these points go through the normal `upgrade_item` message, so they are probably saved. After you toggle the cheat off, the points total is clamped with `max(…, 0)` (**unverified**).

## Resources screen: +100 resource (debug)

`AN:Menu:Screens:Resources:Active:debug` at `0x469d22`.

- **Gate:** `is_debug_enabled()` at `0x469d24` (sender) and again in `AN.Menu.Data` (`0x173491`, receiver).
- **Input:** **Triangle** (`0x469dcf`) with the cursor on a resource.
- **Effect:** sends `resource_cheat` with `cheat = [{name: rows[y][x].resource_name, count: 100}]`. Because it uses the real resource name, it works for credits, every `core<type>_<level>`, metals, flowers and keys.

## Missions screen (debug)

### World map: `AN:Menu:Screens:Missions:World_Map:debug` at `0x5796d4`

Gate: `is_debug_enabled()` (`0x5796e2`). It's also skipped while a confirm dialog is open.

| Input | Branch | Message | Effect |
|---|---|---|---|
| **Hold Square** for over 1 s | `0x57982a` → `0x579722` | `cheat_mission` | Toggles `cheat_mission_unlock` on `AN.Menu.Data`. While it's set, the prerequisite check (`0x131f02`) returns true for every mission (`0x131f34`), so all story, global and special missions show as available |
| **Tap Square** (release before 1 s) | `0x579782` → `0x579793` | `cheat_mission {partial: true}` | Toggles `cheat_mission_unlock_partial`. Only missions whose definition has `partial_unlock_cheat` count as unlocked (`0x1323d6`) |
| **L2** with a mission focused | `0x579803` → `0x5797c7` | `cheat_rewards {target}` | See below |

Receiver: `0x16e487` toggles the flags (`0x16e3e8`–`0x16e46f`), then recomputes `prerequisites_ok` for every mission (`0x16e0c0`). The two unlock flags are only fields on the running `AN.Menu.Data` machine, so they don't survive a restart. The recomputed `prerequisites_ok` values are written into `menu_data_story_missions` (**unverified** whether they persist).

### Mission list: `AN:Menu:Screens:Missions:Missions:debug` at `0x57717c`

Gate: `is_debug_enabled()` (`0x57718a`), and no confirm dialog open.

| Input | Branch | Message | Effect |
|---|---|---|---|
| **Select** (probably touchpad) with a mission focused | `0x577244` → `0x577200` | `cheat_complete_mission {target}` | Story missions only (`0x16e0a4` checks `type == 'story_mission'`). Sets `COMPLETED` on the mission (`0x16df75`) and recomputes prerequisites, so the next missions unlock |
| **L2** with a mission focused | `0x5771ea` → `0x5771a6` | `cheat_rewards {target}` | See below |

`cheat_rewards` (receiver `0x16e49a`, gated `0x173464`) finds the target in `menu_data_story_missions` and grants each entry of its `rewards` list via the normal reward function (`0x14b12a`). It doesn't complete the mission, so you can repeat it.

`Zoom_Out:update` (`0x576f00`) also shows up in a string search, but only because the disassembler falls through into the `Missions:debug` code after `accept_final`. It doesn't send cheats itself.

## Bounties screen (debug, Windows only)

`AN:Menu:Screens:Bounties:Active:debug` at `0x37de2e`. It rejects unless `platform() == 'windows'` (`0x37de3c`), so it **can't fire on PS4** even with the debug patch. On a PC dev build, Triangle + debug sends `cheat_new_bounties` (receiver `0x16e682`, no debug check there), which clears `used` and refills the available bounties up to 6.

## Gear screen: `cheat0rz_plaz0rz` (debug, keyboard, probably dead)

`AN:Menu:Screens:Gear:cheat0rz_plaz0rz:cheat` at `0x2c0df4`.

- **Gate:** `is_debug_enabled()` at `0x2c0df6`.
- **Input:** USB keyboard keys, read as `input.keyboard` through `keyboard_was_pressed`.

| Key | Branch | Message | Effect (receiver in `AN.Menu.Data`) |
|---|---|---|---|
| `0` | `0x2c10a5` → `0x2c0e01` | `resource_cheat` | +50,000 `credits` (`0x16ddc9`; counts are capped at 99,999) |
| `1` / `2` / `3` | `0x2c1089` / `0x2c106d` / `0x2c1051` | `resource_cheat` | +100 of `core1` / `core2` / `core3`. Real core resources are named `core<type>_<level>`, so this probably adds a bogus entry |
| `b` | `0x2c1035` → `0x2c0f3d` | `bulletcolor_cheat` | Unlocks every bullet colour in `bullet_color_props` (`0x15db8b`, gated `0x1734f7`) |
| `a` | `0x2c1019` → `0x2c0f69` | `blueprint_cheat` | For every weapon and item in `menu_data_research`, adds one new copy (rarity `rand_range_int(3,4)`, your class's upgrade level, random name seed), up to 10 per list (`0x15dc89`, gated `0x1734e8`) |
| `c` | `0x2c0ffd` → `0x2c0f95` | `colorset_cheat` | Adds one random colour set (8 random colours, random rarity 0–4) if you have fewer than 10 (`0x15dea0`, gated `0x1734d9`) |
| `p` | `0x2c0fe1` → `0x2c0fc1` | `suitpaint_cheat` | Unlocks up to 8 random suit paints you don't own that aren't `can_be_bought` (`0x172946`; the receiver has **no** debug check) |

`cheat0rz_plaz0rz:0wn3d` (`0x2c6026`) waits one frame after a cheat (`cheat_pending_update`), then refreshes the upgrades page (`menu_gear_upgrades` / `redefine`).

**Why it's probably dead:** the Gear screen's `input` is `AN.Menu.Input` (`Gear:Init:wait`, `0x2c6e6a`), and nothing in the script blob ever writes a `keyboard` field there. The only `SelfPut keyboard` sites are `Debug.Debug_Keys`, `AN.HUD.Manager`, `AN.Menu.Scene`, `AN.Managers.Local_Player_Controls` and `AN.Managers.Camera_Controller`. So `StoreGet keyboard` at `0x2c10ac` reads a missing key. The bytecode has a separate `StoreTryGet`, which suggests `StoreGet` treats a missing key as an error. Either way the keys can't fire unless the VM falls back to a default keyboard (**unverified**). The same effects are available through the working Resources screen cheat or a save edit.

## Player cheats: `AN:Player:Player_Character:Debug_Stuff`

These are already reachable through the debug keyboard and debug menu in [developer-hooks.md](developer-hooks.md). This section only records what the player side does.

### `Cheats` (`0x1ccbee`)

Consumes the `debug_events` flags set by `Debug.Debug_Keys`. Notes beyond the keyboard table:

| Event | Offset | Effect |
|---|---|---|
| `player_toggle_god_mode` | `0x1cd061` | Toggles `_health.godmode` |
| `player_toggle_demigod_mode` | `0x1ccfb1` | Toggles `demigodmode` |
| `aliens_toggle_sight` | `0x1ccf83` | Toggles `alien_can_see` |
| `toggle_rush_timer` | `0x1ccf72` | Toggles `no_rush_timer`. No key is bound to it |
| `respawn` | `0x1ccf3b` | Respawns at your position (debug menu `respawn` button) |
| `checkpoint_now` / `restart_level_here` | `0x1cceff` / `0x1ccec3` | Creates a `debug_checkpoint` at your position |
| `collect_story_item` | `0x1cce93` | Collects a random `story_item_1`…`7`. No key is bound to it |
| `collect_grenade` | `0x1cce64` | +1 grenade |
| `collect_credits` | `0x1cce54` | Adds `money` = `extconfig_get_player_level_xp(_armor.paragon_level + 1) / 5`. Skipped for remotely owned players |
| `get_aggro` | `0x1ccd8d` | Calls the aggro helper `0x1c3b74` with argument 10 |
| `toggle_player_move_mode` | `0x1ccd78` | Switches between `dynamic` and `follow_animation` |
| `fall_down_test` | `0x1ccd18` | Arms the test. After that, each melee press sets `ragdoll_dir` to your aim direction |
| `spawn_vehicle` | `0x1cccfe` | Sets `debug_vehicle_enabled` |

### `cheat_badges` (`0x1cf224`)

This state checks for `Msg` activations tagged `give_badge_*` (`0x1b523e`). For each one it sets `player_data.stats.cheat_badges.<badge> = true` (`0x1c4041`). The messages come from the **Badges** buttons in the `Debug.Debug_Keys` GUI menu (`0xd9284`):

| Button | Message | Flag |
|---|---|---|
| `mission` | `give_badge_objectives` (`0xda3f3`) | `objectives` |
| `damage` | `give_badge_undamaged` (`0xda38c`) | `undamaged` |
| `score` | `give_badge_highscore` (`0xda342`) | `highscore` |
| `kills` | `give_badge_all_aliens` (`0xda2f8`) | `all_aliens` |
| `complete` | `end_level_instant` (`0xda2e1`) | Ends the level immediately |

`cheat_badges` is reset to all-false in the player's stats initializer (`0x1d5080`) and in an `AN.Menu.Manager` stats initializer (`0x25d341`). No script reads it back, so the end-of-mission screen probably reads it natively (**unverified**).

## Cheat messages handled by `AN.Menu.Data`

`AN:Menu:Data:Main:listen` (`0x15690b`) receives these as `Msg` objects with `tag = 'Data'`. Every handler that changes player data also sets a per-user flag (`list_set(flags, user_idx, true)`). After the message loop, that flag makes `listen` rebuild the character's save block (`0x1569c5`: `Version`, `last_login`, `STAMP`, …). So the cheats probably persist to `savedata.dat` (**unverified**).

| Message id | Dispatch | Receiver gate | Handler | Senders |
|---|---|---|---|---|
| `resource_cheat` | `0x158697` | `cheat` field present + debug (`0x1734a0`/`0x173491`) | `0x16ddc9` | Resources screen, Gear `0`–`3` |
| `bulletcolor_cheat` | `0x1584d5` | debug (`0x1734f7`) | `0x15db8b` | Gear `b` |
| `blueprint_cheat` | `0x1584e7` | debug (`0x1734e8`) | `0x15dc89` | Gear `a` |
| `colorset_cheat` | `0x1584f9` | debug (`0x1734d9`) | `0x15dea0` | Gear `c` |
| `suitpaint_cheat` | `0x1588a1` | **none** | `0x172946` | Gear `p` |
| `cheat_mission` | `0x1586bb` | debug (`0x173473`) | `0x16e487` | World map Square |
| `cheat_complete_mission` | `0x1586a9` | debug (`0x173482`) | `0x16e0a4` | Mission list Select |
| `cheat_rewards` | `0x1586cd` | debug (`0x173464`) | `0x16e49a` | World map / mission list L2 |
| `cheat_new_bounties` | `0x158703` | **none** | `0x16e682` | Bounties Triangle (Windows only) |

- `partial_unlock_cheat` isn't a message. It's a per-mission data field checked at `0x1323d6` (and read in `Missions:Leave_Squad:select`, `0x56e34f`).
- `add_item` isn't a cheat either. It's the normal loot/inventory message, sent by `AN.HUD.Manager`, `AN.Menu.List`, `AN.Menu.Manager`, `AN.Menu.Tree` and `Game_Systems`.
