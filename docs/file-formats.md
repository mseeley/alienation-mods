# File formats

## Conventions used in these docs

- Notes are from the PS5-dumped PS4 build (CUSA04181). All addresses refer to the **patch0** `eboot.bin` (APP_VER 01.07) unless stated otherwise.
- The eboot is a decrypted `ET_SCE_DYNEXEC` ELF with stripped symbols. All three load segments map as **`vaddr = file_offset - 0x4000`**.
- Addresses written as `0x1156e0` are virtual addresses. File offsets are given separately where they matter for patching. ps-patch-system XML addresses are `0x400000 + vaddr`.
- Offsets into Stated scripts are bytecode offsets in the `STAD` record payload, not eboot addresses.
- Anything marked **unverified** or **untested** was derived statically and has not been tested on hardware.

## Engine overview

- **Engine:** Housemarque "Sasquatch" (`e:\Motherlode\Projects\AlienNation\Libs\Sasquatch\...`).
- **Gameplay:** "Stated" state machines compiled to a custom bytecode, shipped as one large `STAD` record in `stream.dat`. Debug names (state machine, state and transition names) are in a separate `STDD` record.
- **Rendering:** plain-text Lua source in `SCRI` records (e.g. `Compute_Tiled_Lights_Construct`). Relevant to the resolution/framerate patch.
- **Physics/AI:** Havok (`Havok/`, `Navmeshes/`).

## `stream.dat`

A sequence of records aligned to 64 bytes. **Record ID = file offset / 0x40.** Records reference each other by ID.

### Record header

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | u32 | Record ID |
| 0x04 | u32 | Stored (compressed) payload size |
| 0x08 | u32 | Uncompressed payload size |
| 0x0C | u32 | Unknown |
| 0x10 | u32 | Record ID (repeated) |
| 0x14 | char[4] | FourCC, stored byte-reversed (`MRCS` on disk = `SCRM`) |
| 0x18 | u32 | Version (usually 1) |
| 0x1C | u32 | `n_int`: number of internal pointer fixups |
| 0x20 | u64 | `n_ext`: number of external pointer fixups |
| 0x28 | u32 × `n_int` | Offsets of pointers that point inside this record |
| align 8 | (u32 target_id, u32 offset) × `n_ext` | Pointers to other records |
| … | bytes | zlib payload (stored raw when compressed size == uncompressed size) |

The decompressed payload is a memory image; fixups say where pointers must be patched after loading.

### Manifests

The `MFST` record at ID 0 has its own layout and lists 18 manifest record IDs:
`5, 7, 0x2e, 0x178, 0x179, 0x17c, 0x186, 0x187, 0x188, 0x189, 0x1a2, 0x1c8, 0x1c9, 0x207, 0x23e, 0x250, 0x251, 0x252`.

Notable manifests:

| FourCC | ID | Points to |
|---|---|---|
| `SCRM` | 0x17c | 40 `SCRI` records (Lua render scripts), sorted by name hash |
| `STAM` | 0x250 | `STAD` 0x124af99: compiled Stated program (7.7 MB) |
| `STDM` | 0x251 | `STDD` 0x1255d46: Stated debug info (13.4 MB) |
| `PARM`, `RAWM`, `GENM`, `SHAM`, `GTMF`, … | | Parameters, raw data, shaders, textures, … |

Single-entry manifests such as `STAM`/`STDM` store a raw `{u32 count, u32 name_hash, u32 record_id}` with no fixups.

A linear walk of the file loses sync on some record types; traversing the fixup graph from the manifest roots is reliable (about 6,000 reachable records). About 3,100 references don't resolve to a record header in the patch file and haven't been investigated.

## `STAD` (compiled Stated program)

| Offset | Contents |
|---|---|
| 0x000 | Header (magic `0x214e0403`, then offsets and counts, see below) |
| 0x1C4 | String hash table: 30,926 × (u32 hash, u32 string offset), sorted by hash |
| 0x3C834 | String pool (NUL-terminated; includes all localization text, stored as value then key) |
| 0xFA5AF | Bytecode (0x5C306B bytes, header field +0x18) |
| 0x6BD61A | Table of 0x36E entries (header +0x0C/+0x10) |
| 0x6BE3D4 | Table of 0x2B7 entries (header +0x04/+0x08), runs to end |

How bytecode references strings is not yet confirmed. Opcode names (`BC_Tuple_Explode`, `BC_StoreGet`, `BC_RefNew`, `BC_StringJoin`, …) and value type names (`Void`, `Bool`, `Block_Idx`, `Float`, `Unique_Id`, `SM_Instance`, `Property_Set`, `Vec2`–`Vec4`, `Mtx44`, …) are present in the eboot and are the starting point for a disassembler.

Stated values are 64-bit with the type tag in the top bits; for example, Bool true is `0x0400000000000001`.

## `savedata.dat`

Written by the persistence manager to the save directory `savedata`. You need a decrypted save (for example, exported with Apollo Save Tool) to work on it.

### Wrapper (verified from code)

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | char[4] | Magic `AYE!` (`41 59 45 21`) |
| 0x04 | u32 | CRC32 (standard zlib/IEEE) over bytes `[0x08, 0x14 + len)` |
| 0x08 | u32 | Data offset, always `0x14` |
| 0x0C | u32 | `len`: payload length |
| 0x10 | u16 | `0x0401` (written, not checked on load) |
| 0x14 | bytes | Payload |

On load (`0x3b5f60`) the game checks the magic, that the file is large enough, and the CRC. Any failure means the save is ignored. After editing, recompute the CRC.

The file is always the full fixed-size buffer: 1 MiB of payload space plus the header (1,048,596 bytes). Bytes after `0x14 + len` are leftovers from earlier saves and are ignored.

### Payload (verified against a real save)

The payload is **not compressed**, even though `0x131290` is a raw-deflate wrapper. It is a Stated value stream: a version byte `0x01`, then one tagged value (the root table).

| Tag | Type | Encoding after the tag byte |
|---|---|---|
| `0x01` | Void (nil) | nothing |
| `0x02` | Bool | u8 |
| `0x03` | Int | i32 |
| `0x05` | Float | f32 |
| `0x0A`–`0x0C` | Vec2–Vec4 | 2–4 × f32 |
| `0x0D` | Mtx44 | 16 × f32 (assumed; not seen in the save) |
| `0x0E` | String | u32 length + bytes (no terminator) |
| `0x10` | List | u16 count + values |
| `0x11` | Tuple | u16 count + values |
| `0x12` | Table | u16 count + count × (u32 key hash, value) |

All values are little-endian. Tags `0x04`, `0x06`–`0x09`, `0x0F` and `0x13+` don't occur in the save.

**Key hash:** the first four bytes of `MD5(key.upper())`, read as a little-endian u32. Uppercasing affects only `a`–`z`, so keys are case-insensitive. The routine is `0x12a280` → `0x12aab0`: an MD5 init/update/final where the update uppercases each byte. String objects cache their hash at +0x14 (`0x2578b0`). Names can be recovered by hashing every string in STAD, STDD and the eboot. Only 3 keys in the sample save don't resolve this way (boolean flags in `game_char_data`).

The root holds a save `version` (76 in the sample) and each character slot holds its own `version` (51). The boot menu rejects saves with a missing, older or newer version ("Save data version number missing", "Old, incompatible save data version", "Too new save data version"), so leave these alone.

See [weapons-and-cores.md](weapons-and-cores.md#save-layout) for the save schema, and `tools/research/savedata.py` for a reader/writer.

### Key code addresses

| Address | Function |
|---|---|
| `0x45ff90` | Orbis load thread (reads whole file) |
| `0x460710` | Orbis save thread (writes buffer to `savedata.dat`) |
| `0x45f1e0` | Persistence manager update / state machine |
| `0x3b5f60` | Load: validate header and CRC, copy payload |
| `0x3b64d0` | Reset buffer: write magic, data offset 0x14, version 0x401 |
| `0x3b6020` / `0x3b63a0` | Save: compute CRC, copy buffer out |
| `0x129b70` | CRC32 (table at `0x1770e90`) |
| `0x3b5b20` | `persistence_set_data` |
| `0x3bd750` | `serialize_stated_value_to_binary` |
| `0x3bd8c0` | `deserialize_binary_to_stated_value` |
| `0x131290` | Deflate wrapper (not applied to the save payload) |
| `0x12a280` | Key hash: low 32 bits of MD5 of the uppercased string |
