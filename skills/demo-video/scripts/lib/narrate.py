"""dv.py narrate - generate narration audio for a storyboard and reconcile subtitle timing.

    dv.py narrate [--storyboard demo/storyboard.json]
    dv.py narrate --dry-run     # estimate, write nothing
    dv.py narrate --provider edge-tts --voice ko-KR-SunHiNeural

Run this BEFORE rendering. Speech is slower than reading, so a subtitle that was
long enough to read can be too short to say. Every line is measured and the
step gets `narrationMs`; `holdMs` becomes max(reading time, speech + 400ms)
(FR-013) and `dwellMs` is refilled by the validate rules, so render records
scenes that already have room for the voice.

Provider and voice come from config.narration (`dv.py init --narration say|edge-tts`),
overridable here. Rates come from theme.narration (150 wpm, 120 for careful lines).
Prosody markup ([[slnc]], [[rate]], [[emph]]) is Apple `say` syntax; edge-tts gets
a plain rendering of it. A line that already carries [[...]] is never rewritten.
"""
import argparse
import math
import re
import sys

from . import common, tts
from .validate import hold_ms, validate

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
    ap.add_argument("--provider", default=None, choices=["say", "edge-tts", "none"])
    ap.add_argument("--voice", default=None)
    ap.add_argument("--rate", type=int, default=None, help="words per minute; default theme.narration.rate")
    ap.add_argument("--no-auto-prosody", action="store_true", help="speak the lines exactly as written")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    demo_dir = sb_path.parent
    audio_dir = demo_dir / "audio"
    name = common.name_of(sb)
    version = common.schema_version(sb)
    theme = common.load_theme(demo_dir)
    cfg_p = demo_dir / "config.json"
    cfg = (common.load_json(cfg_p) if cfg_p.exists() else {}).get("narration") or {}
    sbn = sb.get("narration") or (sb.get("meta") or {}).get("narration") or {}
    if isinstance(sbn, bool):
        sbn = {"enabled": sbn}
    provider = args.provider or cfg.get("provider") or ("say" if sbn.get("voice") else None) or "none"
    if provider == "none" or sbn.get("enabled") is False:
        die("narration is off (config.narration.provider = none). Run `dv.py init --narration say|edge-tts`, "
            "or pass --provider")
    voice = args.voice or cfg.get("voice") or sbn.get("voice") or tts.DEFAULT_VOICE[provider]
    rate = args.rate or sbn.get("rate") or theme["narration"]["rate"]
    careful_rate = theme["narration"].get("carefulRate", CAREFUL_RATE)
    pad = theme["narration"].get("padMs", PAD_MS)
    auto = sbn.get("autoProsody", True) and not args.no_auto_prosody

    audio_dir.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        problem = tts.check_voice(provider, voice, audio_dir)
        if problem:
            die(problem)

    lines, changed, prosody = [], [], []
    for scene in sb.get("scenes") or []:
        sid = scene["id"]
        idx = 0
        for item in common.subtitle_steps(scene, version):
            step = item["step"]
            sub = step["subtitle"] if version >= 2 else step
            shown = sub.get("text", "")
            if sub.get("narration") is False:      # subtitle only, stay silent
                step.pop("narrationMs", None)
                idx += 1
                continue
            text = sub.get("narration") or shown
            if not text:
                idx += 1
                continue
            if auto:
                annotated, notes = auto_prosody(text, sub.get("emphasis"))
                if notes:
                    prosody.append((sid, idx, notes))
                    sub["narration"] = annotated   # written back so it is editable
                    text = annotated
            careful = text.startswith(f"[[rate {CAREFUL_RATE}]]")
            line_rate = careful_rate if careful else rate
            rel = f"audio/{sid}-{idx}.{tts.ext(provider)}"
            out = demo_dir / rel
            if not args.dry_run:
                try:
                    ms = tts.synthesize(provider, voice, line_rate, text, out)
                except RuntimeError as e:
                    die(f"{sid}[{idx}]: {e}")
            else:
                ms = int(len(spoken_text(text)) * 60000 / (line_rate * 2.2))   # ~2.2 syllables per "word"

            # FR-013: the subtitle stays for the longer of reading time and speech + pad.
            need = max(hold_ms(shown, theme), ms + pad)
            if step.get("holdMs") != need:
                changed.append((sid, idx, step.get("holdMs"), need))
                step["holdMs"] = need
            step["narrationMs"] = ms
            lines.append({"sceneId": sid, "index": idx, "text": text, "file": rel, "durationMs": ms, "rateWpm": line_rate})
            idx += 1

    if not lines:
        die("no narratable subtitle steps found")

    # Scenes must fit their voice: refill dwellMs with the storyboard rules (holds + actions + density floor).
    if version >= 2:
        f, _ = validate(sb, demo_dir, theme=theme, fix=True)
        for fx in f.fixes:
            print(f"  {fx}")
        if f.errors:
            print("\n".join(f"warning [{e['rule']}] {e['where']}: {e['msg']}" for e in f.errors), file=sys.stderr)

    total = sum(l["durationMs"] for l in lines)
    print(f"{provider} {voice} @ {rate}wpm  |  {len(lines)} lines  |  {total / 1000:.1f}s of speech  |  auto-prosody {'on' if auto else 'off'}")
    for l in lines:
        print(f'  {l["sceneId"]}[{l["index"]}] {l["durationMs"] / 1000:>5.2f}s  {spoken_text(l["text"])[:38]}')
    for sid, i, notes in prosody:
        print(f'  prosody {sid}[{i}]: ' + ", ".join(notes))
    for sid, i, was, now in changed:
        print(f'  holdMs {sid}[{i}]: {was} -> {now}')

    if args.dry_run:
        print("\n--dry-run: no audio written, storyboard untouched")
        return 0
    nar_out = demo_dir / f"narration-{name}.json"
    common.dump_json(nar_out, {"provider": provider, "voice": voice, "rate": rate, "padMs": pad, "lines": lines})
    common.dump_json(sb_path, sb)
    print(f"\nwrote {len(lines)} clips to audio/ and {nar_out.name}, and updated storyboard timings")
    print("re-render the affected scenes so the clips match the new holds (the hash cache does that)")
    return 0
