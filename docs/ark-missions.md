# Ark Ship (dreadnought) missions

Goal: make Ark Ship missions available offline. Static analysis with `tools/research/stated.py`; nothing here has been tested on console unless stated.

## Summary

**The Ark Ship mission is a built-in story mission and needs no server.** It's story mission **1601**, unlocked by completing the Mothership mission (1600), which needs the final campaign mission Havre M04 (1104). Each run costs one Ark Ship key (`key2`). Keys drop from static loot data, so the whole chain works offline.

An earlier version of this note concluded Ark missions only came from the server as global missions. That was wrong: server global missions *can* carry `extra_params.dreadnought`, but the story mission is the offline-native source.

## The procedural story missions

Defined in code in `AN.Menu.Data` (story mission table around `0x14da3c`–`0x14ec7c`):

| ID | Mission | `level_name` | `extra_params` | Prerequisites | Cost |
|---|---|---|---|---|---|
| 1501 | Battleship | `Procedural_Alien_Ship` | `battleship`, `force_mission_type = story_mission` | — | — |
| 1502 | UFO (`BRIEFING_UFO`, regenerates as `ufo1`–`ufo10`) | `Procedural_Alien_Ship` | `battleship`, `ufo`, `fail_mission_on_team_wipe` | — | `key1` × 1 |
| 1600 | Mothership (`TITLE_MOTHERSHIP`, `hide_when_completed`) | `Procedural_Alien_Ship` | `mothership = 0`, `force_floor_count = 1`, `fail_mission_on_team_wipe` | story 1104 completed | — |
| **1601** | **Ark Ship** (`TITLE_DREADNOUGHT` / `BRIEFING_DREADNOUGHT`) | **`Procedural_Endgame`** | `mothership = 0`, **`dreadnought = true`**, `force_floor_count = 5`, `fail_mission_on_team_wipe`, `retain_level_data_on_level_change` | story 1600 completed | **`key2` × 1** |

1601 has two difficulty levels (`difficulty_delta` 4 and 20); the second needs the first completed.

How the variant is chosen at runtime:

- `AN.Menu.Manager` copies `selected_mission.extra_params` into the game start parameters (`0x2607a0`). `Game_Startup` merges them into the game properties (`table_merge_inplace`, `0x1a659e`).
- `AN.Levels.Procedural_Endgame.Goal_Manager` enters its `Procedural_Levels:Mothership` stage only when `Game_Systems.extra_params.dreadnought == true` (`0x477cdc`). Room generation reads `variation_dreadnought` (`AN.Levels.Procedural_Alien_Ship.Room`).
- `Procedural_Alien_Ship` (UFO/battleship/mothership) reads `mothership` and `ufo`.

### Save state

Story progress is in `slots[N].story_missions`: `{id, completed, difficulty_levels[6]}` (1600 has no difficulty list; 1601 has 2). In the sample saves, both characters that completed 1600 had also played 1601, and held `key2`.

The user's character (CUSA04181 save) has 1103 and 1104 incomplete, so the chain hasn't started.

### Key drops

`key1`/`key2` are plain inventory resources. Loot box quality data (`quality_info`, property sets around `0x5853c8` and `0x585827`, box scenes `endloot` and `items.newbox`) has `dreadnought_key_drop_chance = 1.0`. The box logic at `0x24d8f2` drops a `dreadnought` key when `rand() <= chance`. `ufo_key_drop_chance` can be a list. All static, no `extconfig`.

## Offline options

1. **Play it:** complete Havre M03 + M04, then the Mothership, then use an Ark key on the Ark Ship mission.
2. **Save edit (untested):**
   - In `slots[N].story_missions`, set `completed: true` on 1103, 1104 and 1600.
   - For missions with an all-false `difficulty_levels` list, also set its first entry true, as game-made saves record it.
   - The save editor doesn't do this. A one-off script that did was removed on 2026-10-12, since story unlocks are easy in game.

## QA / developer launch hooks

The `Startup` root state machine (index 293) builds the `global_settings` property set from its spawn fields (`0x401a5d`–`0x401cef`):

| Spawn field | `global_settings` key | Notes |
|---|---|---|
| `startup_level` | `startup_level` | Boots straight into that level; `AN.Menu.Boot` skips the intro video |
| `s_mission_id` | `startup_mission_id` | Starts a story mission by id |
| `s_mothership` | `force_mothership` | Adds `extra_params.mothership = 0` to any mission (`0x2609e0`) |
| `s_test` | `test_mode` | Only if `is_debug_enabled()`. Soak test: random armor/level, auto-join/create online games, "continuing offline" on failure |
| `s_offline` | `offline_mode` | Skips spawning `Network_Manager` |
| `s_god`, `s_world_level`, `s_player_level`, `s_battleship_level`, `s_difficulty`, `s_unlocked_missions` (`fake_unlocked_missions`), `s_armor`, `s_disable_enemies`, `s_xp_multiplier`, `s_random_seed`, … | | |

The startup launcher (`AN.Menu.Manager` `0x272a08`) picks a story mission by `startup_mission_id` from `menu_data_story_missions`, or fabricates `{level_name = startup_level, player_count = 1, type = story_mission, difficulty = 0, world_level}`. `startup_mission_id = 1601` would therefore launch the Ark Ship directly with its real `extra_params`.

The native command-line parser (application vtable `0x1edc010`, handler `0x2d0`) knows `-startup_sm:`, `-startup_level:`, `-join_coop_game:`, `-replay:`, `-platform:`, `-demo`, `-trial`, `-no_splash`, `-skip_navmesh`, `-smasher_test`, `-create_coop_game`, and the sound/rumble/ability flags. How the generic `s_*` fields reach `Startup` hasn't been traced; the eboot contains no `s_` prefix string. Retail launches pass no arguments, so using these needs an eboot patch.

Other QA tweakables: `an__weekly__override_enabled`, `an__weekly__mission_location_override` (index into a 21-level list where 10 = `procedural_alien_ship`) and `an__weekly__mission_id_override` rewrite the server's weekly mission (`AN.Menu.Network`, `0x550b`). `an__metagame__battleship_level_override`, `an__metagame__world_level_override` and `an__gameplay__player_level_override` are also available via the debug overlay's Tweakables page.

## Server facts (for reference)

- Server: `prod.alienation.online.scee.com` (resolved to an AWS load balancer on 2026-10-10). `AN.Menu.Network` `Connected:receive` (`0x65c0`) turns `getGlobalMissions` results into `add_global_mission` messages.
- The normalizer rewrites `level_name = procedural_alien_ship` global missions to `pripyat_m05` (`0x47f5`) and keeps `extra_params`.
- `buy_global_mission` (`0x159ae9`) deducts `prerequisites.cost` and marks the mission bought.
- `special_missions` (save root) are restored on load (`0x14893e`) but nothing in this build creates them.
