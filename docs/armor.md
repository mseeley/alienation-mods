# Armor colour sets

The in-game "ARMOR SETS" (gear menu): each set has four colours with matching material settings, plus two effects. Static analysis plus three game-made saves (71 sets), and a console colour/material test (2026-10-12).

## Save layout

Under `slots[N].inventory`:

| Key | Meaning |
|---|---|
| `color_sets` | List of colour-set items, below |
| `active_color_set` | Index of the equipped set |
| `armor.colors` | Copy of the equipped set's 8 colours. Matches in all 13 characters; keep it in sync |
| `suit_paints`, `bullet_colors`, `active_color_set` | Owned paint packs and ammo colours (not covered here) |

### Colour set

| Key | Type | Meaning |
|---|---|---|
| `rarity` | int | 0 = stock set (no perks), 1 = looted set with perks |
| `perks` | list | Normally 2 entries: one positive, one negative. Absent on rarity 0 |
| `colors` | list of 8 vec4 | Below |
| `upgrade_level` | int | 0–29 |
| `lock` | bool | Locked against salvaging (optional) |
| `new` | bool | Not yet viewed (optional) |

### Colours

`AN.Player.Player_Character` (`0x1c5e5a`) applies them to the armor as shader options:

| Index | Shader option | Index | Shader option |
|---|---|---|---|
| 0 | `user_colormask_non` | 4 | `user_colormask_non_mat` |
| 1 | `user_colormask_pri` | 5 | `user_colormask_pri_mat` |
| 2 | `user_colormask_sec` | 6 | `user_colormask_sec_mat` |
| 3 | `user_colormask_tri` | 7 | `user_colormask_tri_mat` |

The armor shaders (`main_fp_glow_colormask_rim`, SHDR records) take a `COLORMASK_SAMPLER` texture that marks the primary / secondary / tertiary areas of each armor; `non` covers the unmasked rest. Each area gets an RGBA colour (indices 0–3; alpha is 0 except index 3, up to 0.2) and a material vec4 (indices 4–7; shader also has `METALLIC_INTENSITY`). The data doesn't name the parts, and neither does the colour-customisation menu ("ARMOR ELEMENTS"). A console test on the Saboteur armor (2026-10-12, set with four contrasting colours) showed:

| Index | Mask | Paints | Save editor name |
|---|---|---|---|
| 1 | `pri` | The armor plates (chest centre, knees, forearm plates) | `plates` |
| 2 | `sec` | The suit under the plates (most of the body, helmet shell, shoulder fins) | `suit` |
| 3 | `tri` | The visor | `visor` |
| 0 | `non` | Small accent details (shoulder bolts, trim lines) | `accent` |

The gear menu's four swatches per set are in that order: pri, sec, tri, non. The save editor calls them plates, suit, visor and accent.

**Materials (decoded).** The armor pixel shader (`main_fp_glow_colormask_rim`, SHDR record `0x000fe8b6` at code 0x1264; same in `0x007abca3` and the menu variant) was disassembled with `tools/research/gcn_disasm.py`. Its parameter table puts `USER_COLOR`, `USER_COLOR_RIM`, then the four colours and four materials (pri, sec, tri, non) in one constant buffer at 0x00-0x9c, and the material buffer holds `METALLIC_INTENSITY` and `SMOOTHNESS_INTENSITY`. Per pixel:

- The armor texture gives a metallic value (lerp of `DEFAULT_MATERIAL.y` and MATERIALMAP.y by `METALLIC_INTENSITY`) and a smoothness value (`DEFAULT_MATERIAL.z` and MATERIALMAP.x by `SMOOTHNESS_INTENSITY`).
- Each area's material `(x, y, z, w)` turns those into **metallic = clamp(z + x × texture metallic)** and **smoothness = clamp(w + y × texture smoothness)**. The colour mask texture blends the four areas (accent first, then plates, suit, visor on top).
- They're written to the G-buffer material target (green = metallic, blue = smoothness; red is 1, alpha is `DEFAULT_MATERIAL.w`).
- In plain terms, metallic is bare metal (1, reflections take the colour) versus paint/plastic (0), and smoothness is gloss: 1 polished with sharp highlights, 0 matte.
- **Plan format.** Each area is written as `color` (RGB), `glow` (the colour's alpha), `metallic` and `shine` (smoothness). metallic is `z` alone when `x` = 0 (even), else `[z, z + x]`: the value where the design map is 0 (surface) and where it is 1 (details). shine is the same with `w` and `y`. The editor labels the scales with words (metallic: none < 0.1, slight < 0.4, half < 0.7, mostly < 0.95, full; shine: flat < 0.25, sheen < 0.55, gloss < 0.85, mirror). The pair's difference is taken in decimal, so game-made values round-trip exactly (`[0.4, 0.7]` gives x = 0.3).
- Colour: albedo = texture × area colour. The colour's alpha is a glow strength: the emissive target (mrt4) gets pri.rgb × pri.a × mask.pri + sec.rgb × sec.a × mask.sec + tri.rgb × tri.a × mask.tri (plates, suit, visor; accent/`non` isn't included, so its alpha is unused). No texture multiplies it, so the glow is an even fill of the area's colour that ignores the armor's detail and the scene lighting. The same target also gets the rim light (`USER_COLOR_RIM`) and the armor's own glow texture tinted by `USER_COLOR`; neither is in the save. Game-made sets only give the visor alpha (up to 0.2). Confirmed in the gear menu on 2026-10-12 with a glow test recipe, since removed (five sets differing only in glow: red plates, green suit, blue visor, flat non-metallic finish): 0.2 is barely brighter than 0; 0.5 is clearly brighter and more saturated with the panel lines still visible; 1 turns the area into a flat, even, neon patch with the shading and panel lines mostly gone and a soft halo at the edges; a set with glowing plates and a non-glowing suit shows a sharp boundary, so glow is per area. Not yet checked: how glowing areas look in dark levels, and the visor (dark blue glows weakly). The editor labels glow none < 0.01, faint < 0.35, medium < 0.7, strong < 0.95, full.

That matches the console test (base area, one number at 1, the rest 0): x = 1 is the texture's metallic with no smoothness (looked matte), y = 1 the texture's smoothness on a non-metal (soft highlights), z = 1 fully metallic but rough (saturated, tinted look), w = 1 a fully smooth non-metal (hard, sharp highlights); all four at 1 is smooth metal (chrome). Values are clamped after the maths, so numbers outside 0-1 only matter in combination (e.g. z = -0.5 with x = 2 stretches the texture's contrast); game-made sets stay within 0-1.

Ranges in game-made sets: colours 0–3 RGB 0–1; index 5 always has x = 0; index 7 is always `(0, 1, 0.5–1, 0)`.

## Perks (effects)

Generator table `color_perks_props` (`Property_Sets`, `0x58e506`):

| Positive | Value | Negative | Value |
|---|---|---|---|
| `movement_speed` | 1.05 | `max_hp_multiplier` | 0.85 |
| `rush_recharge` | 1.1 | `rush_recharge` | 0.9 |
| `health_drop_rate` | 1.2 | `health_drop_rate` | 0.8 |
| `ability_drop_rate` | 1.2 | `ability_drop_rate` | 0.8 |
| `ability_recharge_1/2/3` | −1 | `ability_recharge_1/2/3` | +1 |

Each saved perk is `{is_positive, localization_hint ('mult' or 'ability'), code, value}`. Localization also has `max_hp_multiplier_positive` and `movement_speed_negative`, which the generator never rolls.

### How the game applies them

At player setup (`0x1b66df`) the player builds `_color_perks` with neutral values (`movement_speed`, `rush_recharge`, `health_drop_rate`, `ability_drop_rate`, `max_hp_multiplier` = 1; `ability_recharge_1..3` = 0), then runs `_color_perks[perk.code] = perk.value` for **every** perk in the active set (`0x1b676b`). Consequences:

- Values are read straight from the save, so custom strengths work in principle.
- The number of perks isn't fixed at two; a repeated code keeps the last value. `is_positive` and `localization_hint` only affect the menu.
- Uses: `movement_speed` multiplies movement speed (`0x1dbb08`), `rush_recharge` multiplies rush recharge (`0x1ce93f`), `max_hp_multiplier` scales max HP (`0x1b8bc0`). `ability_recharge_N` is added to ability slot N's recharge time in seconds: charge rate = dt / (recharge time + value), clamped to 0–1 (`0x1c2979`). Avoid values that make the divisor zero or negative.

## Test save

`tools/example-recipes/11_armor_colour_test.yaml` appends three sets. On the sample save, which has 8 sets, they become sets 8–10. Build it with:

```bash
tools/.venv/bin/python tools/save-editor-cli.py apply savegames/CUSA04181_sdimg_savedata tools/example-recipes/11_armor_colour_test.yaml --slot 0 --allow-untested -o edits/armor_test/CUSA04181_sdimg_savedata
```

The sets:

| Set | Colours | Perks | Tests |
|---|---|---|---|
| 8 (equipped) | accent white, armor red, base green, visor blue (current materials) | standard pair | Which armor part each slot paints (done 2026-10-12, see above) |
| 9 | current | `movement_speed` 1.2, `max_hp_multiplier` 1.25 (both positive) | Custom values, two positives |
| 10 | current | `movement_speed` 1.1, `rush_recharge` 1.2, `health_drop_rate` 1.5, `ability_drop_rate` 1.5 | More than two perks |
