"""savedata.dat format: header and CRC, the Stated value stream codec, the value model
(Table/Tuple/Vec), key-name recovery, JSON conversion and safe output paths.

Command line: tools/research/savedata.py. File layout: tools/research/README.md and docs/file-formats.md.
"""
import hashlib
import os
import pickle
import re
import struct
import zlib
from collections import OrderedDict

from .common import CACHE_DIR, EBOOT_BIN, ROOT, STREAM_DAT, Stream

MAGIC = b'AYE!'
HEADER_SIZE = 0x14
HEADER_VERSION = 0x0401
STREAM_VERSION = 1
STAD_ID, STDD_ID = 0x124AF99, 0x1255D46

T_VOID, T_BOOL, T_INT, T_FLOAT = 0x01, 0x02, 0x03, 0x05
T_VEC = {0x0A: 2, 0x0B: 3, 0x0C: 4, 0x0D: 16}
T_STRING, T_LIST, T_TUPLE, T_TABLE = 0x0E, 0x10, 0x11, 0x12

from .gamedata import CORE_TYPES, SOCKET_COLOURS  # noqa: F401  (re-exported for research/savedata.py)
# Installed cores store a 0-based level: ('core2', 3) is a level-4 Power core. Inventory
# resource names (core2_4) and weapon upgrade_level + 1 are what the game displays.


def key_hash(name):
    return struct.unpack('<I', hashlib.md5(name.upper().encode()).digest()[:4])[0]


# --- value model -----------------------------------------------------------------------------

class Tuple(list):
    pass


class Vec(tuple):
    pass


class Table(OrderedDict):
    """Ordered map of u32 key hash -> value. Accepts names or hashes for lookup."""

    def _k(self, k):
        return k if isinstance(k, int) else key_hash(k)

    def __getitem__(self, k):
        return super().__getitem__(self._k(k))

    def __setitem__(self, k, v):
        super().__setitem__(self._k(k), v)

    def __contains__(self, k):
        return super().__contains__(self._k(k))

    def get(self, k, default=None):
        return super().get(self._k(k), default)


# --- binary codec ----------------------------------------------------------------------------

class Reader:
    def __init__(self, data):
        self.d, self.p = data, 0

    def take(self, fmt):
        v = struct.unpack_from(fmt, self.d, self.p)
        self.p += struct.calcsize(fmt)
        return v if len(v) > 1 else v[0]

    def value(self):
        start = self.p
        t = self.take('<B')
        if t == T_VOID:
            return None
        if t == T_BOOL:
            return bool(self.take('<B'))
        if t == T_INT:
            return self.take('<i')
        if t == T_FLOAT:
            return self.take('<f')
        if t in T_VEC:
            return Vec(self.take(f'<{T_VEC[t]}f'))
        if t == T_STRING:
            n = self.take('<I')
            s = self.d[self.p:self.p + n]
            self.p += n
            return s.decode('utf-8')
        if t in (T_LIST, T_TUPLE):
            n = self.take('<H')
            items = [self.value() for _ in range(n)]
            return Tuple(items) if t == T_TUPLE else items
        if t == T_TABLE:
            n = self.take('<H')
            tbl = Table()
            for _ in range(n):
                k = self.take('<I')
                OrderedDict.__setitem__(tbl, k, self.value())
            return tbl
        raise ValueError(f'unknown value tag {t:#x} at payload offset {start:#x}')


def write_value(out, v):
    if v is None:
        out += bytes([T_VOID])
    elif isinstance(v, bool):
        out += struct.pack('<BB', T_BOOL, v)
    elif isinstance(v, int):
        out += struct.pack('<Bi', T_INT, v)
    elif isinstance(v, float):
        out += struct.pack('<Bf', T_FLOAT, v)
    elif isinstance(v, Vec):
        tag = {n: t for t, n in T_VEC.items()}[len(v)]
        out += struct.pack(f'<B{len(v)}f', tag, *v)
    elif isinstance(v, str):
        b = v.encode('utf-8')
        out += struct.pack('<BI', T_STRING, len(b)) + b
    elif isinstance(v, Table):
        out += struct.pack('<BH', T_TABLE, len(v))
        for k, item in OrderedDict.items(v):
            out += struct.pack('<I', k)
            write_value(out, item)
    elif isinstance(v, list):
        out += struct.pack('<BH', T_TUPLE if isinstance(v, Tuple) else T_LIST, len(v))
        for item in v:
            write_value(out, item)
    else:
        raise TypeError(f'cannot encode {type(v).__name__}: {v!r}')


def decode_payload(payload):
    if payload[0] != STREAM_VERSION:
        raise ValueError(f'unsupported value stream version {payload[0]}')
    r = Reader(payload)
    r.p = 1
    root = r.value()
    if r.p != len(payload):
        raise ValueError(f'trailing data after root value ({len(payload) - r.p} bytes)')
    return root


def encode_payload(root):
    out = bytearray([STREAM_VERSION])
    write_value(out, root)
    return bytes(out)


# --- file wrapper ----------------------------------------------------------------------------

class SaveFile:
    def __init__(self, raw):
        if len(raw) < HEADER_SIZE or raw[:4] != MAGIC:
            raise ValueError('not an Alienation savedata.dat (bad magic)')
        self.raw = raw
        self.crc, self.data_offset, self.length, self.header_version = struct.unpack_from('<IIIH', raw, 4)
        end = self.data_offset + self.length
        if end > len(raw):
            raise ValueError('payload runs past end of file')
        self.crc_ok = zlib.crc32(raw[8:end]) == self.crc
        self.payload = raw[self.data_offset:end]
        self.root = decode_payload(self.payload)

    @classmethod
    def load(cls, path):
        with open(path, 'rb') as f:
            return cls(f.read())

    def build(self, root=None):
        """New file bytes. Keeps the original file size: the game writes its whole fixed-size
        buffer, so bytes past the payload are leftovers and are kept as-is."""
        payload = encode_payload(self.root if root is None else root)
        capacity = len(self.raw) - HEADER_SIZE
        if len(payload) > capacity:
            raise ValueError(f'payload is {len(payload)} bytes; the save buffer holds {capacity}')
        buf = bytearray(self.raw)
        buf[HEADER_SIZE:HEADER_SIZE + len(payload)] = payload
        struct.pack_into('<4sIIIH', buf, 0, MAGIC, 0, HEADER_SIZE, len(payload), HEADER_VERSION)
        struct.pack_into('<I', buf, 4, zlib.crc32(buf[8:HEADER_SIZE + len(payload)]))
        return bytes(buf)


class OutputPathError(SystemExit):
    """A refused output path. Exits like sys.exit(msg) when uncaught; GUIs can catch it."""


def check_output_path(path, inputs=()):
    """Refuse to overwrite one of the files being read."""
    for i in inputs:
        if os.path.exists(path) and os.path.samefile(path, i):
            raise OutputPathError('refusing to overwrite an input file')


def write_output(path, data, inputs=()):
    check_output_path(path, inputs)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    print(f'wrote {path} ({len(data)} bytes)')


# --- key names -------------------------------------------------------------------------------

def load_names():
    """hash -> lower-case name, built from strings in STAD, STDD and the eboot (cached)."""
    st = os.stat(STREAM_DAT)
    path = os.path.join(CACHE_DIR, f'keynames_{st.st_size}_{int(st.st_mtime)}.pkl')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return pickle.load(f)
    s = Stream()
    blobs = [s.record(STAD_ID)['data'], s.record(STDD_ID)['data']]
    with open(EBOOT_BIN, 'rb') as f:
        blobs.append(f.read())
    words = set()
    for blob in blobs:
        for m in re.finditer(rb'[\x20-\x7e]{1,80}', blob):
            w = m.group()
            words.add(w)
            words.update(p for p in re.split(rb'[:.\s,()\[\]"\'=]+', w) if p)
    names = {}
    for w in sorted(words):
        name = w.decode().lower()
        names.setdefault(key_hash(name), name)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(names, f)
    return names


# --- JSON conversion -------------------------------------------------------------------------

def to_json(v, names):
    if isinstance(v, Table):
        return OrderedDict((names.get(k, f'#{k:08x}'), to_json(x, names)) for k, x in OrderedDict.items(v))
    if isinstance(v, Tuple):
        return {'$tuple': [to_json(x, names) for x in v]}
    if isinstance(v, Vec):
        return {('$mtx44' if len(v) == 16 else f'$vec{len(v)}'): list(v)}
    if isinstance(v, list):
        return [to_json(x, names) for x in v]
    return v


def from_json(v):
    if isinstance(v, dict):
        if len(v) == 1:
            (k, x), = v.items()
            if k == '$tuple':
                return Tuple(from_json(i) for i in x)
            if k in ('$vec2', '$vec3', '$vec4', '$mtx44'):
                return Vec(float(i) for i in x)
        t = Table()
        for k, x in v.items():
            OrderedDict.__setitem__(t, int(k[1:], 16) if k.startswith('#') else key_hash(k), from_json(x))
        return t
    if isinstance(v, list):
        return [from_json(x) for x in v]
    return v


def tree_lines(v, names, indent=0):
    pad = '  ' * indent
    items = ([(names.get(k, f'#{k:08x}'), x) for k, x in OrderedDict.items(v)] if isinstance(v, Table)
             else [(f'[{i}]', x) for i, x in enumerate(v)])
    for label, x in items:
        if isinstance(x, (Table, list)):
            kind = 'table' if isinstance(x, Table) else 'tuple' if isinstance(x, Tuple) else 'list'
            yield f'{pad}{label}: {kind}[{len(x)}]'
            yield from tree_lines(x, names, indent + 1)
        else:
            yield f'{pad}{label}: {fmt_scalar(x)}'


def fmt_scalar(x):
    if x is None:
        return 'nil'
    if isinstance(x, bool):
        return 'true' if x else 'false'
    if isinstance(x, float):
        return f'{x:g}f'
    if isinstance(x, Vec):
        return 'vec(' + ', '.join(f'{a:g}' for a in x) + ')'
    return repr(x)
