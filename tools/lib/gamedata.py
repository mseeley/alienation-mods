"""Facts about ALIENATION (CUSA04181, patch 01.07) that the save editor needs to read and write saves:
internal item, perk and stat names, the in-game display names, and number tables read from the game data
or measured across game-made saves.

This is the only game-derived content in the code. It holds no game files or assets, only the values
the editor checks plans against. Where each value comes from is noted next to it; the full findings are
in docs/weapons-and-cores.md and docs/armor.md. No imports: tools/lib/saveedit.py and
tools/lib/savedata.py import from here.
"""


# --- classes, rarity, levels -----------------------------------------------------------------

RARITIES = ['stock', 'common', 'uncommon', 'rare', 'legendary']   # menu__loot__rarity0..4
CLASSES = {'ninja_armor': 'saboteur', 'health_regen': 'bio-specialist', 'shield_armor': 'tank'}
MAX_LEVEL = 30

# --- sockets and cores -----------------------------------------------------------------------

# Socket colours (upgrade 'type') and core types. Any core fits any socket; matching colours
# give the bonus, white sockets accept anything, Prismatic cores count as any colour.
SOCKETS = {'blue': 'core1', 'red': 'core2', 'yellow': 'core3', 'white': 'core'}
SOCKET_NAMES = {v: k for k, v in SOCKETS.items()}
CORES = {'boost': 1, 'power': 2, 'utility': 3, 'prismatic': 4}
CORE_NAMES = {v: k for k, v in CORES.items()}
CORE_TYPES = {1: 'Boost', 2: 'Power', 3: 'Utility', 4: 'Prismatic'}
# Socket colours as drawn in game; 'core' sockets are white (any colour).
SOCKET_COLOURS = {'core1': 'blue', 'core2': 'red', 'core3': 'yellow', 'core': 'white'}

# --- weapons ---------------------------------------------------------------------------------

# Weapons: modifier codes in the order the game writes them, plus the stat ranges seen across 155
# game-made weapons (all rarities/levels). damage_level scales with upgrade_level and rarity.
RATE_FIRE, RATE_CHARGE = 'fire_rate', 'charge_time'
WEAPONS = {
    'energy_gun':   dict(damage='damage_level', order=['damage', 'fire_rate', 'clip_size', 'critical_hit_chance']),
    'flamethrower': dict(damage='damage_level', order=['damage', 'fire_rate', 'clip_size', 'critical_hit_chance']),
    'launcher':     dict(damage='damage_level', order=['damage', 'fire_rate', 'clip_size', 'critical_hit_chance']),
    'machine_gun':  dict(damage='damage_level', order=['damage', 'fire_rate', 'clip_size', 'critical_hit_chance']),
    'powershot':    dict(damage='damage_level', order=['damage', 'fire_rate', 'clip_size', 'critical_hit_chance']),
    'revolver':     dict(damage='damage_level', order=['damage', 'fire_rate', 'clip_size', 'critical_hit_chance']),
    'shotgun':      dict(damage='damage_level', order=['damage', 'fire_rate', 'clip_size', 'critical_hit_chance']),
    'smg':          dict(damage='damage_level', order=['damage', 'fire_rate', 'clip_size', 'critical_hit_chance']),
    'xenorifle':    dict(damage='damage_level', order=['damage', 'fire_rate', 'clip_size', 'critical_hit_chance']),
    'laser_gun':    dict(damage='damage_per_second', order=['damage', 'clip_size', 'critical_hit_chance', 'charge_time']),
    'sphere_gun':   dict(damage='damage_level', order=['damage', 'clip_size', 'critical_hit_chance', 'charge_time']),
}
# Generator (item_levels.json, RAWD 0x00f199d8): value = base * (1 + U(-v/2, +v/2)). Every
# multiplier stat has base 1.0; damage uses DAMAGE_BASE. v per stat, with clip size varying per code.
DAMAGE_SPREAD = 0.25
STAT_SPREAD = {'fire_rate': 0.25, 'charge_time': 0.25, 'critical_hit_chance': 0.5}
CLIP_SPREAD = {'xenorifle': 0.25, 'machine_gun': 0.25, 'flamethrower': 0.25, 'energy_gun': 0.25,
               'laser_gun': 0.25, 'sphere_gun': 0.25, 'smg': 0.3, 'shotgun': 0.7, 'revolver': 0.75,
               'powershot': 0.75, 'launcher': 0.75}
DAMAGE_BASE = [  # M[level 0-29][rarity 0-4], item_levels.json (RAWD 0x00f199d8); same for every code
    [1.0, 1.56, 1.56, 2.31, 4.77],
    [1.25, 1.95, 1.95, 2.89, 5.96],
    [1.56, 2.44, 2.44, 3.61, 7.45],
    [1.95, 3.05, 3.05, 4.51, 9.31],
    [2.44, 3.81, 3.81, 5.64, 11.64],
    [3.05, 4.77, 4.77, 7.05, 14.55],
    [3.81, 5.96, 5.96, 8.81, 18.19],
    [4.77, 7.45, 7.45, 11.01, 22.74],
    [5.96, 9.31, 9.31, 13.76, 28.42],
    [7.45, 11.64, 11.64, 17.2, 35.53],
    [9.31, 14.55, 14.55, 21.5, 44.41],
    [11.64, 18.19, 18.19, 26.88, 55.51],
    [14.55, 22.74, 22.74, 33.6, 69.39],
    [18.19, 28.42, 28.42, 42.0, 86.74],
    [22.74, 35.53, 35.53, 52.5, 108.42],
    [28.42, 44.41, 44.41, 65.62, 135.53],
    [35.53, 55.51, 55.51, 82.03, 169.41],
    [44.41, 69.39, 69.39, 102.54, 211.76],
    [55.51, 86.74, 86.74, 128.17, 264.7],
    [69.39, 108.42, 108.42, 160.21, 330.87],
    [86.74, 135.53, 135.53, 200.27, 413.59],
    [108.42, 169.41, 169.41, 250.34, 516.99],
    [135.53, 211.76, 211.76, 312.92, 646.23],
    [169.41, 264.7, 264.7, 391.15, 807.79],
    [211.76, 330.87, 330.87, 488.94, 1009.74],
    [264.7, 413.59, 413.59, 611.17, 1262.18],
    [330.87, 516.99, 516.99, 763.96, 1577.72],
    [413.59, 646.23, 646.23, 954.95, 1972.15],
    [516.99, 807.79, 807.79, 1193.69, 2465.19],
    [646.23, 1009.74, 1009.74, 1492.12, 3081.49],
]

# --- equipment -------------------------------------------------------------------------------

# Equipment: one damage modifier, sockets on the main path only, attribute perk.
EQUIPMENT = {
    'grenade': 'damage_level', 'cluster_grenade': 'damage_level', 'mine': 'damage_level',
    'boomerang': 'damage_level', 'vortex_grenade': 'damage_per_second',
}
EQUIPMENT_PERKS = {'fast_recharge': 'fast_recharge_perk', 'speed_jolt': 'speed_jolt_perk',
                   'double_reserve': 'double_reserve_perk'}
# The game rolls fast_recharge or speed_jolt. A perk slot only takes effect if its attribute is in
# the item type's attribute list (0x130695): vortex lists double_reserve instead of speed_jolt.
EQUIPMENT_PERKS_ROLLED = {'fast_recharge', 'speed_jolt'}
EQUIPMENT_PERKS_APPLIED = {code: {'fast_recharge', 'speed_jolt'} for code in EQUIPMENT}
EQUIPMENT_PERKS_APPLIED['vortex_grenade'] = {'fast_recharge', 'double_reserve'}

# --- weapon perks ----------------------------------------------------------------------------

# Weapon perks: condition ("cause") -> effect. Only the SEEN ones occur in game-made saves.
CAUSES = ['on_enemy_hit', 'on_enemy_hit_critical', 'on_enemy_hit_melee', 'on_player_hit',
          'enemy_within_range', 'enemies_within_range', 'boss_within_range', 'player_within_range',
          'staying_still', 'rush_not_ready', 'low_ammo']
EFFECTS = ['bonus_talent_power', 'reduce_damage_taken', 'gain_shield', 'bonus_weapon_fire_rate',
           'bonus_weapon_damage', 'bonus_critical_chance', 'bonus_critical_damage',
           'cluster_shell_from_target', 'boomerang_at_target', 'knockdown_target', 'gain_ammo_clip',
           'poison_target', 'explosion_target', 'chain_lightning_target']
CAUSES_SEEN = {'on_enemy_hit', 'on_enemy_hit_melee', 'on_player_hit'}
EFFECTS_SEEN = {'boomerang_at_target', 'chain_lightning_target', 'cluster_shell_from_target', 'knockdown_target'}
# perk_value for on_enemy_hit is a fixed proc chance per weapon type; every other cause uses 1.0.
ON_HIT_CHANCE = {'energy_gun': 0.04, 'flamethrower': 0.05, 'laser_gun': 1.0, 'launcher': 1.25,
                 'machine_gun': 1 / 15, 'powershot': 1.0, 'revolver': 1.0, 'shotgun': 1 / 3, 'smg': 1 / 3,
                 'sphere_gun': 1 / 30, 'xenorifle': 0.1}
EFFICIENCY_RANGE = (0.5, 1.0)
# How a perk condition reads its perk_value (condition table, 0x2978c7): hit chances are % per
# unit of value, ranges metres per unit of value.
PERK_HIT_CHANCE = {'on_enemy_hit': 50, 'on_enemy_hit_critical': 75, 'on_enemy_hit_melee': 100}
PERK_GUARANTEE_AFTER = 3      # s: on_enemy_hit always procs if no perk fired for this long
PERK_PLAYER_HIT_COOLDOWN = 0.3   # s, on_player_hit
PERK_RANGE_METRES = {'enemy_within_range': 5, 'enemies_within_range': 10, 'boss_within_range': 30,
                     'player_within_range': 5}
PERK_LOW_AMMO_PERCENT = 20    # low_ammo: ammo below 20% x value
# Effect strength = base x weapon level x efficiency (0x1c787b).
EFFECT_BASE = {'boomerang_at_target': 100, 'chain_lightning_target': 100, 'knockdown_target': 100,
               'poison_target': 100, 'cluster_shell_from_target': 250, 'explosion_target': 250}
PERK_AMMO_CLIP_PERCENT = 20   # gain_ammo_clip: 20% x efficiency chance

# --- upgrade trees ---------------------------------------------------------------------------

# Upgrade-tree sizes seen per rarity: (main path, branch-1 sockets, branch-2 sockets, perk allowed).
# The perk is the last slot of branch 1 and only appears once branch 1 has its 3 sockets.
WEAPON_TREE = {0: (0, 0, 0, False), 1: (0, 0, 0, False), 2: (2, 2, 0, False), 3: (3, 3, 0, True),
               4: (5, 3, 4, True)}
# Equipment: main path only; rarity 4 ends in the attribute perk after 5 sockets.
EQUIPMENT_TREE = {0: (0, False), 1: (0, False), 2: (2, False), 3: (4, False), 4: (5, True)}

# --- armor sets ------------------------------------------------------------------------------

# Armor sets. colors[0..3] are the armor shader masks user_colormask_non/pri/sec/tri. A console test
# (2026-10-12) showed what each paints: non = accent details, pri = the plates, sec = the suit
# underneath, tri = the visor. The gear menu shows the swatches as plates, suit, visor, accent.
ARMOR_AREAS = ['accent', 'plates', 'suit', 'visor']         # save / shader order (colors[0..3])
ARMOR_AREAS_MENU = ['plates', 'suit', 'visor', 'accent']    # the gear menu's swatch order
# code -> (neutral value, positive direction). Generator values: docs/armor.md.
ARMOR_EFFECTS = {
    'movement_speed': (1.0, +1), 'max_hp_multiplier': (1.0, +1), 'rush_recharge': (1.0, +1),
    'health_drop_rate': (1.0, +1), 'ability_drop_rate': (1.0, +1),
    'ability_recharge_1': (0.0, -1), 'ability_recharge_2': (0.0, -1), 'ability_recharge_3': (0.0, -1),
}
ARMOR_EFFECT_GENERATED = {  # values the game's generator rolls (positive, negative)
    'movement_speed': (1.05, None), 'max_hp_multiplier': (None, 0.85), 'rush_recharge': (1.1, 0.9),
    'health_drop_rate': (1.2, 0.8), 'ability_drop_rate': (1.2, 0.8),
    'ability_recharge_1': (-1.0, 1.0), 'ability_recharge_2': (-1.0, 1.0), 'ability_recharge_3': (-1.0, 1.0),
}
# Material vec4 (x, y, z, w) per area, colors[4..7]. The armor shader works out metallic = clamp(z + x * texture)
# and smoothness (shine) = clamp(w + y * texture); docs/armor.md.
ARMOR_FINISH = {'metallic': (0, 2), 'shine': (1, 3)}       # key -> (factor index, added index)
# The most common settings in 71 game-made sets, as plan values.
ARMOR_FINISH_TYPICAL = {'accent': {'metallic': 0.8, 'shine': 0.5}, 'plates': {'metallic': 0.4, 'shine': 0.5},
                        'suit': {'metallic': 0.7, 'shine': [0.4, 0.7]}, 'visor': {'metallic': 1, 'shine': [0, 1]}}

# --- weapon tints ----------------------------------------------------------------------------

# The tints themselves: WEAPON_COLORS, built by the gameplay script Property_Sets_Menu (start code,
# Stated bytecode 0x34c120-0x34df2e, STAD record 0x124af99) as [rarity][tint] -> 8 vec4s in the armor
# colour-set layout. Only the three painted areas change between tints, so only they are kept here:
# (pri, sec, tri) RGB, 0-1 floats exactly as the script has them (a few go above 1, i.e. brighter than
# white). The rest is the same for every tint: non = (0.5, 0.5, 0.5); alpha = glow, 0 on pri, 0.01-0.1
# on sec/tri; the four finish vec4s vary only for legendary (see docs/weapons-and-cores.md).
# Every weapon's model script paints with it (Super_Gun, Flamethrower, 360_Beam,
# Targeting_Missile_Launcher); equipment uses it only for the Gear menu preview.
WEAPON_TINTS = [
    [  # 0
        ((1, 1, 1), (0.6, 0.3, 0), (1, 1, 1.2)),
        ((1, 1, 1), (0, 0, 0), (1, 1, 1.2)),
        ((1, 1, 1), (0.2, 0.2, 0.2), (1, 1, 1.2)),
        ((1, 1, 1), (0, 0, 0), (1, 1.5, 0)),
        ((0, 0, 0), (1, 1, 1), (0.2, 0.3, 0.5)),
        ((0, 0, 0), (0.2, 0.2, 0.2), (1, 1, 1)),
        ((1, 1, 1), (1, 1, 1), (0.5, 0.4, 0.3)),
        ((1, 1, 1), (0.2, 0.4, 0.1), (0, 0.02, 0.5)),
        ((0.03, 0.01, 0), (0.5, 0.5, 0.5), (1, 1, 1)),
        ((1, 1, 1), (1, 1, 1), (1, 1, 1)),
    ],
    [  # 1
        ((0, 0.2, 0), (1, 1, 1), (0.2, 0.2, 0.2)),
        ((0, 0.2, 0), (0.12, 0.16, 0.04), (0.2, 0.2, 0.2)),
        ((0, 0.2, 0), (0.04, 0.01, 0.01), (1.2, 1.2, 1.2)),
        ((0, 0.2, 0), (0.4, 0.6, 0.3), (0.15, 0.5, 0.5)),
        ((0, 0, 0), (0, 0.2, 0), (0.1, 0.6, 0.05)),
        ((0, 0.2, 0), (0.2, 0.3, 0), (0.8, 0.2, 0.01)),
        ((0, 0.2, 0), (0.01, 0.31, 0.3), (0.5, 0.5, 0.65)),
        ((0, 0.2, 0), (0, 0.2, 0.1), (0.2, 0, 0)),
        ((0, 0.2, 0), (0.1, 0.2, 0), (0.2, 0.65, 0)),
        ((0, 0.3, 0), (0.2, 1.7, 0), (1, 0.7, 0.4)),
    ],
    [  # 2
        ((0, 0.2, 1), (1, 1, 1), (0, 0.1, 1)),
        ((0, 0.2, 1), (0.3, 0.3, 0.3), (1, 1, 1)),
        ((0.5, 0.5, 0.5), (0, 0.2, 1), (0.2, 0.4, 1)),
        ((0.5, 0.5, 0.5), (0, 0.2, 1), (0.2, 0.2, 0.2)),
        ((0, 0.2, 1), (1, 1, 1), (0.6, 0.4, 0.08)),
        ((0, 0, 0), (0, 0.2, 1), (0, 0.1, 1)),
        ((0, 0.2, 1), (0.05, 0, 0), (0.6, 0.6, 0.6)),
        ((0, 0.2, 1), (0.3, 0.6, 0.8), (0, 0.1, 1)),
        ((0, 0.2, 1), (0.2, 0, 0), (0.4, 0.4, 0.4)),
        ((0, 0.2, 1), (1, 0.6, 0.25), (0.3, 0.15, 0.3)),
    ],
    [  # 3
        ((0.15, 0.02, 1), (1, 1, 1), (0.03, 0.01, 0.9)),
        ((0.1, 0.02, 0.9), (0.3, 0.4, 0.4), (0.27, 0.27, 0.29)),
        ((0.1, 0.02, 0.9), (0.5, 0.5, 0.5), (0.75, 0.9, 1)),
        ((0.1, 0.02, 0.9), (0.5, 0.4, 0.2), (0, 0, 0)),
        ((0.1, 0.02, 0.9), (0.3, 0.25, 0.15), (0.6, 0.6, 0.4)),
        ((0.1, 0.02, 0.9), (0.1, 0.01, 0), (0.12, 0.14, 0.16)),
        ((0.1, 0.02, 0.9), (0.65, 0.35, 0.1), (0.5, 0.4, 0.5)),
        ((0.1, 0.02, 0.9), (1, 1, 1), (0, 0, 0)),
        ((1, 1, 1), (0.06, 0.03, 0.6), (0.1, 0.3, 0.4)),
        ((1, 1, 1), (0.3, 0.4, 1), (0.06, 0.03, 0.6)),
    ],
    [  # 4
        ((0.9, 0.4, 0.02), (1, 1, 1), (0.7, 0.2, 0.02)),
        ((0.9, 0.4, 0.02), (1, 1, 1), (0.04, 0, 0.03)),
        ((0.9, 0.4, 0.02), (0.5, 0.3, 0.1), (1, 1, 1)),
        ((0.9, 0.4, 0.02), (0, 0, 0), (0.3, 0.3, 0.3)),
        ((0.9, 0.4, 0.02), (0, 0.1, 0.2), (0.3, 0.3, 0.3)),
        ((0.9, 0.4, 0.02), (0.08, 0.02, 0), (0.5, 0.5, 0.5)),
        ((0.9, 0.4, 0.02), (0.9, 0.4, 0.02), (0.1, 0.02, 0.07)),
        ((1, 1, 1), (0.9, 0.4, 0.02), (0, 0.05, 0.2)),
        ((1, 1, 1), (0.9, 0.4, 0.02), (1, 0.3, 0)),
        ((1, 1, 1), (0.9, 0.4, 0.02), (0, 0, 0)),
    ],
]

# --- inventory -------------------------------------------------------------------------------

KEYS = {'ufo': 'key1', 'ark': 'key2'}
METALS = {'stock': 'metal0', 'common': 'metal1', 'uncommon': 'metal2', 'rare': 'metal3', 'legendary': 'metal4',
          'unobtainium': 'metal5'}
# inventory.active_weapons = [unused, heavy, primary, secondary]. A weapon's slot follows its
# ammo_name (rockets / bullets / fuel cells); the gear menu and pickup code both use it.
WEAPON_SLOTS = {'heavy': 1, 'primary': 2, 'secondary': 3}
WEAPON_CATEGORY = {
    'machine_gun': 'heavy', 'launcher': 'heavy', 'flamethrower': 'heavy', 'sphere_gun': 'heavy',
    'xenorifle': 'primary', 'smg': 'primary', 'energy_gun': 'primary',
    'powershot': 'secondary', 'shotgun': 'secondary', 'revolver': 'secondary', 'laser_gun': 'secondary',
}
# Only the primary is class-bound (armor props illegal_weapons); heavies and secondaries are open
# to every class. The weapon hack add-on lifts the restriction.
CLASS_PRIMARY = {'shield_armor': 'energy_gun', 'ninja_armor': 'smg', 'health_regen': 'xenorifle'}
# Add-on weapons: illegal on load and in loot without their entitlement, even with the weapon hack.
DLC_ITEMS = {'sphere_gun': 'Collapser', 'laser_gun': 'Devastator', 'vortex_grenade': 'Vortex Grenade'}
EQUIPMENT_SLOT = 2          # active_items index for the equipment slot (all five equipment codes)

# Pickup and menu add_item refuse at 10 weapons of the same slot category and at 10 equipment
# items (Weapon_Collectible 0x1efc47, add_item 0x15d731). One real character sits exactly at 10/10/10 + 10.
MAX_PER_CATEGORY = 10
MAX_EQUIPMENT = 10
# AN.Menu.Data adds a looted set only while color_sets has fewer than 10 (0x15d91d). More than 10 is fine
# otherwise: a console-tested save holds 14. So it's a warning, not an error.
MAX_ARMOR_SETS = 10
FLOWER = 'flower'          # Xenoflowers collected ("XENOFLOWERS" on the Resources screen)

# --- player and hero levels ------------------------------------------------------------------

# player_level_xp.json (RAWD 0x00f1ffdb): XP to go from level u-1 to u (u = 0-based level).
LEVEL_XP = [0, 4500, 9682, 18396, 32194, 53120, 82335, 119386, 161172, 217582, 288296, 379109, 494737,
            625842, 794820, 1009421, 1281965, 1628095, 2067681, 2625955, 3308703, 4168966, 5252897,
            6566121, 8207651, 10259564, 12927051, 16288084, 20522986, 25858962]
MAX_HERO = 300          # default_armor_props paragon_level_cap = 299 (0-based)

# --- in-game display names -------------------------------------------------------------------

WEAPON_NAMES = {
    'machine_gun': 'Minigun', 'launcher': 'Launcher', 'flamethrower': 'Flamethrower', 'sphere_gun': 'Collapser',
    'xenorifle': 'Xeno Rifle', 'smg': 'SMG', 'energy_gun': 'Energy gun',
    'powershot': 'Power shot', 'shotgun': 'Plasma shotgun', 'revolver': 'Revolver', 'laser_gun': 'Devastator',
}
PRIMARY_CLASS = {'xenorifle': 'Bio-Specialist', 'smg': 'Saboteur', 'energy_gun': 'Tank'}
EQUIPMENT_NAMES = {'grenade': 'Grenade', 'cluster_grenade': 'Cluster grenade', 'mine': 'Mine',
                   'boomerang': 'Boomerang', 'vortex_grenade': 'Vortex grenade'}
