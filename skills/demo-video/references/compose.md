# Compose

```bash
python3 <skill>/scripts/dv.py compose
```

Reads the storyboard, finds each scene's rendered `.webm` under `demo/scenes/`, chains them with `xfade` transitions, and encodes `demo/output/<name>.mp4` (H.264, yuv420p, CRF 20). Also writes `demo/output/<name>.srt` and `demo/manifest.json`.

When `demo/narration.json` exists, each audio line is delayed to the exact moment its subtitle appeared - taken from the per-scene `timing.json` that `dv.py render` recorded, offset by where that scene starts on the final timeline - and mixed over a full-length silent bed so the AAC track always matches the video length. A line whose cue is missing is reported and skipped, never guessed.

Options:

| Flag | Effect |
|---|---|
| `--scenes-dir DIR` | Where the `.webm` clips are. Default `demo/scenes`. |
| `--out-dir DIR` | Default `demo/output`. |
| `--crf N` | Default 20. Lower is bigger and sharper. |
| `--videotoolbox` | Hardware H.264. Much faster, slightly larger. |
| `--keep-webm` | Also write a VP9 WebM alongside the mp4. |
| `--no-audio` | Skip the narration track even if `narration.json` exists. |
| `--no-srt` | Skip the `.srt` sidecar. |
| `--dry-run` | Print the ffmpeg command and exit. |

## What ffmpeg must provide

`dv.py doctor` checks these; its report is the source of truth for the current machine.

- **Required**: `xfade`, `concat`, `fps`, `scale`, `amix`, `adelay`, `libx264`, `aac`. `h264_videotoolbox` is optional (`--videotoolbox`).
- **Never used**: `drawtext`, `subtitles`, `ass`. Many builds lack `libass`/`libfreetype`, so text belongs in the browser overlay - see `effects.md`. The `.srt` is a sidecar, never burned in.

## Transitions

`transitionOut.type` on each scene, consumed when joining it to the next:

- `fade` - the safe default; use it unless there is a reason not to.
- `wipeleft` / `wiperight` / `wipeup` / `wipedown`
- `slideleft` / `slideright` / `slideup` / `slidedown` - reads as "moving forward through the app".
- `circlecrop`, `circleopen`, `dissolve`, `smoothleft`, `pixelize`, and the rest of xfade's 58.

`transitionOut.durationMs` default 500. Keep transitions between 300-700ms; longer ones eat the content on both sides.

**A transition consumes real time from both clips.** Total runtime is `sum(scene durations) - sum(transition durations)`. `compose` reports the arithmetic. A scene shorter than its own transition is an error, not a warning - the script refuses it.

## Mixed sizes

Every clip must share one resolution. `compose` runs `ffprobe` on each and aborts on a mismatch rather than silently scaling - a scene recorded at the wrong `size` is a re-record, not a rescale.

## Verify the result

Never report done on exit code 0. Tile the frames and look:

```bash
ffmpeg -y -v error -i demo/output/<name>.mp4 \
  -vf "select='not(mod(n\,50))',scale=426:-1,tile=5x4" -frames:v 1 demo/output/check.png
```

Read `demo/output/check.png`. Confirm the intro card, the subtitles, and the click ripples are visible and the transitions are not cutting off content.
