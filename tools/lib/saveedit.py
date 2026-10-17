"""Shared core of the Alienation save editor: game data, YAML plan parsing and validation, item
builders, and a SaveSession that checks, applies and writes plans. Used by both front ends:

  tools/save-editor-cli.py   command line
  tools/save-editor-gui.py   desktop editor for plan files

Nothing here prints or exits: problems are raised as PlanError / SaveEditError, or collected in a
Report. Plan format: docs/save-editor.md.

Everything a plan asks for is checked against what game-made saves contain (docs/weapons-and-cores.md,
docs/armor.md). Combinations never seen in a real save are refused unless allow_untested is set;
anything that is merely unusual (e.g. a weapon outside the character's class) is a warning.
"""
import copy
import glob
import os
from decimal import Decimal
import random
import re
import shutil
from collections import OrderedDict

import yaml

from .gamedata import (  # all game-derived data; re-exported so callers can use saveedit.X
    ARMOR_AREAS, ARMOR_AREAS_MENU, ARMOR_EFFECTS, ARMOR_EFFECT_GENERATED, ARMOR_FINISH, ARMOR_FINISH_TYPICAL,
    CAUSES, CAUSES_SEEN, CLASSES, CLASS_PRIMARY, CLIP_SPREAD, CORES, CORE_NAMES, CORE_TYPES, DAMAGE_BASE,
    DAMAGE_SPREAD, DLC_ITEMS, EFFECTS, EFFECTS_SEEN, EFFECT_BASE, EFFICIENCY_RANGE, EQUIPMENT,
    EQUIPMENT_NAMES, EQUIPMENT_PERKS, EQUIPMENT_PERKS_APPLIED, EQUIPMENT_PERKS_ROLLED, EQUIPMENT_SLOT,
    EQUIPMENT_TREE, FLOWER, KEYS, LEVEL_XP, MAX_ARMOR_SETS, MAX_EQUIPMENT, MAX_HERO, MAX_LEVEL,
    MAX_PER_CATEGORY, METALS, ON_HIT_CHANCE, PERK_AMMO_CLIP_PERCENT, PERK_GUARANTEE_AFTER, PERK_HIT_CHANCE,
    PERK_LOW_AMMO_PERCENT, PERK_PLAYER_HIT_COOLDOWN, PERK_RANGE_METRES, PRIMARY_CLASS, RARITIES, RATE_CHARGE,
    RATE_FIRE, SOCKETS,
    SOCKET_COLOURS, SOCKET_NAMES, STAT_SPREAD, WEAPONS, WEAPON_CATEGORY, WEAPON_NAMES, WEAPON_SLOTS,
    WEAPON_TINTS, WEAPON_TREE,
)
from .savedata import ROOT, SaveFile, Table, Tuple, Vec, write_output

# --- editor data (game data is in gamedata.py) ---------------------------------------------

CORE_ALIASES = {'blue': 1, 'red': 2, 'yellow': 3, 'white': 4}
SOCKET_DEFAULT_CORE = {'core1': 1, 'core2': 2, 'core3': 3, 'core': 4}


def stat_range(code, stat):
    v = CLIP_SPREAD[code] if stat == 'clip_size' else STAT_SPREAD[stat]
    return 1 - v / 2, 1 + v / 2


def weapon_stats(code):
    return [k for k in WEAPONS[code]['order'] if k != 'damage']


def damage_range(rarity, level0):
    m = DAMAGE_BASE[level0][rarity]
    return m * (1 - DAMAGE_SPREAD / 2), m * (1 + DAMAGE_SPREAD / 2)


OLD_ARMOR_AREAS = {'armor': 'plates', 'base': 'suit'}

# Each area's settings in a plan. The save stores colour + glow as one RGBA vec4 and metallic + shine
# as a material vec4 (x, y, z, w). The armor shader (docs/armor.md) works out
#   metallic = clamp(z + x * design map)    smoothness (shine) = clamp(w + y * design map)
# where the design map is the armor model's own 0-1 metallic / smoothness texture. Plans write each
# one as a number (x or y = 0: even all over) or [surface, details] = [z, z + x].
ARMOR_AREA_KEYS = ('color', 'glow', 'metallic', 'shine')
# Words for the 0-1 armor scales, as (below this value, word).
ARMOR_SCALE_WORDS = {'glow': ((0.01, 'none'), (0.35, 'faint'), (0.7, 'medium'), (0.95, 'strong'), (9, 'full')),
                     'metallic': ((0.1, 'none'), (0.4, 'slight'), (0.7, 'half'), (0.95, 'mostly'), (9, 'full')),
                     'shine': ((0.25, 'flat'), (0.55, 'sheen'), (0.85, 'gloss'), (9, 'mirror'))}
OLD_ARMOR_KEYS = {'material': 'metallic and shine', 'metal': 'metallic', 'gloss': 'shine'}


def scale_word(key, value):
    """The word for a glow / metallic / shine value, e.g. scale_word('shine', 0.6) == 'gloss'."""
    return next(word for top, word in ARMOR_SCALE_WORDS[key] if value < top)


class SaveEditError(Exception):
    """A problem with the save or the request (missing file, empty slot, ...)."""


class PlanError(SaveEditError):
    """A problem with a plan file."""


class Report:
    """Collects errors, untested-combination findings and warnings while a plan is applied."""

    def __init__(self, allow_untested):
        self.allow_untested = allow_untested
        self.errors, self.untested, self.warnings, self.notes = [], [], [], []

    def error(self, msg):
        self.errors.append(msg)

    def untested_(self, msg):
        (self.warnings if self.allow_untested else self.untested).append(f'untested: {msg}')

    def warn(self, msg):
        self.warnings.append(msg)

    def note(self, msg):
        self.notes.append(msg)

    def failed(self):
        return bool(self.errors or self.untested)

    def messages(self):
        """(level, text) pairs, least severe first; level is note / warning / untested / error."""
        return ([('note', m) for m in self.notes] + [('warning', m) for m in self.warnings] +
                [('untested', m) for m in self.untested] + [('error', m) for m in self.errors])

    def worst(self):
        for level in ('error', 'untested', 'warning', 'note'):
            if any(lv == level for lv, _ in self.messages()):
                return level
        return None

    def lines(self):
        out = []
        for level, m in self.messages():
            out.append({'note': f'{m}', 'warning': f'warning: {m}', 'error': f'error: {m}',
                        'untested': f'refused ({m}); pass --allow-untested to write it anyway'}[level])
        return out


# --- small parsers ---------------------------------------------------------------------------

def parse_rarity(v, where):
    if isinstance(v, int) and 0 <= v <= 4:
        return v
    if isinstance(v, str) and v.lower() in RARITIES:
        return RARITIES.index(v.lower())
    raise PlanError(f'{where}: rarity must be 0-4 or one of {", ".join(RARITIES)} (got {v!r})')


def parse_level(v, where):
    if not isinstance(v, int) or not 1 <= v <= MAX_LEVEL:
        raise PlanError(f'{where}: level must be 1-{MAX_LEVEL} as shown in game (got {v!r})')
    return v - 1          # stored 0-based


def parse_core(text, socket_type, where):
    """'power6' / 'power 6' / 'red6' / '6' (matching the socket) -> (type 1-4, level 1-6)."""
    m = re.fullmatch(r'\s*([a-z]*)\s*(\d+)\s*', text.lower())
    if not m:
        raise PlanError(f'{where}: cannot read core {text!r}; use e.g. "power6" or "6"')
    name, level = m.group(1), int(m.group(2))
    if name in CORES:
        t = CORES[name]
    elif name in CORE_ALIASES:
        t = CORE_ALIASES[name]
    elif name == '':
        t = SOCKET_DEFAULT_CORE[socket_type]
    else:
        raise PlanError(f'{where}: unknown core type {name!r}; use {", ".join(CORES)}')
    if not 1 <= level <= 6:
        raise PlanError(f'{where}: core level must be 1-6 (got {level})')
    return t, level


def parse_socket(spec, where):
    """'red' | 'red power6' | 'red 6' | {socket: red, core: power, level: 6} -> (type, core or None)."""
    if isinstance(spec, dict):
        colour = str(spec.get('socket', '')).lower()
        core = spec.get('core')
        if core is not None and spec.get('level') is not None:
            core = f'{core}{spec["level"]}'
        elif spec.get('level') is not None:
            core = str(spec['level'])
    elif isinstance(spec, str):
        parts = spec.strip().split(None, 1)
        colour = parts[0].lower() if parts else ''
        core = parts[1] if len(parts) > 1 else None
    else:
        raise PlanError(f'{where}: socket must be a string like "red power6" (got {spec!r})')
    stype = SOCKETS.get(colour) or (colour if colour in SOCKET_NAMES else None)
    if stype is None:
        raise PlanError(f'{where}: unknown socket colour {colour!r}; use {", ".join(SOCKETS)}')
    return stype, (parse_core(str(core), stype, where) if core is not None else None)


def socket_text(u):
    s = SOCKET_NAMES.get(u['type'], u['type'])
    core = u.get('core')
    if core is None:
        return s
    t = int(core[0][4:])
    return f'{s} {CORE_NAMES[t]}{core[1] + 1}'


def f32(x):
    """Round-trip through float32 so dumped values print as the game stores them."""
    import struct
    return struct.unpack('<f', struct.pack('<f', float(x)))[0]


def nice(x):
    """Shortest decimal that rounds to the same float32 as x (1.100000023841858 -> 1.1)."""
    x = f32(x)
    for p in range(1, 18):
        y = float(f'{x:.{p}g}')
        if f32(y) == x:
            return y
    return x


def same32(a, b):
    return f32(a) == f32(b)


def new_seed():
    return random.randint(-2**31, 2**31 - 1)


def tint_of(seed):
    """The tint (0-9) a save's name_seed gives: the game uses WEAPON_COLORS[min(rarity, 4)][abs(seed % 10)]
    (gameplay script AN.Weapons.Super_Gun, Stated bytecode 0x0b6a12), with C's truncating %, which is
    abs(seed) % 10."""
    return abs(seed) % 10


def tint_hex(rarity, tint):
    """The three '#rrggbb' colours of a tint (values above 1 shown as full brightness)."""
    return ['#' + ''.join(f'{round(min(max(c, 0), 1) * 255):02x}' for c in rgb)
            for rgb in WEAPON_TINTS[min(max(rarity, 0), 4)][tint]]


def make_table(pairs):
    t = Table()
    for k, v in pairs:
        if v is not None:
            t[k] = v
    return t


# --- upgrade trees ---------------------------------------------------------------------------

def link_synergy(slots):
    """slots: list of dicts {type, parent} in final order; sets 'syn' to a set of 'prev'/'next'."""
    for s in slots:
        s['syn'] = set()
    for j, s in enumerate(slots):
        p = s['parent']
        if p is None or s['type'] == 'perk' or slots[p]['type'] == 'perk':
            continue
        if s['type'] == slots[p]['type'] and s['type'] in ('core1', 'core2', 'core3'):
            slots[p]['syn'].add('next')
            s['syn'].add('prev')


def synergy_table(syn):
    if not syn:
        return None
    t = Table()
    if 'prev' in syn:
        t['prev'] = True
    if 'next' in syn:
        t['next'] = True
    return t


def build_weapon_upgrades(main, b1, perk, b2):
    """main/b1/b2: lists of (socket type, core or None); perk: Table or None. Canonical order:
    main path, branch 1, perk (end of branch 1), branch 2 -- the order of every 13-slot weapon."""
    slots = []
    for i, (t, c) in enumerate(main):
        slots.append(dict(type=t, core=c, branch=0, root=(1 if i == 0 else 2 if i == 1 else None),
                          parent=(i - 1 if i else None)))
    for b, items in ((1, b1), (2, b2)):
        root_idx = 0 if b == 1 else 1
        prev = root_idx
        for t, c in items:
            slots.append(dict(type=t, core=c, branch=b, root=None, parent=prev))
            prev = len(slots) - 1
        if b == 1 and perk is not None:
            slots.append(dict(type='perk', core=None, branch=1, root=None, parent=prev, perk=perk))
    link_synergy(slots)
    out = []
    for s in slots:
        if s['type'] == 'perk':
            p = s['perk']
            out.append(make_table([('type', 'perk'), ('effect_id', p['effect_id']), ('perk_id', p['perk_id']),
                                   ('perk_value', p['perk_value']), ('branch', 1),
                                   ('effect_efficiency', p['effect_efficiency'])]))
            continue
        core = Tuple([f'core{s["core"][0]}', s['core'][1] - 1]) if s['core'] else None
        out.append(make_table([('type', s['type']), ('branch_root', s['root']),
                               ('synergy', synergy_table(s['syn'])), ('core', core),
                               ('branch', s['branch'] or None)]))
    return out


def build_equipment_upgrades(main, perk_attrs):
    slots = [dict(type=t, core=c, parent=(i - 1 if i else None)) for i, (t, c) in enumerate(main)]
    link_synergy(slots)
    out = []
    for s in slots:
        core = Tuple([f'core{s["core"][0]}', s['core'][1] - 1]) if s['core'] else None
        out.append(make_table([('type', s['type']), ('synergy', synergy_table(s['syn'])), ('core', core)]))
    for a in perk_attrs:
        out.append(make_table([('attribute', a), ('type', 'perk'), ('value', True)]))
    return out


def split_tree(ups):
    """Existing upgrades -> (main, branch1, perk, branch2) in tree order, or raise if irregular."""
    main, b1, b2, perks = [], [], [], []
    for u in ups or []:
        if u['type'] == 'perk':
            perks.append(u)
        elif u.get('branch') == 1:
            b1.append(u)
        elif u.get('branch') == 2:
            b2.append(u)
        else:
            main.append(u)
    return main, b1, (perks[0] if perks else None), b2, len(perks)


# --- item builders -----------------------------------------------------------------------------

def pick(v, lo, hi, what, where, rep):
    """number | max | min | mid -> float32 value, flagging numbers outside the game's roll range."""
    if v is None or v == 'max':
        return f32(hi)
    if v == 'min':
        return f32(lo)
    if v in ('mid', 'average'):
        return f32((lo + hi) / 2)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise PlanError(f'{where}: {what} must be a number or max/min/mid (got {v!r})')
    if not f32(lo) - 1e-6 <= v <= f32(hi) + 1e-6:
        rep.untested_(f'{where}: {what} {v:g} is outside what the game rolls ({lo:g}-{hi:g})')
    return f32(v)


def stat_value(v, code, stat, where, rep):
    lo, hi = stat_range(code, stat)
    return pick(v, lo, hi, stat, where, rep)


def damage_value(v, where, rep, level0, rarity):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v <= 0:
        raise PlanError(f'{where}: damage must be positive')
    lo, hi = damage_range(rarity, level0)
    return pick(v, lo, hi, f'damage at {RARITIES[rarity]} level {level0 + 1}', where, rep)


def parse_flags(spec, base):
    """lock/new/tint/bullet_color: plan value, else the replaced item's, else defaults.
    The tint is stored as the last digit of the save's name_seed (tint_of); the rest of the seed does nothing,
    so a replaced item keeps its own seed whenever the tint is unchanged."""
    lock = spec.get('locked', base.get('lock') if base is not None else None)
    new = spec.get('new', base.get('new') if base is not None else None)
    if 'tint_seed' in spec:
        raise PlanError('tint_seed was replaced by tint (0-9); a seed only ever picked the tint')
    tint = spec.get('tint')
    if tint is not None and (not isinstance(tint, int) or isinstance(tint, bool) or not 0 <= tint <= 9):
        raise PlanError(f'tint must be 0-9 (got {tint!r})')
    if base is not None and (tint is None or tint_of(base['name_seed']) == tint):
        seed = base['name_seed']
    elif tint is not None:
        seed = random.randrange(0, 2**31 - 10, 10) + tint
    else:
        seed = new_seed()
    bullet = base.get('bullet_color') if base is not None else None
    return (True if lock else None), (True if new else None), seed, bullet


def build_weapon(spec, where, rep, base=None):
    code = spec.get('code')
    if code not in WEAPONS:
        raise PlanError(f'{where}: unknown weapon code {code!r}; known: {", ".join(sorted(WEAPONS))}')
    rarity = parse_rarity(spec.get('rarity', 'legendary'), where)
    level0 = parse_level(spec.get('level', MAX_LEVEL), where)
    w = WEAPONS[code]

    stats = spec.get('stats') or {}
    unknown = set(stats) - set(weapon_stats(code))
    if unknown:
        raise PlanError(f'{where}: {code} has no stat(s) {", ".join(sorted(unknown))}; '
                        f'it has {", ".join(weapon_stats(code))}')
    values = {'damage': damage_value(spec.get('damage'), where, rep, level0, rarity)}
    for stat in weapon_stats(code):
        values[stat] = stat_value(stats.get(stat), code, stat, where, rep)
    mods = [make_table([('multiplier', values[k]), ('code', w['damage'] if k == 'damage' else k)])
            for k in w['order']]

    sockets = spec.get('sockets') or {}
    if isinstance(sockets, list):
        sockets = {'main': sockets}
    extra = set(sockets) - {'main', 'branch1', 'branch2'}
    if extra:
        raise PlanError(f'{where}: sockets has unknown group(s) {", ".join(sorted(extra))}; '
                        f'use main, branch1, branch2')
    main = [parse_socket(s, f'{where} main[{i}]') for i, s in enumerate(sockets.get('main') or [])]
    b1 = [parse_socket(s, f'{where} branch1[{i}]') for i, s in enumerate(sockets.get('branch1') or [])]
    b2 = [parse_socket(s, f'{where} branch2[{i}]') for i, s in enumerate(sockets.get('branch2') or [])]
    if (b1 or b2) and not main:
        raise PlanError(f'{where}: branches hang off the main path; add main sockets first')
    if b2 and len(main) < 2:
        raise PlanError(f'{where}: branch2 hangs off main socket 2; give at least 2 main sockets')
    if len(main) > 5 or len(b1) > 3 or len(b2) > 4:
        raise PlanError(f'{where}: the upgrade tree holds at most 5 main, 3 branch1 and 4 branch2 sockets')

    perk = None
    p = spec.get('perk')
    if p:
        cause, effect = p.get('cause'), p.get('effect')
        if cause not in CAUSES:
            raise PlanError(f'{where}: unknown perk cause {cause!r}; known: {", ".join(CAUSES)}')
        if effect not in EFFECTS:
            raise PlanError(f'{where}: unknown perk effect {effect!r}; known: {", ".join(EFFECTS)}')
        if cause not in CAUSES_SEEN:
            rep.untested_(f'{where}: perk cause {cause} never appears in a game-made save')
        if effect not in EFFECTS_SEEN:
            rep.untested_(f'{where}: perk effect {effect} never appears in a game-made save')
        eff = p.get('efficiency', 1.0)
        if not isinstance(eff, (int, float)):
            raise PlanError(f'{where}: perk efficiency must be a number')
        if not EFFICIENCY_RANGE[0] <= eff <= EFFICIENCY_RANGE[1]:
            rep.untested_(f'{where}: perk efficiency {eff} outside the 0.5-1.0 the game rolls')
        default_value = ON_HIT_CHANCE[code] if cause == 'on_enemy_hit' else 1.0
        value = p.get('value', 'default')
        if value == 'default':
            value = default_value
        elif not isinstance(value, (int, float)):
            raise PlanError(f'{where}: perk value must be a number or "default"')
        elif not same32(value, default_value):
            rep.untested_(f'{where}: perk value {value} differs from the game\'s fixed {default_value:g} '
                          f'for {cause} on {code}')
        perk = dict(perk_id=cause, effect_id=effect, perk_value=f32(value), effect_efficiency=f32(eff))
        if len(b1) != 3:
            rep.untested_(f'{where}: the perk sits after 3 branch1 sockets in every game-made weapon '
                          f'(this one has {len(b1)})')

    tmain, tb1, tb2, tperk = WEAPON_TREE[rarity]
    if len(main) > tmain or len(b1) > tb1 or len(b2) > tb2 or (perk and not tperk):
        rep.untested_(f'{where}: {RARITIES[rarity]} weapons have at most {tmain} main / {tb1} branch1 / '
                      f'{tb2} branch2 sockets{" and a perk" if tperk else " and no perk"} in game-made saves')

    lock, new, seed, bullet = parse_flags(spec, base)
    item = make_table([('name_seed', seed), ('rarity', rarity),
                       ('upgrades', build_weapon_upgrades(main, b1, perk, b2)), ('code', code),
                       ('lock', lock), ('new', new), ('modifiers', mods), ('bullet_color', bullet),
                       ('upgrade_level', level0)])
    return item


def build_equipment(spec, where, rep, base=None):
    code = spec.get('code')
    if code not in EQUIPMENT:
        raise PlanError(f'{where}: unknown equipment code {code!r}; known: {", ".join(sorted(EQUIPMENT))}')
    rarity = parse_rarity(spec.get('rarity', 'legendary'), where)
    level0 = parse_level(spec.get('level', MAX_LEVEL), where)
    damage = damage_value(spec.get('damage'), where, rep, level0, rarity)
    sockets = spec.get('sockets') or []
    if isinstance(sockets, dict):
        if set(sockets) - {'main'}:
            raise PlanError(f'{where}: equipment only has main sockets')
        sockets = sockets.get('main') or []
    main = [parse_socket(s, f'{where} sockets[{i}]') for i, s in enumerate(sockets)]
    if len(main) > 6:
        raise PlanError(f'{where}: equipment holds at most 6 sockets')
    perks = spec.get('perk') or []
    if isinstance(perks, str):
        perks = [perks]
    attrs = []
    for perk in perks:
        if perk not in EQUIPMENT_PERKS:
            raise PlanError(f'{where}: equipment perk must be one of {", ".join(EQUIPMENT_PERKS)}')
        if perk not in EQUIPMENT_PERKS_ROLLED:
            rep.untested_(f'{where}: {perk} is never rolled (cut); the equipment code supports it')
        if perk not in EQUIPMENT_PERKS_APPLIED[code]:
            rep.warn(f'{where}: {code} does not list {perk}_perk among its attributes, so the game '
                     f'most likely ignores it (supported: {", ".join(sorted(EQUIPMENT_PERKS_APPLIED[code]))})')
        attrs.append(EQUIPMENT_PERKS[perk])
    if len(attrs) > 1:
        rep.untested_(f'{where}: game-made equipment has one perk slot (this one has {len(attrs)})')
    attr = attrs[0] if attrs else None
    tsock, tperk = EQUIPMENT_TREE[rarity]
    if len(main) > tsock or (attr and not tperk):
        rep.untested_(f'{where}: {RARITIES[rarity]} equipment has at most {tsock} sockets'
                      f'{" and a perk" if tperk else " and no perk"} in game-made saves')
    if attr and len(main) != 5:
        rep.untested_(f'{where}: the equipment perk follows 5 sockets in every game-made item')
    elif len(main) < tsock:
        rep.warn(f'{where}: game-made {RARITIES[rarity]} equipment always has {tsock} sockets (this one has {len(main)})')
    lock, new, seed, bullet = parse_flags(spec, base)
    mod = make_table([('multiplier', damage), ('code', EQUIPMENT[code])])
    return make_table([('name_seed', seed), ('rarity', rarity),
                       ('upgrades', build_equipment_upgrades(main, attrs)), ('code', code),
                       ('lock', lock), ('new', new), ('modifiers', [mod]), ('bullet_color', bullet),
                       ('upgrade_level', level0)])


def parse_colour(v, where):
    """'#rrggbb' / '#rrggbbaa' / [r, g, b] / [r, g, b, a] (0-1 floats) -> 4 floats."""
    if isinstance(v, str):
        h = v.lstrip('#')
        if not re.fullmatch(r'[0-9a-fA-F]{6}([0-9a-fA-F]{2})?', h):
            raise PlanError(f'{where}: colour {v!r} is not #rrggbb or #rrggbbaa')
        vals = [int(h[i:i + 2], 16) / 255 for i in range(0, len(h), 2)]
    elif isinstance(v, list) and len(v) in (3, 4) and all(isinstance(x, (int, float)) for x in v):
        vals = [float(x) for x in v]
    else:
        raise PlanError(f'{where}: colour must be "#rrggbb" or [r, g, b(, a)] with 0-1 values')
    if len(vals) == 3:
        vals.append(0.0)
    return vals


def parse_finish(v, what, where, rep):
    """metallic / shine: a number (even all over) or [surface, details], each 0-1. Returns the
    save's (texture factor, added amount): value = added + factor x the armor design's own 0-1 map."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        low = high = v
    elif (isinstance(v, list) and len(v) == 2
          and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)):
        low, high = v
    else:
        raise PlanError(f'{where}: {what} must be a number from 0 to 1, or [surface, details]')
    # The game caps the result to 0-1, so any numbers are safe. The difference is taken in decimal so
    # [0.4, 0.7] gives exactly the 0.3 a game-made set stores.
    return f32(float(Decimal(repr(float(high))) - Decimal(repr(float(low))))), f32(low)


def finish_value(factor, added):
    """Inverse of parse_finish, exact: a number when even, else [surface, details]."""
    if factor == 0:
        return nice(added)
    low = nice(added)
    return [low, float(Decimal(repr(low)) + Decimal(repr(nice(factor))))]


def colour_value(rgb):
    """'#rrggbb' when the channels are exact 8-bit values (as the editor writes them), else [r, g, b]."""
    if all(0 <= x <= 1 and f32(round(x * 255) / 255) == f32(x) for x in rgb):
        return '#' + ''.join(f'{round(x * 255):02x}' for x in rgb)
    return [nice(x) for x in rgb]


def build_armor_set(spec, where, rep, template, base=None):
    rarity = parse_rarity(spec.get('rarity', 1), where)
    if rarity > 1:
        rep.untested_(f'{where}: armor sets in game-made saves are rarity 0 (stock) or 1 (looted)')
    level0 = parse_level(spec.get('level', MAX_LEVEL), where)

    colors = [list(c) for c in (base['colors'] if base is not None else template)]
    for area, v in (spec.get('colors') or {}).items():
        name = str(area)
        if name not in ARMOR_AREAS:
            hint = f' ({name} is now {OLD_ARMOR_AREAS[name]})' if name in OLD_ARMOR_AREAS else ''
            raise PlanError(f'{where}: unknown colour area {area!r}{hint}; use {", ".join(ARMOR_AREAS_MENU)}')
        i, at = ARMOR_AREAS.index(name), f'{where} {area}'
        if not isinstance(v, dict):
            v = {'color': v}                       # shorthand: just the colour
        unknown = set(v) - set(ARMOR_AREA_KEYS)
        if unknown:
            renamed = [f'{k} is now {OLD_ARMOR_KEYS[k]}' for k in sorted(unknown & set(OLD_ARMOR_KEYS))]
            hint = f' ({", ".join(renamed)})' if renamed else ''
            raise PlanError(f'{at}: unknown setting(s) {", ".join(sorted(map(str, unknown)))}{hint}; '
                            f'use {", ".join(ARMOR_AREA_KEYS)}')
        if 'color' in v:
            rgba = parse_colour(v['color'], at)
            given_alpha = (len(v['color'].lstrip('#')) == 8 if isinstance(v['color'], str)
                           else len(v['color']) == 4)
            if given_alpha:
                raise PlanError(f'{at}: give the glow as glow: instead of a colour alpha')
            colors[i][:3] = [f32(x) for x in rgba[:3]]
            if not all(0 <= x <= 1 for x in rgba[:3]):
                rep.untested_(f'{at}: colour channels outside 0-1')
        if 'glow' in v:
            g = v['glow']
            if not isinstance(g, (int, float)) or isinstance(g, bool):
                raise PlanError(f'{at}: glow must be a number from 0 (none) to 1')
            colors[i][3] = f32(g)
            if not 0 <= g <= 1:
                rep.untested_(f'{at}: glow {g:g} is outside 0-1')
            if name == 'accent' and g:
                rep.warn(f'{at}: the accent area never glows (the game ignores its glow)')
        for key, (ti, ai) in ARMOR_FINISH.items():
            if key in v:
                colors[4 + i][ti], colors[4 + i][ai] = parse_finish(v[key], key, at, rep)
    colors = [Vec(c) for c in colors]

    effects = spec.get('effects')
    perks = []
    if effects:
        items = effects.items() if isinstance(effects, dict) else [next(iter(e.items())) for e in effects]
        for code, value in items:
            if code not in ARMOR_EFFECTS:
                raise PlanError(f'{where}: unknown armor effect {code!r}; known: {", ".join(ARMOR_EFFECTS)}')
            if not isinstance(value, (int, float)):
                raise PlanError(f'{where}: armor effect {code} needs a number')
            neutral, direction = ARMOR_EFFECTS[code]
            positive = (value - neutral) * direction > 0
            if code.startswith('ability_recharge') and value <= -10:
                rep.untested_(f'{where}: {code} {value} could make the recharge time zero or negative')
            if not any(same32(value, x) for x in ARMOR_EFFECT_GENERATED[code] if x is not None):
                rep.untested_(f'{where}: {code} {value} is not a value the game rolls '
                              f'({", ".join(str(x) for x in ARMOR_EFFECT_GENERATED[code] if x is not None)})')
            perks.append(make_table([('is_positive', positive),
                                     ('localization_hint', 'ability' if code.startswith('ability_recharge') else 'mult'),
                                     ('code', code),
                                     ('value', int(value) if code.startswith('ability_recharge') and float(value).is_integer()
                                      else f32(value))]))
        if rarity == 0:
            rep.untested_(f'{where}: stock (rarity 0) sets never carry effects')
        if len(perks) != 2:
            rep.untested_(f'{where}: game-made sets carry exactly 2 effects (this one has {len(perks)})')
    elif rarity == 1 and base is None:
        rep.warn(f'{where}: a looted (rarity 1) set without effects; game-made ones have two')

    lock = spec.get('locked', base.get('lock') if base is not None else None)
    new = spec.get('new', base.get('new') if base is not None else None)
    return make_table([('rarity', rarity), ('perks', perks or None), ('colors', colors),
                       ('lock', True if lock else None), ('new', True if new else None),
                       ('upgrade_level', level0)])


# --- dump (save -> plan) ---------------------------------------------------------------------

def dump_weapon(w):
    code = w['code']
    mods = {m['code']: m['multiplier'] for m in w['modifiers']}
    main, b1, perk, b2, _ = split_tree(w['upgrades'])
    out = OrderedDict(code=code, rarity=RARITIES[w['rarity']], level=w['upgrade_level'] + 1)
    out['damage'] = nice(mods[WEAPONS[code]['damage']]) if code in WEAPONS else None
    if code in WEAPONS:
        out['stats'] = OrderedDict((s, nice(mods[s])) for s in weapon_stats(code))
    socks = OrderedDict()
    for name, group in (('main', main), ('branch1', b1), ('branch2', b2)):
        if group:
            socks[name] = [socket_text(u) for u in group]
    if socks:
        out['sockets'] = socks
    if perk is not None:
        out['perk'] = OrderedDict(cause=perk['perk_id'], effect=perk['effect_id'],
                                  efficiency=nice(perk['effect_efficiency']))
        if code in ON_HIT_CHANCE:
            default = ON_HIT_CHANCE[code] if perk['perk_id'] == 'on_enemy_hit' else 1.0
            if not same32(perk['perk_value'], default):
                out['perk']['value'] = nice(perk['perk_value'])
    if w.get('lock'):
        out['locked'] = True
    if w.get('new'):
        out['new'] = True
    out['tint'] = tint_of(w['name_seed'])
    return out


def dump_equipment(w):
    code = w['code']
    out = OrderedDict(code=code, rarity=RARITIES[w['rarity']], level=w['upgrade_level'] + 1,
                      damage=nice(w['modifiers'][0]['multiplier']))
    socks = [socket_text(u) for u in w['upgrades'] or [] if u['type'] != 'perk']
    if socks:
        out['sockets'] = socks
    perks = [next((k for k, v in EQUIPMENT_PERKS.items() if v == u.get('attribute')), u.get('attribute'))
             for u in w['upgrades'] or [] if u['type'] == 'perk']
    if perks:
        out['perk'] = perks[0] if len(perks) == 1 else perks
    if w.get('lock'):
        out['locked'] = True
    if w.get('new'):
        out['new'] = True
    out['tint'] = tint_of(w['name_seed'])
    return out


def dump_armor_set(s):
    out = OrderedDict(rarity=s['rarity'], level=s['upgrade_level'] + 1)
    cols = OrderedDict()
    for area in ARMOR_AREAS_MENU:
        i = ARMOR_AREAS.index(area)
        c, m = s['colors'][i], s['colors'][4 + i]
        a = cols[area] = OrderedDict(color=colour_value(c[:3]), glow=nice(c[3]))
        for key, (ti, ai) in ARMOR_FINISH.items():
            a[key] = finish_value(m[ti], m[ai])
    out['colors'] = cols
    if s.get('perks'):
        out['effects'] = [{p['code']: nice(p['value'])} for p in s['perks']]
    if s.get('lock'):
        out['locked'] = True
    if s.get('new'):
        out['new'] = True
    return out


def resource_counts(inv):
    return OrderedDict((r['name'], r['count']) for r in inv['resources'])


def dump_profile(inv):
    res = resource_counts(inv)
    prof = OrderedDict()
    prof['level'] = inv['armor']['upgrade_level'] + 1
    if inv['armor']['upgrade_level'] == 29:
        prof['hero_level'] = (inv['armor'].get('paragon_level') or 0) + 1
    prof['keys'] = OrderedDict((k, res[v]) for k, v in KEYS.items() if v in res)
    prof['cores'] = OrderedDict((f'{CORE_NAMES[t]}{lv}', res[f'core{t}_{lv}'])
                                for t in range(1, 5) for lv in range(1, 7) if f'core{t}_{lv}' in res)
    prof['metals'] = OrderedDict((k, res.get(v, 0)) for k, v in METALS.items() if v in res)
    if 'credits' in res:
        prof['credits'] = res['credits']
    if FLOWER in res:
        prof['flowers'] = res[FLOWER]
    return prof


# --- save access -----------------------------------------------------------------------------

def open_save(path):
    if os.path.isdir(path):
        folder, file = path, os.path.join(path, 'savedata.dat')
    else:
        folder, file = None, path
    if not os.path.exists(file):
        raise SaveEditError(f'no savedata.dat at {file}')
    return folder, file, SaveFile.load(file)


def characters(root):
    for i, c in enumerate(root['slots']):
        if c is not None:
            yield i, c


def class_of(char):
    return CLASSES.get(char['inventory']['armor']['code'], char['inventory']['armor']['code'])


def pick_slots(root, requested, plan_target):
    chars = dict(characters(root))
    if requested is None and plan_target is not None:
        requested = [str(plan_target)]
    if requested is None:
        if len(chars) == 1:
            return list(chars)
        raise SaveEditError(f'this save has {len(chars)} characters (slots {", ".join(map(str, chars))}); '
                            f'choose one with --slot N, or --slot all')
    if requested == ['all']:
        return list(chars)
    out = []
    for r in requested:
        if not str(r).isdigit() or int(r) not in chars:
            raise SaveEditError(f'slot {r}: no character in that slot (have {", ".join(map(str, chars))})')
        out.append(int(r))
    return out


# --- applying a plan ---------------------------------------------------------------------------

SECTIONS = ['target', 'weapons', 'equipment', 'armor_sets', 'remove', 'profile']


def parse_plan_text(text, name='plan'):
    """YAML text -> list of plan documents (plain dicts). Raises PlanError on bad YAML."""
    try:
        docs = [d for d in yaml.safe_load_all(text) if d]
    except yaml.YAMLError as e:
        raise PlanError(f'{name}: {e}')
    for d in docs:
        if not isinstance(d, dict):
            raise PlanError(f'{name}: a plan must be a mapping with weapons/equipment/armor_sets/profile')
    return docs


def load_plans(paths):
    """Read and merge plan files (see merge_plans)."""
    named = []
    for p in paths:
        with open(p) as f:
            named += [(p, d) for d in parse_plan_text(f.read(), p)]
    return merge_plans(named)


def merge_plans(named_docs):
    """[(name, plan dict)] -> (merged plan, target slot). Lists concatenate, profile/target/remove merge."""
    merged = OrderedDict(weapons=[], equipment=[], armor_sets=[], remove=OrderedDict(), profile=OrderedDict())
    target = None
    for p, d in named_docs:
        unknown = set(d) - set(SECTIONS)
        if unknown:
            raise PlanError(f'{p}: unknown section(s) {", ".join(sorted(unknown))}')
        for k in ('weapons', 'equipment', 'armor_sets'):
            v = d.get(k) or []
            if isinstance(v, dict):
                v = [v]
            merged[k] += [(p, i, x) for i, x in enumerate(v)]
        for k, v in (d.get('remove') or {}).items():
            merged['remove'].setdefault(k, []).extend(v if isinstance(v, list) else [v])
        for k, v in (d.get('profile') or {}).items():
            if isinstance(v, dict) and isinstance(merged['profile'].get(k), dict):
                merged['profile'][k].update(v)
            else:
                merged['profile'][k] = v
        if d.get('target') is not None:
            t = d['target'].get('slot') if isinstance(d['target'], dict) else d['target']
            target = t
    return merged, target


def parse_index_ref(ref, lst, kind, where, code_key='code'):
    """3 | {index: 3, code: smg} -> index, checking it exists and (optionally) what it holds."""
    if isinstance(ref, dict):
        idx, expect = ref.get('index'), ref.get(code_key)
    else:
        idx, expect = ref, None
    if not isinstance(idx, int) or not 0 <= idx < len(lst):
        raise PlanError(f'{where}: {kind} index {idx!r} does not exist (0-{len(lst) - 1})')
    if expect is not None and lst[idx].get(code_key) != expect:
        raise PlanError(f'{where}: {kind}[{idx}] is {lst[idx].get(code_key)!r}, not {expect!r}')
    return idx


def apply_list(inv, key, entries, builder, rep, extra=None, label=None):
    """Replacements happen in place; additions are appended. Returns [(final index, spec)].
    Messages use label, the plan's section name, rather than the savegame field key."""
    lst = inv[key]
    label = label or key
    placed = []
    for path, i, spec in entries:
        where = f'{os.path.basename(path)} {label}[{i}]'
        if not isinstance(spec, dict):
            raise PlanError(f'{where}: each entry must be a mapping')
        rep_ref = spec.get('replace')
        base = None
        if rep_ref is not None:
            idx = parse_index_ref(rep_ref, lst, label, where)
            base = lst[idx]
        item = builder(spec, where, rep, base) if extra is None else builder(spec, where, rep, extra, base)
        if rep_ref is not None:
            lst[idx] = item
            rep.note(f'{label}[{idx}] replaced{describe(item, key)}')
            placed.append((idx, spec, where))
        else:
            lst.append(item)
            rep.note(f'{label}[{len(lst) - 1}] added{describe(item, key)}')
            placed.append((len(lst) - 1, spec, where))
    return placed


def describe(item, key):
    if key in ('armor_sets', 'color_sets'):
        return f': rarity {item["rarity"]}, {len(item.get("perks") or [])} effects'
    n = len(item['upgrades'] or [])
    return f': {item["code"]} ({RARITIES[item["rarity"]][0].upper()}) ({item["upgrade_level"] + 1}), {n} slots'


def remove_items(inv, key, refs, active_key, rep, label):
    lst = inv[key]
    idxs = sorted({parse_index_ref(r, lst, label, f'remove.{label}') for r in refs}, reverse=True)
    active = inv.get(active_key) if active_key else None
    for idx in idxs:
        if active_key == 'active_color_set':
            if inv.get('active_color_set') == idx:
                raise PlanError(f'remove.{label}: armor set {idx} is the one being worn, so it can\'t be deleted '
                                f'until another set is worn (equip: true on another set)')
        elif active is not None and idx in active:
            raise PlanError(f'remove.{label}: {label}[{idx}] is equipped, so it can\'t be deleted until another '
                            f'item is equipped in its slot (equip: true on another entry)')
        del lst[idx]
        if active_key == 'active_color_set':
            if inv['active_color_set'] > idx:
                inv['active_color_set'] -= 1
        elif active is not None:
            for j, a in enumerate(active):
                if isinstance(a, int) and a > idx:
                    active[j] = a - 1
        rep.note(f'{label}[{idx}] deleted')
    return idxs


def shift_after_removal(placed, removed):
    """Final index of an entry placed before removals happened."""
    out = []
    for idx, spec, where in placed:
        out.append((idx - sum(1 for r in removed if r < idx), spec, where))
    return out


def set_resource(inv, name, count, rep):
    if not isinstance(count, int) or count < 0:
        raise PlanError(f'profile: {name} needs a non-negative whole number (got {count!r})')
    if count > 999999:
        rep.untested_(f'profile: {name} = {count} is far above anything seen')
    for r in inv['resources']:
        if r.get('name') == name:
            r['count'] = count
            return
    if count == 0:
        return
    inv['resources'].append(make_table([('name', name), ('count', count)]))


def hero_step(p):
    """XP to go from hero level p-1 to p (0-based paragon_level), at player level 30."""
    return (LEVEL_XP[29] // 10) * (1 + p // 10)


def cumulative_xp(u, p):
    return sum(LEVEL_XP[1:u + 1]) + (sum(hero_step(k) for k in range(1, p + 1)) if u == 29 else 0)


def next_cost(u, p):
    return LEVEL_XP[u + 1] if u < 29 else hero_step(min(p + 1, MAX_HERO - 1))


def set_levels(char, level, hero, rep):
    """armor.upgrade_level (0-29) and armor.paragon_level (0-299); armor.xp is progress within the
    level and must stay below the next level's cost; stats.xp (lifetime, a string) moves by the
    same amount so the lifetime total stays consistent."""
    armor = char['inventory']['armor']
    u0, p0 = armor['upgrade_level'], armor.get('paragon_level', 0) or 0
    u = u0 if level is None else parse_level(level, 'profile.level')
    if hero is not None:
        if not isinstance(hero, int) or not 1 <= hero <= MAX_HERO:
            raise PlanError(f'profile.hero_level must be 1-{MAX_HERO} (got {hero!r})')
        if u != 29:
            raise PlanError('profile.hero_level needs player level 30 (set level: 30 as well)')
        p = hero - 1
    else:
        p = p0 if u == 29 else 0
    if (u, p) == (u0, p0):
        return
    if (u, p) < (u0, p0):
        rep.warn(f'lowering the character from level {u0 + 1}/hero {p0 + 1} to {u + 1}/hero {p + 1}')
    xp = armor['xp'] if armor['xp'] < next_cost(u, p) else 0
    delta = cumulative_xp(u, p) + xp - cumulative_xp(u0, p0) - armor['xp']
    armor['upgrade_level'] = u
    armor['paragon_level'] = p
    armor['xp'] = xp
    stats = char.get('stats')
    if stats is not None and isinstance(stats.get('xp'), str) and stats['xp'].lstrip('-').isdigit():
        stats['xp'] = str(max(0, int(stats['xp']) + delta))
    rep.note(f'level {u0 + 1}/hero {p0 + 1} -> level {u + 1}/hero {p + 1} '
             f'(lifetime XP {delta:+,}; trophies for the skipped levels will not fire)')


def apply_profile(char, prof, rep):
    inv = char['inventory']
    for k, v in (prof.get('keys') or {}).items():
        if k not in KEYS:
            raise PlanError(f'profile.keys: unknown key {k!r}; use ufo or ark')
        set_resource(inv, KEYS[k], v, rep)
    for k, v in (prof.get('cores') or {}).items():
        m = re.fullmatch(r'([a-z]+)\s*(\d)', str(k).lower())
        t = (CORES.get(m.group(1)) or CORE_ALIASES.get(m.group(1))) if m else None
        if not t or not 1 <= int(m.group(2)) <= 6:
            raise PlanError(f'profile.cores: {k!r} should look like power6 (type + level 1-6)')
        set_resource(inv, f'core{t}_{m.group(2)}', v, rep)
    for k, v in (prof.get('metals') or {}).items():
        if k not in METALS:
            raise PlanError(f'profile.metals: unknown metal {k!r}; use {", ".join(METALS)}')
        if k == 'unobtainium':
            rep.untested_('profile.metals: metal5 (unobtainium) never appears in a game-made save')
        set_resource(inv, METALS[k], v, rep)
    if 'credits' in prof:
        set_resource(inv, 'credits', prof['credits'], rep)
    if 'flowers' in prof:
        set_resource(inv, FLOWER, prof['flowers'], rep)
    if 'level' in prof or 'hero_level' in prof:
        set_levels(char, prof.get('level'), prof.get('hero_level'), rep)
    extra = set(prof) - {'keys', 'cores', 'metals', 'credits', 'flowers', 'level', 'hero_level'}
    if extra:
        raise PlanError(f'profile: unknown setting(s) {", ".join(sorted(extra))}')


def equip(inv, placed, key, rep):
    taken = {}                    # slot -> the plan entry that equipped it first
    for idx, spec, where in placed:
        e = spec.get('equip')
        if not e:
            continue
        slot = WEAPON_CATEGORY.get(inv['weapons'][idx]['code']) if key == 'weapons' else key
        if slot in taken:
            rep.warn(f'{where} and {taken[slot]} both equip the {SLOT_NAMES.get(slot, slot)}; the last one wins')
        taken.setdefault(slot, where)
        if key == 'weapons':
            code = inv['weapons'][idx]['code']
            category = WEAPON_CATEGORY[code]
            slot = category if e is True else e
            if slot not in WEAPON_SLOTS:
                raise PlanError(f'{where}: equip must be true, heavy, primary or secondary')
            if slot != category:
                raise PlanError(f'{where}: {code} is a {category} weapon and can only be equipped as {category}')
            inv['active_weapons'][WEAPON_SLOTS[slot]] = idx
            rep.note(f'weapons[{idx}] equipped as {slot}')
        elif key == 'equipment':
            if inv.get('active_items') is None:
                inv['active_items'] = [None, None, None, None]
            inv['active_items'][EQUIPMENT_SLOT] = idx
            rep.note(f'equipment[{idx}] equipped')
        elif key == 'armor_sets':
            inv['active_color_set'] = idx
            inv['armor']['colors'] = [Vec(c) for c in inv['color_sets'][idx]['colors']]
            rep.note(f'armor_sets[{idx}] equipped (armor colours updated)')


SLOT_NAMES = {'heavy': 'heavy slot', 'primary': 'primary slot', 'secondary': 'secondary slot',
              'equipment': 'equipment slot', 'armor_sets': 'armor set'}


def check_character(inv, cls, rep):
    w, it = inv['weapons'], inv.get('items') or []
    armor = inv['armor']['code']
    for cat in WEAPON_SLOTS:
        n = sum(1 for x in w if WEAPON_CATEGORY.get(x['code']) == cat)
        if n > MAX_PER_CATEGORY:
            rep.error(f'{n} {cat} weapons; the game refuses an 11th of a slot type ({MAX_PER_CATEGORY} max)')
    if len(it) > MAX_EQUIPMENT:
        rep.error(f'{len(it)} equipment items; the game refuses an 11th ({MAX_EQUIPMENT} max)')
    sets = inv.get('color_sets') or []
    if len(sets) > MAX_ARMOR_SETS:
        rep.warn(f'{len(sets)} armor sets: the game keeps them all, but gives you no new looted sets while '
                 f'you have {MAX_ARMOR_SETS} or more')
    own = CLASS_PRIMARY.get(armor)
    if own and not any(x['code'] == own for x in w):
        rep.warn(f'no {own} left: the {cls} needs one for its primary slot unless the weapon hack add-on is owned')
    for j, a in enumerate(inv['active_weapons']):
        if isinstance(a, int) and 0 <= a < len(w):
            slot = next((n for n, v in WEAPON_SLOTS.items() if v == j), None)
            if slot and WEAPON_CATEGORY.get(w[a]['code']) != slot:
                rep.error(f'the {slot} slot holds a {WEAPON_CATEGORY.get(w[a]["code"])} weapon ({w[a]["code"]})')
    for j, a in enumerate(inv['active_weapons']):
        if a is not None and not (isinstance(a, int) and 0 <= a < len(w)):
            rep.error(f'active weapon slot {j} points at a missing weapon ({a})')
    for j, a in enumerate(inv.get('active_items') or []):
        if a is not None and not (isinstance(a, int) and 0 <= a < len(it)):
            rep.error(f'active equipment slot {j} points at a missing item ({a})')
    if inv.get('color_sets') is not None and not 0 <= inv.get('active_color_set', 0) < len(inv['color_sets']):
        rep.error('active armor set points at a missing set')
    # Every slot holds exactly one item: a slot can only hold one index, and none may be empty.
    for slot, j in WEAPON_SLOTS.items():
        if inv['active_weapons'][j] is None:
            have = [i for i, x in enumerate(w) if WEAPON_CATEGORY.get(x['code']) == slot]
            rep.error(f'the {slot} slot is empty: ' + (f'equip one of weapons {have} (add a replace entry with equip: true)'
                                                      if have else f'add a {slot} weapon with equip: true'))
    if (inv.get('active_items') or [None] * 4)[EQUIPMENT_SLOT] is None:
        rep.error('the equipment slot is empty: ' + ('equip one of the equipment items' if it else
                                                    'add an equipment item with equip: true'))
    if inv.get('color_sets') and inv.get('active_color_set') is None:
        rep.error('no armor set is equipped: give one armor set equip: true')


def apply_plan(root, slot, plan, rep):
    char = root['slots'][slot]
    inv = char['inventory']
    cls = class_of(char)
    template = [tuple(c) for c in inv['armor']['colors']]
    if inv.get('items') is None:
        inv['items'] = []
    if inv.get('color_sets') is None:
        inv['color_sets'] = []

    placed = {}
    placed['weapons'] = apply_list(inv, 'weapons', plan['weapons'], build_weapon, rep)
    placed['equipment'] = apply_list(inv, 'items', plan['equipment'], build_equipment, rep, label='equipment')
    placed['armor_sets'] = apply_list(inv, 'color_sets', plan['armor_sets'], build_armor_set, rep, extra=template,
                                     label='armor_sets')

    armor = inv['armor']['code']
    for idx, spec, where in placed['weapons']:
        code = inv['weapons'][idx]['code']
        if WEAPON_CATEGORY[code] == 'primary' and CLASS_PRIMARY.get(armor) not in (None, code):
            rep.warn(f'{where}: {code} is another class\'s primary; it only works with the weapon hack add-on '
                     f'(without it the game swaps it out of the primary slot on load)')
        if code in DLC_ITEMS:
            rep.warn(f'{where}: {code} needs the {DLC_ITEMS[code]} add-on (or All Weapons)')
    for idx, spec, where in placed['equipment']:
        code = inv['items'][idx]['code']
        if code in DLC_ITEMS:
            rep.warn(f'{where}: {code} needs the {DLC_ITEMS[code]} add-on (or All Weapons)')

    rem = plan['remove']
    unknown = set(rem) - {'weapons', 'equipment', 'armor_sets'}
    if unknown:
        raise PlanError(f'remove: unknown list(s) {", ".join(sorted(unknown))}')
    # Equip first so an equipped item can be swapped out and removed in the same plan.
    equip(inv, placed['weapons'], 'weapons', rep)
    equip(inv, placed['equipment'], 'equipment', rep)
    equip(inv, placed['armor_sets'], 'armor_sets', rep)
    for label, key, active in (('weapons', 'weapons', 'active_weapons'), ('equipment', 'items', 'active_items'),
                               ('armor_sets', 'color_sets', 'active_color_set')):
        if rem.get(label):
            removed = remove_items(inv, key, rem[label], active, rep, label)
            placed[label] = shift_after_removal(placed[label], removed)

    apply_profile(char, plan['profile'], rep)
    check_character(inv, cls, rep)
    return cls


# --- perk maths (shown by the GUI, documented in docs/weapons-and-cores.md) --------------------

CAUSE_TEXT = {
    'on_enemy_hit': 'chance on enemy hit', 'on_enemy_hit_critical': 'chance on critical enemy hit',
    'on_enemy_hit_melee': 'chance on melee enemy hit', 'on_player_hit': 'chance on player hit',
    'enemy_within_range': 'an enemy within range', 'enemies_within_range': '3 enemies within range',
    'boss_within_range': 'a boss within range', 'player_within_range': 'another player within range',
    'staying_still': 'standing still', 'rush_not_ready': 'rush not charged', 'low_ammo': 'ammo below a threshold',
}
EFFECT_TEXT = {
    'bonus_talent_power': '+% gear power', 'reduce_damage_taken': '% player damage reduction',
    'gain_shield': 'front shield', 'bonus_weapon_fire_rate': '+% fire rate',
    'bonus_weapon_damage': '+% weapon damage', 'bonus_critical_chance': '+% critical hit chance',
    'bonus_critical_damage': '+% critical damage', 'cluster_shell_from_target': 'cluster shell on the target',
    'boomerang_at_target': 'boomerang thrown at the target', 'knockdown_target': 'knocks the target down',
    'gain_ammo_clip': 'chance to gain one ammo clip', 'poison_target': 'poisons the target',
    'explosion_target': 'explosion on the target', 'chain_lightning_target': 'chain lightning from the target',
}


def default_perk_value(code, cause):
    return ON_HIT_CHANCE.get(code, 1.0) if cause == 'on_enemy_hit' else 1.0


def perk_trigger_text(cause, value):
    """What the perk's condition means for a given perk_value."""
    if cause in PERK_HIT_CHANCE:
        what = {'on_enemy_hit': 'hit', 'on_enemy_hit_critical': 'critical hit', 'on_enemy_hit_melee': 'melee hit'}[cause]
        text = f'{min(PERK_HIT_CHANCE[cause] * value, 100):.2f}% chance per {what}'
        if cause == 'on_enemy_hit':
            text += f', plus a guaranteed proc when no perk fired in the last {PERK_GUARANTEE_AFTER} s'
        return text
    if cause == 'on_player_hit':
        return f'every time you are hit ({PERK_PLAYER_HIT_COOLDOWN} s cooldown)'
    if cause in PERK_RANGE_METRES:
        return f'{CAUSE_TEXT[cause]}: {PERK_RANGE_METRES[cause] * value:g} m'
    if cause == 'low_ammo':
        return f'ammo below {round(PERK_LOW_AMMO_PERCENT * value)}%'
    return CAUSE_TEXT.get(cause, cause)


def perk_effect_text(effect, level, efficiency):
    """Effect strength = base x weapon level x efficiency."""
    if effect in EFFECT_BASE:
        n = EFFECT_BASE[effect] * level * efficiency
        return f'{n:,.0f} {"strength" if effect == "knockdown_target" else "HP"} per proc'
    if effect == 'gain_ammo_clip':
        return f'{round(PERK_AMMO_CLIP_PERCENT * efficiency)}% chance to gain a clip'
    return f'{EFFECT_TEXT.get(effect, effect)} (strength not decoded)'


# --- checking plans without a save ---------------------------------------------------------------

COMMON_KEYS = {'replace', 'equip', 'locked', 'new', 'tint'}
ENTRY_KEYS = {
    'weapons': {'code', 'rarity', 'level', 'damage', 'stats', 'sockets', 'perk'} | COMMON_KEYS,
    'equipment': {'code', 'rarity', 'level', 'damage', 'sockets', 'perk'} | COMMON_KEYS,
    'armor_sets': {'rarity', 'level', 'colors', 'effects', 'replace', 'equip', 'locked', 'new'},
}
NEUTRAL_ARMOR_TEMPLATE = [(0.5, 0.5, 0.5, 0.0)] * 4 + [(0.0, 1.0, 0.5, 1.0)] * 4


def entry_label(section, spec, names=None):
    """Short one-line description of a plan entry, e.g. 'smg (L) (30)': rarity initial (Stock, Common,
    Uncommon, Rare, Legendary) and level. names maps codes to the names to show instead (the GUI's 'SMG')."""
    if not isinstance(spec, dict):
        return '(not a mapping)'
    r = spec.get('rarity', 'legendary' if section != 'armor_sets' else 1)
    if isinstance(r, int) and 0 <= r <= 4:
        r = RARITIES[r]
    if section == 'armor_sets':
        r = {0: 'stock', 1: 'looted', 'stock': 'stock', 'common': 'looted'}.get(spec.get('rarity', 1),
                                                                                f'rarity {spec.get("rarity")}')
        eff = spec.get('effects') or {}
        n = len(eff)
        return f'armor set, {r}' + (f', {n} effect{"s" * (n != 1)}' if n else '')
    code = spec.get('code', '?')
    tag = r[0].upper() if r in RARITIES else str(r)
    return f'{(names or {}).get(code, code)} ({tag}) ({spec.get("level", MAX_LEVEL)})'


def check_entry(section, spec, where, allow_untested=False):
    """Validate one weapons / equipment / armor_sets entry on its own. Checks that need the save
    (indices, inventory caps, class) happen in SaveSession.apply."""
    rep = Report(allow_untested)
    if not isinstance(spec, dict):
        rep.error(f'{where}: each entry must be a mapping')
        return rep
    unknown = set(spec) - ENTRY_KEYS[section]
    if unknown:
        rep.warn(f'{where}: unknown key(s) {", ".join(sorted(map(str, unknown)))} are ignored')
    try:
        ref = spec.get('replace')
        if ref is not None:
            idx = ref.get('index') if isinstance(ref, dict) else ref
            if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
                raise PlanError(f'{where}: replace needs an item index (a whole number from show/dump)')
        if section == 'weapons':
            build_weapon(spec, where, rep)
            code, e = spec['code'], spec.get('equip')
            if e and e is not True and e != WEAPON_CATEGORY[code]:
                rep.error(f'{where}: {code} is a {WEAPON_CATEGORY[code]} weapon; equip must be true or '
                          f'{WEAPON_CATEGORY[code]}')
            if code in DLC_ITEMS:
                rep.warn(f'{where}: {code} needs the {DLC_ITEMS[code]} add-on (or All Weapons)')
        elif section == 'equipment':
            build_equipment(spec, where, rep)
            if spec['code'] in DLC_ITEMS:
                rep.warn(f'{where}: {spec["code"]} needs the {DLC_ITEMS[spec["code"]]} add-on (or All Weapons)')
        else:
            build_armor_set(spec, where, rep, NEUTRAL_ARMOR_TEMPLATE)
    except PlanError as e:
        rep.error(str(e))
    except (TypeError, AttributeError, ValueError, KeyError) as e:
        rep.error(f'{where}: malformed entry ({e})')
    return rep


def check_profile(prof, allow_untested=False):
    """Validate a profile section against a placeholder level-1 character (notes are dropped)."""
    rep = Report(allow_untested)
    if not isinstance(prof, dict):
        rep.error('profile must be a mapping')
        return rep
    char = {'inventory': {'resources': [], 'armor': {'upgrade_level': 0, 'paragon_level': 0, 'xp': 0}}}
    try:
        apply_profile(char, prof, rep)
    except PlanError as e:
        rep.error(str(e))
    except (TypeError, AttributeError, ValueError) as e:
        rep.error(f'profile: malformed ({e})')
    rep.notes = []
    return rep


def check_remove(rem):
    rep = Report(False)
    if not isinstance(rem, dict):
        rep.error('remove must be a mapping of weapons / equipment / armor_sets')
        return rep
    for label, refs in rem.items():
        if label not in ('weapons', 'equipment', 'armor_sets'):
            rep.error(f'remove: unknown list {label!r}; use weapons, equipment, armor_sets')
            continue
        for r in refs if isinstance(refs, list) else [refs]:
            idx = r.get('index') if isinstance(r, dict) else r
            if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
                rep.error(f'remove.{label}: {r!r} is not an item index')
    return rep


def check_document(doc, name='plan', allow_untested=False):
    """Validate one plan document without a save. Returns {key: Report} where key is a section name
    ('plan', 'target', 'profile', 'remove') or (section, index) for list entries."""
    out = {'plan': Report(allow_untested)}
    if not isinstance(doc, dict):
        out['plan'].error(f'{name}: a plan must be a mapping')
        return out
    unknown = set(doc) - set(SECTIONS)
    if unknown:
        out['plan'].error(f'{name}: unknown section(s) {", ".join(sorted(map(str, unknown)))}')
    t = doc.get('target')
    if t is not None:
        slot = t.get('slot') if isinstance(t, dict) else t
        out['target'] = Report(allow_untested)
        if not isinstance(slot, int) or isinstance(slot, bool) or slot < 0:
            out['target'].error('target.slot must be a character slot number')
    for section in ('weapons', 'equipment', 'armor_sets'):
        entries = doc.get(section) or []
        if isinstance(entries, dict):
            entries = [entries]
        for i, spec in enumerate(entries):
            out[(section, i)] = check_entry(section, spec, f'{section}[{i}]', allow_untested)
        if section == 'equipment' and len(entries) > MAX_EQUIPMENT:
            out['plan'].error(f'{len(entries)} equipment entries; a character holds at most {MAX_EQUIPMENT}')
    taken = {}
    for section in ('weapons', 'equipment', 'armor_sets'):
        entries = doc.get(section) or []
        for i, spec in enumerate([entries] if isinstance(entries, dict) else entries):
            if not isinstance(spec, dict) or not spec.get('equip'):
                continue
            slot = WEAPON_CATEGORY.get(spec.get('code')) if section == 'weapons' else section
            if slot is None:
                continue
            if slot in taken:
                out[(section, i)].warn(f'{section}[{i}] and {taken[slot]} both equip the {SLOT_NAMES[slot]}; '
                                       f'the last one wins')
            taken.setdefault(slot, f'{section}[{i}]')
    if doc.get('profile') is not None:
        out['profile'] = check_profile(doc['profile'], allow_untested)
    if doc.get('remove') is not None:
        out['remove'] = check_remove(doc['remove'])
    return out


# --- dump (save -> plan document) ----------------------------------------------------------------

def represent_ordered(dumper, data):
    return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())


class PlanDumper(yaml.SafeDumper):
    pass


PlanDumper.add_representer(OrderedDict, represent_ordered)


def flow_list(dumper, data):
    return dumper.represent_sequence('tag:yaml.org,2002:seq', data,
                                     flow_style=all(not isinstance(x, (dict, list)) for x in data))


PlanDumper.add_representer(list, flow_list)

DUMP_HEADER = ('# Generated by tools/save-editor-cli.py dump. Applying it unchanged rebuilds the same items.\n'
               '# Edit entries in place, delete the ones you do not want to touch, or drop the\n'
               '# replace: lines to add copies. Format: docs/save-editor.md\n')


def plan_to_yaml(doc, header=DUMP_HEADER):
    return header + yaml.dump(doc, Dumper=PlanDumper, sort_keys=False, width=110)


def dump_plan(root, slot):
    """One character's inventory as a plan whose entries replace each item in place."""
    inv = root['slots'][slot]['inventory']
    doc = OrderedDict()
    doc['target'] = OrderedDict(slot=slot)
    doc['weapons'] = []
    active = list(inv['active_weapons'])
    for j, w in enumerate(inv['weapons']):
        d = OrderedDict(replace=OrderedDict(index=j, code=w['code']))
        d.update(dump_weapon(w))
        for n, s in WEAPON_SLOTS.items():
            if active[s] == j:
                d['equip'] = n
        doc['weapons'].append(d)
    doc['equipment'] = []
    for j, w in enumerate(inv.get('items') or []):
        d = OrderedDict(replace=OrderedDict(index=j, code=w['code']))
        d.update(dump_equipment(w))
        if j in list(inv.get('active_items') or []):
            d['equip'] = True
        doc['equipment'].append(d)
    doc['armor_sets'] = []
    for j, s in enumerate(inv.get('color_sets') or []):
        d = OrderedDict(replace=OrderedDict(index=j))
        d.update(dump_armor_set(s))
        if inv.get('active_color_set') == j:
            d['equip'] = True
        doc['armor_sets'].append(d)
    doc['profile'] = dump_profile(inv)
    return doc


def inventory_rows(char):
    """[(section, index, code or None, text, equipped as or None)] for one character."""
    inv = char['inventory']
    rows = []
    active = list(inv['active_weapons'])
    for j, w in enumerate(inv['weapons']):
        mark = next((n for n, s in WEAPON_SLOTS.items() if active[s] == j), None)
        rows.append(('weapons', j, w['code'], f'{w["code"]} {RARITIES[w["rarity"]]} L{w["upgrade_level"] + 1} '
                     f'{len(w["upgrades"] or [])} slots{" locked" if w.get("lock") else ""}', mark))
    ai = list(inv.get('active_items') or [])
    for j, w in enumerate(inv.get('items') or []):
        rows.append(('equipment', j, w['code'], f'{w["code"]} {RARITIES[w["rarity"]]} L{w["upgrade_level"] + 1} '
                     f'{len(w["upgrades"] or [])} slots', 'equipped' if j in ai else None))
    for j, s in enumerate(inv.get('color_sets') or []):
        eff = ', '.join(f'{p["code"]} {p["value"]:g}' for p in s.get('perks') or [])
        rows.append(('armor_sets', j, None, f'rarity {s["rarity"]}{": " + eff if eff else ""}',
                     'equipped' if inv.get('active_color_set') == j else None))
    return rows


def character_summary(char):
    inv = char['inventory']
    res = resource_counts(inv)
    armor = inv['armor']
    lvl = armor.get('upgrade_level', 0) + 1
    hero = (armor.get('paragon_level') or 0) + 1 if lvl == MAX_LEVEL else None
    return (f'{class_of(char)}, level {lvl}{f" hero {hero}" if hero else ""}, {len(inv["weapons"])} weapons, '
            f'{len(inv.get("items") or [])} equipment, {len(inv.get("color_sets") or [])} armor sets; '
            f'keys ufo={res.get("key1", 0)} ark={res.get("key2", 0)}')


# --- one save on disk ----------------------------------------------------------------------------

class SaveSession:
    """A save folder or savedata.dat. apply() always starts from a fresh read of the file, so a
    check never changes what a later check or write sees."""

    def __init__(self, path):
        self.path = path
        self.folder, self.file, self.save = open_save(path)

    @property
    def root(self):
        return self.save.root

    def characters(self):
        return list(characters(self.root))

    def slots_for(self, requested=None, plan_target=None):
        return pick_slots(self.root, requested, plan_target)

    def apply(self, plan, slots, allow_untested=False):
        """Apply a merged plan (merge_plans / load_plans) to each slot.
        Returns ({slot: Report}, savedata bytes or None if any slot failed)."""
        save = SaveFile.load(self.file)
        reports = {}
        for slot in slots:
            rep = Report(allow_untested)
            try:
                apply_plan(save.root, slot, copy.deepcopy(plan), rep)
            except PlanError as e:
                rep.error(str(e))
            reports[slot] = rep
        if any(r.failed() for r in reports.values()):
            return reports, None
        return reports, save.build()

    def apply_each(self, plans, allow_untested=False):
        """Apply a different merged plan to each character in one pass: {slot: plan}.
        Returns ({slot: Report}, savedata bytes or None if any slot failed). Characters without a
        plan are written back unchanged."""
        save = SaveFile.load(self.file)
        reports = {}
        for slot, plan in plans.items():
            rep = Report(allow_untested)
            try:
                apply_plan(save.root, slot, copy.deepcopy(plan), rep)
            except PlanError as e:
                rep.error(str(e))
            reports[slot] = rep
        if any(r.failed() for r in reports.values()):
            return reports, None
        return reports, save.build()

    def write(self, data, out_dir):
        """Write savedata.dat (and sce_sys when the input was a folder) into out_dir. Writing over
        the input save raises savedata.OutputPathError."""
        written = [os.path.join(out_dir, 'savedata.dat')]
        write_output(written[0], data, [self.file])
        if self.folder and os.path.isdir(os.path.join(self.folder, 'sce_sys')):
            shutil.copytree(os.path.join(self.folder, 'sce_sys'), os.path.join(out_dir, 'sce_sys'),
                            dirs_exist_ok=True, ignore=shutil.ignore_patterns('.DS_Store'))
            written.append(os.path.join(out_dir, 'sce_sys'))
        SaveFile.load(written[0])       # re-read what was written as a final consistency check
        return written


# --- self test -----------------------------------------------------------------------------------

def canonical(item):
    """Structure-only view of an item for comparisons: drops key order and slot order within a branch."""
    def norm(v):
        if isinstance(v, Table):
            return tuple(sorted((k, norm(x)) for k, x in OrderedDict.items(v)))
        if isinstance(v, list):
            return (type(v).__name__,) + tuple(norm(x) for x in v)
        return (type(v).__name__, v)
    t = OrderedDict.copy(item) if isinstance(item, Table) else item
    return norm(t)


def tree_sorted(item):
    """Same item with upgrades in canonical order (main, branch1, perk, branch2)."""
    it = Table()
    for k, v in OrderedDict.items(item):
        OrderedDict.__setitem__(it, k, v)
    if item.get('upgrades'):
        main, b1, perk, b2, _ = split_tree(item['upgrades'])
        it['upgrades'] = main + b1 + ([perk] if perk is not None else []) + b2
    return it


def selftest():
    """Dump every weapon/item/armor set in savegames/ to a plan entry and rebuild it.
    Yields (where, status, detail) with status 'ok', 'FAIL' or 'DIFF'."""
    paths = sorted(glob.glob(os.path.join(ROOT, 'savegames', '**', 'savedata.dat'), recursive=True))
    for p in paths:
        save = SaveFile.load(p)
        for slot, c in characters(save.root):
            inv = c['inventory']
            template = [tuple(x) for x in inv['armor']['colors']]
            for kind, lst, dumper, builder in (('weapon', inv['weapons'], dump_weapon, build_weapon),
                                                ('equipment', inv.get('items') or [], dump_equipment, build_equipment),
                                                ('armor set', inv.get('color_sets') or [], dump_armor_set, None)):
                for j, item in enumerate(lst):
                    rep = Report(allow_untested=True)
                    spec = yaml.safe_load(yaml.dump(dumper(item), Dumper=PlanDumper))
                    where = f'{os.path.relpath(p, ROOT)} slot {slot} {kind} {j}'
                    try:
                        if builder is None:
                            rebuilt = build_armor_set(spec, where, rep, template, base=None)
                        else:
                            rebuilt = builder(spec, where, rep, None)
                            if item.get('bullet_color') is not None:
                                rebuilt['bullet_color'] = item['bullet_color']
                            # A new item gets a fresh seed; only its tint digit has to match.
                            if tint_of(rebuilt['name_seed']) != tint_of(item['name_seed']):
                                yield where, 'DIFF', ('tint', tint_of(item['name_seed']), tint_of(rebuilt['name_seed']))
                                continue
                            rebuilt['name_seed'] = item['name_seed']
                    except PlanError as e:
                        yield where, 'FAIL', str(e)
                        continue
                    a, b = canonical(tree_sorted(item)), canonical(tree_sorted(rebuilt))
                    yield where, ('ok' if a == b else 'DIFF'), (a, b)


# --- field help (shown next to every field in the GUI) ---------------------------------------------
# Plain text; a blank line starts a new paragraph. Keys are '<entry kind>.<plan key path>'.

FIELD_HELP = {
    'file': 'A plan is a YAML file with any of the sections target, weapons, equipment, armor_sets, '
            'remove and profile. Only what a plan lists changes; everything else in the save stays as it is.\n\n'
            'Use one file per loadout or per item. Several files can be applied together and are merged in order.',
    'target.slot': 'Which character in the save the plan is for (0-based slot, as listed by "show" or the '
                   'save panel). Optional: a save with one character is picked automatically, and the '
                   '--slot option on the command line wins over this.',

    # shared by weapons, equipment and armor sets
    'entry.replace': 'Off: the item is added to the end of the inventory.\n\n'
                     'On: the item at this index is rebuilt in place, keeping its position (and equipped '
                     'state). Flags you leave unset (locked, new, tint, bullet colour) are copied from '
                     'the old item. Indices come from "show"/"dump" or the save panel.',
    'entry.replace.code': 'Safety check: the plan refuses to run unless the item at that index is this '
                          'code, so a plan written for an older copy of the save cannot hit the wrong item.',
    'entry.equip': 'Equip the item once the plan has run. Weapons go to their own slot type (heavy, '
                   'primary or secondary); equipment to the equipment slot; an armor set also repaints the '
                   'armor. Equipping happens before removals, so you can swap out and remove the old item '
                   'in one plan.',
    'entry.locked': 'Locked items are protected from scrapping (hold L3) and selling.',
    'entry.new': 'Shows the "new" marker on the item in the gear menu until you look at it.',
    'entry.tint': 'The colour tint the item is drawn with, 0-9. Each rarity has its own 10 tints, so the same '
                  'number can look different on another rarity. In the desktop editor, the swatch beside each '
                  'tint shows its three colours for the item\'s current rarity. Equipment only shows its tint in the '
                  'gear menu\'s preview, not when thrown.\n\n'
                  'Leave unset for a random tint (new items) or to keep the current one (replaced items).',

    'weapon.code': 'The weapon type. Its slot is fixed by type:\n\n'
                   'heavy: machine_gun, launcher, flamethrower, sphere_gun\n'
                   'primary: xenorifle (Bio-Specialist), smg (Saboteur), energy_gun (Tank)\n'
                   'secondary: powershot, shotgun, revolver, laser_gun\n\n'
                   'Only the primary is class-bound; another class\'s primary needs the weapon hack add-on. '
                   'sphere_gun and laser_gun need their own add-on (or All Weapons).',
    'weapon.rarity': 'stock, common, uncommon, rare or legendary (0-4). Rarity sets the damage table and '
                     'how big the upgrade tree is in game-made weapons:\n\n'
                     'stock/common: no sockets\nuncommon: 2 main + 2 branch 1\n'
                     'rare: 3 main + 3 branch 1 + perk\nlegendary: 5 main + 3 branch 1 + perk + 4 branch 2\n\n'
                     'Bigger trees than the rarity allows need "allow untested".',
    'weapon.level': 'Item level 1-30, as shown in game. Damage ranges scale with it, and so does the '
                    'strength of the perk effect.',
    'weapon.damage': 'max, mid, min, or a number. The game rolls damage = base x (1 +/- 12.5%), with the '
                     'base from item_levels.json for this rarity and level (a level-30 legendary rolls '
                     '2,696.30 - 3,466.68). Numbers outside the range need "allow untested".',
    'weapon.stats.fire_rate': 'Fire-rate multiplier: higher fires faster. The game rolls 0.875 - 1.125; '
                              'omitted = max.',
    'weapon.stats.charge_time': 'Charge-time multiplier (Devastator and Collapser, instead of fire rate): how long '
                                'the weapon takes to reach its maximum damage, which the game shows in seconds. '
                                'Lower gets there sooner. The game rolls 0.875 - 1.125; omitted = max (1.125).',
    'weapon.stats.clip_size': 'Clip-size multiplier. The range depends on the weapon: 0.875 - 1.125 for most, '
                              'smg 0.85 - 1.15, shotgun 0.65 - 1.35, revolver/powershot/launcher 0.625 - 1.375. '
                              'Omitted = max.',
    'weapon.stats.critical_hit_chance': 'Critical-hit-chance multiplier. The game rolls 0.75 - 1.25; omitted = max.',
    'weapon.sockets': 'The upgrade tree: a main path of up to 5 sockets, branch 1 (up to 3) hanging off main '
                      'socket 1 and ending in the perk, branch 2 (up to 4) hanging off main socket 2.\n\n'
                      'Click a socket to change its colour or core; click + to add one. Socket colours: '
                      'blue (Boost: fire rate), red (Power: damage), yellow (Utility: clip size), white (any). '
                      'Any core fits any socket; only matching colours give the bonus, and Prismatic cores '
                      'count as every colour. Neighbouring sockets of the same colour link up (synergy) '
                      'automatically. Core levels are 1-6.',
    'weapon.perk': 'A conditional action at the end of branch 1: when the cause happens, the effect fires. '
                   'Game-made weapons only have one once branch 1 holds 3 sockets (rare and legendary).',
    'weapon.perk.cause': 'When the perk fires. The game only ever rolls on_enemy_hit, on_enemy_hit_melee and '
                         'on_player_hit; the others exist in the code and menus but are untested.',
    'weapon.perk.effect': 'What happens. The game only ever rolls boomerang_at_target, chain_lightning_target, '
                          'cluster_shell_from_target and knockdown_target; the others are untested.',
    'weapon.perk.efficiency': 'Effect strength, 0.5 - 1.0 as rolled. Strength = base x weapon level x '
                              'efficiency: boomerang, chain lightning, knockdown, poison have base 100, '
                              'cluster shell and explosion 250 (boomerang at level 30, efficiency 1.0 = '
                              '3,000 HP per proc).',
    'weapon.perk.value': 'The cause\'s parameter (perk_value). For on_enemy_hit it is the trigger chance: '
                         '50 x value % per hit, fixed per weapon type by the game (smg 1/3 = 16.7%), plus a '
                         'guaranteed proc whenever no perk fired in the last 3 s. 2.0 = every hit.\n\n'
                         'Critical hits: 75 x value %; melee: 100 x value %. Range causes use it as distance '
                         '(5/10/30 x value m), low_ammo as a threshold (20 x value %).\n\n'
                         'Leave on "default" for the game\'s value; anything else needs "allow untested".',

    'equipment.code': 'The equipment type: grenade, cluster_grenade, mine, boomerang, or vortex_grenade (needs '
                      'the Vortex Grenade add-on or All Weapons). A character holds at most 10 equipment items.',
    'equipment.rarity': 'stock, common, uncommon, rare or legendary (0-4). Game-made equipment has a fixed '
                        'number of sockets: uncommon 2, rare 4, legendary 5 plus the perk.',
    'equipment.level': 'Item level 1-30, as shown in game. Damage ranges scale with it.',
    'equipment.damage': 'max, mid, min, or a number, from the same damage table as weapons '
                        '(level-30 legendary: 2,696.30 - 3,466.68).',
    'equipment.sockets': 'One row of up to 6 sockets (5 in game-made items). On equipment: blue/Boost = '
                         'effect radius, red/Power = damage, yellow/Utility = recharge rate (vortex: effect '
                         'lifetime). Click a socket to change it; click + to add one.',
    'equipment.perk': 'Attribute perks after the 5th socket (legendary only):\n\n'
                      'fast_recharge: doubles how fast it refills (rolled)\n'
                      'speed_jolt: movement-speed boost when thrown (rolled; the vortex grenade ignores it)\n'
                      'double_reserve: doubles how many you carry (never rolled, untested; only the vortex '
                      'grenade lists it)\n\n'
                      'Game-made items have one; ticking two is untested. Weapon cause/effect perks cannot '
                      'go on equipment.',

    'armor.rarity': '0 = stock (never has effects), 1 = looted (two effects). Higher is untested.',
    'armor.level': 'Item level 1-30, as shown in game.',
    'armor.colors': 'The four colour areas, in the gear menu\'s swatch order: plates, suit (underneath the '
                    'plates), visor, and accent (small details). Each has a colour, a glow, and a finish '
                    '(metallic and shine).\n\n'
                    'Untick a setting to keep it from the set that is worn when the savegame is saved.',
    'armor.color': 'The area\'s colour, "#rrggbb". It tints the armor\'s own texture, so dark or worn parts of '
                   'the design stay darker.',
    'armor.glow': 'Glow makes the area give off light in its own colour, as if it were lit from inside.\n\n'
                  'At 0 (none) the area is just painted armor, lit only by the scene. As glow goes up (faint, '
                  'medium, strong, full) the area\'s colour shines out more, so it stays visible in shadow and in '
                  'the dark.\n\n'
                  'It\'s an even fill. The glow covers the whole area at the same strength and ignores the '
                  'armor\'s texture, so a strong glow turns the area into a flat, bright patch of colour and the '
                  'plates and panel lines fade out.\n\n'
                  'Game-made sets barely use it. Only the visor ever gets glow, and at most 0.2 (faint), which '
                  'is what makes visors look lit. The accent area never glows; the game ignores its value.',
    'armor.finish': 'The finish is how the area catches the light. It has two settings, both 0 to 1.\n\n'
                    'Metallic: how much the area looks like metal, from painted or plastic (none) to bare metal '
                    '(full).\n\n'
                    'Shine: how polished it is, from dull like rubber (flat) to sharp highlights and clear '
                    'reflections (mirror). Full metallic with mirror shine looks like chrome.\n\n'
                    'Each has two separate numbers, not a range: one for the armor\'s surface and one for its '
                    'details. The armor\'s own texture decides which parts are which. Set both the same for an '
                    'even finish.',
    'armor.metallic': 'Metallic sets how much the area looks like metal.\n\n'
                      'At 0 (none) it looks painted or plastic: light bounces off in white highlights on top of '
                      'the colour. At 1 (full) it looks like bare metal: reflections take on the area\'s colour, '
                      'which gives a saturated, tinted look. Slight, half and mostly are in between.\n\n'
                      'Surface and Details are two separate settings, not a range. The armor\'s own texture '
                      'decides which parts are surface and which are details; where it is part-way, the two are '
                      'mixed. Set both the same for an even finish.\n\n'
                      'Game-made sets: plates about 0.4 (half), suit 0.7 (mostly), accent 0.8 (mostly), visor 1 '
                      '(full).',
    'armor.shine': 'Shine sets how polished the area looks.\n\n'
                   'At 0 (flat) it is dull, like rubber or cloth: light spreads into a soft, wide glow across the '
                   'surface. Going up through sheen and gloss, that tightens into smaller, brighter highlights. At '
                   '1 (mirror) the highlights are small and sharp and the surface shows clear reflections. Full '
                   'metallic with mirror shine looks like chrome.\n\n'
                   'Surface and Details are two separate settings, not a range, like metallic.\n\n'
                   'Game-made sets: plates and accent about 0.5 (sheen); suit 0.4 surface (sheen) and 0.7 details '
                   '(gloss); visor 0 surface (flat) and 1 details (mirror).',
    'armor.effects': 'Effects the set gives. The game rolls exactly two, from these values:\n\n'
                     'movement_speed 1.05\nmax_hp_multiplier 0.85 (only as a downside)\n'
                     'rush_recharge, health_drop_rate, ability_drop_rate: 1.1/1.2 or 0.9/0.8\n'
                     'ability_recharge_1/2/3: -1 or +1 seconds (negative is better)\n\n'
                     'Multipliers are 1 = neutral. Other values or counts need "allow untested".',

    'profile.level': 'Player level 1-30. The XP inside the level is kept when it still fits, and the '
                     'lifetime XP total moves by the same amount so menus stay consistent. Trophies for '
                     'skipped levels will not pop.',
    'profile.hero_level': 'Hero level 1-300; needs player level 30. A hero level costs '
                          '2,585,896 x (1 + hero // 10) XP.',
    'profile.keys': 'UFO keys (key1) and Ark Ship keys (key2).',
    'profile.cores': 'Loose cores in the inventory (not the ones slotted in gear), per type and level 1-6: '
                     'Boost (blue), Power (red), Utility (yellow), Prismatic (white).',
    'profile.metals': 'Salvage materials used to reroll weapon stats, per rarity. Unobtainium (metal5) '
                      'never appears in a game-made save and is untested.',
    'profile.credits': 'Credits.',
    'profile.flowers': 'Xenoflowers collected (save name "flower"), shown as XENOFLOWERS on the Resources '
                       'screen. Picking up a Xenoflower gives a short boost (XP, speed or melee); this is the '
                       'running count.',
    'remove': 'Items deleted from the savegame (the plan\'s remove: list). In the desktop editor, use an '
              'item\'s Delete button; Restore brings it back. In a plan file they are indices as shown by '
              '"show"/"dump", i.e. before the plan runs; later items shift down and the equipped pointers are '
              'fixed for you. An equipped item cannot be deleted unless something else is equipped in its '
              'slot.',
}
