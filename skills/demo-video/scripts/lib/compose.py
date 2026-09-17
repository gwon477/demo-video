"""dv.py compose - join demo scene clips with xfade transitions and encode an mp4.

    dv.py compose [--storyboard demo/storyboard.json] [options]

Text is never burned in here. ffmpeg builds without libass/libfreetype are
common, so subtitles and cards are recorded in the browser. See
references/compose.md.

When the narration index exists, each line is placed on the final timeline at
the exact moment its subtitle appeared (from the per-scene timing.json that
render wrote) and muxed as an AAC track. A matching .srt sidecar is written
from the same cues.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import common

FPS = 25


def probe(path: Path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True)
    if out.returncode != 0:
        common.die(f"ffprobe failed on {path}\n{out.stderr.strip()}")
    d = json.loads(out.stdout)
    st = (d.get("streams") or [{}])[0]
    dur = float(d.get("format", {}).get("duration") or 0)
    if not dur:
        common.die(f"{path} has no duration - was screencast.stop() called?")
    return {"path": path, "w": st.get("width"), "h": st.get("height"), "dur": dur}


def srt_time(ms):
    h, ms = divmod(int(ms), 3600000)
    m, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def load_cues(scenes_dir: Path, sid):
    p = scenes_dir / f"{sid}.timing.json"
    if not p.exists():
        return []
    return common.load_json(p).get("cues") or []


def find_narration(demo_dir: Path, name):
    for cand in (demo_dir / f"narration-{name}.json", demo_dir / "narration.json"):
        if cand.exists():
            return common.load_json(cand)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py compose", description=__doc__.splitlines()[0])
    ap.add_argument("--storyboard", default=None)
    ap.add_argument("--scenes-dir", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--videotoolbox", action="store_true")
    ap.add_argument("--keep-webm", action="store_true")
    ap.add_argument("--no-audio", action="store_true", help="skip the narration track")
    ap.add_argument("--no-srt", action="store_true", help="skip the .srt sidecar")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    root = sb_path.parent

    name = common.name_of(sb)
    version = common.schema_version(sb)
    theme = common.load_theme()
    scenes_dir = Path(args.scenes_dir).resolve() if args.scenes_dir else root / "scenes"
    out_dir = Path(args.out_dir).resolve() if args.out_dir else root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    scenes = list(sb.get("scenes") or [])
    if not scenes:
        common.die("storyboard has no scenes")
    if version >= 2:
        # HTML intro/outro were rendered as clips; user videos are normalized in M3.
        if (sb.get("intro") or {}).get("source") == "html":
            scenes.insert(0, {"id": "00-intro", "kind": "intro"})
        if (sb.get("outro") or {}).get("source") == "html":
            scenes.append({"id": "99-outro", "kind": "outro",
                           "transitionIn": {"type": theme["transition"]["default"], "ms": theme["transition"]["defaultMs"]}})

    clips, missing = [], []
    for sc in scenes:
        sid = sc.get("id") or common.die("a scene is missing its id")
        p = scenes_dir / f"{sid}.webm"
        if not p.exists():
            missing.append(str(p))
            continue
        info = probe(p)
        info["scene"] = sc
        clips.append(info)
    if missing:
        common.die("scene clips not rendered yet:\n  " + "\n  ".join(missing))

    sizes = {(c["w"], c["h"]) for c in clips}
    if len(sizes) > 1:
        detail = "\n  ".join(f'{c["scene"]["id"]}: {c["w"]}x{c["h"]}' for c in clips)
        common.die("scene clips have different resolutions - re-record, do not rescale:\n  " + detail)
    w, h = clips[0]["w"], clips[0]["h"]

    # transitions:"none" 은 컷 편집 - xfade 없이 이어 붙인다. 한 세션을
    # 끊김 없이 보여주는 영상에서는 크로스페이드가 오히려 장면 전환처럼 읽힌다.
    cut_only = str(sb.get("transitions", "")).lower() == "none"

    # Transition out of clip i, in ms, taken from that scene. Last scene has none.
    trans = []
    for i, c in enumerate(clips[:-1]):
        if cut_only:
            trans.append(("cut", 0.0))
            continue
        if version >= 2:
            # v2: the transition belongs to the scene being entered.
            t = clips[i + 1]["scene"].get("transitionIn") or {}
            ms = int(t.get("ms", theme["transition"]["defaultMs"]))
            typ = t.get("type", theme["transition"]["default"])
            if typ == "cut":
                trans.append(("cut", 0.0))
                continue
        else:
            t = (c["scene"].get("transitionOut") or {})
            ms = int(t.get("durationMs", 500))
            typ = t.get("type", "fade")
        if ms / 1000.0 >= min(c["dur"], clips[i + 1]["dur"]):
            common.die(f'{c["scene"]["id"]}: transition {ms}ms is longer than the clip '
                       f'({c["dur"]:.2f}s) - shorten the transition or lengthen the scene')
        trans.append((typ, ms / 1000.0))

    # Warn where a scene is too short for the subtitles it carries.
    for c in clips:
        need = sum(int(s["holdMs"] or 0) for s in common.subtitle_steps(c["scene"], version)) / 1000.0
        if need and c["dur"] + 0.4 < need:
            print(f'warning: {c["scene"]["id"]} is {c["dur"]:.2f}s but its subtitles '
                  f'need {need:.2f}s - some will be cut off', file=sys.stderr)

    parts, inputs = [], []
    for i, c in enumerate(clips):
        inputs += ["-i", str(c["path"])]
        parts.append(f"[{i}:v]fps={FPS},format=yuv420p,setsar=1,scale={w}:{h}[s{i}]")

    if len(clips) == 1:
        parts.append("[s0]copy[vout]")
    elif cut_only:
        parts.append("".join(f"[s{i}]" for i in range(len(clips)))
                     + f"concat=n={len(clips)}:v=1:a=0[vout]")
    else:
        acc = clips[0]["dur"]
        prev = "s0"
        for i in range(1, len(clips)):
            typ, tdur = trans[i - 1]
            if typ == "cut":
                # One graph for everything: a cut is a one-frame fade in xfade terms.
                typ, tdur = "fade", 1.0 / FPS
                trans[i - 1] = (typ, tdur)
            offset = acc - tdur
            label = "vout" if i == len(clips) - 1 else f"v{i}"
            parts.append(
                f"[{prev}][s{i}]xfade=transition={typ}:duration={tdur:.3f}:"
                f"offset={offset:.3f}[{label}]")
            acc = acc + clips[i]["dur"] - tdur
            prev = label

    total = sum(c["dur"] for c in clips) - sum(t[1] for t in trans)

    # Where each scene's own frame 0 lands on the final timeline - the same
    # accumulation the xfade offsets use.
    starts, acc = [0.0], 0.0
    for i in range(1, len(clips)):
        acc += clips[i - 1]["dur"] - trans[i - 1][1]
        starts.append(acc)

    # Absolute subtitle cues, for both the narration placement and the .srt.
    cues = []
    for c, start in zip(clips, starts):
        for i, cue in enumerate(load_cues(scenes_dir, c["scene"]["id"])):
            cues.append({"sceneId": c["scene"]["id"], "index": i,
                         "startMs": int(start * 1000) + cue["startMs"],
                         "endMs": int(start * 1000) + (cue.get("endMs") or cue["startMs"] + 2000),
                         "text": cue.get("text", "")})
    cues.sort(key=lambda c: c["startMs"])

    narration = None if args.no_audio else find_narration(root, name)

    fc = ";".join(parts)
    mp4 = out_dir / f"{name}.mp4"
    venc = (["-c:v", "h264_videotoolbox", "-b:v", "6M"] if args.videotoolbox
            else ["-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf)])

    # Narration: one input per line, delayed to its subtitle's moment, mixed
    # over a full-length silent bed so the track never ends before the video.
    audio_inputs, amaps, aenc, amap, unplaced = [], [], [], [], []
    placed = 0
    if narration:
        by_cue = {(c["sceneId"], c["index"]): c for c in cues}
        n = len(clips)
        for line in narration.get("lines") or []:
            cue = by_cue.get((line["sceneId"], line["index"]))
            src = root / line["file"]
            if cue is None or not src.exists():
                unplaced.append(f'{line["sceneId"]}[{line["index"]}]')
                continue
            idx = n + placed                       # ffmpeg input index, not list length
            audio_inputs += ["-i", str(src)]
            amaps.append(f'[{idx}:a]aresample=48000,'
                         f'adelay={cue["startMs"]}|{cue["startMs"]}[na{placed}]')
            placed += 1

        if placed:
            bed_idx = len(clips) + placed
            audio_inputs += ["-f", "lavfi", "-t", f"{total:.3f}",
                             "-i", "anullsrc=r=48000:cl=stereo"]
            mixed = "".join(f"[na{i}]" for i in range(placed))
            fc += ";" + ";".join(amaps) + (
                f";[{bed_idx}:a]{mixed}"
                f"amix=inputs={placed + 1}:normalize=0:dropout_transition=0[aout]")
            amap = ["-map", "[aout]"]
            aenc = ["-c:a", "aac", "-b:a", "128k"]

    cmd = (["ffmpeg", "-y", "-v", "error", "-stats"] + inputs + audio_inputs +
           ["-filter_complex", fc, "-map", "[vout]"] + amap + venc + aenc +
           ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)])

    print(f"{len(clips)} scenes  {w}x{h}  "
          f"{sum(c['dur'] for c in clips):.2f}s raw "
          f"- {sum(t[1] for t in trans):.2f}s transitions "
          f"= {total:.2f}s final")
    for c, t in zip(clips, list(trans) + [None]):
        tail = '' if (t is None or t[0] == "cut") else f'  -{t[0]} {t[1]:.2f}s'
        print(f'  {c["scene"]["id"]:<20} {c["dur"]:>6.2f}s{tail}')

    if narration:
        spoken = sum(l["durationMs"] for l in narration.get("lines") or []) / 1000.0
        print(f'  narration: {placed} lines, {spoken:.1f}s spoken, voice {narration.get("voice")}')
        for u in unplaced:
            print(f"  warning: no subtitle cue for narration line {u} - not placed", file=sys.stderr)

    if args.dry_run:
        print("\n" + " ".join(cmd))
        return 0

    r = subprocess.run(cmd)
    if r.returncode != 0:
        common.die("ffmpeg failed - rerun with --dry-run and inspect the filter graph")

    outputs = [mp4]

    if cues and not args.no_srt:
        srt = out_dir / f"{name}.srt"
        with srt.open("w", encoding="utf-8") as f:
            for i, c in enumerate(cues, 1):
                f.write(f'{i}\n{srt_time(c["startMs"])} --> {srt_time(c["endMs"])}\n'
                        f'{c["text"]}\n\n')
        outputs.append(srt)

    if args.keep_webm:
        webm = out_dir / f"{name}.webm"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-stats"] + inputs +
                           ["-filter_complex", fc, "-map", "[vout]",
                            "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", str(webm)])
        if r.returncode == 0:
            outputs.append(webm)

    common.dump_json(root / "manifest.json", {
        "name": name,
        "baseUrl": sb.get("baseUrl"),
        "resolution": f"{w}x{h}",
        "fps": FPS,
        "durationSec": round(total, 2),
        "narration": ({"voice": narration.get("voice"), "rate": narration.get("rate"),
                       "lines": placed} if narration else None),
        "subtitleCues": len(cues),
        "scenes": [{"id": c["scene"]["id"], "durationSec": round(c["dur"], 2)} for c in clips],
        "outputs": [common.rel(p, root) for p in outputs],
    })

    for p in outputs:
        print(f"{p}  {p.stat().st_size / 1e6:.2f} MB")
    return 0
