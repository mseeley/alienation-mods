# Resolution

Static analysis of the patch0 eboot (APP_VER 01.07) and the Lua render scripts.

**Shipped: "Resolution 720p (1280x720)" only**, meant to be paired with "60 FPS" for a steadier frame rate. It changes just the display-config immediate (`0x6ffe22`: `80 07 00 00 38 04 00 00` → `00 05 00 00 d0 02 00 00`), so the front buffer and `RENDER_RESOLUTION` are both 1280×720, and the console scales the image to the TV. Untested on console. Why it's built this way:

- **Output 720p too, not just render 720p:** the final tonemap pass point-samples the scene (see below), so rendering at 720p into a 1080p front buffer would be an uneven nearest-neighbour stretch. The console's video-out scaler filters better.
- **Video-out scaling works:** the 1440p entries displayed an image on console before they crashed, so video-out accepts a front buffer that isn't 1080p.
- **Memory:** about 44% of the 1080p pixel count. Resolution-scaled targets shrink from ~440 MB to roughly 200 MB, so the higher-resolution memory problem doesn't apply and the pool stays at 1 GB.
- **Fixed-size targets are unaffected:** bloom mips (960×544 down), the shadow map (2048×1024) and the bloom texel offsets keep their 1080p values. Bloom may look slightly tighter.

Six higher-resolution entries were built (below) and tested on console on 2026-10-10: every one booted, then crashed once combat started (shooting, explosions). The likely cause is memory that grows with effects (particles, decals, transient render targets) running out at the larger sizes; not diagnosed. They were removed from [`patches/xml_orbis/CUSA04181.xml`](../patches/xml_orbis/CUSA04181.xml) (last version: PatchVer 1.2). This page is kept as the record of the analysis and the exact bytes.

## Current behaviour

The game renders at a **fixed 1920×1080** on every console.

- The display object (`Display_Control_Orbis`, global `0x27b7ee0`) is constructed by `0x2ffec0` from a config block built by `0x2ffe10`. The only resolution in it is the immediate at `0x2ffe20` (`movabs rax, 0x438_00000780`, i.e. 1920×1080), stored at config `+0x30`.
- The constructor creates the **`frontbuffer`** render target at that size (`0x437ef0`, `0x3115d0`) and stores it as the render resolution at `[display+0x2c]` / `[display+0x30]` (with the aspect ratio at `+0x34`).
- Lua sees it as **`RENDER_RESOLUTION_X/Y`** (registered at `0x1f55d8`, display method `+0x20` = `0x300df0`). **`DISPLAY_RESOLUTION_X/Y`** is the real video-out size from `sceVideoOutGetResolutionStatus` (method `+0x18` = `0x300d70`).
- The main renderer script (`SCRI_01249c40`, "SCRIPTED RENDERER CONFIGURATION") sizes every render target from `RENDER_RESOLUTION_X/Y` (G-buffer, SSAO, lighting, history buffers, alpha, half/quarter-res chains). One value therefore resizes the whole pipeline.
- **No PS4 Pro resolution mode.** `sceKernelIsNeoMode` is only used for GPU clock and CU-count constants (`0x2b5600`…) and as a flag passed into texture/render-target creation (`0x27cec58`). The 1.07 update added `ATTRIBUTE` bit `0x800000` to `param.sfo` (believed to be the Pro-support flag; unconfirmed).
- No other code hard-codes 1920×1080 (the immediate at `0x2ffe22` is the only `(1920, 1080)` pair in code). The bloom script keeps a `bloom_mips` table with `x0 = 1920, y0 = 1080` used for texel offsets, so bloom spread may shift slightly at other sizes.

## GPU memory

`GFX_Resources_Orbis` (`0x301d00`) allocates three fixed direct-memory pools at boot, sized from the same config block: **1 GB** ("fast gpu memory"), **128 MB** ("fast gpu memory (2)") and **512 MB**. Resolution-scaled GPU memory, estimated from every `Rendertarget_Create*`, `Texture_2D_RW_Create_Texture*` (mip chains × 4/3) and resolution-scaled `Depthbuffer_Create*` call in the render scripts (depth assumed 5 B/px), plus three 32-bit front buffers, excluding debug targets. 102 allocations; upper bound, since conditional targets are included:

| Resolution | Total | Increase over 1080p |
|---|---|---|
| 1920×1080 | ~440 MB | — |
| 2560×1440 | ~780 MB | +342 MB |
| 3840×2160 | ~1,760 MB | +1,319 MB |

The 1 GB pool fits 1080p plus whatever non-render data shares it, so a resolution needs roughly 1 GB plus its increase: about 1.34 GB for 1440p and about 2.3 GB for 2160p.

Render targets (`Render_Target_Impl_Orbis`, `0x174a10`) allocate from GFX resources (global `0x27b8538`, vtable `0x1ef5e50`) method `+0x10` = `[gfx+0x50]`, the **"fast gpu memory"** heap on the 1 GB pool. The other heaps are `+0x58` "fast gpu memory (2)" (128 MB) and `+0x60` "cpu-coherent memory" (512 MB). The pool sizes come from the display config defaults: the 16-byte constant at `0x178f230` (1 GB, 128 MB; read only at `0x2ffe14`) plus the immediate 512 MB at `0x2ffe2e`.

All `sceKernelAllocateDirectMemory` calls (3 sites):

| Size | Use | Site |
|---|---|---|
| 1,792 MB | "User Malloc" CPU heap | `0x910` |
| 351 MB | Stated GC heap | `0x279f20` (size from `0x116307`) |
| 1,024 + 128 + 512 MB | GPU pools | `0x301d00` → `0x301f30` |

That's ≈3.8 GB in total. The PS4 game budget is roughly 4.5–5 GB, believed to be about 512 MB more in Pro mode (unverified).

## Removed patches

Every resolution entry wrote the **same four locations**: output (front-buffer) size, render-target pool size, the render-size hook, and the hook's code. If more than one was enabled, the last one applied won as a whole.

| Patch | Output (front buffer) | Render size | Pool | Total reservations | Needs Pro mode |
|---|---|---|---|---|---|
| Resolution 1440p | 2560×1440 | same | 1 GB | ~3.8 GB | yes |
| Resolution 1440p + 1.5 GB pool | 2560×1440 | same | 1.5 GB | ~4.3 GB | yes |
| Resolution 2160p + 2 GB pool | 3840×2160 | same | 2 GB | ~4.8 GB (may still run out) | yes |
| Supersampling: render 1440p, output 1080p + 1.5 GB | 1920×1080 | 2560×1440 | 1.5 GB | ~4.3 GB | no |
| Supersampling: render 2160p, output 1080p + 2 GB | 1920×1080 | 3840×2160 | 2 GB | ~4.8 GB (may still run out) | no |
| Render 1440p, output 2160p + 1.5 GB | 3840×2160 | 2560×1440 | 1.5 GB | ~4.3 GB | yes |

Locations: output size `0x6ffe22` (vaddr `0x2ffe22`, original `80 07 00 00 38 04 00 00`); pool `0x1b8f230` (`0x178f230`, original 1 GB); hook `0x7000be` (`0x3000be`, original `48 8d bd 60 ff ff ff` = `lea rdi, [rbp-0xa0]`); code `0x6ffde0` (`0x2ffde0`, 29 bytes). Entries whose render size equals the output size restore the original hook and cave bytes. A failed pool allocation is only logged (`0x301f30`), so it shows up as a later crash.

## Decoupled render size (supersampling / upscaling)

The display constructor (`0x2ffec0`) uses one local size, `[rbp-0x98]`, copied from config `+0x30`, for three things in order:

1. The colour **front buffer** (`0x437ef0`, `0x3000a6`): the image scanned out to the TV.
2. The **`frontbuffer` depth buffer** (`0x3115d0`, `0x3000d7`): the same creator `Depthbuffer_Create_Depthbuffer` uses. The render scripts use it as `frontbuffer_z` for the HUD views, which draw into render-sized targets.
3. **`RENDER_RESOLUTION`** (`0x300113`–`0x300145`, stored at `[display+0x2c]`): sizes every render target in the Lua pipeline.

The hook at `0x3000be`, between steps 1 and 2, jumps to a code cave in `0x2ffde0`, an unused config builder (no calls, jumps, LEAs or pointers reference it). The cave does:

```
movabs rax, (render_h << 32) | render_w
mov    [rbp-0x98], rax          ; depth buffer + RENDER_RESOLUTION use the render size
lea    rdi, [rbp-0xa0]          ; displaced instruction
jmp    0x3000c5
```

`rax` is dead at the hook (reloaded at `0x3000dc`). After the hook, the local is read only by steps 2 and 3.

### What the final pass actually does

The only pass that writes the front buffer is the final bloom/tonemap composite: `Bloom_New` → `bloom_new_2_combine_tonemap` (`fsx-hdrbloom-new` pass 0, shader record `0x124aa38`). After it, only a no-draw "menu setup" state and `Finalize()` run. Its GCN code was decoded by hand (pixel shader at record offset `0xc24`–`0x101c`, vertex shader `0x854`–`0x8b4`, binding metadata after each `OrbShdr` footer):

- **Coordinates are normalized, so there is no crop.** The vertex shader builds a full-screen triangle from `vertex_id`, with UV 0–1 across the screen plus a constant from `VERTEX_UV_OFFSETS`. The pixel shader's only input is that interpolated `frag.uv`. It never reads the pixel position or the global screen size.
- **The scene is point-sampled, so there is no averaging.** Bindings: t0 `SOURCE_1` (scene), t1 `SOURCE_2` (bloom), t2 `SOURCE_COLORGRADE`; s0 `SOURCE_COLORGRADE_SAMPLER`, s1 `LINEAR_CLAMP_SAMPLER`, s2 `POINT_CLAMP_SAMPLER`. The shader takes 13 offset taps of the bloom buffer through the linear sampler and **one tap of the scene through `POINT_CLAMP_SAMPLER`**, at the unmodified UV. Two checks agree on which is which: the bloom taps use the `CONFIG` offsets (1.5 bloom texels); the first texture/sampler of each kind arrives in user SGPRs and the rest in the resource table, in slot order.
- **`POINT_CLAMP_SAMPLER` is a real point sampler.** Shaders bind global samplers by name hash (`0x4226a0`; `0xad4149ff` = MD5 prefix of `POINT_CLAMP_SAMPLER`) to a table built at `0x422530`/`0x4220b0`. That entry's S# word 2 is `0x05000000` (XY mag/min point, Z and mip point) with clamp addressing; `LINEAR_CLAMP_SAMPLER` is `0x0a500000` (trilinear). The render target's own `Rendertarget_Set_Sampling(TS_LINEAR, …)` doesn't apply: the engine only pairs a texture with a `<name>_SAMPLER` slot (`0x41f1e0`), and this shader has no `SOURCE_1_SAMPLER`.

So each output pixel copies the one rendered pixel under its centre:

| Entry | Effect |
|---|---|
| Render 2160p → output 1080p | Keeps one pixel of every 2×2 block. Looks like native 1080p (thin lines and HUD text may break up) at about 4× the cost |
| Render 1440p → output 1080p | Skips every 4th rendered row and column. Uneven, shimmering edges; worse than native 1080p at about 1.8× the cost |
| Render 1440p → output 2160p | Nearest-neighbour 1.5× upscale (every other pixel doubled). Blockier than outputting 1440p and letting the console or TV scale it |

The bloom is unaffected: it's read through the linear sampler from its fixed 960×544 buffer.

**Making it real supersampling** would need the scene read through a filtering sampler. The shader lives in `stream.dat`, so it can't be changed with an eboot XML patch. Turning the global `POINT_CLAMP_SAMPLER` linear (`0x4220ba`: `or ecx, 0x5000000` → `0xa500000`) would work for this pass at exactly 2× (one bilinear tap at the texel corner averages 2×2). But it would change every other shader that binds that sampler, and some of those (depth, G-buffer or integer reads) likely need point sampling. Not attempted.

## Risks to watch for

- **Boot or level-load crash:** GPU memory exhausted (likely at 2160p), or video-out refusing the larger front buffer.
- **Frame rate:** about 1.8× (1440p) or 4× (2160p) the pixel work. Combined with the 60 FPS patch the console may not hold 60, and below target the game slows rather than drops frames (see [framerate.md](framerate.md)).
- **UI scale:** if HUD or menu layout is in render-resolution pixels it will look smaller. Not yet checked.

