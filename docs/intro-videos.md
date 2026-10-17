# Intro videos

Patch: "Skip intro videos" in [`patches/xml_orbis/CUSA04181.xml`](../patches/xml_orbis/CUSA04181.xml). Addresses are patch0 eboot vaddrs (APP_VER 01.07). **Untested on console.**

## What plays at boot

`AN.Menu.Boot` (Stated) plays two videos from `app0/video/`:

| File | When | States |
|---|---|---|
| `splash.mp4` (`splash_SIE.mp4` for `build_region() == "kr"`) | Boot, logo reel | `Init1:start_video` / `wait_video`, `Video_Switcher` |
| `intro.mp4` (with audio, Wwise `Play_Intro` / `Play_Intro_jp`, subtitles `INTRO_SUBTITLE_01`–`10`) | After saves load; skippable with the confirm button once the `SKIP_INTRO` prompt shows | `Init4:ready`, `Intro:start_video` / `subtitles` / `done` |

Other videos: `title.mp4` (title-screen background loop, `AN.Menu.Screens.Title`) and `7s_place_holder_cut_scene.mp4` (`AN.Menu.Dialogs.Story`). `loading.mp4` is on disc but not referenced by any script.

## The script's own skip

Boot sets `skip_video = is_platform_windows() or test_mode or demo_mode or is_string(startup_level)` (bytecode `0x3c7432`–`0x3c746a`). Each of those has side effects elsewhere (`is_platform_windows` alone is read by ~200 scripts), and the bytecode lives in `stream.dat`, so neither can be changed with an eboot XML patch.

## How the patch skips them

Every script video goes through `av_player_new` (native `0x66170`), which opens `"/app0/" + path` and constructs `AV_Player_Orbis` (`0x113780`). That constructor sets the `initialized` flag (`+0x80e5`, read by `av_player_is_initialized`, `0x114590`) synchronously, only after `sceAvPlayerInit`, `sceAvPlayerAddSource` and the setup calls succeed. Any failure jumps to `0x113b34`, which closes the player.

The boot script treats an uninitialised player as "no video":

- `Init1:start_video`: not ready and not initialised → removes `av_player`, marks the video started. `wait_video` then sees no player and continues immediately (the 5-second `VIDEO START FAILURE` timeout only applies to a player that initialised but never produced a frame).
- `Intro:start_video`: not initialised → removes the player. `Intro:done` accepts at once when there's no player.

The patch hooks the constructor just before `sceAvPlayerAddSource` (`0x113a60`) and jumps to code in `0x6cdb0`, an unreferenced 48-byte helper (no calls, jumps, LEAs, rel8 branches or stored pointers reference it):

```
cmp dword [r15+12], 'spla'   ; r15 = "/app0/video/<name>"
je  fail
cmp dword [r15+12], 'intr'
je  fail
mov rdi, [rbx+0x30]          ; displaced instructions
mov rsi, r15
jmp 0x113a67                 ; call sceAvPlayerAddSource
fail: jmp 0x113b34           ; close the player, leave it uninitialised
```

`title.mp4` and the story placeholder don't match, so they play as before.
