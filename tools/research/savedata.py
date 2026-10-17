"""Read, inspect and rebuild Alienation savedata.dat files.

  python3 tools/research/savedata.py info    SAVE                    # validate header/CRC, summary
  python3 tools/research/savedata.py tree    SAVE [-o tree.txt]      # whole save as an indented tree
  python3 tools/research/savedata.py weapons SAVE [--slot 0]         # weapons with slots, cores and perks
  python3 tools/research/savedata.py cores   SAVE [--slot 0]         # core inventory grid
  python3 tools/research/savedata.py export  SAVE -o save.json       # editable JSON
  python3 tools/research/savedata.py import  save.json --base SAVE -o out/savedata.dat
  python3 tools/research/savedata.py set     SAVE -o out/savedata.dat core1_3=20 core4_6=5 metal4=999

File layout (see tools/README.md): "AYE!" header with CRC32, then a Stated value stream:
a version byte (1) followed by one tagged value. Table keys are the first little-endian u32 of
MD5(key.upper()), so key names are case-insensitive and recovered from game strings.

JSON conventions: tables are objects (unknown keys appear as "#xxxxxxxx"), lists are arrays,
ints/floats/bools/strings/null map directly (floats always carry a decimal point), and the
remaining types are wrapped: {"$tuple": [...]}, {"$vec2|3|4": [...]}, {"$mtx44": [...]}.
"""
import argparse
import json
import os
import re
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/, for lib

from lib.savedata import (CORE_TYPES, HEADER_SIZE, SOCKET_COLOURS, SaveFile, Table, check_output_path,
                          encode_payload, from_json, load_names, to_json, tree_lines, write_output)


# --- game-level views ------------------------------------------------------------------------

def character(root, slot):
    c = root['slots'][slot]
    if c is None:
        sys.exit(f'save slot {slot} is empty')
    return c


def describe_upgrade(u):
    kind = u.get('type')
    tree = ''
    if 'branch_root' in u:
        tree = f" root{u['branch_root']}"
    elif 'branch' in u:
        tree = f" b{u['branch']}"
    syn = ''.join(s for s, k in (('<', 'prev'), ('>', 'next')) if k in u.get('synergy', Table()))
    if kind == 'perk' and 'perk_id' in u:
        return (f"perk  {u.get('perk_id')} ({u.get('perk_value', 0):g}) -> {u.get('effect_id')} "
                f"x{u.get('effect_efficiency', 0):.3f}{tree}")
    if kind == 'perk':
        return f"perk  {u.get('attribute')}{tree}"
    core = u.get('core')
    filled = f'{core[0]} L{core[1] + 1}' if core else 'empty'
    if core and not 0 <= core[1] <= 5:
        filled += ' (INVALID: stored level must be 0-5)'
    attr = f" attr={u['attribute']}" if 'attribute' in u else ''
    colour = f'{kind} ({SOCKET_COLOURS.get(kind, "?")})'
    return f'socket {colour:<15} {filled}{syn and " synergy" + syn}{tree}{attr}'


def cmd_weapons(save, args):
    inv = character(save.root, args.slot)['inventory']
    active = inv.get('active_weapons', [])
    for group in ('weapons', 'items'):
        print(f'== {group}')
        for i, w in enumerate(inv.get(group, [])):
            tag = ''
            if group == 'weapons' and i in active:
                tag = ['', ' [primary]', ' [secondary]', ' [heavy]'][active.index(i)]
            print(f"[{i}] {w.get('code')} rarity={w.get('rarity')} level={w.get('upgrade_level', 0) + 1} "
                  f"locked={bool(w.get('lock'))}{tag}")
            for m in w.get('modifiers', []):
                print(f"      stat   {m.get('code')} = {m.get('multiplier'):g}")
            for j, u in enumerate(w.get('upgrades', [])):
                print(f'      {j:2} {describe_upgrade(u)}')


def core_counts(inv):
    counts = {}
    for r in inv.get('resources', []):
        m = re.fullmatch(r'core(\d)_(\d)', r.get('name', ''))
        if m:
            counts[int(m.group(1)), int(m.group(2))] = r.get('count')
    return counts


def cmd_cores(save, args):
    inv = character(save.root, args.slot)['inventory']
    counts = core_counts(inv)
    print('type          ' + ''.join(f'  L{lv:<4}' for lv in range(1, 7)))
    for t, name in CORE_TYPES.items():
        cells = ''.join(f"  {counts.get((t, lv), '-'):<5}" for lv in range(1, 7))
        print(f'core{t} {name:<9}{cells}')
    others = [(r.get('name'), r.get('count')) for r in inv.get('resources', [])
              if not re.fullmatch(r'core\d_\d', r.get('name', ''))]
    print('other: ' + ', '.join(f'{n}={c}' for n, c in others))


def cmd_set(save, args):
    check_output_path(args.out, [args.save])
    inv = character(save.root, args.slot)['inventory']
    res = inv['resources']
    for spec in args.assignments:
        name, _, val = spec.partition('=')
        if not val.lstrip('-').isdigit():
            sys.exit(f'bad assignment {spec!r}; expected name=integer')
        for r in res:
            if r.get('name') == name:
                old = r.get('count')
                r['count'] = int(val)
                break
        else:
            entry = Table()
            entry['name'] = name
            entry['count'] = int(val)
            res.append(entry)
            old = '(new)'
        print(f'{name}: {old} -> {val}')
    write_output(args.out, save.build(), [args.save])


def cmd_info(save, args):
    print(f'payload {save.length} bytes, buffer {len(save.raw) - HEADER_SIZE} bytes, '
          f'header version {save.header_version:#06x}, crc {"OK" if save.crc_ok else "MISMATCH"}')
    rebuilt = encode_payload(save.root)
    print('re-encode: ' + ('byte-identical' if rebuilt == save.payload else 'DIFFERS'))
    root = save.root
    print(f"save version {root.get('version')}, latest slot {root.get('latest_slot')}")
    for i, c in enumerate(root.get('slots', [])):
        if c is not None:
            inv = c['inventory']
            print(f"slot {i}: {c.get('id')}  mode={c.get('game_mode')}  "
                  f"weapons={len(inv.get('weapons', []))}  items={len(inv.get('items', []))}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('info', 'tree', 'weapons', 'cores', 'export', 'set'):
        p = sub.add_parser(name)
        p.add_argument('save')
        p.add_argument('--slot', type=int, default=0)
        if name in ('tree', 'export', 'set'):
            p.add_argument('-o', '--out', required=name != 'tree')
        if name == 'set':
            p.add_argument('assignments', nargs='+', metavar='NAME=COUNT')
    p = sub.add_parser('import')
    p.add_argument('json')
    p.add_argument('--base', required=True, help='original savedata.dat (supplies buffer size)')
    p.add_argument('-o', '--out', required=True)
    args = ap.parse_args()

    if args.cmd == 'import':
        with open(args.json) as f:
            root = from_json(json.load(f, object_pairs_hook=OrderedDict))
        base = SaveFile.load(args.base)
        write_output(args.out, base.build(root), [args.base, args.json])
        return

    save = SaveFile.load(args.save)
    if not save.crc_ok:
        print('warning: CRC mismatch; the game would ignore this file', file=sys.stderr)
    if args.cmd == 'info':
        cmd_info(save, args)
    elif args.cmd == 'tree':
        text = '\n'.join(tree_lines(save.root, load_names()))
        if args.out:
            check_output_path(args.out, [args.save])
            with open(args.out, 'w') as f:
                f.write(text + '\n')
        else:
            print(text)
    elif args.cmd == 'export':
        check_output_path(args.out, [args.save])
        with open(args.out, 'w') as f:
            json.dump(to_json(save.root, load_names()), f, indent=1)
        print(f'wrote {args.out}')
    elif args.cmd == 'weapons':
        cmd_weapons(save, args)
    elif args.cmd == 'cores':
        cmd_cores(save, args)
    elif args.cmd == 'set':
        cmd_set(save, args)


if __name__ == '__main__':
    main()
