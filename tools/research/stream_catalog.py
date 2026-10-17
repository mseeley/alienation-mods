"""Walk the stream.dat record graph from the MFST manifests and catalogue record types.

  python3 tools/research/stream_catalog.py                       # counts per fourcc
  python3 tools/research/stream_catalog.py --list SCRI           # ids of every SCRI record
  python3 tools/research/stream_catalog.py --dump SCRI out/      # extract every SCRI (Lua render scripts)

Some manifests (e.g. STAM, STDM) reference their target by an id inside the payload rather than
a fixup, so those targets are not reached by this walk; extract them with stream_extract.py.
"""
import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/, for lib

from lib.common import STREAM_DAT, Stream


def walk(s):
    seen, stack = {}, list(s.manifest_roots())
    while stack:
        rid = stack.pop()
        if rid in seen:
            continue
        h = seen[rid] = s.header(rid)
        if h:
            stack.extend(t for t, _ in h['fix'] if t not in seen)
    return seen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stream', default=STREAM_DAT)
    ap.add_argument('--list', metavar='FOURCC')
    ap.add_argument('--dump', nargs=2, metavar=('FOURCC', 'DIR'))
    a = ap.parse_args()

    s = Stream(a.stream)
    seen = walk(s)
    good = {k: v for k, v in seen.items() if v}
    want = a.list or (a.dump and a.dump[0])
    if want:
        ids = sorted(k for k, v in good.items() if v['cc'] == want)
        if a.dump:
            os.makedirs(a.dump[1], exist_ok=True)
        for rid in ids:
            if a.dump:
                path = os.path.join(a.dump[1], f'{want.strip()}_{rid:08x}.bin')
                with open(path, 'wb') as f:
                    f.write(s.record(rid)['data'])
            print(f'{rid:#x}')
        return
    print(f'reachable records: {len(good)}, unresolved refs: {len(seen) - len(good)}')
    for cc, n in collections.Counter(v['cc'] for v in good.values()).most_common():
        print(f'  {cc} {n}')


if __name__ == '__main__':
    main()
