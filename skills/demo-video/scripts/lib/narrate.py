"""dv.py narrate - generate narration audio for a storyboard and reconcile subtitle timing.

    dv.py narrate [--storyboard demo/storyboard.json]
    dv.py narrate --dry-run     # preview, write nothing

Run this BEFORE rendering. Speech is slower than reading, so a subtitle that
was long enough to read can be too short to say. This measures every line and
sets `holdMs` to what the voice actually needs, and raises `dwellMs` only when
the scene is shorter than its narration end to end, so render.py records scenes
that already have room for the voice-over.

Uses macOS `say` (provider abstraction is scheduled for M4). A voice that is
listed but not installed produces ~16ms of silence; the probe below refuses it.

Prosody is derived from what each line says: a beat at the first clause
boundary, a slower rate for lines carrying numbers or error wording, and
emphasis on a substring the step names via `emphasis`. The markup is written
back into the storyboard so it stays visible and editable, and a line that
already carries [[...]] is never touched. Disable with --no-auto-prosody or
`narration.autoProsody: false`. See references/narration.md.
"""
import argparse
import math
import re
import subprocess
import sys

from . import common

PAD_MS = 400          # breathing room after a line before the subtitle clears
MIN_HOLD_MS = 1800
CLAUSE_PAUSE_MS = 300
CAREFUL_RATE = 155    # for lines carrying numbers, units, or error wording

# A clause boundary the viewer needs a beat at: "~하면", "~한 후", "~하고".
# Matched at a syllable boundary and only when real text follows.
CLAUSE_ENDINGS = [
    r"(?<=[가-힣])면", r"(?<=[가-힣])으면", r"(?<=[가-힣])하면", r"(?<=[가-힣])되면",
    r"(?<=[가-힣])후에", r"(?<=[가-힣\s])후", r"(?<=[가-힣\s])다음",
    r"(?<=[가-힣])지만", r"(?<=[가-힣])는데",
]
# Content that must not be rushed.
CAREFUL_PATTERNS = [r"\d", r"오류", r"에러", r"실패", r"경고", r"주의", r"필수", r"삭제"]


def spoken_text(text):
    """Drop [[...]] prosody commands - they are directives, not speech."""
    return re.sub(r"\[\[.*?\]\]", "", text).strip()


def auto_prosody(text, emphasis=None):
    """Annotate a line from what it says.

    Only mechanical, defensible edits: a beat at the first clause boundary, a
    slower rate for lines the viewer has to take in carefully, and emphasis on
    a substring the storyboard names explicitly. Anything already carrying
    [[...]] is left alone - a hand-tuned line is the author's decision.
    """
    if "[[" in text:
        return text, []
    out, notes = text, []

    # Decide from the words alone. Checking the annotated string instead would
    # let an inserted "[[slnc 300]]" read as a number and slow the whole line.
    base = spoken_text(text)
    careful = any(re.search(p, base) for p in CAREFUL_PATTERNS)

    if emphasis and emphasis in out:
        out = out.replace(emphasis, f"[[emph +]]{emphasis}[[emph -]]", 1)
        notes.append(f"emph '{emphasis}'")

    # One pause per line - two makes the delivery choppy.
    if len(spoken_text(out)) >= 14:
        for pat in CLAUSE_ENDINGS:
            m = re.search(pat + r"(?=\s)", out)
            if m and len(spoken_text(out[m.end():])) >= 6:
                out = out[:m.end()] + f"[[slnc {CLAUSE_PAUSE_MS}]]" + out[m.end():]
                notes.append(f"slnc {CLAUSE_PAUSE_MS} after '{m.group(0)}'")
                break

    if careful:
        out = f"[[rate {CAREFUL_RATE}]]" + out
        notes.append(f"rate {CAREFUL_RATE}")

    return out, notes


def reading_ms(text):
    """Same formula as prelude.js readingMs - 5 Korean chars/sec."""
    return max(MIN_HOLD_MS, math.ceil(len(text) / 5) * 1000 + 600)


duration_ms = common.duration_ms
die = common.die


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py narrate", description=__doc__.splitlines()[0])
    ap.add_argument("--storyboard", default=None)
    ap.add_argument("--voice", default=None, help="override the storyboard voice")
    ap.add_argument("--rate", type=int, default=None, help="words per minute; default 180")
    ap.add_argument("--no-auto-prosody", action="store_true",
                    help="speak the lines exactly as written")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    demo_dir = sb_path.parent
    audio_dir = demo_dir / "audio"
    name = sb.get("name") or "demo"   # narration 파일을 스토리보드별로 분리

    cfg = sb.get("narration") or {}
    if cfg.get("enabled") is False:
        die("storyboard sets narration.enabled = false")
    voice = args.voice or cfg.get("voice") or "Yuna"
    rate = args.rate or cfg.get("rate") or 180
    auto = cfg.get("autoProsody", True) and not args.no_auto_prosody

    audio_dir.mkdir(parents=True, exist_ok=True)
    probe = audio_dir / ".voice-check.aiff"
    subprocess.run(["say", "-v", voice, "-o", str(probe), "테스트"], capture_output=True)
    if not probe.exists() or duration_ms(probe) < 200:
        die(f"voice '{voice}' produces no audio - it is listed but not installed. "
            f"Try Yuna, or install the voice in System Settings > Accessibility > Spoken Content.")

    lines, changed, prosody = [], [], []
    for scene in sb.get("scenes") or []:
        sid = scene["id"]
        idx = 0
        for step in common.steps_of(scene):
            if step.get("action") != "subtitle":
                continue
            if step.get("narration") is False:      # subtitle only, stay silent
                silent = reading_ms(step.get("text", ""))
                if step.get("holdMs") != silent:
                    changed.append((sid, idx, step.get("holdMs"), silent))
                    step["holdMs"] = silent         # no voice: silent reading speed
                idx += 1
                continue
            text = step.get("narration") or step.get("text")
            if not text:
                idx += 1
                continue

            if auto:
                annotated, notes = auto_prosody(text, step.get("emphasis"))
                if notes:
                    prosody.append((sid, idx, notes))
                    step["narration"] = annotated   # written back so it is editable
                    text = annotated

            rel = f"audio/{sid}-{idx}.aiff"
            out = demo_dir / rel
            if not args.dry_run:
                r = subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(out), text],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    die(f"say failed on {sid}[{idx}]: {r.stderr.strip()}")
                ms = duration_ms(out)
            else:
                ms = int(len(spoken_text(text)) * 125)   # ~0.125s/char at rate 180

            # A narrated line is paced by the voice, not by silent reading. Taking
            # max() with readingMs here padded every subtitle by seconds of dead
            # air (measured: 390s of holds against 208s of speech).
            need = max(MIN_HOLD_MS, ms + PAD_MS)
            if step.get("holdMs") != need:
                changed.append((sid, idx, step.get("holdMs"), need))
                step["holdMs"] = need

            lines.append({"sceneId": sid, "index": idx, "text": text,
                          "file": rel, "durationMs": ms})
            idx += 1

        # A scene must fit its narration end to end - voices do not overlap.
        # Not the sum of holds: a sticky subtitle stays up across several visual
        # beats, so holds overlap them rather than adding to the scene.
        mine = [l for l in lines if l["sceneId"] == sid]
        spoken = sum(l["durationMs"] for l in mine)
        floor = spoken + 300 * max(0, len(mine) - 1) + PAD_MS if mine else 0
        if floor and scene.get("dwellMs") and scene["dwellMs"] < floor:
            print(f"  {sid}: dwellMs {scene['dwellMs']}ms is under the {floor}ms "
                  f"its narration needs ({len(mine)} lines) - raising", file=sys.stderr)
            scene["dwellMs"] = floor

    if not lines:
        die("no narratable subtitle steps found - add `steps` with action \"subtitle\"")

    total = sum(l["durationMs"] for l in lines)
    print(f"voice {voice} @ {rate}wpm  |  {len(lines)} lines  |  "
          f"{total / 1000:.1f}s of speech  |  auto-prosody {'on' if auto else 'off'}")
    for l in lines:
        print(f'  {l["sceneId"]}[{l["index"]}] {l["durationMs"] / 1000:>5.2f}s  '
              f'{spoken_text(l["text"])[:38]}')
    for sid, i, notes in prosody:
        print(f'  prosody {sid}[{i}]: ' + ", ".join(notes))
    for sid, i, was, now in changed:
        print(f'  holdMs {sid}[{i}]: {was} -> {now}')

    if args.dry_run:
        print("\n--dry-run: no audio written, storyboard untouched")
        return 0

    nar_out = demo_dir / f"narration-{name}.json"
    common.dump_json(nar_out, {"voice": voice, "rate": rate, "padMs": PAD_MS, "lines": lines})
    common.dump_json(sb_path, sb)
    print(f"\nwrote {len(lines)} clips to audio/ and {nar_out.name}, "
          f"and updated storyboard timings")
    print("re-render the affected scenes so the clips match the new holds")
    return 0
