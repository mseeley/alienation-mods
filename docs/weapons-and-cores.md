# Weapons, perks and cores

Derived from the `STAD` string pool, localization text and `STDD` debug names, then confirmed against a real save ([Save layout](#save-layout)). For the binary encoding see [file-formats.md](file-formats.md).

## Where the logic lives

| State machine | Role |
|---|---|
| `AN.Managers.Inventory_Manager` | Inventory management |
| `AN.Menu.Upgrade_Weapon` | Core assignment screen (states `assign`, `cursor`, `setup`, …) |
| `AN.Menu.Screens.Gear` | Gear screen, includes the `cheat0rz_plaz0rz` cheat state |
| `AN:Menu:Data` | Menu data model; handles `add_item`, `sell_item`, `lock_item`, `refurbish_item`, `drop_item`, `item_activate`, `use_resources`, `resource_cheat`, … |
| `Scripts:Perks` | Perk logic |
| `AN.Objects.Loot.Alien_Core` | Core pickups |
| `Property_Sets:Weapons:*` | Per-weapon tuning data |

## Weapons

Weapon base names: `xenorifle`, `smg`, `revolver`, `powershot_rifle`, `plasmarifle`, `plasma_shotgun`, `minigun`, `launcher`, `laser_gun`, `flamer`, `energygun`, `devastator`, plus the `Super_gun`, `Sphere_Gun`, `Deathray`, `Vortex` and `Targeting_Missile_Launcher` property sets.

Slots follow the weapon's `ammo_name`. Each slot holds at most 10 weapons: the pickup and menu `add_item` refuse an 11th (`Weapon_Collectible` 0x1efc47, `add_item` 0x15d731). Equipment is capped at 10 too. Armor sets aren't capped on load (a console-tested save holds 14), but `AN.Menu.Data` only adds a looted set while `color_sets` has fewer than 10 (0x15d91d).

| `active_weapons` index | Slot | Ammo | Codes |
|---|---|---|---|
| 1 | Heavy | rockets | `machine_gun`, `launcher`, `flamethrower`, `sphere_gun` |
| 2 | Primary | bullets | `xenorifle`, `smg`, `energy_gun` |
| 3 | Secondary | fuel cells | `powershot`, `shotgun`, `revolver`, `laser_gun` |

Class rules (armor props `illegal_weapons`):
- **Primary is class-bound.** Saboteur gets `smg`, Bio-Specialist `xenorifle`, Tank `energy_gun`. Heavies and secondaries are open to every class.
- **Weapon hack add-on** empties the class lists. `sphere_gun`, `laser_gun` and `vortex_grenade` still need their own add-on.
- **On load** (0x1367eb–0x136a12), an illegal equipped weapon is replaced by the last legal weapon with the same ammo (or nil). An out-of-range index becomes 0. A wrong slot type is not corrected.
- **New characters** start with just their class primary and a grenade. Level-15 starts add `shotgun` and `machine_gun`.

Item fields seen in strings include `rarity`, `item_level`, `weapon_slots`, `slot_idx`, `cores`, `allowed_cores`, `attributes`, `active_perks` and `blueprint_id`.

Base attributes: damage, fire rate, clip size, reload time, critical hit chance, efficiency.

## Perks (conditional actions)

A perk is a **condition** paired with an **effect**.

| Condition key (`perk_id_*`) | Text | Status |
|---|---|---|
| `on_enemy_hit` | %.2f%% CHANCE ON ENEMY HIT | **rolled** |
| `on_enemy_hit_critical` | %.2f%% CHANCE ON CRITICAL ENEMY HIT | untested |
| `on_enemy_hit_melee` | %.2f%% CHANCE ON MELEE ENEMY HIT | **rolled** |
| `on_player_hit` | %.2f%% CHANCE ON PLAYER HIT | **rolled** |
| `enemy_within_range` | ENEMY WITHIN %dm | untested |
| `enemies_within_range` | 3 ENEMIES WITHIN %dm | untested |
| `boss_within_range` | BOSS ENEMY WITHIN %dm | untested |
| `player_within_range` | ANOTHER PLAYER WITHIN %dm | untested |
| `staying_still` | STANDING STILL | untested |
| `rush_not_ready` | RUSH NOT CHARGED | untested |
| `low_ammo` | AMMO BELOW %d%% | untested |

| Effect key (`perk_effect_*`) | Text | Status |
|---|---|---|
| `bonus_talent_power` | %+d%% GEAR POWER | untested |
| `reduce_damage_taken` | %d%% PLAYER DAMAGE REDUCTION | untested |
| `gain_shield` | FRONT SHIELD (WIDTH %dm) | untested |
| `bonus_weapon_fire_rate` | %+d%% FIRE RATE | untested |
| `bonus_weapon_damage` | %+d%% WEAPON DAMAGE | untested |
| `bonus_critical_chance` | %+d%% CRITICAL HIT CHANCE | untested |
| `bonus_critical_damage` | %+d%% CRITICAL DAMAGE BONUS | untested |
| `cluster_shell_from_target` | %dHP DAMAGE CLUSTER SHELL ON TARGET | **rolled** |
| `boomerang_at_target` | %dHP DAMAGE BOOMERANG AT TARGET | **rolled** |
| `knockdown_target` | KNOCKDOWN TARGET | **rolled** |
| `gain_ammo_clip` | %d%% CHANCE TO GAIN ONE AMMO CLIP | untested |
| `poison_target` | %dHP POISON DAMAGE | untested |
| `explosion_target` | %dHP EXPLOSION DAMAGE | untested |
| `chain_lightning_target` | %dHP CHAIN LIGHTNING DAMAGE | **rolled** |

Related save/config fields: `perk_effect_ranges`, `debug_perk_condition`, `debug_perk_effect`.

**Effect strength** (`0x1c787b`). When a weapon is equipped, `effect_efficiency` becomes the perk's `effect_multiplier`. The strength is then `base × level × efficiency`, where level is the weapon's displayed level (`max(1, upgrade_level + 1)`). The game rolls efficiency between 0.5 and 1.0 (`perk_effect_ranges`).

| Effect | Strength | Level 30, efficiency 1.0 |
|---|---|---|
| `boomerang_at_target` | 100 × level × efficiency HP | 3,000 HP |
| `chain_lightning_target` | 100 × level × efficiency HP | 3,000 HP |
| `knockdown_target` | 100 × level × efficiency | 3,000 |
| `poison_target` | 100 × level × efficiency HP | 3,000 HP |
| `cluster_shell_from_target` | 250 × level × efficiency HP | 7,500 HP |
| `explosion_target` | 250 × level × efficiency HP | 7,500 HP |
| `gain_ammo_clip` | round(20 × efficiency) % chance | 20% |

The other bonus effects (crit, damage, fire rate, shield, damage reduction, gear power) have their own branches after `0x1c7b0b`.

**Trigger chance** (per hit, in each enemy's damage handling, e.g. 0x2978c7):
- **The chance** is `50 × perk_value` % for `on_enemy_hit`, `75 × perk_value` % for `on_enemy_hit_critical` and `100 × perk_value` % for `on_enemy_hit_melee`. `on_player_hit` is always 100%, with a 0.3 s cooldown.
- **Some damage carries a `trigger_chance_multiplier`,** which scales the chance (not for knockdown).
- **`on_enemy_hit` also has a guaranteed proc:** `perk_cooldown_consume(player, 3)` fires the perk with no roll if no perk has fired in the last 3 seconds.
- **Otherwise each hit rolls** `rand() < chance`.
- The game sets `perk_value` to 1/fire rate per weapon, so fast weapons proc less often per hit: SMG 1/3 → 16.7%, Collapser 1/30 → 1.7%, launcher 1.25 → 62.5%.
- **`perk_value` 2.0 makes `on_enemy_hit` 100%** (the menu shows "100.00% CHANCE ON ENEMY HIT").

**Condition values** (same function), from the slot's `perk_value`:

| Condition | Meaning |
|---|---|
| `enemy_within_range` | 5 × value metres |
| `enemies_within_range` | 10 × value metres |
| `boss_within_range` | 30 × value metres |
| `player_within_range` | 5 × value metres |
| `staying_still`, `rush_not_ready` | value |
| `low_ammo` | round(20 × value) % |

## Cores

Four types, each with levels 1–6. N cores combine into one core of the next level ("Press X to combine %d cores into 1 higher level core").

| Type | Name | Effect |
|---|---|---|
| 1 | Boost (blue) | Weapon fire rate; effect radius of equipment |
| 2 | Power (red) | Damage of weapons and equipment |
| 3 | Utility (yellow) | Weapon clip size; equipment recharge rate |
| 4 | Prismatic (white) | Weapons only; critical hit chance; activates the bonus in any socket colour |

- A core in a socket of matching colour gives a bonus ("synergy").
- Assigned cores can't be retrieved. Assigning over an existing core destroys the old one.
- Strings such as `core4_%d` and `resources_core_icon_%s_%d` suggest per-type, per-level resource counters.

## Other resources

- Reroll metals: `metal0`–`metal5` (Stock, Common, Uncommon, Rare, Legendary, Unobtainium), used to reroll weapon modifiers.
- Access keys: UFO key, Dreadnought (Ark Ship) key.

## Save layout

Verified against three real saves (CUSA04181 and CUSA00062, 13 characters across all three classes, 3 of them hardcore, 155 weapons, 48 equipment items). The format is identical across both title IDs. Key names are case-insensitive. The paths below are under `slots[N]`, one table per character, or `nil` for an empty slot.

```
slots[N]
  id, game_mode, version (51), stamp, last_login, story_missions, bounties, stats, game_char_data
  inventory
    weapons:          list of weapon tables (below)
    active_weapons:   [nil, heavy, primary, secondary]   0-based indices into weapons
    items:            equipment (grenades, boomerang, ...), same layout as weapons
    active_items:     [nil, ?, equipment, ?]             0-based indices into items (all equipment uses index 2)
    resources:        list of {name, count}              core and material counts
    armor, color_sets, suit_paints, bullet_colors, story_items, active_beacons,
    world_level, battleship_level, ...
```

Because `active_weapons` and `active_items` store indices, reordering or removing entries in `weapons`/`items` means updating them too. Appending is safe.

### Weapon

| Key | Type | Example / meaning |
|---|---|---|
| `code` | string | Weapon type. Seen: `xenorifle`, `smg`, `machine_gun`, `shotgun`, `revolver`, `powershot`, `energy_gun`, `laser_gun`, `sphere_gun`, `flamethrower`, `launcher`. Equipment: `grenade`, `cluster_grenade`, `vortex_grenade`, `mine`, `boomerang` |
| `rarity` | int | 0–4 |
| `upgrade_level` | int | 0–29, **0-based**: the game shows `upgrade_level + 1` (29 = "LEVEL 30", confirmed on console) |
| `name_seed` | int | Picks the weapon's colour tint (`abs(seed % 10)`); despite the name, not the item name |
| `lock` | bool | Locked against salvaging (absent when false) |
| `new` | bool | Not yet viewed in the menu (optional) |
| `bullet_color` | | Optional, rare |
| `modifiers` | list of `{code, multiplier}` | Stats, below |
| `upgrades` | list | One entry per slot, 0–13 entries, below |

Equipment items use the same layout with 0–6 slots. Their single modifier is `damage_level` or `damage_per_second`, and their perk slot carries `attribute` + `value: true` instead of a condition/effect pair.
- **Perk flags** (`AN.Weapons.Equipment.Super_Grenade`): `fast_recharge_perk` doubles `ammo_replenish_rate`, `double_reserve_perk` doubles `max_grenades`, and `speed_jolt_perk` boosts movement speed on throw.
- **Only listed attributes apply.** A perk takes effect only if it's in the item type's attribute list. The vortex grenade lists `double_reserve_perk` but not `speed_jolt_perk`, although the game rolls speed jolt for it.
- **No cause/effect perks on equipment.** Only weapons collect cause/effect perks when an equipped item's info is built (0x1704b8).

### Modifiers

Every weapon has four: an absolute damage value plus three multipliers. Ranges seen across all saves:

| Code | Weapons | Range |
|---|---|---|
| `damage_level` | all except Devastator | 2.4 – 3,470 (scales with `upgrade_level`) |
| `damage_per_second` | Devastator, vortex grenade | 7.4 – 3,470 |
| `fire_rate` | all except Devastator and Collapser | 0.88 – 1.12 |
| `charge_time` | Devastator, Collapser | 0.875 – 1.12 |
| `clip_size` | all weapons | 0.64 – 1.37 (wider for powershot, shotgun, revolver, launcher) |
| `critical_hit_chance` | all weapons | 0.75 – 1.25 |

### Slot layout

The slot list is an upgrade tree. A 13-slot weapon (the maximum: 12 core sockets plus 1 perk) looks like this:

```
 0 root1   1 root2   2   3   4        main path
 5 b1   6 b1   7 b1   8 b1 perk       branch 1, perk last
 9 b2  10 b2  11 b2  12 b2            branch 2
```

All 18 thirteen-slot weapons in the saves use exactly this order. Smaller weapons use the same tree but list slots in varying order (e.g. a 7-slot weapon may put branch 2 at indices 5–6), so read each slot's `branch`/`branch_root` keys rather than relying on position. Each weapon has at most one perk: index 8 on weapons with 9+ slots, otherwise the last slot.

**Tree rule** (verified on all 1,150 slots in the saves):
- Slots without `branch` form the main path, in list order. The slot with `branch_root: 1` is the main-path slot that branch 1 hangs off; likewise for `branch_root: 2`.
- A slot's parent is the previous slot in the list with the same `branch` value. The first slot of branch *b* has the `branch_root: b` slot as its parent.

**Synergy rule** (same 1,150 slots, no exceptions): when a slot and its parent have the same coloured socket type (`core1`–`core3`), the parent gets `synergy.next` and the child gets `synergy.prev`. `core` (any-colour) sockets and perks never link. The flags depend only on socket colours, not on which cores are installed.

### Upgrade slot (`upgrades[i]`)

**Core socket:**

| Key | Type | Meaning |
|---|---|---|
| `type` | string | Socket colour: `core1` = blue, `core2` = red, `core3` = yellow, `core` = white (any colour); colours confirmed on console. Any core can go in any socket. The saves contain mismatched cores and Prismatic cores in coloured sockets; matching colours give the bonus |
| `core` | tuple `(string, int)` | Installed core. **The level is 0-based**: `('core4', 3)` is a level-4 Prismatic core, so valid values are 0–5 (levels 1–6). Absent when empty. Writing 6 crashed the game as soon as the weapon was selected in the gear menu (console test, 2026-10-10) |
| `synergy` | table | `{next: true}` / `{prev: true}` link adjacent same-colour sockets |
| `branch_root` | int | Marks the first slot of upgrade-tree branch 1 or 2 |
| `branch` | int | Slot belongs to branch 1 or 2. Slots with neither key are on the main path |

**Perk slot:**

| Key | Type | Meaning |
|---|---|---|
| `type` | string | `'perk'` |
| `perk_id` | string | Condition (table above), e.g. `on_enemy_hit_melee`. The gear screen labels `on_enemy_hit` as "ACTION: SHOOT AT ENEMY" (seen in screenshots; label text not found in the game data) |
| `perk_value` | float | Condition parameter. `on_enemy_hit`: 0.033–1.25; `on_enemy_hit_melee` and `on_player_hit`: always 1 |
| `effect_id` | string | Effect (table above), e.g. `chain_lightning_target` |
| `effect_efficiency` | float | Effect strength, 0.50–1.0 seen |
| `branch` | int | As for sockets |

### Core inventory (`inventory.resources`)

Each entry is `{name: 'core<type>_<level>', count: <int>}` with a **1-based** level, e.g. `core4_3` = Prismatic level 3 (unlike installed cores). Editing these counts works in game (console test). All 24 combinations (types 1–4, levels 1–6) occur in real saves. The same list holds `metal0`–`metal4`, `credits`, `flower`, `key1` (UFO) and `key2` (Dreadnought). `metal5` never appears.

`stats.resources` uses the same names with **string** counts. These are lifetime totals, not inventory.

### Perks seen in real saves

Only 3 of the 11 conditions and 4 of the 14 effects occur across all 155 weapons:

- Conditions: `on_enemy_hit`, `on_enemy_hit_melee`, `on_player_hit`
- Effects: `boomerang_at_target`, `chain_lightning_target`, `cluster_shell_from_target`, `knockdown_target`

All 11 pairings of these appear. The other conditions and effects exist in localization but may be unused or cut; whether they work if written into a save is unknown.

The character class is stored as the armor `code`: `ninja_armor` = Saboteur, `health_regen` = Bio-Specialist, `shield_armor` = Tank (inferred from each tree's abilities). Characters of every class hold every weapon type in the saves because of the weapon hack (`ANWEAPONHACK0001`, see [developer-hooks.md](developer-hooks.md)), which lets any class carry any weapon. Two saves have `settings.weapon_hack_announced = true`; the EU save lacks the flag but still has cross-class weapons. The per-class weapon lists without the hack can't be read from these saves.

Armor (`inventory.armor`) is the class ability tree (`lazor_sword_*`, `snipe_*`, …) with `attribute`/`value` entries, not conditional perks. Each armor has a `requires_lvl15_entitlement` flag, tied to the `ANLEVEL15*` entitlement labels.

### Untested on hardware

Everything listed above occurs in game-made saves, so building weapons within those bounds should be safe. **Confirmed on console (2026-10-10):** an appended 13-slot SMG (rarity 4, `upgrade_level` 29, four sockets each of blue/red/yellow with 9 synergy links, level-6 cores stored as `('coreN', 5)`, damage 3466.65, fire rate 1.125, clip 1.15, crit 1.25, `on_enemy_hit` → `boomerang_at_target` at efficiency 1.0) plus 100 level-6 cores of each type loads and works (rebuilt by `tools/example-recipes/10_max_smg_boomerang.yaml`). Still untested: more than 13 slots, more than one perk or a perk in a non-standard position, perk conditions and effects never seen in saves, values outside the observed ranges, and `metal5`. Test these one at a time.

## Scrapping (hold L3)

`AN.Objects.Loot.Weapon_Collectible` sets `sell_time = props.sell_times[rarity]` when the weapon spawns (bytecode `0x1e8bc4`, `0x1e950c`). The `Player_Close:Sell` state then advances `sell_phase += delta_t / sell_time` while L3 is held and scraps at `sell_phase >= 1` (`0x1ef988`). The table is built at `0x587f15`–`0x587f32`:

| Rarity | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| Hold time (s) | 0.5 | 0.5 | 0.5 | 1.0 | 2.0 |

While L3 is held, the player sends the nearest weapon an `alt_action` message every frame (`Player_Character` `Handle_Actions`, `0x1dd2db`). Without a message that frame, `sell_phase` resets to 0. So the fill rate is constant, holding longer doesn't speed it up, and releasing restarts the bar. When holding through several weapons, each starts from 0 with its own time.

Patch "Fast weapon scrapping" ([`patches/xml_orbis/CUSA04181.xml`](../patches/xml_orbis/CUSA04181.xml), PatchVer 1.1, untested on console) sets the table to **0.3 / 0.4 / 0.5 / 0.75 / 1.0 s**: faster overall, but still longer for rarer weapons. (1.0 made every rarity 0.5 s, which made it hard to stop before scrapping a rare weapon.) The values are `PushFloat32` operands in stream.dat, out of reach of an eboot patch, so it rewrites them in memory at load. It hooks the Stated bytecode loader (`0x3dad40`, which already rewrites intrinsic calls in place) at `0x3dae06` and jumps to code in `0x2b050`, an unreferenced 48-byte function. That code points `rcx` at STAD+`0x6824c5` (the five operands, 5 bytes apart). If the last value is still 2.0 (top byte `0x40`), it writes 0.3 and 0.4 as dwords, 1.0 → 0.75 as one byte (`+0x11`: `0x80` → `0x40`) and 2.0 → 1.0 as one word (`+0x16`: `00 40` → `80 3f`). The STAD record has no fixups, so nothing else rewrites those bytes.

## How the game generates items

Static analysis; the sample saves match every rule.

**Stats.** `extconfig_get_item_level_modifiers(code, rarity, upgrade_level)` reads `item_levels.json` (stream.dat RAWD `0x00f199d8`). It returns `[base, spread]` per modifier, and the rolled value is `base × (1 + U(−spread/2, +spread/2))` (0x1e9aea; rerolls use the same formula, 0x2c2bb5).
- **Damage** uses one base table for every weapon and equipment type. At level 30 it's 646.23 / 1009.74 / 1009.74 / 1492.12 / 3081.49 for rarity 0–4, with spread 0.25.
- **Fire rate and charge time:** spread 0.25.
- **Crit chance:** spread 0.5.
- **Clip size:** spread 0.25 for most weapons, 0.3 for `smg`, 0.7 for `shotgun`, 0.75 for `revolver`, `powershot` and `launcher`.

**Sockets.** Every weapon uses the same 13-slot template. A slot exists if the item's rarity reaches it, and a failed probability roll ends that branch:

| Rarity | Main path | Branch 1 | Branch 2 |
|---|---|---|---|
| 0–1 | 0 | – | – |
| 2 | 2 | 0–2 (75% each) | – |
| 3 | 3 | 0–3 (75% each); perk 30% if all 3 succeed | – |
| 4 | 5 | 0–3; perk 100% if all 3 succeed | 0–4 (75/50/50/50%) |

- **Colour:** `rand_range_int(0, 4)` gives white for 0 or 4 and `core1`–`core3` for 1–3.
- **Equipment** is deterministic: 2 / 4 / 5 sockets + perk for rarity 2 / 3 / 4. Its perk is `fast_recharge_perk` or `speed_jolt_perk`, with value `true`.

**Weapon perks** roll one of 3 conditions (`on_enemy_hit`, `on_enemy_hit_melee`, `on_player_hit`) and one of 4 effects. That's why the saves never show the others.
- `effect_efficiency` is U(0.5, 1.0).
- `perk_value` is 1.0, except `on_enemy_hit`, where it's fixed per weapon.
- With debug mode on, the tweakables `an__gameplay__perks__effect_override` and `an__gameplay__perks__condition_override` force a perk at generation (0x1e9e97).

**`name_seed`** is a random int32. It picks the [weapon tint](#weapon-tints) `WEAPON_COLORS[min(rarity, 4)][abs(seed % 10)]`, not the name; the name comes from `strings_weapons_<code>`.

## Weapon tints

`WEAPON_COLORS` is built by the gameplay script `Property_Sets_Menu` (start code, Stated bytecode 0x34c120–0x34df2e in STAD record `0x124af99`), stored in the `menu_player` property set. It's `[rarity][tint]`, 5 × 10, and each entry is a full 8-colour set in the [armor colour-set layout](armor.md): `non`, `pri`, `sec`, `tri`, then the four finish values.

- **Who reads it.** The model script of every weapon (`AN.Weapons.Super_Gun`, `Flamethrower`, `360_Beam`, `Targeting_Missile_Launcher`; Super_Gun's lookup at bytecode 0x0b6a12) and the gear menu's 3D preview (`AN.Menu.Screens.Gear`, 0x2be749). The lookup is `list_get(colours, abs(name_seed % list_size))` on `list_get(WEAPON_COLORS, min(rarity, 4))`; with no `rarity` it uses rarity 0, with no `name_seed` tint 0.
- **Equipment.** The gear menu preview tints equipment from the same table (same rarity/seed lookup). Thrown grenades, mines and boomerangs don't: `AN.Weapons.Equipment.Super_Grenade` never sets colours.
- **What changes between tints:** only `pri`, `sec` and `tri`. `non` is always (0.5, 0.5, 0.5). Glow (the colour's alpha) is 0 on `pri`, 0.01–0.1 on `sec` and `tri`. The four finish values are shared by rarity 0–2, rare changes one of them, and legendary's vary per tint.
- **Which part of the gun each area paints** isn't known yet (the weapon textures haven't been looked at). On armor, `pri` / `sec` / `tri` are the plates, the suit and the visor.
- **Colours** below are `pri / sec / tri`, as `#rrggbb` of the 0–1 values (no gamma), like the armor colours in the save editor. A few values go above 1 (brighter than white); they're shown capped, with the real numbers in brackets. The values are also in `tools/lib/gamedata.py` (`WEAPON_TINTS`), and the desktop save editor shows them as swatches in the Tint dropdown.

| Tint | 0 (stock) | 1 (common) | 2 (uncommon) | 3 (rare) | 4 (legendary) |
|---|---|---|---|---|---|
| 0 | `#ffffff` / `#994c00` / `#ffffff` (bright: 1, 1, 1.2) | `#003300` / `#ffffff` / `#333333` | `#0033ff` / `#ffffff` / `#001aff` | `#2605ff` / `#ffffff` / `#0803e6` | `#e66605` / `#ffffff` / `#b23305` |
| 1 | `#ffffff` / `#000000` / `#ffffff` (bright: 1, 1, 1.2) | `#003300` / `#1f290a` / `#333333` | `#0033ff` / `#4c4c4c` / `#ffffff` | `#1a05e6` / `#4c6666` / `#45454a` | `#e66605` / `#ffffff` / `#0a0008` |
| 2 | `#ffffff` / `#333333` / `#ffffff` (bright: 1, 1, 1.2) | `#003300` / `#0a0303` / `#ffffff` (bright: 1.2, 1.2, 1.2) | `#808080` / `#0033ff` / `#3366ff` | `#1a05e6` / `#808080` / `#bfe6ff` | `#e66605` / `#804c1a` / `#ffffff` |
| 3 | `#ffffff` / `#000000` / `#ffff00` (bright: 1, 1.5, 0) | `#003300` / `#66994c` / `#268080` | `#808080` / `#0033ff` / `#333333` | `#1a05e6` / `#806633` / `#000000` | `#e66605` / `#000000` / `#4c4c4c` |
| 4 | `#000000` / `#ffffff` / `#334c80` | `#000000` / `#003300` / `#1a990d` | `#0033ff` / `#ffffff` / `#996614` | `#1a05e6` / `#4c4026` / `#999966` | `#e66605` / `#001a33` / `#4c4c4c` |
| 5 | `#000000` / `#333333` / `#ffffff` | `#003300` / `#334c00` / `#cc3303` | `#000000` / `#0033ff` / `#001aff` | `#1a05e6` / `#1a0300` / `#1f2429` | `#e66605` / `#140500` / `#808080` |
| 6 | `#ffffff` / `#ffffff` / `#80664c` | `#003300` / `#034f4c` / `#8080a6` | `#0033ff` / `#0d0000` / `#999999` | `#1a05e6` / `#a6591a` / `#806680` | `#e66605` / `#e66605` / `#1a0512` |
| 7 | `#ffffff` / `#33661a` / `#000580` | `#003300` / `#00331a` / `#330000` | `#0033ff` / `#4c99cc` / `#001aff` | `#1a05e6` / `#ffffff` / `#000000` | `#ffffff` / `#e66605` / `#000d33` |
| 8 | `#080300` / `#808080` / `#ffffff` | `#003300` / `#1a3300` / `#33a600` | `#0033ff` / `#330000` / `#666666` | `#ffffff` / `#0f0899` / `#1a4c66` | `#ffffff` / `#e66605` / `#ff4c00` |
| 9 | `#ffffff` / `#ffffff` / `#ffffff` | `#004c00` / `#33ff00` (bright: 0.2, 1.7, 0) / `#ffb266` | `#0033ff` / `#ff9940` / `#4c264c` | `#ffffff` / `#4c66ff` / `#0f0899` | `#ffffff` / `#e66605` / `#000000` |

## Player level and hero level

Stored on `inventory.armor`:

| Field | Meaning |
|---|---|
| `upgrade_level` | Player level, 0–29 |
| `paragon_level` | Hero level, 0–299 (`paragon_level_cap` = 299) |
| `xp` | Progress within the current level |
| `stats.xp` | Lifetime total, stored as a string |

- **XP to level 30** comes from `player_level_xp.json` (RAWD `0x00f1ffdb`; 125,255,273 in total).
- **Each hero level** costs `2,585,896 × (1 + hero // 10)`.
- **Level-15 boost** characters (`requires_lvl15_entitlement`) start their lifetime counter 3,281,171 lower.
- **The level-up code** is in `Receive_items`, 0x1d7739.
