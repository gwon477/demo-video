"""dv.py check-sync - check that storyboard, scene body, narration and recorded cues agree.

    dv.py check-sync [--storyboard demo/storyboard.json]

Run it twice: after writing the scene bodies (catches drift before you spend a
render) and after rendering (catches drift the render revealed). Exit code 1
means the video would be out of sync - fix it before composing.

Four things must line up for page, subtitle and voice to land together:

  storyboard step  ->  subtitle() call in the body   (same count, same text)
  storyboard step  ->  narration line                (one audio clip per line)
  subtitle() call  ->  recorded cue in timing.json   (render writes these)
  cue on-screen    >=  its narration length          (voice fits the subtitle)
"""
import argparse
import re
import sys

from . import bodygen, common
from .compose import find_narration

MARGIN_MS = 150       # a cue may be this much shorter than its line and still pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py check-sync", description=__doc__.splitlines()[0])
    ap.add_argument("--storyboard", default=None)
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    demo_dir = sb_path.parent
    scenes_dir = demo_dir / "scenes"

    version = common.schema_version(sb)
    narration = find_narration(demo_dir, common.name_of(sb))
    nar_by_key = {(l["sceneId"], l["index"]): l for l in (narration or {}).get("lines", [])}

    errors, warnings, checked = [], [], 0

    for scene in sb.get("scenes") or []:
        sid = scene["id"]
        steps = common.subtitle_steps(scene, version)

        body_path = scenes_dir / f"{sid}.body.js"
        if body_path.exists():
            body = body_path.read_text(encoding="utf-8")
        elif version >= 2:
            body = bodygen.scene_body(scene)      # what render will generate
        else:
            errors.append(f"{sid}: no body at scenes/{sid}.body.js")
            continue

        # 1. storyboard steps vs subtitle-producing calls
        calls = (len(re.findall(r"\bsubtitle\s*\(", body))
                 + len(re.findall(r"\bsubtitleSpan\s*\(", body)))
        seq = len(re.findall(r"\bsubtitles\s*\(", body))
        if seq:
            warnings.append(f"{sid}: uses subtitles([...]) - its lines are not counted here")
        elif calls != len(steps):
            errors.append(f"{sid}: storyboard has {len(steps)} subtitle step(s) "
                          f"but the body makes {calls} subtitle() call(s)")

        # 2. the text actually shown matches the text planned
        for i, st in enumerate(steps):
            txt = st.get("text", "")
            if txt and txt not in body:
                errors.append(f'{sid}[{i}]: body never shows "{txt[:30]}"')

        # 3. one narration clip per narratable step
        if narration:
            for i, st in enumerate(steps):
                if st.get("narration") is False:
                    continue
                line = nar_by_key.get((sid, i))
                if not line:
                    errors.append(f"{sid}[{i}]: no narration line - re-run narrate")
                elif not (demo_dir / line["file"]).exists():
                    errors.append(f'{sid}[{i}]: narration audio missing at {line["file"]}')

        # 4. recorded cues - only present after a render
        timing_path = scenes_dir / f"{sid}.timing.json"
        if not timing_path.exists():
            if steps:
                warnings.append(f"{sid}: not rendered yet - cue checks skipped")
            continue
        cues = common.load_json(timing_path).get("cues") or []

        if len(cues) != len(steps):
            errors.append(f"{sid}: recorded {len(cues)} cue(s) for {len(steps)} "
                          f"subtitle step(s) - the body and the storyboard disagree")

        webm = scenes_dir / f"{sid}.webm"
        clip_ms = common.duration_ms(webm) if webm.exists() else 0

        for i, cue in enumerate(cues):
            checked += 1
            on_screen = (cue.get("endMs") or 0) - cue["startMs"]
            if on_screen <= 0:
                errors.append(f"{sid}[{i}]: cue never closed - the subtitle was not disposed")
                continue
            if clip_ms and cue["endMs"] > clip_ms + 50:
                errors.append(f'{sid}[{i}]: subtitle runs to {cue["endMs"]}ms but the clip '
                              f"ends at {clip_ms}ms - it is cut off")
            line = nar_by_key.get((sid, i))
            if line and on_screen + MARGIN_MS < line["durationMs"]:
                errors.append(f'{sid}[{i}]: on screen {on_screen}ms but narration is '
                              f'{line["durationMs"]}ms - the voice outlasts the subtitle. '
                              f"Re-run narrate, then re-render {sid}.")
            if line and i < len(cues) - 1:
                gap = cues[i + 1]["startMs"] - (cue["startMs"] + line["durationMs"])
                if gap < 0:
                    errors.append(f"{sid}[{i}]: narration overruns the next subtitle "
                                  f"by {-gap}ms")

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} sync problem(s) - do not compose yet", file=sys.stderr)
        return 1
    print(f"in sync: {len(sb.get('scenes') or [])} scene(s), {checked} cue(s) checked"
          + (f", narration {len(nar_by_key)} line(s)" if narration else ", no narration"))
    return 0
