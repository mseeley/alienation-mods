# `is_platform_windows()`: audit and patch

Static analysis of the patch0 eboot (APP_VER 01.07) and the Stated scripts. Nothing here is tested on console. **Conclusion: forcing Windows mode breaks core gameplay. No patch ships.**

## How the value is produced

`platform()`, `is_platform_windows()` and `is_platform_orbis()` are Stated **intrinsics**, not ordinary natives. Their native bodies (`0x35dd20`, `0x35dd30`, `0x35dd40`) are a bare `ret`. Registration marks them with extended VM opcodes `0x4f`, `0x50` and `0x51`, via `0x278600` (`[desc+0x48] = 1`, `[desc+0x4c] = opcode`); 45 natives use opcodes 72–116. At load, `0x3dadd5` rewrites each `CallExt` to such a native in place, as `[opcode] 47 47`. The interpreter (`0x3f25c0`, byte-opcode switch over 0–0x74, table `0x17b1c00`) then runs:

| Opcode | Handler | Pushes |
|---|---|---|
| `0x50` `is_platform_windows` | `0x3f4593` | `0x0400000000000000` (bool false) |
| `0x51` `is_platform_orbis` | `0x3f45b7` | `0x0400000000000001` (bool true) |

**Patch (not shipped):** one byte, `0x7f45aa` (vaddr `0x3f45aa`, the low byte of `movabs rcx, 0x0400000000000000`): `00` → `01`. `is_platform_windows()` then returns true and `is_platform_orbis()` stays true. No native code reads the platform any other way. Every check goes through this opcode.

## Where Windows is checked

362 call sites in about 150 state machines. Grouped by what the Windows branch does:

| Sites | Where | Windows-only behaviour | Effect on a PS4 |
|---|---|---|---|
| 96 | Spawners (`AN.Spawners.*`) | Sends a `debug_spawner_init` message describing the spawner | Extra messages; harmless |
| 76 | Level `Startup` SMs | Strips a `-PC` suffix from the signed-in user's name (a Windows machine-name artefact) | Harmless |
| 49 | Enemy AI | Reads `an__ai__debug_pathfinding` (exists in retail) | Harmless unless toggled |
| 25 | Enemy movement | Multiplies speed by `an__gameplay__enemy_speed_multiplier` | **Blocker: tweakable missing** |
| 22 | Enemy shooting | Multiplies bullet speed by `an__gameplay__enemy_bullet_speed_multiplier` | **Blocker: tweakable missing** |
| 5 | `Player_Character` | Forward/backward speed multipliers, stick dead-zone angle | **Blocker: tweakables missing** |
| 5 | `Super_Gun`, `Gibs` | `player_weapon_damage_multiplier`, `player_fire_rate_multiplier` | **Blocker: tweakables missing** |
| 8 | Gear, Player and Campaign_Select menus, `Alien_Soul`, `Havre_S02.Goal_Manager` | `an__menu__player_color__override_enabled` / `_idx` | **Blocker: tweakables missing** |
| 23 | `Menu.Manager`, `Game_Startup`, `Patrol_Route`, `Alien_Core`, `Shriek_Indicator`, `Shell_Super`, `Havre_S02` | Reads `global_settings.debug_analytics` | Not set, so no-op |
| ~12 | `Menu.Manager` | Test-mode matchmaking (`test_mode_blacklist`, `*** TEST MODE joining game…`, `join_coop_game`) | Only with test mode or `join_coop_game` |
| 2 | `Startup` | `s_*` spawn fields → `global_settings`; `s_im_so_entitled` sets `an__drm__*` tweakables | Fields aren't set on retail; `an__drm__*` don't exist (would error if they were) |
| 1 | `Menu.Boot` | `skip_video = true` | **Skips the splash and intro videos** |
| 2 | `Menu.Screens.Title` | Static background instead of `title.mp4` | Cosmetic |
| 1 | `Menu.Dialogs.Story` | Skips the story video | Cosmetic |
| 1 | `Menu.Network` | Skips the PSN `online_user_can_use_online_services` check | Online permission checks bypassed |
| 1 | `Network_Manager` | Skips an `online_user_can_play_online` check during game scan | Online permission checks bypassed |
| 2 | `Generic_Exploding_Object` (+ deprecated copy) | Validates `wrecked_remnant` against the resource list; with debug on, calls `error()` | Possible script error with debug mode on |
| 4 | `Instant_Spawn` | Prints "couldn't find a position on navmesh" | Log only |
| rest | `Box_Activator`, `Plasma`, `HUD.Log`, `Healthbar`, `Camera_Block_Zone`, `Cubemap_*`, `Spawner_Manager`, `Boss_360`, `Game_Systems` | Debug drawing, editor validation, particle tuning, minimap debug | Mostly harmless; `Level_Settings` never reaches its check (`is_master_release()` is true) |

### The blocker

The nine tweakables marked "missing" exist only in dev PC builds. Their names appear nowhere in the retail eboot or in stream.dat data. For an unknown name, `tweakable_get` (`0x3cd490`) raises a script error, "Tweakable '%s' not found; unable to get!" (`0x276470` sets the context error flag). The engine documents an error as halting script execution, and these reads sit in every enemy's movement and shooting update, the player's movement, weapon damage and three menu screens. Expect enemies, the player and the character menus to stop working. Exactly what gets halted (the state, or the whole state machine) wasn't traced.

## With both predicates true

Since `is_platform_orbis()` is already true, "both true" means current behaviour plus every Windows branch. The 11 state machines that test both:

- `Menu.Manager` (`Test_Create`, network wait): the orbis check comes first and takes the PS4 path ("running on ps4 -> single player", skip `Network_Manager`). Consistent.
- `Game_Systems` minimap debug: Windows enables the debug spawn display, then `is_platform_orbis()` skips the `debug_gui_button` call. Consistent.
- `Menu.Network`: Windows skips the PSN service-permission check, but the orbis branches still fetch the PSN auth code and account id. Works, but bypasses a platform requirement; keep it offline.
- `Player_Character`, `Blob_Exploding`, `Popcorn_prototype`, `Camera_Block_Zone`, `Cubemap_*`, `FortItaipu_Ambush`, `jukka_test_0`: the two checks guard unrelated code. No conflict, apart from the missing-tweakable blockers above.

No site was found where both being true runs two conflicting platform paths. The breakage comes entirely from Windows branches that need dev-only tweakables.

## Making it usable

The useful parts (video skip, PSN-check bypass) are reachable more safely. The "Skip intro videos" patch already covers the boot videos. Windows mode would only become viable if `tweakable_get` returned a neutral default for unknown names instead of raising an error. But the defaults differ (multipliers want 1.0, override flags want false, `override_idx` wants a negative number, and the dead-zone angle's default is unknown), so one generic fallback can't be correct for all of them.
