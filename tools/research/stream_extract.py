"""Extract one stream.dat record and list its pointer fixups.

  python3 tools/research/stream_extract.py 0x124af99 -o stad.bin      # STAD: compiled Stated program
  python3 tools/research/stream_extract.py 0x1255d46 -o stdd.bin      # STDD: Stated debug names
  python3 tools/research/stream_extract.py 0x17c --types              # SCRM, with fixup target types
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/, for lib

from lib.common import STREAM_DAT, Stream


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('id', type=lambda s: int(s, 0), help='record id (file offset / 0x40)')
    ap.add_argument('-o', '--out', help='write decompressed payload to this file')
    ap.add_argument('--stream', default=STREAM_DAT)
    ap.add_argument('--types', action='store_true', help='show the fourcc of each fixup target')
    a = ap.parse_args()

    s = Stream(a.stream)
    r = s.record(a.id)
    print(f"{r['cc']} id={a.id:#x} zsize={r['zs']:#x} size={r['sz']:#x} "
          f"internal_fixups={len(r['ints'])} external_fixups={len(r['fix'])}")
    for t, o in r['fix']:
        cc = ''
        if a.types:
            h = s.header(t)
            cc = h['cc'] if h else '<invalid>'
        print(f'  +{o:#x} -> {t:#x} {cc}')
    if a.out:
        with open(a.out, 'wb') as f:
            f.write(r['data'])
        print(f"wrote {len(r['data'])} bytes to {a.out}")


if __name__ == '__main__':
    main()
