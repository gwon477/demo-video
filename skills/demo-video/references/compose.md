# Compose and verify

```bash
python3 <skill>/scripts/dv.py compose            # demo/output/<name>.mp4 + .srt, demo/manifest.json
python3 <skill>/scripts/dv.py verify             # look at the result: tile, black frames, subtitles, loudness
python3 <skill>/scripts/dv.py compose --draft    # draft clips, cuts only, no audio -> <name>-draft.mp4
```

`compose` reads the storyboard, takes each clip from `demo/scenes/`, chains them with `xfade`, mixes audio, and encodes H.264 exactly once (FR-056). Intermediate clips stay WebM.

## Structure (FR-040 ~ FR-043)

```
intro  →  fade  →  scene 1  →  transitionIn  →  scene 2 … →  fade  →  outro
```

- **Intro / outro from HTML** (`source: "html"`): `render` records `assets/intro/default.html` (or a template under `demo/` when `template` is a path) with the title, tagline, brand and cta filled in; animations start on camera. The clip is padded to `holdMs` because a static card emits no frames.
- **Intro / outro from a user video** (`source: "video"`): `compose` normalizes it to the frame size, 25fps and yuv420p. A different aspect ratio is letterboxed and reported in `manifest.notes` - tell the user (FR-041).
- Transitions belong to the scene being entered: `transitionIn: { type, ms }`, `fade` 400ms by default, `cut` between scenes on the same page (FR-043). A cut is a one-frame fade so the whole video is one filter graph.
- Total runtime is `Σ clips − Σ transitions`; `compose` prints the arithmetic and refuses a transition longer than either clip.

## Audio (FR-078)

| Source | What compose does |
|---|---|
| Narration (`demo/narration-<name>.json`) | each line delayed to its recorded cue (`timing.json` + scene start), mixed over a silent bed |
| BGM (`config.bgm.source: "file"`, registered by `dv.py bgm probe <file>`) | looped to the video length, fade in 1.5s, fade out 2s, ducked −18 dB under narration (300ms attack, 800ms release, deterministic from the cue times) |
| Mix | two-pass `loudnorm` to −16 LUFS integrated, −1 dBTP; AAC 192k |

Values live in `assets/theme.json` → `audio`. No BGM and no narration → the mp4 has no audio track. `bgm fetch` / `pick` (the catalog) are not available until the catalog is verified.

## Draft mode (FR-052)

`render --draft` records 960px-wide clips into `demo/scenes/draft/`; `compose --draft` joins them with cuts, no audio, into `<name>-draft.mp4`. Use it for the first look; the full-size cache is untouched.

## Verify - never report done on exit code 0

```bash
python3 <skill>/scripts/dv.py verify            # writes output/verify-tile.png and output/verify.json
```

| Check | Fails when |
|---|---|
| frames | a black frame at a scene's start, middle or end |
| subtitle under zoom | on a zoomed frame the subtitle box leaves the title-safe area (88%), is not in the bottom band, or is off center |
| loudness | integrated loudness outside target ±1 LU, true peak above the ceiling (only with audio) |
| narration | the first cue is silent; without BGM, the gap before it is not silent |

Then **read `output/verify-tile.png`** (one frame per scene) and confirm the intro card, subtitles and effects are visible. Report the mp4 path, runtime, and whether narration and BGM are included. That is G4.

## Manifest

`demo/manifest.json` records name, resolution, duration, scene starts, cue count, notes (letterboxing, streaming spans) and output paths. `verify` reads it, so run `compose` first.
