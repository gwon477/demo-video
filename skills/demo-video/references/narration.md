# Narration and subtitles

Two separate outputs, one source text:

| Output | How | Burned in? |
|---|---|---|
| On-screen subtitle | browser overlay, recorded into the frames | yes |
| Voice-over | macOS `say`, muxed as an AAC track | separate audio track |
| `.srt` sidecar | written from the recorded cues | no - a separate file |

The `.srt` cannot be burned into the picture: this ffmpeg build has no `libass`. It exists for players, YouTube, and search. The visible subtitle is already in the frames.

## The order matters

```
storyboard.json  →  dv.py narrate  →  dv.py render  →  dv.py compose
                    measures &      records      places audio
                    widens holds    cues         on the cues
```

Speech is slower than reading. A subtitle sized to be *read* is often too short to be *said*, so `dv.py narrate` runs first: it generates every line, measures it, and widens `holdMs` to `max(readingMs, spokenMs + 400)`, raising the scene's `dwellMs` if the subtitles no longer fit. It rewrites `storyboard.json` in place and prints every change.

**Re-render any scene whose holds changed.** `dv.py narrate` says which. Skipping this leaves clips shorter than their narration, and the voice runs past the picture.

`--dry-run` estimates durations (~0.125s per Korean character) and writes nothing.

## Voices

`say -v '?'` lists several `ko_KR` voices, but a listed voice is not necessarily installed - an uninstalled one synthesizes ~16ms of silence. `dv.py doctor` reports which voices are real; `dv.py narrate` probes the chosen voice and refuses to run on a silent one. `Yuna` is the usual default.

To add voices: System Settings → Accessibility → Spoken Content → System Voice → Manage Voices. Verify a new one before trusting it:

```bash
say -v <name> -o demo/audio/voice-check.aiff "테스트" && ffprobe -v error -show_entries format=duration -of csv=p=0 demo/audio/voice-check.aiff
```

Anything under ~0.2s means it is not installed.

Rate is words per minute, default 180, set per storyboard or per line with `[[rate N]]`. Measured on Korean text: 150 → 3.27s, 180 → 2.76s, 210 → 1.97s for the same 21-character line. Below 150 sounds sluggish; above 210 clips consonants.

Provider abstraction (`say`, `edge-tts`, `none`) is planned for M4. Until then the contract is fixed: one audio file per line plus its measured duration.

## Prosody from what the subtitle says

`dv.py narrate` annotates each line from its own content, so delivery matches meaning instead of every sentence coming out flat. It runs by default, writes the markup **back into the storyboard** so it stays visible and editable, and never touches a line that already carries `[[...]]` - a hand-tuned line is the author's decision.

| Subtitle content | Applied | Why |
|---|---|---|
| Clause boundary - `~하면`, `~되면`, `~한 후`, `~다음`, `~지만`, `~는데` | `[[slnc 300]]` after it | The viewer looks at the screen at exactly that beat. Speaking through it means they miss either the words or the picture. |
| A number, unit, `오류`, `에러`, `실패`, `경고`, `주의`, `필수`, `삭제` | `[[rate 155]]` on the line | Content the viewer has to take in exactly, or a consequence they cannot undo. |
| Step declares `"emphasis": "<substring>"` | `[[emph +]]…[[emph -]]` | Marks the one word the scene is actually about. |
| Short, simple line | nothing | Markup on a five-word line reads as a stutter. |

Only one pause is inserted per line - two makes the delivery choppy. The decision is made on the words alone, before any markup is inserted, so an inserted `[[slnc 300]]` is never mistaken for a number.

```json
{ "action": "subtitle",
  "text": "필터를 적용하면 조건에 맞는 결과만 표시됩니다",
  "emphasis": "결과만" }
```

becomes

```
필터를 적용하면[[slnc 300]] 조건에 맞는 [[emph +]]결과만[[emph -]] 표시됩니다
```

Turn it off with `--no-auto-prosody` or `"narration": { "autoProsody": false }`. Override any single line by writing its `narration` field with your own markup.

### When to override by hand

The rules are mechanical and will not catch meaning. Take over when:

- The pause belongs somewhere other than the first clause boundary.
- The line needs two beats - write both yourself; the rule only ever adds one.
- The emphasis is on a phrase the storyboard cannot name as a single substring.
- The line reads a proper noun or an abbreviation that needs checking by ear.

## Prosody control

A narration string may carry Apple's embedded speech commands, `[[...]]`. They pass through `dv.py narrate` to `say` untouched, and durations are measured on the rendered audio - so a pause or a rate change is already counted in the subtitle hold. `dv.py narrate` strips the markup when printing and when estimating in `--dry-run`.

Measured on `Yuna` at rate 180, baseline line "핵심 지표를 확인합니다" = 1.639s:

| Command | Effect | Verified |
|---|---|---|
| `[[slnc N]]` | insert N ms of silence | yes |
| `[[rate N]]` | change speed mid-sentence, words per minute | yes |
| `[[pbas N]]` | pitch base, roughly 30-70 | yes |
| `[[emph +]]` … `[[emph -]]` | stress the enclosed word | yes |
| `[[volm N]]` | volume 0.0-1.0 (`0.5` measured 12 dB down) | yes |
| `[[pmod N]]` | pitch modulation | **ignored** - output is byte-identical to baseline |

Do not reach for `[[pmod]]`; it does nothing on this voice. To vary expressiveness, use `[[pbas]]` and `[[emph]]` instead.

### Pauses

Mid-sentence `[[slnc N]]` is accurate to within ~5%:

```
slnc 200  → +255ms      slnc 1000 → +998ms
slnc 500  → +534ms      slnc 2000 → +1916ms
```

**Leading silence is partly swallowed** - `[[slnc 500]]` at the start of a line adds only ~369ms, `[[slnc 1000]]` ~834ms. To delay a line's onset, do not pad the text; the line is already placed at its subtitle's cue, so move the `subtitle()` call later in the scene body instead.

Punctuation also paces speech without any markup: a comma adds ~255ms, a period ~280ms. An ellipsis behaves exactly like a period - it is not a longer pause.

### Tuning by ear

Duration is measurable; naturalness is not. Generate a candidate and listen before committing:

```bash
say -v Yuna -r 180 "필터를 적용하면[[slnc 400]] 조건에 맞는 결과만 표시됩니다"
```

Practical starting points:

- `[[slnc 300]]`-`[[slnc 500]]` after a clause that introduces something the viewer needs to look at.
- `[[rate 150]]` for a line carrying a number, an error message, or anything the viewer must copy down. Default 180 elsewhere.
- `[[emph +]]` on exactly one word per line. Two emphases in one sentence read as none.
- Leave `[[volm]]` alone unless a line is competing with something; the mix has no other audio.

## Storyboard fields

```json
{
  "narration": { "enabled": true, "voice": "Yuna", "rate": 180 },
  "scenes": [{
    "id": "03-dashboard",
    "steps": [
      { "action": "subtitle", "text": "대시보드에서 핵심 지표를 확인합니다" },
      { "action": "subtitle", "text": "기간 변경", "narration": "기간을 바꾸면 그래프가 즉시 갱신됩니다" },
      { "action": "subtitle", "text": "화면에만 표시", "narration": false }
    ]
  }]
}
```

- Default: the subtitle text is spoken as-is.
- `narration: "<text>"` speaks something different from what is shown. Use this when the subtitle has to be short enough to fit on screen but the explanation needs more words, or when the line needs prosody markup that must not appear on screen.
- `narration: false` shows the subtitle silently.

## Placement

Narration is **not** placed from the storyboard's planned timings - those drift from what actually gets recorded. `subtitle()` stamps each cue's real in/out point during recording, `dv.py render` writes them to `demo/scenes/<id>.timing.json`, and `dv.py compose` places line *n* of a scene at cue *n* of that scene, offset by where the scene starts on the final timeline (accounting for transition overlap).

A narration line with no matching cue is reported and left out rather than guessed at. That mismatch means the scene body has fewer `subtitle()` calls than the storyboard has subtitle steps - fix the body.

## Writing lines that work as both

The same sentence has to read well on screen and sound right out loud.

- Under 40 characters. Longer wraps on screen and runs long in speech.
- End sentences properly. `say` uses punctuation for prosody; a line with no final period sounds clipped.
- Avoid bare English abbreviations mid-sentence - `say` reads `API` letter by letter in Korean context, which is usually right, but check anything unusual by listening.
- Numbers and units are read out; `3초` is fine, `3s` is not.
