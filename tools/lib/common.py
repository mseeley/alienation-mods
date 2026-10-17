"""Shared helpers for the Alienation (CUSA04181) dump: stream.dat records and eboot.bin access."""
import mmap
import os
import struct
import zlib

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # tools/
ROOT = os.path.dirname(TOOLS_DIR)
GAME_DIR = os.path.join(ROOT, 'dumps', 'CUSA04181-patch0_ALIENATION')
STREAM_DAT = os.path.join(GAME_DIR, 'stream.dat')
EBOOT_BIN = os.path.join(GAME_DIR, 'eboot.bin')
CACHE_DIR = os.path.join(TOOLS_DIR, '.cache')


class Stream:
    """stream.dat: records aligned to 0x40 bytes; a record's id is its file offset / 0x40.

    Record header:
      +0x00 u32 id, +0x04 u32 zsize, +0x08 u32 size, +0x0C u32 ?, +0x10 u32 id
      +0x14 fourcc (stored reversed), +0x18 u32 version, +0x1C u32 n_internal, +0x20 u64 n_external
      +0x28 n_internal * u32 offset           (pointers into this record)
      (align 8) n_external * (u32 target_id, u32 offset)   (pointers to other records)
      then the payload: zlib if zsize != size, raw otherwise.
    """

    def __init__(self, path=STREAM_DAT):
        self.f = open(path, 'rb')
        self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)

    def header(self, rid):
        """Parse a record header, or return None if no valid record starts at this id."""
        off = rid * 0x40
        if off + 0x28 > len(self.m):
            return None
        i, zs, sz, c, i2 = struct.unpack_from('<5I', self.m, off)
        if i != rid or i2 != rid:
            return None
        cc = self.m[off + 0x14:off + 0x18][::-1].decode('latin1')
        ver, ni, ne = struct.unpack_from('<IIQ', self.m, off + 0x18)
        ints = list(struct.unpack_from(f'<{ni}I', self.m, off + 0x28))
        eo = (off + 0x28 + 4 * ni + 7) & ~7
        fix = [struct.unpack_from('<II', self.m, eo + 8 * k) for k in range(ne)]
        return dict(id=rid, cc=cc, ver=ver, c=c, zs=zs, sz=sz, ints=ints, fix=fix, zo=eo + 8 * ne)

    def record(self, rid):
        """Parse a record and return its header plus decompressed payload under 'data'."""
        h = self.header(rid)
        if h is None:
            raise ValueError(f'no record at id {rid:#x}')
        raw = self.m[h['zo']:h['zo'] + h['zs']]
        h['data'] = zlib.decompress(raw) if h['zs'] != h['sz'] else raw
        return h

    def manifest_roots(self):
        """Record ids of the per-type manifests listed in the MFST record at id 0."""
        assert self.m[0x14:0x18] == b'TSFM'
        n = struct.unpack_from('<H', self.m, 0x1A)[0]
        return list(struct.unpack_from(f'<{n}I', self.m, 0x28))


class Eboot:
    """Decrypted eboot.bin. All segments map with vaddr = file_offset - 0x4000."""

    BASE = 0x4000
    TEXT_SIZE = 0x1ED9640  # first PT_LOAD (code + rodata)

    def __init__(self, path=EBOOT_BIN):
        self.path = path
        with open(path, 'rb') as f:
            self.d = f.read()

    def read(self, vaddr, n):
        return self.d[vaddr + self.BASE:vaddr + self.BASE + n]

    def u64(self, vaddr):
        return struct.unpack_from('<Q', self.d, vaddr + self.BASE)[0]

    def cstr(self, vaddr, min_len=3):
        """Printable NUL-terminated string at vaddr, or None."""
        o = vaddr + self.BASE
        if not 0 <= o < len(self.d):
            return None
        e = self.d.find(b'\0', o, o + 256)
        if e - o < min_len:
            return None
        s = self.d[o:e]
        if all(32 <= c < 127 or c in (9, 10) for c in s):
            return s.decode()
        return None
