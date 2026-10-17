"""Edit Alienation saves from human-friendly YAML plans: add, replace and remove weapons, equipment
and armor sets, and set resources (keys, cores, metals, credits, levels).

  python3 tools/save-editor-cli.py show  SAVE                         # characters, indexed inventory
  python3 tools/save-editor-cli.py dump  SAVE --slot 0 -o mine.yaml   # inventory as an editable plan
  python3 tools/save-editor-cli.py check plan.yaml [more.yaml ...]    # validate plans without a save
  python3 tools/save-editor-cli.py apply SAVE plan.yaml [more.yaml ...] --slot 0 -o OUT_DIR [--dry-run]
  python3 tools/save-editor-cli.py selftest                           # rebuild every item in savegames/

SAVE is a save folder (savedata.dat + sce_sys) or a savedata.dat file. OUT_DIR receives
savedata.dat and, when SAVE is a folder, a copy of sce_sys, ready to copy back to the console.

Plan format: docs/save-editor.md. Plans can also be edited in tools/save-editor-gui.py.
Both front ends share tools/lib/saveedit.py. Needs PyYAML (tools/requirements.txt).

Everything a plan asks for is checked against what game-made saves contain. Combinations never
seen in a real save are refused unless --allow-untested is given; anything merely unusual (e.g. a
weapon outside the character's class) is a warning.
"""
import argparse
import sys

import yaml

from lib import saveedit as core


def open_session(path):
    try:
        return core.SaveSession(path)
    except core.SaveEditError as e:
        sys.exit(str(e))


def print_report(rep, indent='  '):
    for line in rep.lines():
        print(f'{indent}{line}')


def cmd_show(args):
    session = open_session(args.save)
    for i, c in session.characters():
        if args.slot not in (None, 'all') and str(i) != str(args.slot):
            continue
        print(f'slot {i}: {core.character_summary(c)}')
        for section, j, _, text, mark in core.inventory_rows(c):
            tag = f' [{mark}]' if mark else ''
            print(f'  {section}[{j}]: {text}{tag}')


def cmd_dump(args):
    session = open_session(args.save)
    try:
        slots = session.slots_for([args.slot] if args.slot is not None else None)
    except core.SaveEditError as e:
        sys.exit(str(e))
    if len(slots) != 1:
        sys.exit('dump one character at a time (--slot N)')
    text = core.plan_to_yaml(core.dump_plan(session.root, slots[0]))
    if args.output:
        with open(args.output, 'w') as f:
            f.write(text)
        print(f'wrote {args.output}')
    else:
        print(text)


def cmd_check(args):
    failed = False
    for path in args.plans:
        print(f'{path}:')
        try:
            with open(path) as f:
                docs = core.parse_plan_text(f.read(), path)
        except core.PlanError as e:
            print(f'  error: {e}')
            failed = True
            continue
        for doc in docs:
            for key, rep in core.check_document(doc, path, args.allow_untested).items():
                print_report(rep)
                failed |= rep.failed()
    if failed:
        sys.exit('problems found (checks that need a save run with apply --dry-run)')
    print('ok (checks that need a save run with apply --dry-run)')


def cmd_apply(args):
    session = open_session(args.save)
    try:
        plan, target = core.load_plans(args.plans)
    except (core.PlanError, yaml.YAMLError) as e:
        sys.exit(f'plan error: {e}')
    try:
        slots = session.slots_for(args.slot, target)
    except core.SaveEditError as e:
        sys.exit(str(e))
    reports, data = session.apply(plan, slots, args.allow_untested)
    for slot, rep in reports.items():
        print(f'slot {slot} ({core.class_of(session.root["slots"][slot])}):')
        print_report(rep)
    if data is None:
        sys.exit('nothing written: fix the errors above')
    if args.dry_run:
        print(f'dry run: would write {len(data)} bytes')
        return
    if not args.output:
        sys.exit('give an output folder with -o (or --dry-run)')
    written = session.write(data, args.output)
    if len(written) > 1:
        print(f'copied sce_sys to {args.output}')


def cmd_selftest(args):
    total = bad = 0
    for where, status, detail in core.selftest():
        total += 1
        if status == 'ok':
            continue
        bad += 1
        print(f'{status} {where}{": " + detail if status == "FAIL" else ""}')
        if status == 'DIFF' and args.verbose:
            print('  save :', detail[0])
            print('  built:', detail[1])
    print(f'{total - bad}/{total} items rebuilt identically')
    if bad:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('show', help='list characters and their indexed inventory')
    p.add_argument('save')
    p.add_argument('--slot')
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser('dump', help="write one character's inventory as an editable plan")
    p.add_argument('save')
    p.add_argument('--slot')
    p.add_argument('-o', '--output')
    p.set_defaults(fn=cmd_dump)
    p = sub.add_parser('check', help='validate plan files without a save')
    p.add_argument('plans', nargs='+')
    p.add_argument('--allow-untested', action='store_true')
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser('apply', help='apply one or more plan files')
    p.add_argument('save')
    p.add_argument('plans', nargs='+')
    p.add_argument('--slot', action='append', help='character slot (repeatable) or "all"')
    p.add_argument('-o', '--output', help='output folder')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--allow-untested', action='store_true',
                   help='write combinations never seen in a game-made save (test one at a time)')
    p.set_defaults(fn=cmd_apply)
    p = sub.add_parser('selftest', help='rebuild every item in savegames/ from its dumped plan')
    p.add_argument('-v', '--verbose', action='store_true')
    p.set_defaults(fn=cmd_selftest)
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
