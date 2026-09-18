# Narration and subtitles

Two outputs from one text: the on-screen subtitle (recorded into the frames) and the voice-over (a separate AAC track placed at each subtitle's recorded cue). The `.srt` sidecar is written from the same cues; nothing is burned in by ffmpeg.

## Order

```
storyboard.json  →  dv.py narrate  →  dv.py render  →  dv.py compose
                    measures & sets    records cues    places audio on the cues
                    holdMs/narrationMs
```

Speech is slower than reading, so `narrate` runs before `render`: each line is synthesized and measured, the step gets `narrationMs`, `holdMs = max(reading time, speech + 400ms)` (FR-013), and `dwellMs` is refilled by the validate rules. Re-rendering after `narrate` is automatic: holds are in the scene hash, so only scenes whose holds changed are re-recorded. `check-sync` then confirms every cue is on screen at least as long as its line.

## Providers (`dv.py init --narration ...`, `config.narration.provider`)

| Provider | Voice default | Where the text goes | Markup |
|---|---|---|---|
| `say` (macOS) | `Yuna` | local | Apple `[[slnc N]]` `[[rate N]]` `[[emph +]]…[[emph -]]` honored |
| `edge-tts` | `ko-KR-SunHiNeural` | Microsoft service - not for confidential lines (DESIGN A5) | markup stripped; `[[slnc]]` becomes a comma pause |
| `none` | - | - | `narrate` refuses |

`dv.py doctor` reports which providers are installed. A listed `say` voice can still be uninstalled; `narrate` probes it and refuses one that yields silence.

## Rates

`theme.narration.rate` 150 wpm (about 330-350 syllables/min, the pace of a news reader) and `carefulRate` 120 for lines carrying numbers, units or error words. edge-tts gets the same intent as a percent offset. Override per run with `--rate`.

## Prosody from what the subtitle says

`narrate` annotates each line from its own words and writes the markup back into the step's `narration` field so it stays visible and editable. A line that already carries `[[...]]` is never touched.

| Content | Applied |
|---|---|
| First clause boundary (`~하면`, `~되면`, `~한 후`, `~다음`, `~지만`, `~는데`) | `[[slnc 300]]` after it - one per line |
| A number, unit, `오류`, `에러`, `실패`, `경고`, `주의`, `필수`, `삭제` | careful rate for the line |
| `"emphasis": "<substring>"` on the step | `[[emph +]]…[[emph -]]` |

`--no-auto-prosody` or `narration.autoProsody: false` turns it off. Hand-tune by writing the step's `narration` yourself.

## Storyboard fields (schemaVersion 2)

```json
{ "subtitle": { "text": "기간 변경", "emphasis": "기간", "narration": "기간을 바꾸면[[slnc 300]] 그래프가 즉시 갱신됩니다" } }
{ "subtitle": { "text": "화면에만 표시", "narration": false } }
```

- default: the subtitle text is spoken as-is
- `narration: "<text>"`: speak something longer than the one-line subtitle
- `narration: false`: silent subtitle

## Writing lines that work as both

- Under 32 weighted characters on screen (FR-012); the spoken `narration` may be longer.
- End sentences properly; the voice uses punctuation for prosody.
- Numbers and units are read out: `3초`, not `3s`.
- Check a proper noun by ear once: `say -v Yuna "..."`.
