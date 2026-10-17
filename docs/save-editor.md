# Save editor (YAML plans)

The save editor adds, replaces and removes weapons, equipment and armor sets, and sets resources, from small YAML "plans". It has a command line (`tools/save-editor-cli.py`) and a desktop app (`tools/save-editor-gui.py`). It's meant for taking control of the game's loot RNG, not for building characters from scratch. Setup (once):

```bash
python3 -m venv tools/.venv && tools/.venv/bin/pip install -r tools/requirements.txt
```

```bash
tools/.venv/bin/python tools/save-editor-cli.py show  SAVE                        # characters + indexed inventory
tools/.venv/bin/python tools/save-editor-cli.py dump  SAVE --slot 0 -o mine.yaml  # current inventory as a plan
tools/.venv/bin/python tools/save-editor-cli.py check plan.yaml                   # validate a plan without a save
tools/.venv/bin/python tools/save-editor-cli.py apply SAVE plan.yaml [more.yaml ...] --slot 0 -o edits/NAME/CUSA04181_sdimg_savedata
tools/.venv/bin/python tools/save-editor-cli.py apply ... --dry-run               # check only
```

### Desktop editor

```bash
tools/.venv/bin/python tools/save-editor-gui.py [plan.yaml]
```

On macOS you can double-click **`tools/Alienation Savegame Editor.app`** instead. It runs the same script with the venv.
- **Keeping it handy:** drag it to the Dock, or copy it to `/Applications`. It remembers where the project is.
- **Rebuilding:** if the project folder moves, rebuild it with `tools/.venv/bin/python tools/make-save-editor-app.py`.
- **Problems:** errors go to `tools/.cache/save-editor-gui.log`, and a dialog shows them if the editor fails to start.

`save-editor-gui.py` edits a savegame directly. The toolbar has two menus, also in the menu bar:
- **Savegame:** Open, Recent, Save, Save as, Revert, Close.
  - **Open** a savegame folder. Pick a character under **CHARACTER** in the sidebar; its whole inventory is listed to edit in place, grouped as the game limits it: primary, secondary and heavy weapons, equipment and armor sets, each with its count out of 10. ＋ turns off when a weapon or equipment group is full. Armor sets can go past 10: the game keeps them, it just stops giving you new looted sets (a warning). Switching character keeps your edits, and characters with unsaved edits show ● in the dropdown.
  - Edit an item to change it, **Delete** or **Duplicate** it, or use a heading's **＋** for a new one. An equipped item (or the worn armor set) can't be deleted: equip another one first, since its slot can't be left empty. Items are named like **Launcher (L) (30)**: rarity initial (Stock, Common, Uncommon, Rare, Legendary) and level. The dot shows the rarity in the game's colours (stock light grey, common green, uncommon blue, rare purple, legendary orange). Double-click an item (or right-click ▸ Equip / Wear) to equip it; whatever held that slot is unequipped. The mouse wheel only scrolls the page: it never changes a number, dropdown or slider under the pointer. Armor sets show their four colours (plates, suit, visor, accent) as a badge after the name. New and changed items show in orange; equipped ones show a ★ in place of the dot. **Profile** has levels, keys and resources.
  - **Save as** writes every edited character into an edited copy of the savegame, in a folder you choose (e.g. on a USB drive). It goes into a subfolder named like the original save folder (e.g. `CUSA04181_sdimg_savedata`), ready to copy back. **Save** writes to the same folder again. Characters you didn't touch are written back unchanged.
  - **Saving is disabled** while any edited character has errors or refused (untested) values.
  - **Revert** discards the edits to every character; **Edit ▸ Revert this character** just the one shown.
- **Recipe:** reusable sets of items and profile values, in the plan format.
  - **Apply recipe… / Apply example** adds a recipe's items to the current character and sets its profile values. Parts tied to item numbers (`replace:` / `remove:`) can't carry over to another character: replaced items are added as new ones, and deletions are skipped.
  - **Save as recipe…** saves what you tick, as it is now (new and changed things are pre-ticked), without item numbers, so the recipe applies to any character. The list has your items plus a **Profile values** entry. That entry is only the profile values the editor sets: levels, keys, cores, metals, credits and Xenoflowers. The rest of the savegame's profile, such as unlocks and game progress, isn't part of a recipe.
  - Recipes also work with `save-editor-cli.py apply`.

Inside the editor:
- **Forms for everything.** There's a form for each weapon, piece of equipment and armor set, plus the profile. Every field has a **?** button (or press **F1** in it) with its help text.
- **Clickable socket tree.** Synergy links are drawn for you, and sockets beyond what the rarity allows get a dotted pink ring (the untested colour).
- **Live perk maths.** The perk card shows the trigger chance and effect strength as you edit.
- **Tint swatches.** Each tint in the Tint dropdown has a swatch of the three colours the game paints the item with, for the item's current rarity, and the swatches change when you change the rarity. Equipment only shows its tint in the gear menu's preview, not when thrown. The colours are the game's own values (see [weapons-and-cores.md](weapons-and-cores.md#weapon-tints)), but on the item they tint its textures, so dark or worn parts look darker than the swatch.
- **YAML tab** (hidden by default; Settings ▸ General ▸ Show the YAML tab). The current character's working copy, in the plan format, tied to this savegame. Typing there updates the forms, and Savegame ▸ Save writes it. For a portable copy, use Recipe ▸ Save as recipe.
- **Unsaved changes.** The **Changes** tab (Edit ▸ Show unsaved changes, Ctrl+Shift+D) shows what changed for the current character since the savegame was opened or last saved. Changed items are shown in orange in the sidebar. Edit ▸ Undo works per character.
- **Weapons you add** start with **Marked new** ticked, like a fresh pickup.
- **Deleting items.** An item's **Delete** button deletes it from the savegame when it is saved. ⌘Z undoes it, and the Changes tab shows what was deleted.
- **Checks as you type.** They're the same checks as `save-editor-cli.py check`, plus the check against the savegame. They're flagged per entry in the sidebar, and the Checks tab's icon shows the most serious result. The tab lists errors first, then untested values and warnings, and last (greyed) what saving will change for the items you've added or edited. Each message names its item as the sidebar does and follows the sidebar's order; items that share a name are numbered #1, #2, … in both places, and clicking a message opens its item. **Allow untested values** (like `--allow-untested`) is in the **Settings** tab.
- **Settings tab, General.** **Ask to save before quitting or relaunching** is on by default (↻ in the toolbar relaunches the editor, reopening the same savegame and character). **Open the last savegame on launch** is also on by default: the editor starts with the savegame you opened last, at slot 0. If that savegame has been moved or deleted, or can't be read, you get the start page with no error.

The command line and the editor share `tools/lib/saveedit.py`. Validation, field help, perk maths, dumping and writing saves exist once, so the two always agree.

`SAVE` is a save folder (`savedata.dat` + `sce_sys`) or a `savedata.dat` file. The output folder gets the new `savedata.dat` and a copy of `sce_sys`, ready to copy back to the console. Writing over the input save is refused.

## How it stays safe

- **One character at a time.** Choose it with `--slot N`, or `target: {slot: N}` in the plan. A save with a single character is picked automatically. `--slot all` applies the same plan to every character; use it with care, since class matters.
- **Checked against real saves.** Every value and combination is compared with what game-made saves contain (155 weapons, 50 equipment items, 71 armor sets across 13 characters). Anything never seen is **refused** unless you pass `--allow-untested`, which writes it with a warning. Test those one at a time on the console.
- **Hard limits** (always errors): unknown codes; level outside 1–30; core level outside 1–6; more sockets than the upgrade tree holds; more than 10 weapons of one slot type (heavy / primary / secondary) or 10 equipment items per character, which is where the game's pickup refuses; equipping a weapon in the wrong slot type; removing an equipped item without equipping a replacement; any equipped slot left pointing at a missing item.
- **Indices are kept consistent.** Replacing keeps an item's index. Removing shifts later items down and updates the equipped-weapon, equipped-item and equipped-armor pointers. Removals use the indices shown by `show`/`dump`, i.e. before the plan runs.
- **`expect` guards.** `replace: {index: 3, code: smg}` and `remove: {weapons: [{index: 3, code: smg}]}` fail if index 3 isn't an SMG, so a plan can't hit the wrong item after the save has changed.
- **Verified round trip.** `dump` followed by `apply` reproduces each of the 13 characters in the sample saves byte for byte. `selftest` rebuilds all 274 items exactly from their YAML.
- **Classes.** Only the primary weapon is class-bound: Saboteur `smg`, Bio-Specialist `xenorifle`, Tank `energy_gun`. Heavies and secondaries are open to every class. Another class's primary is allowed with a warning. Without the weapon hack add-on, the game swaps it out of the primary slot when the save loads. The editor also warns if a character would be left without its own primary, which the game falls back to.
- **Add-on items.** `sphere_gun`, `laser_gun` and `vortex_grenade` need their add-on (or All Weapons) even with the weapon hack, so the editor warns.

## Plan files

Commented, ready-to-run examples for everything below are in [`tools/example-recipes/`](../tools/example-recipes/README.md).

A plan is a YAML mapping with any of these sections. Use one file per loadout or one file per item; several files can be applied together and are merged in order.

```yaml
target: {slot: 0}        # optional; --slot on the command line wins
weapons:    [...]        # list (or a single mapping) of weapon entries
equipment:  [...]        # grenades, mines, boomerang
armor_sets: [...]        # colour sets with effects
remove:     {weapons: [3], equipment: [1], armor_sets: [5]}
profile:    {...}        # levels, keys, cores, metals, credits, Xenoflowers
```

Every weapon, equipment or armor-set entry can also have:

| Key | Meaning |
|---|---|
| `replace: 3` or `replace: {index: 3, code: smg}` | Rebuild item 3 in place instead of appending. Unset flags (`locked`, `new`, `tint`, bullet colour) are kept from the old item |
| `equip: true` | Equip the item after the plan runs. Weapons go to their own slot type; `equip: heavy` / `primary` / `secondary` also works but must match |
| `locked: true` | Protected from scrapping |
| `new: true` | Shows the "new" marker |
| `tint: 0-9` | The item's colour tint, from 10 per rarity ([colours](weapons-and-cores.md#weapon-tints)). Default: random for new items, kept for replacements. (The save stores it as the last digit of `name_seed`; the rest of that number does nothing, and an unchanged tint keeps the item's own seed.) |

### Weapons

```yaml
weapons:
  - code: smg                 # primary:   xenorifle smg energy_gun (class-bound)
                              # heavy:     machine_gun launcher flamethrower sphere_gun
                              # secondary: powershot shotgun revolver laser_gun
    rarity: legendary         # stock common uncommon rare legendary, or 0-4
    level: 30                 # as shown in game, 1-30
    damage: max               # number, or max / min / mid of what the game rolls for this rarity + level
    stats:                    # each: number, max, min or mid; omitted = max
      fire_rate: max          # laser_gun and sphere_gun have charge_time instead
      clip_size: 1.15
      critical_hit_chance: max
    sockets:
      main:    [blue boost6, red power6, red 6, red, white prismatic6]   # up to 5
      branch1: [blue 6, blue 6, blue 6]          # up to 3; hangs off main socket 1
      branch2: [yellow 6, yellow 6, yellow 6, yellow 6]   # up to 4; hangs off main socket 2
    perk:
      cause: on_enemy_hit     # condition
      effect: boomerang_at_target
      efficiency: 1.0         # 0.5-1.0; effect strength = base x weapon level x efficiency
                              # (boomerang: 100 x 30 x 1.0 = 3,000 HP at level 30)
      value: default          # trigger chance: on_enemy_hit fires 50 x value % of hits (SMG default 1/3
                              # = 16.7%); 2.0 = every hit (untested)
    locked: true
```

**Sockets** are written `"<socket> [<core>]"`:

| Socket | Colour | Core types | Notes |
|---|---|---|---|
| `blue` | Boost | `boost` | Fire rate |
| `red` | Power | `power` | Damage |
| `yellow` | Utility | `utility` | Clip size |
| `white` | Any | `prismatic` | Crit chance; Prismatic counts as every colour |

- `red` is an empty red socket. `red power6` holds a level-6 Power core. `red 6` holds a level-6 core of the socket's own type (white → Prismatic). Any core fits any socket (`red boost3`); matching gives the bonus.
- Synergy links between neighbouring same-colour sockets are computed automatically.
- The perk always sits at the end of branch 1. Game-made weapons only have one once branch 1 holds 3 sockets.

Tree sizes seen in game-made saves (larger is `--allow-untested`):

| Rarity | Main | Branch 1 | Branch 2 | Perk |
|---|---|---|---|---|
| stock, common | 0 | 0 | 0 | no |
| uncommon | 2 | 2 | 0 | no |
| rare | 3 | 3 | 0 | yes |
| legendary | 5 | 3 | 4 | yes |

**Damage and stats come from the game's generator** (`item_levels.json`):
- Every item rolls `base × (1 ± spread/2)`.
- Damage uses one table for every weapon and equipment type. At level 30 the base is 646 / 1,010 / 1,010 / 1,492 / 3,081 for stock … legendary, with a ±12.5% spread. So `max` for a level-30 legendary is 3,466.68.
- Stat ranges:

| Stat | Range |
|---|---|
| `fire_rate`, `charge_time` | 0.875–1.125 |
| `critical_hit_chance` | 0.75–1.25 |
| `clip_size` (most weapons) | 0.875–1.125 |
| `clip_size` (`smg`) | 0.85–1.15 |
| `clip_size` (`shotgun`) | 0.65–1.35 |
| `clip_size` (`revolver`, `powershot`, `launcher`) | 0.625–1.375 |

Numbers outside these ranges are `--allow-untested`. All 205 weapons and equipment items in the sample saves fall inside them.

**Perk causes:** `on_enemy_hit`, `on_enemy_hit_melee` and `on_player_hit` are seen in saves. Untested: `on_enemy_hit_critical`, `enemy_within_range`, `enemies_within_range`, `boss_within_range`, `player_within_range`, `staying_still`, `rush_not_ready`, `low_ammo`.

**Effects:** `boomerang_at_target`, `chain_lightning_target`, `cluster_shell_from_target` and `knockdown_target` are seen. Untested: `bonus_talent_power`, `reduce_damage_taken`, `gain_shield`, `bonus_weapon_fire_rate`, `bonus_weapon_damage`, `bonus_critical_chance`, `bonus_critical_damage`, `gain_ammo_clip`, `poison_target`, `explosion_target`.

### Equipment

```yaml
equipment:
  - code: vortex_grenade      # grenade cluster_grenade vortex_grenade mine boomerang
    rarity: legendary
    level: 30
    damage: max
    sockets: [red 6, red 6, red 6, red 6, red 6]   # main path only; legendary: 5 + perk
    perk: speed_jolt          # fast_recharge | speed_jolt | double_reserve, or a list; legendary only
    equip: true
```

Equipment sockets aren't random: uncommon always has 2, rare 4, legendary 5 + perk. Fewer is allowed with a warning.

**Equipment perks** are flags read by the shared equipment code (`AN.Weapons.Equipment.Super_Grenade`):

| Perk | Effect | Notes |
|---|---|---|
| `fast_recharge` | Doubles the ammo replenish rate | Rolled by the game |
| `speed_jolt` | Movement-speed boost on throw | Rolled by the game |
| `double_reserve` | Doubles how many you can carry (`max_grenades`) | Never rolled; untested |

- A perk only applies if it's in that item type's attribute list (0x130695). Grenade, cluster grenade, mine and boomerang list fast recharge and speed jolt. The vortex grenade lists fast recharge and double reserve, **not** speed jolt, so a vortex's speed jolt (which the game does roll) is most likely ignored. The editor warns about combinations that won't apply.
- `perk: [double_reserve, fast_recharge]` adds a second perk slot. The game evaluates every slot, so both should apply, but no game-made item has two (untested).
- Weapon-style cause/effect perks can't go on equipment. When the game builds an equipped item's info, it collects `perk_id` perks only for weapons (0x1704b8); equipment gets none, and the grenade code has no triggers for them.

### Armor sets

```yaml
armor_sets:
  - rarity: 1                 # 0 = stock (no effects), 1 = looted
    level: 30
    colors:                   # anything left out is kept from the set you're wearing
      plates: '#ff0000'       # a bare colour sets just the colour
      suit:                   # the suit under the plates
        color: '#00ff00'
        glow: 0               # 0-1: lights the area up in its colour
        metallic: 0.7         # 0 none .. 1 full metal
        shine: [0.4, 0.7]     # 0 flat .. 1 mirror; [surface, details]
      visor: {color: '#0000ff', glow: 0.2}
      accent: '#ffffff'       # small details (never glows)
    effects:                  # any number; a mapping or a list of one-key mappings
      movement_speed: 1.05
      max_hp_multiplier: 0.85
    equip: true
```

- **Areas**, in the gear menu's swatch order: `plates`, `suit` (underneath the plates), `visor`, `accent` (small details). The old names `armor` and `base` are refused with a hint.
- **Each area** takes `color` (`"#rrggbb"`), `glow`, `metallic` and `shine`, each 0 to 1 (the editor shows a word under each number). Leave any out to keep the worn set's.
- **glow** (none, faint, medium, strong, full) makes the area give off light in its own colour, as if it were lit from inside. At 0 the area is just painted armor, lit only by the scene; as glow goes up, its colour shines out more, so it stays visible in shadow and in the dark.
  - It's an even fill: the glow covers the whole area at the same strength and ignores the armor's texture. A strong glow turns the area into a flat, bright patch of colour, and the plates and panel lines fade out.
  - Game-made sets barely use it: only the visor ever gets glow, and at most 0.2, which is what makes visors look lit. The accent area never glows; the game ignores its value.
- **metallic** (none, slight, half, mostly, full) is how much the area looks like metal. At 0 it looks painted or plastic, with white highlights on top of the colour; at 1 it looks like bare metal, and reflections take on the area's colour.
- **shine** (flat, sheen, gloss, mirror) is how polished it looks: from dull like rubber, through softer and then sharper highlights, to small sharp highlights and clear reflections. Full metallic with mirror shine looks like chrome.
- **metallic and shine** are one number for an even finish, or `[surface, details]`: two separate settings (not a range), one used on the armor's surface and one on its details. The armor's own texture decides which parts are which. Results above 1 count as 1. How this maps onto the save: `docs/armor.md`.
- **Typical finishes.** The most common values in the 71 game-made sets. In the desktop editor each area's Finish row shows them, and **Use these** sets them.

  | Area | metallic | shine |
  |---|---|---|
  | `plates` | 0.4 (half) | 0.5 (sheen) |
  | `suit` | 0.7 (mostly) | 0.4 surface (sheen), 0.7 details (gloss) |
  | `visor` | 1 (full) | 0 surface (flat), 1 details (mirror) |
  | `accent` | 0.8 (mostly) | 0.5 (sheen) |

- **Effects:** `movement_speed`, `max_hp_multiplier`, `rush_recharge`, `health_drop_rate`, `ability_drop_rate` are multipliers (1 = neutral). `ability_recharge_1/2/3` add seconds to that ability's recharge (negative is better).
  - The game rolls only these values: movement 1.05; max HP 0.85; rush, health drop and ability drop 1.1/1.2 or 0.9/0.8; ability recharge ±1. Other values, more or fewer than two effects, and rarity above 1 are `--allow-untested`.
  - The game applies every effect in the list, and a repeated code keeps its last value.
  - `movement_speed` multiplies running speed (`Behavior_Running`). For comparison, the speed Xenoflower adds 0.3 (`xenoflower_props.flower_boost_movement`, 60 s, scaled by `xenoflower_power_boost`, normally 1), so `movement_speed: 1.3` is the same +30%, permanently (untested). The two multiply: 1.3 × 1.3 ≈ 1.69 with both.

### Remove

```yaml
remove:
  weapons: [3, {index: 5, code: launcher}]
  equipment: [1]
  armor_sets: [4]
```

### Profile

```yaml
profile:
  keys: {ufo: 99, ark: 99}
  cores: {boost6: 100, power6: 100, utility6: 100, prismatic6: 100}   # <type><level 1-6>
  metals: {stock: 999, common: 999, uncommon: 999, rare: 999, legendary: 999}
  credits: 1000000
  flowers: 100                # Xenoflowers collected (save name "flower")
```

```yaml
profile:
  level: 30                   # player level 1-30
  hero_level: 300             # 1-300; needs level 30
```

These cover every resource in game-made saves: credits, `key1`/`key2`, `core<type>_<level>`, `metal0`–`metal4` and `flower`.

Levels are stored directly: `armor.upgrade_level` and `armor.paragon_level`. `armor.xp` is the progress towards the next level; it's kept if it's still below the new level's cost, otherwise reset. The lifetime total `stats.xp` moves by the same amount, so the XP shown in menus stays consistent.

The XP table is the game's own `player_level_xp.json`. A hero level costs `2,585,896 × (1 + hero // 10)`. Level 30 takes 125,255,273 XP; hero 300 takes 12.0 billion more. This was checked exactly against all 13 sample characters.

Trophies and any rewards for the skipped levels don't fire, because they come from level-up events.

## Typical workflows

**Re-roll a weapon you own:**
1. `dump` the character.
2. Keep the weapon's entry and delete the rest.
3. Edit its sockets, stats or perk.
4. Apply. The `replace:` line rewrites it in place.

**Add a loadout:** start from one of the commented plans in [`tools/example-recipes/`](../tools/example-recipes/), e.g. [`10_max_smg_boomerang.yaml`](../tools/example-recipes/10_max_smg_boomerang.yaml), and apply it to any character.

**Clean up:** list unwanted items under `remove:`.

## Armor colour test: results template

Copy this into a message after testing the save built from `tools/example-recipes/11_armor_colour_test.yaml`; the build command is in `docs/armor.md`. On the sample save the test sets are 8–10. Set 8 is equipped: accent = white, plates = red, suit = green, visor = blue. (The colour map was confirmed on 2026-10-12; sets 9 and 10 are still open.)

```yaml
armor_test:
  date: 2026-10-
  class: saboteur            # armor you looked at
  set_8_colours:             # which visible part turned which colour
    white (accent): ""       # e.g. "shoulder bolts"
    red (plates): ""
    green (suit): ""
    blue (visor): ""
    unchanged parts: ""
  set_9_custom_values:       # movement_speed 1.2, max_hp_multiplier 1.25
    loads: yes/no
    menu shows: ""           # the effect text in the armor sets menu
    feels faster / more HP: ""
  set_10_four_effects:       # movement 1.1, rush 1.2, health drop 1.5, ability drop 1.5
    loads: yes/no
    menu shows: ""           # all four, only two, or garbled?
  problems: ""
```
