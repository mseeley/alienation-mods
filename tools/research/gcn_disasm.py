"""Disassemble PS4 GPU shader code (GCN gen 2 / Sea Islands), e.g. from SHDR records in stream.dat.

  python3 tools/research/stream_catalog.py --dump SHDR out/                         # extract shader records
  python3 tools/research/gcn_disasm.py out/SHDR_000fe8b6.bin 0x1264 0x17c8          # armor pixel shader

LLVM's AMDGPU disassembler doesn't support this generation, so this covers the formats PS4 pixel and
vertex shaders use (SOP*, SMRD, VOP1/2/3/C, VINTRP, MIMG, EXP), with opcode names for the common ones.
A program's code starts at `s_mov_b32 vcc_hi, <literal>` (0xbeeb03ff) and ends at s_endpgm; its
"OrbShdr" footer and parameter table (name, constant buffer offset) follow. See docs/armor.md.
"""
import struct
import sys

SOP2 = {0: 's_add_u32', 1: 's_sub_u32', 2: 's_add_i32', 3: 's_sub_i32', 4: 's_addc_u32', 5: 's_subb_u32',
        6: 's_min_i32', 7: 's_min_u32', 8: 's_max_i32', 9: 's_max_u32', 10: 's_cselect_b32', 11: 's_cselect_b64',
        14: 's_and_b32', 15: 's_and_b64', 16: 's_or_b32', 17: 's_or_b64', 18: 's_xor_b32', 19: 's_xor_b64',
        20: 's_andn2_b32', 21: 's_andn2_b64', 22: 's_orn2_b32', 23: 's_orn2_b64', 30: 's_lshl_b32',
        31: 's_lshl_b64', 32: 's_lshr_b32', 33: 's_lshr_b64', 34: 's_ashr_i32', 38: 's_mul_i32', 39: 's_bfe_u32'}
SOP1 = {3: 's_mov_b32', 4: 's_mov_b64', 5: 's_cmov_b32', 6: 's_cmov_b64', 7: 's_not_b32', 8: 's_not_b64',
        10: 's_wqm_b64', 36: 's_and_saveexec_b64', 37: 's_or_saveexec_b64', 32: 's_swappc_b64', 33: 's_rfe_b64',
        31: 's_setpc_b64', 30: 's_getpc_b64'}
SOPC = {0: 's_cmp_eq_i32', 1: 's_cmp_lg_i32', 2: 's_cmp_gt_i32', 3: 's_cmp_ge_i32', 4: 's_cmp_lt_i32',
        5: 's_cmp_le_i32', 6: 's_cmp_eq_u32', 7: 's_cmp_lg_u32', 8: 's_cmp_gt_u32', 9: 's_cmp_ge_u32',
        10: 's_cmp_lt_u32', 11: 's_cmp_le_u32'}
SOPP = {0: 's_nop', 1: 's_endpgm', 2: 's_branch', 4: 's_cbranch_scc0', 5: 's_cbranch_scc1', 6: 's_cbranch_vccz',
        7: 's_cbranch_vccnz', 8: 's_cbranch_execz', 9: 's_cbranch_execnz', 10: 's_barrier', 12: 's_waitcnt',
        13: 's_sethalt', 14: 's_sleep', 15: 's_setprio', 16: 's_sendmsg', 22: 's_ttracedata'}
SOPK = {0: 's_movk_i32', 2: 's_cmovk_i32', 15: 's_addk_i32', 16: 's_mulk_i32', 17: 's_cbranch_i_fork'}
SMRD = {0: 's_load_dword', 1: 's_load_dwordx2', 2: 's_load_dwordx4', 3: 's_load_dwordx8', 4: 's_load_dwordx16',
        8: 's_buffer_load_dword', 9: 's_buffer_load_dwordx2', 10: 's_buffer_load_dwordx4',
        11: 's_buffer_load_dwordx8', 12: 's_buffer_load_dwordx16', 30: 's_memtime', 31: 's_dcache_inv'}
VOP2 = {0: 'v_cndmask_b32', 1: 'v_readlane_b32', 2: 'v_writelane_b32', 3: 'v_add_f32', 4: 'v_sub_f32',
        5: 'v_subrev_f32', 6: 'v_mac_legacy_f32', 7: 'v_mul_legacy_f32', 8: 'v_mul_f32', 9: 'v_mul_i32_i24',
        10: 'v_mul_hi_i32_i24', 11: 'v_mul_u32_u24', 12: 'v_mul_hi_u32_u24', 13: 'v_min_legacy_f32',
        14: 'v_max_legacy_f32', 15: 'v_min_f32', 16: 'v_max_f32', 17: 'v_min_i32', 18: 'v_max_i32', 19: 'v_min_u32',
        20: 'v_max_u32', 21: 'v_lshr_b32', 22: 'v_lshrrev_b32', 23: 'v_ashr_i32', 24: 'v_ashrrev_i32',
        25: 'v_lshl_b32', 26: 'v_lshlrev_b32', 27: 'v_and_b32', 28: 'v_or_b32', 29: 'v_xor_b32', 30: 'v_bfm_b32',
        31: 'v_mac_f32', 32: 'v_madmk_f32', 33: 'v_madak_f32', 34: 'v_bcnt_u32_b32', 35: 'v_mbcnt_lo_u32_b32',
        36: 'v_mbcnt_hi_u32_b32', 37: 'v_add_i32', 38: 'v_sub_i32', 39: 'v_subrev_i32', 40: 'v_addc_u32',
        41: 'v_subb_u32', 42: 'v_subbrev_u32', 43: 'v_ldexp_f32', 44: 'v_cvt_pkaccum_u8_f32',
        45: 'v_cvt_pknorm_i16_f32', 46: 'v_cvt_pknorm_u16_f32', 47: 'v_cvt_pkrtz_f16_f32', 48: 'v_cvt_pk_u16_u32',
        49: 'v_cvt_pk_i16_i32'}
VOP1 = {0: 'v_nop', 1: 'v_mov_b32', 2: 'v_readfirstlane_b32', 5: 'v_cvt_f32_i32', 6: 'v_cvt_f32_u32',
        7: 'v_cvt_u32_f32', 8: 'v_cvt_i32_f32', 10: 'v_cvt_f16_f32', 11: 'v_cvt_f32_f16', 12: 'v_cvt_rpi_i32_f32',
        13: 'v_cvt_flr_i32_f32', 17: 'v_cvt_f32_ubyte0', 18: 'v_cvt_f32_ubyte1', 19: 'v_cvt_f32_ubyte2',
        20: 'v_cvt_f32_ubyte3', 32: 'v_fract_f32', 33: 'v_trunc_f32', 34: 'v_ceil_f32', 35: 'v_rndne_f32',
        36: 'v_floor_f32', 37: 'v_exp_f32', 38: 'v_log_clamp_f32', 39: 'v_log_f32', 40: 'v_rcp_clamp_f32',
        41: 'v_rcp_legacy_f32', 42: 'v_rcp_f32', 43: 'v_rcp_iflag_f32', 44: 'v_rsq_clamp_f32',
        45: 'v_rsq_legacy_f32', 46: 'v_rsq_f32', 51: 'v_sqrt_f32', 53: 'v_sin_f32', 54: 'v_cos_f32',
        55: 'v_not_b32', 56: 'v_bfrev_b32', 59: 'v_frexp_mant_f32'}
VOP3_ONLY = {0x140: 'v_mad_legacy_f32', 0x141: 'v_mad_f32', 0x142: 'v_mad_i32_i24', 0x143: 'v_mad_u32_u24',
             0x144: 'v_cubeid_f32', 0x145: 'v_cubesc_f32', 0x146: 'v_cubetc_f32', 0x147: 'v_cubema_f32',
             0x148: 'v_bfe_u32', 0x149: 'v_bfe_i32', 0x14a: 'v_bfi_b32', 0x14b: 'v_fma_f32', 0x14e: 'v_alignbit_b32',
             0x151: 'v_min3_f32', 0x154: 'v_max3_f32', 0x157: 'v_med3_f32', 0x15f: 'v_div_fixup_f32',
             0x16b: 'v_mul_lo_u32', 0x16c: 'v_mul_hi_u32', 0x16d: 'v_mul_lo_i32', 0x16e: 'v_mul_hi_i32'}
VOPC_NAMES = {0x00: 'f', 0x01: 'lt', 0x02: 'eq', 0x03: 'le', 0x04: 'gt', 0x05: 'lg', 0x06: 'ge', 0x07: 'o',
              0x08: 'u', 0x09: 'nge', 0x0a: 'nlg', 0x0b: 'ngt', 0x0c: 'nle', 0x0d: 'neq', 0x0e: 'nlt', 0x0f: 'tru'}
MIMG = {0: 'image_load', 32: 'image_sample', 34: 'image_sample_d', 36: 'image_sample_l', 37: 'image_sample_b',
        39: 'image_sample_lz', 40: 'image_sample_c', 48: 'image_sample_o', 52: 'image_sample_l_o',
        55: 'image_sample_lz_o', 64: 'image_gather4', 96: 'image_get_lod'}
INLINE_F = {240: '0.5', 241: '-0.5', 242: '1.0', 243: '-1.0', 244: '2.0', 245: '-2.0', 246: '4.0', 247: '-4.0'}


def sreg(n):
    if n <= 103:
        return f's{n}'
    return {106: 'vcc_lo', 107: 'vcc_hi', 124: 'm0', 126: 'exec_lo', 127: 'exec_hi'}.get(n, f's?{n}')


def src(n, lit=None):
    if n < 104:
        return f's{n}'
    if 104 <= n < 128:
        return sreg(n)
    if n == 128:
        return '0'
    if 129 <= n <= 192:
        return str(n - 128)
    if 193 <= n <= 208:
        return str(-(n - 192))
    if n in INLINE_F:
        return INLINE_F[n]
    if n == 251:
        return 'vccz'
    if n == 252:
        return 'execz'
    if n == 253:
        return 'scc'
    if n == 255:
        f = struct.unpack('<f', struct.pack('<I', lit))[0]
        return f'0x{lit:08x}({f:.6g})'
    if n >= 256:
        return f'v{n - 256}'
    return f'?{n}'


def sgpr_range(base, count):
    return f's[{base}:{base + count - 1}]' if count > 1 else f's{base}'


def decode(d, start, end):
    pc = start
    out = []
    while pc < end:
        w = struct.unpack_from('<I', d, pc)[0]
        size = 4
        txt = f'.dword 0x{w:08x}'
        nxt = struct.unpack_from('<I', d, pc + 4)[0] if pc + 4 < len(d) else 0
        top2, top4, top5, top6 = w >> 30, w >> 28, w >> 27, w >> 26
        if w >> 23 == 0b101111111:                      # SOPP
            op = (w >> 16) & 0x7f
            txt = f'{SOPP.get(op, f"sopp{op}")} 0x{w & 0xffff:x}'
        elif w >> 23 == 0b101111110:                    # SOPC
            op = (w >> 16) & 0x7f
            s1, s0 = (w >> 8) & 0xff, w & 0xff
            lit = nxt if 255 in (s0, s1) else None
            size += 4 if lit is not None else 0
            txt = f'{SOPC.get(op, f"sopc{op}")} {src(s0, lit)}, {src(s1, lit)}'
        elif w >> 23 == 0b101111101:                    # SOP1
            op = (w >> 8) & 0xff
            s0, dst = w & 0xff, (w >> 16) & 0x7f
            lit = nxt if s0 == 255 else None
            size += 4 if lit is not None else 0
            txt = f'{SOP1.get(op, f"sop1_{op}")} {sreg(dst)}, {src(s0, lit)}'
        elif top4 == 0b1011:                            # SOPK
            op = (w >> 23) & 0x1f
            txt = f'{SOPK.get(op, f"sopk{op}")} {sreg((w >> 16) & 0x7f)}, 0x{w & 0xffff:x}'
        elif top2 == 0b10:                              # SOP2
            op = (w >> 23) & 0x7f
            s0, s1, dst = w & 0xff, (w >> 8) & 0xff, (w >> 16) & 0x7f
            lit = nxt if 255 in (s0, s1) else None
            size += 4 if lit is not None else 0
            txt = f'{SOP2.get(op, f"sop2_{op}")} {sreg(dst)}, {src(s0, lit)}, {src(s1, lit)}'
        elif top5 == 0b11000:                           # SMRD
            op = (w >> 22) & 0x1f
            dst, sbase, imm, off = (w >> 15) & 0x7f, ((w >> 9) & 0x3f) * 2, (w >> 8) & 1, w & 0xff
            n = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16, 8: 1, 9: 2, 10: 4, 11: 8, 12: 16}.get(op, 1)
            if imm:
                offs = f'0x{off * 4:x}'
            elif off == 255:
                offs = f'0x{nxt:x} (literal)'
                size += 4
            else:
                offs = src(off)
            txt = f'{SMRD.get(op, f"smrd{op}")} {sgpr_range(dst, n)}, s[{sbase}:{sbase + 3}], {offs}'
        elif top6 == 0b110010:                          # VINTRP
            op = (w >> 16) & 3
            vdst, attr, chan, vsrc = (w >> 18) & 0xff, (w >> 10) & 0x3f, (w >> 8) & 3, w & 0xff
            name = ['v_interp_p1_f32', 'v_interp_p2_f32', 'v_interp_mov_f32'][op] if op < 3 else 'v_interp?'
            txt = f'{name} v{vdst}, v{vsrc}, attr{attr}.{"xyzw"[chan]}'
        elif top6 == 0b110100:                          # VOP3
            size = 8
            op = (w >> 17) & 0x1ff
            vdst, absm, clamp = w & 0xff, (w >> 8) & 7, (w >> 11) & 1
            s0, s1, s2 = nxt & 0x1ff, (nxt >> 9) & 0x1ff, (nxt >> 18) & 0x1ff
            omod, neg = (nxt >> 27) & 3, (nxt >> 29) & 7

            def m(i, s):
                t = src(s)
                if absm >> i & 1:
                    t = f'|{t}|'
                if neg >> i & 1:
                    t = f'-{t}'
                return t
            if op < 0x100:
                name = f'v_cmp_{VOPC_NAMES.get(op & 0xf, op)}_f32' if op < 0x10 else f'vopc{op:#x}'
                txt = f'{name} {sreg(w & 0xff)}, {m(0, s0)}, {m(1, s1)}'
            elif op < 0x140:
                name = VOP2.get(op - 0x100, f'vop2_{op - 0x100}')
                args = [m(0, s0), m(1, s1)] + ([m(2, s2)] if name in ('v_cndmask_b32',) else [])
                txt = f'{name} v{vdst}, ' + ', '.join(args)
            elif op < 0x180:
                txt = f'{VOP3_ONLY.get(op, f"vop3_{op:#x}")} v{vdst}, {m(0, s0)}, {m(1, s1)}, {m(2, s2)}'
            else:
                txt = f'{VOP1.get(op - 0x180, f"vop1_{op - 0x180}")} v{vdst}, {m(0, s0)}'
            if clamp:
                txt += ' clamp'
            if omod:
                txt += f' omod{omod}'
        elif top6 == 0b111100:                          # MIMG
            size = 8
            op = (w >> 18) & 0x7f
            dmask = (w >> 8) & 0xf
            vaddr, vdata, srsrc, ssamp = nxt & 0xff, (nxt >> 8) & 0xff, ((nxt >> 16) & 0x1f) * 4, ((nxt >> 21) & 0x1f) * 4
            txt = (f'{MIMG.get(op, f"mimg{op}")} v[{vdata}..] dmask=0x{dmask:x}, v{vaddr}, '
                   f's[{srsrc}:{srsrc + 7}], s[{ssamp}:{ssamp + 3}]')
        elif top6 == 0b111110:                          # EXP
            size = 8
            en, tgt, compr, done = w & 0xf, (w >> 4) & 0x3f, (w >> 10) & 1, (w >> 11) & 1
            vs = [(nxt >> (8 * i)) & 0xff for i in range(4)]
            t = f'mrt{tgt}' if tgt < 8 else ('mrtz' if tgt == 8 else ('null' if tgt == 9 else f'tgt{tgt}'))
            txt = f'exp {t} en=0x{en:x}{" compr" if compr else ""}{" done" if done else ""} ' + ', '.join(f'v{v}' for v in vs)
        elif w >> 25 == 0b0111111:                      # VOP1
            op = (w >> 9) & 0xff
            s0, vdst = w & 0x1ff, (w >> 17) & 0xff
            lit = nxt if s0 == 255 else None
            size += 4 if lit is not None else 0
            txt = f'{VOP1.get(op, f"vop1_{op}")} v{vdst}, {src(s0, lit)}'
        elif w >> 25 == 0b0111110:                      # VOPC
            op = (w >> 17) & 0xff
            s0, v1 = w & 0x1ff, (w >> 9) & 0xff
            lit = nxt if s0 == 255 else None
            size += 4 if lit is not None else 0
            name = f'v_cmp_{VOPC_NAMES.get(op & 0xf, op)}_f32' if op < 0x10 else f'vopc{op:#x}'
            txt = f'{name} vcc, {src(s0, lit)}, v{v1}'
        elif w >> 31 == 0:                              # VOP2
            op = (w >> 25) & 0x3f
            s0, v1, vdst = w & 0x1ff, (w >> 9) & 0xff, (w >> 17) & 0xff
            name = VOP2.get(op, f'vop2_{op}')
            lit = nxt if s0 == 255 or name in ('v_madmk_f32', 'v_madak_f32') else None
            size += 4 if lit is not None else 0
            extra = ''
            if name in ('v_madmk_f32', 'v_madak_f32'):
                extra = f', k={struct.unpack("<f", struct.pack("<I", nxt))[0]:.6g}'
            txt = f'{name} v{vdst}, {src(s0, lit)}, v{v1}{extra}'
        out.append((pc, txt))
        pc += size
        if txt.startswith('s_endpgm'):
            break
    return out


if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    for pc, t in decode(data, int(sys.argv[2], 0), int(sys.argv[3], 0)):
        print(f'{pc:06x}  {t}')
