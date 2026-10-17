"""Disassemble eboot.bin at a virtual address, annotating RIP-relative targets and strings.

  python3 tools/research/disasm.py 0x3b5f60                 # save header validation
  python3 tools/research/disasm.py 0x4607c6 -f -n 300       # back up to the enclosing function first
  python3 tools/research/disasm.py 0x3b5b20 --stop-ret      # stop at the first ret

Requires capstone (pip install -r tools/requirements.txt).
"""
import argparse
import os
import re
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/, for lib

from lib.common import EBOOT_BIN, Eboot

RIP_REL = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')
PROLOGUE = b'\x55\x48\x89\xe5'  # push rbp; mov rbp, rsp


def func_start(eb, vaddr, max_back=0x8000):
    """Nearest preceding frame-pointer prologue (the build keeps frame pointers)."""
    for x in range(vaddr, max(0, vaddr - max_back), -1):
        if eb.read(x, 4) == PROLOGUE:
            return x
    return vaddr


def disasm(eb, start, count, stop_ret=False):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    lines = []
    for i in md.disasm(eb.read(start, count * 15), start):
        cmt = ''
        m = RIP_REL.search(i.op_str)
        if m:
            t = i.address + i.size + int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
            s = eb.cstr(t)
            cmt = f'  ; {t:#x}' + (f' "{s}"' if s else '')
        lines.append(f'{i.address:08x}: {i.mnemonic} {i.op_str}{cmt}')
        if len(lines) >= count or (stop_ret and i.mnemonic == 'ret'):
            break
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('addr', type=lambda s: int(s, 16))
    ap.add_argument('-n', '--count', type=int, default=200, help='max instructions')
    ap.add_argument('-f', '--function', action='store_true', help='start at the enclosing function')
    ap.add_argument('--stop-ret', action='store_true', help='stop at the first ret')
    ap.add_argument('--eboot', default=EBOOT_BIN)
    a = ap.parse_args()

    eb = Eboot(a.eboot)
    start = a.addr
    if a.function:
        start = func_start(eb, a.addr)
        print(f'function @ {start:#x}')
    print(disasm(eb, start, a.count, a.stop_ret))


if __name__ == '__main__':
    main()
