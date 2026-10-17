"""Disassemble Housemarque Stated bytecode from stream.dat (STAD + STDD records).

  python3 tools/research/stated.py list [FILTER]            # state machines (index, name, state count)
  python3 tools/research/stated.py sm Debug.Debug_Keys      # disassemble every state of one machine
  python3 tools/research/stated.py at 0xd91b2               # disassemble from a bytecode offset
  python3 tools/research/stated.py calls FUNCTION_NAME      # state machines/states that call a native fn
  python3 tools/research/stated.py strings TEXT             # state machines/states that push a string

STAD layout (offsets in the decompressed record):
  +0x04/+0x08  state machine records (0x80 bytes each), +0x0C/+0x10 native function table (u32 each),
  +0x14/+0x18  bytecode start/length, +0x20/+0x24 string table: (u32 key hash, u32 offset) per id.
Native function entry: low 16 bits = string id of the name, byte 2 = arg count, byte 3 = return count.
State machine record: +0x00 name string id, +0x04/+0x08 start-code list, +0x0C/+0x10 state groups.
State group (0x3C bytes): +0x00 name string id, +0x14/+0x18 state list, +0x2C GUID;
  state = (u16, u16, u32 code offset, GUID).
STDD maps GUIDs to "SM:Group:State" names as (GUID, u32 0, u32 name offset) entries.
"""
import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/, for lib

from lib.common import Stream

STAD_ID, STDD_ID = 0x124AF99, 0x1255D46

OPS = ('Reserve PushVoid IsVoid PushFalse PushTrue PushFloat32 PushInt8 PushInt32 PushString PushBlock '
       'Join Get Adjust Swap Set Drop StoreHas StoreGet StoreTryGet StoreNew StorePut StoreRem SelfHas '
       'SelfGet SelfTryGet SelfPut SelfRem Jmp JmpIf JmpIfNot Ret CallExt Abs Neg Add Addr Div Divr Mod '
       'Modr Mul Mulr Sub Subr CmpEQ CmpNE CmpGE CmpGT CmpLE CmpLT LogicalNot StreamBegin StreamNextJmp0 '
       'StreamNextJmp1 QueryNew QueryAddTail Exit Die Reject Accept Implode Explode Project ArrayNew Sync '
       'UncheckedSync Self Old RefNew RefGet RefPut').split()

# Operand formats, from the eboot's codegen instruction walker (jump table at 0x17b6f30).
U8 = {'Reserve', 'Join', 'Get', 'Swap', 'Set', 'Drop', 'Implode', 'Explode', 'Project', 'ArrayNew'}
U16 = {'PushString', 'Adjust'}
U32 = {'PushInt32', 'StoreHas', 'StoreGet', 'StoreTryGet', 'StorePut', 'StoreRem',
       'SelfHas', 'SelfGet', 'SelfTryGet', 'SelfPut', 'SelfRem'}
JUMPS = {'PushBlock', 'Jmp', 'JmpIf', 'JmpIfNot', 'StreamNextJmp0', 'StreamNextJmp1'}
HASH_OPS = {'StoreHas', 'StoreGet', 'StoreTryGet', 'StorePut', 'StoreRem',
            'SelfHas', 'SelfGet', 'SelfTryGet', 'SelfPut', 'SelfRem'}
ENDS = {'Ret', 'Exit', 'Die', 'Reject', 'Accept', 'Jmp'}


class Stated:
    def __init__(self):
        s = Stream()
        self.d = d = s.record(STAD_ID)['data']
        self.dbg = s.record(STDD_ID)['data']
        (self.sm_off, self.sm_n, self.fn_off, self.fn_n, self.bc_off, self.bc_len,
         _, self.str_off, self.str_n) = struct.unpack_from('<9I', d, 4)
        self.str_tab = [struct.unpack_from('<II', d, self.str_off + 8 * i) for i in range(self.str_n)]
        self.by_hash = {}
        for i, (h, _) in enumerate(self.str_tab):
            self.by_hash.setdefault(h, i)
        self.fns = struct.unpack_from(f'<{self.fn_n}I', d, self.fn_off)
        self._guid_names = None

    def string(self, i):
        if not 0 <= i < self.str_n:
            return f'<bad string {i}>'
        o = self.str_tab[i][1]
        return self.d[o:self.d.index(b'\0', o)].decode('utf-8', 'replace')

    def hash_name(self, h):
        i = self.by_hash.get(h)
        return self.string(i) if i is not None else f'#{h:08x}'

    def fn(self, i):
        if not 0 <= i < self.fn_n:
            return f'<bad fn {i}>', 0, 0
        e = self.fns[i]
        return self.string(e & 0xFFFF), (e >> 16) & 0xFF, e >> 24

    @property
    def guid_names(self):
        if self._guid_names is None:
            names, dbg = {}, self.dbg
            for m in re.finditer(rb'\x00\x00\x00\x00', dbg):
                p = m.start()
                if p < 16 or p + 8 > len(dbg):
                    continue
                off = struct.unpack_from('<I', dbg, p + 4)[0]
                if 0 < off < len(dbg) and dbg[off - 1:off] == b'\0':
                    end = dbg.find(b'\0', off)
                    name = dbg[off:end]
                    if b':' in name and all(32 <= c < 127 for c in name):
                        names.setdefault(dbg[p - 16:p], name.decode())
            self._guid_names = names
        return self._guid_names

    # --- state machines ---

    def machines(self):
        for i in range(self.sm_n):
            r = struct.unpack_from('<8I', self.d, self.sm_off + 0x80 * i)
            yield i, self.string(r[0]), r

    def find_machine(self, name):
        for i, n, r in self.machines():
            if n == name:
                return i, r
        raise SystemExit(f'no state machine named {name!r}')

    def states(self, r):
        """Yield (label, code offset) for the start code and every state of an SM record."""
        start_off, start_n, grp_off, grp_n = r[1], r[2], r[3], r[4]
        for k in range(start_n):
            code = struct.unpack_from('<I', self.d, start_off + 0x18 * k + 4)[0]
            yield '<start>', code
        for g in range(grp_n):
            gr = struct.unpack_from('<8I', self.d, grp_off + 0x3C * g)
            gname = self.string(gr[0]) if gr[0] < self.str_n else f'group{g}'
            st_off, st_n = gr[5], gr[6]
            for k in range(st_n):
                e = st_off + 0x18 * k
                code = struct.unpack_from('<I', self.d, e + 4)[0]
                guid = self.d[e + 8:e + 24]
                label = self.guid_names.get(guid, f'{gname}:state{k}')
                yield label, code

    # --- disassembly ---

    def decode(self, pc):
        """Decode one instruction at bytecode offset pc -> (name, operand, next_pc)."""
        d, base = self.d, self.bc_off
        op = d[base + pc]
        name = OPS[op] if op < len(OPS) else f'op{op:#x}'
        p = base + pc + 1
        if op >= len(OPS):
            raise ValueError(f'invalid opcode {op:#x} at {pc:#x}')
        if name in U8:
            arg, p = d[p], p + 1
        elif name == 'PushInt8':
            arg, p = struct.unpack_from('<b', d, p)[0], p + 1
        elif name in U16:
            arg, p = struct.unpack_from('<H', d, p)[0], p + 2
        elif name == 'CallExt':
            arg, p = struct.unpack_from('<h', d, p)[0], p + 2
        elif name == 'PushFloat32':
            arg, p = struct.unpack_from('<f', d, p)[0], p + 4
        elif name in U32 or name in JUMPS:
            arg, p = struct.unpack_from('<I', d, p)[0], p + 4
        else:
            arg = None
        return name, arg, p - base

    def fmt(self, name, arg):
        if arg is None:
            return name
        if name == 'PushString':
            return f'{name} {self.string(arg)!r}'
        if name in HASH_OPS:
            return f'{name} {self.hash_name(arg)}'
        if name == 'CallExt':
            fname, nargs, nret = self.fn(arg)
            return f'{name} {fname}({nargs})->{nret}'
        if name in JUMPS:
            return f'{name} L_{arg:06x}'
        if name == 'PushInt32':
            return f'{name} {arg} ({arg:#x})'
        if name == 'PushFloat32':
            return f'{name} {arg:g}'
        return f'{name} {arg}'

    def walk(self, entry):
        """Recursive-descent disassembly from entry; returns {pc: (name, arg, next)}."""
        seen, todo = {}, [entry]
        while todo:
            pc = todo.pop()
            while pc not in seen and 0 <= pc < self.bc_len:
                try:
                    name, arg, nxt = self.decode(pc)
                except ValueError:
                    break
                seen[pc] = (name, arg, nxt)
                if name in JUMPS:
                    todo.append(arg)
                if name in ENDS:
                    break
                pc = nxt
        return seen

    def listing(self, entry):
        code = self.walk(entry)
        targets = {a for (n, a, _) in code.values() if n in JUMPS}
        out = []
        for pc in sorted(code):
            if pc in targets:
                out.append(f'L_{pc:06x}:')
            name, arg, _ = code[pc]
            out.append(f'  {pc:06x}  {self.fmt(name, arg)}')
        return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list').add_argument('filter', nargs='?', default='')
    sub.add_parser('sm').add_argument('name')
    sub.add_parser('at').add_argument('offset', type=lambda s: int(s, 0))
    sub.add_parser('calls').add_argument('function')
    sub.add_parser('strings').add_argument('text')
    a = ap.parse_args()
    st = Stated()

    if a.cmd == 'list':
        for i, n, r in st.machines():
            if a.filter.lower() in n.lower():
                print(f'{i:4} {n}  ({sum(1 for _ in st.states(r))} code entries)')
    elif a.cmd == 'sm':
        _, r = st.find_machine(a.name)
        for label, code in st.states(r):
            print(f'\n=== {label}  @ {code:#x}')
            print('\n'.join(st.listing(code)))
    elif a.cmd == 'at':
        print('\n'.join(st.listing(a.offset)))
    elif a.cmd in ('calls', 'strings'):
        for i, n, r in st.machines():
            for label, code in st.states(r):
                for name, arg, _ in st.walk(code).values():
                    hit = (a.cmd == 'calls' and name == 'CallExt' and st.fn(arg)[0] == a.function) or \
                          (a.cmd == 'strings' and name == 'PushString' and a.text in st.string(arg))
                    if hit:
                        print(f'{n}  {label}  @ {code:#x}')
                        break


if __name__ == '__main__':
    sys.exit(main())
