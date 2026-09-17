"""dv.py compose - join scene clips with xfade transitions, mux audio, encode the mp4 once.

    dv.py compose                     # demo/output/<name>.mp4 + .srt + manifest.json
    dv.py compose --draft             # from demo/scenes/draft, cuts only, no audio -> <name>-draft.mp4
    dv.py compose --dry-run           # print the ffmpeg command

Pipeline (DESIGN.md FR-040 ~ FR-043, FR-056, FR-078):
  intro (HTML clip or user video normalized to the frame, letterboxed if the
  aspect differs) -> fade -> scenes with transitionIn -> fade -> outro.
  Narration lines are placed at their recorded cue times. BGM from config.json
  (user file) is looped to the video length, faded in 1.5s / out 2s, ducked
  -18 dB under narration cues (300ms attack, 800ms release), and the whole mix
  is normalized to -16 LUFS integrated / -1 dBTP. H.264 is encoded exactly once.
Text is never burned in.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from . import common

FPS = 25


def probe(path: Path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True)
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


def load_timing(scenes_dir: Path, sid):
    p = scenes_dir / f"{sid}.timing.json"
    return common.load_json(p) if p.exists() else {}


def find_narration(demo_dir: Path, name):
    for cand in (demo_dir / f"narration-{name}.json", demo_dir / "narration.json"):
        if cand.exists():
            return common.load_json(cand)
    return None


def normalize_video(src: Path, build_dir: Path, w, h, label):
    """FR-041: user intro/outro video -> frame size, 25fps, yuv420p, letterboxed if needed. Cached by content."""
    if not src.exists():
        common.die(f"{label} video not found: {src}")
    stat = src.stat()
    key = hashlib.sha256(f"{src.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{w}x{h}".encode()).hexdigest()[:16]
    out = build_dir / f"{label}.{key}.mp4"
    info = probe(src)
    letterboxed = abs((info["w"] / info["h"]) - (w / h)) > 0.01
    if not out.exists():
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
              f"fps={FPS},format=yuv420p,setsar=1")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", vf, "-an",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)], capture_output=True, text=True)
        if r.returncode != 0:
            common.die(f"could not normalize {label} video:\n{r.stderr.strip()[-400:]}")
    return out, letterboxed, info


def duck_expression(ranges, duck_db, attack_ms, release_ms):
    """volume expression: 1 outside narration, 10^(duck/20) inside, linear ramps around each range."""
    if not ranges:
        return "1"
    gain = 10 ** (duck_db / 20)
    a, r = attack_ms / 1000, release_ms / 1000
    terms = []
    for s, e in ranges:
        # depth(t): ramps 0->1 over [s-a, s], 1 inside, 1->0 over [e, e+r]
        terms.append(f"min(clip((t-({s - a:.3f}))/{a:.3f},0,1),clip((({e + r:.3f})-t)/{r:.3f},0,1))")
    depth = terms[0]
    for t in terms[1:]:
        depth = f"max({depth},{t})"
    return f"1-(1-{gain:.4f})*({depth})"


def merge_ranges(ranges, gap=0.4):
    out = []
    for s, e in sorted(ranges):
        if out and s - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py compose", description=__doc__.splitlines()[0])
    ap.add_argument("--storyboard", default=None)
    ap.add_argument("--scenes-dir", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--videotoolbox", action="store_true")
    ap.add_argument("--keep-webm", action="store_true")
    ap.add_argument("--no-audio", action="store_true", help="skip narration and BGM")
    ap.add_argument("--no-srt", action="store_true")
    ap.add_argument("--draft", action="store_true", help="draft clips, cuts only, no audio")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    root = sb_path.parent
    name = common.name_of(sb) + ("-draft" if args.draft else "")
    version = common.schema_version(sb)
    theme = common.load_theme()
    cfg_path = root / "config.json"
    cfg = common.load_json(cfg_path) if cfg_path.exists() else {}
    scenes_dir = Path(args.scenes_dir).resolve() if args.scenes_dir else (root / "scenes" / "draft" if args.draft else root / "scenes")
    out_dir = Path(args.out_dir).resolve() if args.out_dir else root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    build_dir = scenes_dir / ".build"
    build_dir.mkdir(parents=True, exist_ok=True)
    no_audio = args.no_audio or args.draft
    tdef = theme["transition"]

    scenes = list(sb.get("scenes") or [])
    if not scenes:
        common.die("storyboard has no scenes")
    notes = []
    videos = {}
    if version >= 2:
        intro, outro = sb.get("intro") or {}, sb.get("outro") or {}
        if intro.get("source") == "html":
            scenes.insert(0, {"id": "00-intro", "kind": "intro"})
        elif intro.get("source") == "video":
            scenes.insert(0, {"id": "00-intro", "kind": "intro", "video": intro["path"]})
        if outro.get("source") in ("html", "video"):
            sc = {"id": "99-outro", "kind": "outro", "transitionIn": {"type": tdef["default"], "ms": tdef["defaultMs"]}}
            if outro["source"] == "video":
                sc["video"] = outro["path"]
            scenes.append(sc)

    w_target, h_target = common.frame_size(sb)
    clips, missing = [], []
    for sc in scenes:
        sid = sc["id"]
        if sc.get("video"):
            src = Path(sc["video"])
            src = src if src.is_absolute() else root / src
            # draft clips are smaller: match whatever the scene clips are
            ref = next((c for c in clips if not c.get("user")), None)
            w, h = (ref["w"], ref["h"]) if ref else (w_target, h_target)
            norm, boxed, info = normalize_video(src, build_dir, w, h, sid)
            c = probe(norm)
            c.update({"scene": sc, "user": True})
            if boxed:
                notes.append(f"{sid}: user video is {info['w']}x{info['h']} - letterboxed to {w}x{h}")
            clips.append(c)
            continue
        p = scenes_dir / f"{sid}.webm"
        if not p.exists():
            missing.append(str(p))
            continue
        c = probe(p)
        c["scene"] = sc
        clips.append(c)
    if missing:
        common.die("scene clips not rendered yet:\n  " + "\n  ".join(missing))
    # A user video placed first is normalized before any scene clip is known; redo it at the scene size.
    if clips and clips[0].get("user") and len(clips) > 1 and (clips[0]["w"], clips[0]["h"]) != (clips[1]["w"], clips[1]["h"]):
        sc = clips[0]["scene"]
        src = Path(sc["video"]); src = src if src.is_absolute() else root / src
        norm, boxed, info = normalize_video(src, build_dir, clips[1]["w"], clips[1]["h"], sc["id"])
        c = probe(norm); c.update({"scene": sc, "user": True}); clips[0] = c

    sizes = {(c["w"], c["h"]) for c in clips}
    if len(sizes) > 1:
        detail = "\n  ".join(f'{c["scene"]["id"]}: {c["w"]}x{c["h"]}' for c in clips)
        common.die("scene clips have different resolutions - re-record, do not rescale:\n  " + detail)
    w, h = clips[0]["w"], clips[0]["h"]

    cut_only = args.draft or str(sb.get("transitions", "")).lower() == "none"

    # Transition into clip i+1. v2: the entered scene's transitionIn; v1: the left scene's transitionOut.
    trans = []
    for i, c in enumerate(clips[:-1]):
        if cut_only:
            trans.append(("cut", 0.0))
            continue
        if version >= 2:
            t = clips[i + 1]["scene"].get("transitionIn") or {}
            typ, ms = t.get("type", tdef["default"]), int(t.get("ms", tdef["defaultMs"]))
        else:
            t = c["scene"].get("transitionOut") or {}
            typ, ms = t.get("type", "fade"), int(t.get("durationMs", 500))
        if typ == "cut":
            trans.append(("cut", 0.0))
            continue
        if ms / 1000.0 >= min(c["dur"], clips[i + 1]["dur"]):
            common.die(f'{c["scene"]["id"]}: transition {ms}ms is longer than the clip ({c["dur"]:.2f}s)')
        trans.append((typ, ms / 1000.0))

    for c in clips:
        need = sum(int(s["holdMs"] or 0) for s in common.subtitle_steps(c["scene"], version)) / 1000.0
        if need and c["dur"] + 0.4 < need:
            print(f'warning: {c["scene"]["id"]} is {c["dur"]:.2f}s but its subtitles need {need:.2f}s', file=sys.stderr)

    # ---- video graph
    parts, inputs = [], []
    for i, c in enumerate(clips):
        inputs += ["-i", str(c["path"])]
        # A static card emits no frames while nothing changes, so its clip ends early:
        # clone the last frame up to the planned hold (intro/outro only).
        pad = ""
        if version >= 2 and c["scene"].get("kind") in ("intro", "outro") and not c.get("user"):
            card = sb.get(c["scene"]["kind"]) or {}
            hold = card.get("holdMs", 2500 if c["scene"]["kind"] == "intro" else 3000) / 1000
            if c["dur"] < hold - 0.08:
                pad = f",tpad=stop_mode=clone:stop_duration={hold - c['dur']:.3f}"
                c["dur"] = hold
        parts.append(f"[{i}:v]fps={FPS},format=yuv420p,setsar=1,scale={w}:{h}{pad}[s{i}]")
    if len(clips) == 1:
        parts.append("[s0]copy[vout]")
    elif cut_only:
        parts.append("".join(f"[s{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[vout]")
    else:
        acc, prev = clips[0]["dur"], "s0"
        for i in range(1, len(clips)):
            typ, tdur = trans[i - 1]
            if typ == "cut":
                typ, tdur = "fade", 1.0 / FPS      # one graph for everything: a cut is a one-frame fade
                trans[i - 1] = (typ, tdur)
            offset = acc - tdur
            label = "vout" if i == len(clips) - 1 else f"v{i}"
            parts.append(f"[{prev}][s{i}]xfade=transition={typ}:duration={tdur:.3f}:offset={offset:.3f}[{label}]")
            acc, prev = acc + clips[i]["dur"] - tdur, label
    total = sum(c["dur"] for c in clips) - sum(t[1] for t in trans)

    starts, acc = [0.0], 0.0
    for i in range(1, len(clips)):
        acc += clips[i - 1]["dur"] - trans[i - 1][1]
        starts.append(acc)

    cues, stream_marks = [], []
    for c, start in zip(clips, starts):
        timing = load_timing(scenes_dir, c["scene"]["id"])
        for i, cue in enumerate(timing.get("cues") or []):
            cues.append({"sceneId": c["scene"]["id"], "index": i,
                         "startMs": int(start * 1000) + cue["startMs"],
                         "endMs": int(start * 1000) + (cue.get("endMs") or cue["startMs"] + 2000),
                         "text": cue.get("text", "")})
        for m in timing.get("marks") or []:
            if m.get("type") == "stream" and m.get("speedup"):
                stream_marks.append({"sceneId": c["scene"]["id"], "startMs": int(start * 1000) + m["startMs"],
                                     "endMs": int(start * 1000) + m["endMs"]})
    cues.sort(key=lambda c: c["startMs"])
    for m in stream_marks:
        notes.append(f"{m['sceneId']}: streaming span {(m['endMs'] - m['startMs']) / 1000:.1f}s exceeds "
                     f"{theme['stream']['speedupAfterMs'] / 1000:.0f}s - speed-up is not applied yet, consider a shorter waitStream")

    # ---- audio graph
    narration = None if no_audio else find_narration(root, common.name_of(sb))
    bgm_cfg = (cfg.get("bgm") or {}) if not no_audio else {}
    bgm_path = None
    if bgm_cfg.get("source") == "file" and bgm_cfg.get("path"):
        bgm_path = Path(bgm_cfg["path"])
        bgm_path = bgm_path if bgm_path.is_absolute() else root.parent / bgm_path
        if not bgm_path.exists():
            common.die(f"BGM file not found: {bgm_path} (dv.py bgm probe <file> registers it)")
    elif bgm_cfg.get("source") == "catalog":
        notes.append("bgm.source catalog is not available yet (M3 BGM 1차) - composing without BGM")

    audio_inputs, achain, amap, aenc, unplaced, placed = [], [], [], [], [], 0
    n_in = len(clips)
    narr_ranges = []
    if narration:
        by_cue = {(c["sceneId"], c["index"]): c for c in cues}
        for line in narration.get("lines") or []:
            cue = by_cue.get((line["sceneId"], line["index"]))
            src = root / line["file"]
            if cue is None or not src.exists():
                unplaced.append(f'{line["sceneId"]}[{line["index"]}]')
                continue
            audio_inputs += ["-i", str(src)]
            achain.append(f'[{n_in}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={cue["startMs"]}|{cue["startMs"]}[na{placed}]')
            narr_ranges.append((cue["startMs"] / 1000, (cue["startMs"] + line["durationMs"]) / 1000))
            n_in += 1
            placed += 1
    a = theme["audio"]
    mix_inputs = []
    if placed:
        audio_inputs += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        bed = n_in
        n_in += 1
        achain.append(f"[{bed}:a]" + "".join(f"[na{i}]" for i in range(placed))
                      + f"amix=inputs={placed + 1}:normalize=0:dropout_transition=0[narr]")
        mix_inputs.append("[narr]")
    if bgm_path:
        audio_inputs += ["-stream_loop", "-1", "-i", str(bgm_path)]
        expr = duck_expression(merge_ranges(narr_ranges), a["duckDb"], a["duckAttackMs"], a["duckReleaseMs"]) if placed else "1"
        achain.append(f"[{n_in}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                      f"afade=t=in:d={a['fadeInMs'] / 1000:.2f},afade=t=out:st={max(0.0, total - a['fadeOutMs'] / 1000):.3f}:d={a['fadeOutMs'] / 1000:.2f},"
                      f"volume='{expr}':eval=frame[bgm]")
        n_in += 1
        mix_inputs.append("[bgm]")
    loud_params = f"I={a['integratedLufs']}:TP={a['truePeakDbtp']}:LRA=11"
    if mix_inputs:
        src = mix_inputs[0] if len(mix_inputs) == 1 else "".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:normalize=0:dropout_transition=0[premix];[premix]"
        # Two-pass loudnorm: measure the mix first, then apply a linear gain to the target.
        # Single-pass (dynamic) mode lands 1-3 LU under the target on short programs.
        measured = None
        if not args.dry_run:
            mcmd = (["ffmpeg", "-hide_banner", "-nostats", "-y"] + inputs + audio_inputs +
                    ["-filter_complex", ";".join(achain + [f"{src}loudnorm={loud_params}:print_format=json[m]"]),
                     "-map", "[m]", "-f", "null", "-"])
            mr = subprocess.run(mcmd, capture_output=True, text=True)
            jm = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", mr.stderr or "")
            if jm:
                measured = json.loads(jm.group(0))
        if measured:
            loud = (f"loudnorm={loud_params}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
                    f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
                    f"offset={measured['target_offset']}:linear=true")
        else:
            loud = f"loudnorm={loud_params}"
        achain.append(f"{src}{loud},aresample=48000[aout]")
        amap = ["-map", "[aout]"]
        aenc = ["-c:a", "aac", "-b:a", "192k"]

    fc = ";".join(parts + achain)
    mp4 = out_dir / f"{name}.mp4"
    venc = (["-c:v", "h264_videotoolbox", "-b:v", "6M"] if args.videotoolbox
            else ["-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf)])
    cmd = (["ffmpeg", "-y", "-v", "error", "-stats"] + inputs + audio_inputs +
           ["-filter_complex", fc, "-map", "[vout]"] + amap + venc + aenc +
           ["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", f"{total:.3f}", str(mp4)])

    print(f"{len(clips)} clips  {w}x{h}  {sum(c['dur'] for c in clips):.2f}s raw - {sum(t[1] for t in trans):.2f}s transitions = {total:.2f}s final")
    for c, t in zip(clips, list(trans) + [None]):
        tail = "" if (t is None or t[0] == "cut") else f"  -{t[0]} {t[1]:.2f}s"
        print(f'  {c["scene"]["id"]:<20} {c["dur"]:>6.2f}s{tail}')
    if narration:
        print(f"  narration: {placed} lines, voice {narration.get('voice')}")
        for u in unplaced:
            print(f"  warning: no subtitle cue for narration line {u} - not placed", file=sys.stderr)
    if bgm_path:
        print(f"  bgm: {bgm_path.name}, loop to {total:.1f}s, duck {a['duckDb']} dB under {len(narr_ranges)} lines, target {a['integratedLufs']} LUFS")
    for n in notes:
        print(f"  note: {n}")

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
                f.write(f'{i}\n{srt_time(c["startMs"])} --> {srt_time(c["endMs"])}\n{c["text"]}\n\n')
        outputs.append(srt)
    if args.keep_webm:
        webm = out_dir / f"{name}.webm"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-stats"] + inputs + ["-filter_complex", ";".join(parts),
                            "-map", "[vout]", "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", str(webm)])
        if r.returncode == 0:
            outputs.append(webm)

    common.dump_json(root / ("manifest-draft.json" if args.draft else "manifest.json"), {
        "name": name, "baseUrl": common.base_url(sb, root), "resolution": f"{w}x{h}", "fps": FPS,
        "durationSec": round(total, 2), "draft": args.draft,
        "narration": ({"voice": narration.get("voice"), "lines": placed} if narration else None),
        "bgm": (str(bgm_path) if bgm_path else None),
        "subtitleCues": len(cues), "notes": notes,
        "scenes": [{"id": c["scene"]["id"], "durationSec": round(c["dur"], 2), "startSec": round(s, 2)}
                   for c, s in zip(clips, starts)],
        "outputs": [common.rel(p, root) for p in outputs],
    })
    for p in outputs:
        print(f"{p}  {p.stat().st_size / 1e6:.2f} MB")
    return 0
