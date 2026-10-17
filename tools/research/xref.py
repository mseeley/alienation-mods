"""Find code that references a string in eboot.bin via RIP-relative lea/mov.

  python3 tools/research/xref.py savedata.dat persistence_set_data

Only `lea/mov r64, [rip+disp32]` is indexed; strings loaded through SIMD moves, relocations or
pointer tables will show no references. The index is cached in tools/.cache/.
"""
import argparse
import collections
import os
import pickle
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/, for lib

from lib.common import CACHE_DIR, EBOOT_BIN, Eboot

LEA_MOV_RIP = re.compile(rb'[\x48\x4c][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]')


def build_index(eb):
    refs = collections.defaultdict(list)
    text = eb.d[eb.BASE:eb.BASE + eb.TEXT_SIZE]
    for m in LEA_MOV_RIP.finditer(text):
        a = m.start()
        disp = struct.unpack_from('<i', text, a + 3)[0]
        refs[a + 7 + disp].append(a)
    return dict(refs)


def load_index(eb):
    st = os.stat(eb.path)
    path = os.path.join(CACHE_DIR, f'xref_{st.st_size}_{int(st.st_mtime)}.pkl')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return pickle.load(f)
    refs = build_index(eb)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(refs, f)
    return refs


def string_vaddrs(eb, s):
    b = s.encode() + b'\0'
    return [m.start() - eb.BASE for m in re.finditer(re.escape(b), eb.d) if eb.d[m.start() - 1] == 0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('strings', nargs='+')
    ap.add_argument('--eboot', default=EBOOT_BIN)
    a = ap.parse_args()

    eb = Eboot(a.eboot)
    refs = load_index(eb)
    for s in a.strings:
        hits = string_vaddrs(eb, s)
        if not hits:
            print(f'{s!r}: not found')
        for v in hits:
            print(f'{s!r} @ {v:#x}: ' + (' '.join(f'{x:#x}' for x in refs.get(v, [])) or 'no code refs'))


if __name__ == '__main__':
    main()
