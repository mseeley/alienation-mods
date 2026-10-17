# Save editor examples

Ready-to-use plans for the save editor (`tools/save-editor-cli.py` and `tools/save-editor-gui.py`). Every file is commented and was checked with `--dry-run` against the sample save in `savegames/CUSA04181_sdimg_savedata` (a level-30 Saboteur). The full format is in [docs/save-editor.md](../../docs/save-editor.md).

## Running one

```bash
# once: install PyYAML
python3 -m venv tools/.venv && tools/.venv/bin/pip install -r tools/requirements.txt

# see the characters and inventory indices
tools/.venv/bin/python tools/save-editor-cli.py show savegames/CUSA04181_sdimg_savedata

# check a plan without writing anything
tools/.venv/bin/python tools/save-editor-cli.py apply savegames/CUSA04181_sdimg_savedata \
    tools/example-recipes/10_max_smg_boomerang.yaml --slot 0 --dry-run

# write the edited save (copy the output folder back to the console)
tools/.venv/bin/python tools/save-editor-cli.py apply savegames/CUSA04181_sdimg_savedata \
    tools/example-recipes/10_max_smg_boomerang.yaml --slot 0 -o edits/max_smg_boomerang/CUSA04181_sdimg_savedata
```

Or open any of them in the desktop editor, which has forms, help on every field and a clickable socket tree:

```bash
tools/.venv/bin/python tools/save-editor-gui.py tools/example-recipes/10_max_smg_boomerang.yaml
```

Several plans can be applied in one go; they run in the order given:

```bash
tools/.venv/bin/python tools/save-editor-cli.py apply SAVE tools/example-recipes/10_max_smg_boomerang.yaml \
    tools/example-recipes/06_profile.yaml --slot 0 -o OUT
```

## The files

| File | Shows | Needs `--allow-untested` |
|---|---|---|
| [`01_weapon_minimal.yaml`](01_weapon_minimal.yaml) | The shortest useful plan: one weapon, everything else defaulted | no |
| [`02_weapon_every_option.yaml`](02_weapon_every_option.yaml) | Every weapon key, explained | no |
| [`03_weapon_rarities.yaml`](03_weapon_rarities.yaml) | One weapon per rarity at the largest tree the game makes | no |
| [`04_equipment.yaml`](04_equipment.yaml) | All five grenade types with sockets and perks | no |
| [`05_armor_sets.yaml`](05_armor_sets.yaml) | Armor sets: colour, glow, metallic and shine per area, effects, equipping | no |
| [`06_profile.yaml`](06_profile.yaml) | Keys, cores, metals, credits, level and hero level | no |
| [`07_reroll_in_place.yaml`](07_reroll_in_place.yaml) | Rebuild a weapon you own without moving it | no |
| [`08_remove_and_replace.yaml`](08_remove_and_replace.yaml) | Swap an equipped weapon and remove the old one | no |
| [`09_full_loadout_saboteur.yaml`](09_full_loadout_saboteur.yaml) | Heavy, primary, secondary and grenade, all equipped | no |
| [`10_max_smg_boomerang.yaml`](10_max_smg_boomerang.yaml) | **The maxed SMG with the boomerang perk**, plus spare level-6 cores | no |
| [`11_armor_colour_test.yaml`](11_armor_colour_test.yaml) | Armor test sets: the four areas in contrasting colours, untested effect values, four effects | yes |
| [`12_untested_experiments.yaml`](12_untested_experiments.yaml) | Cut perks and other things the game never generates | yes |

Files 07 and 08 use inventory indices from the sample save. Run `show` on your own save and adjust the `index:` numbers. The `code:` next to each index makes the editor refuse if it points at the wrong item.

## Cheat sheet

```yaml
rarity:  stock | common | uncommon | rare | legendary    # or 0-4
level:   1-30                                            # as shown in game
damage:  max | mid | min | <number>                      # range the game rolls for that rarity + level
sockets: "<socket> <core><level>"                       # "red power6", "white prismatic6"
         "<socket> <level>"                              # core of the socket's own colour: "red 6"
         "<socket>"                                      # empty socket: "red"
         socket:  blue | red | yellow | white
         core:    boost | power | utility | prismatic
perk (weapons):   {cause: on_enemy_hit, effect: boomerang_at_target, efficiency: 1.0}
perk (equipment): fast_recharge | speed_jolt | double_reserve (or a list)
equip:   true                                            # weapons go to their own slot
replace: {index: 3, code: smg}                           # rebuild item 3 in place
```

Weapon slots (one equipped of each):

| Slot | Codes |
|---|---|
| Heavy | `machine_gun`, `launcher`, `flamethrower`, `sphere_gun` |
| Primary (class-bound) | Saboteur `smg`, Bio-Specialist `xenorifle`, Tank `energy_gun` |
| Secondary | `powershot`, `shotgun`, `revolver`, `laser_gun` |

Perks the game rolls:

| | Values |
|---|---|
| Causes | `on_enemy_hit`, `on_enemy_hit_melee`, `on_player_hit` |
| Effects | `boomerang_at_target`, `chain_lightning_target`, `cluster_shell_from_target`, `knockdown_target` |
