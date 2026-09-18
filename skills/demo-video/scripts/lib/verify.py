"""dv.py verify - look at the finished mp4 instead of trusting exit code 0.

    dv.py verify                # demo/output/<name>.mp4 -> verify-tile.png, verify.json, exit 1 on a failure
    dv.py verify --draft

Checks:
  frames     one frame per scene tiled into output/verify-tile.png; a black frame (mean luma < 6)
             at a scene's start, middle or end fails
  subtitles  in every scene that zoomed, the subtitle box on a zoomed frame must sit inside the
             title-safe area (88%) and in the bottom band (FR-010, SC-004)
  loudness   integrated loudness within ±1 LU of the theme target and true peak under the ceiling
             (only when the mp4 has audio)
  narration  one cue must not be silent, and (without BGM) one gap must be silent
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from . import common

BLACK_LUMA = 6.0


def gray_frame(mp4: Path, at_s: float, w: int, h: int):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{at_s:.3f}", "-i", str(mp4), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    return r.stdout[: w * h] if len(r.stdout) >= w * h else None


def mean_luma(frame: bytes) -> float:
    return sum(frame[::97]) / max(1, len(frame[::97]))


def subtitle_bbox(frame: bytes, w: int, h: int, theme):
    """Bounding box of the subtitle's dark backdrop. The expected band comes from the theme
    (bottom 7%, font height), so page content elsewhere cannot be mistaken for the box."""
    st = theme["subtitle"]
    font = round(h * st["fontSizeRatio"])
    box_h = round(font * 1.25 + 2 * round(font * 0.35))
    y1e = h - round(h * st["bottomRatio"])
    y0e = y1e - box_h
    pad = round(font * 0.35)
    # Width from the padding rows just inside the top and bottom edges: no glyphs there,
    # so every column of the box is uniformly dark.
    band = list(range(y0e + 2, y0e + max(3, pad - 1))) + list(range(y1e - max(3, pad - 1), y1e - 2))
    n = len(band)
    flags = [sum(1 for y in band if frame[y * w + x] < 120) >= n * 0.7 for x in range(w)]
    best, run_start, gap = None, None, 0
    for x, dark in enumerate(flags + [False]):
        if dark:
            gap = 0
            if run_start is None:
                run_start = x
        elif run_start is not None:
            gap += 1
            if gap > 6:
                end = x - gap
                if best is None or end - run_start > best[1] - best[0]:
                    best = (run_start, end)
                run_start, gap = None, 0
    if best is None or best[1] - best[0] < w * 0.1:
        return None
    x0, x1 = best
    rows = [y for y in range(max(0, y0e - 12), min(h, y1e + 12))
            if sum(1 for x in range(x0, x1 + 1, 2) if frame[y * w + x] < 120) >= ((x1 - x0) / 2) * 0.5]
    if not rows:
        return None
    return (x0, rows[0], x1, rows[-1])


def css_luma(color: str, page_luma=240.0):
    """Approximate luminance of a CSS color, alpha-blended over a light page. None for transparent/unknown."""
    c = (color or "").strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{6})", c)
    if m:
        r, g, b = (int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
        return 0.299 * r + 0.587 * g + 0.114 * b
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)", c)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = float(m.group(4)) if m.group(4) else 1.0
        return a * (0.299 * r + 0.587 * g + 0.114 * b) + (1 - a) * page_luma
    return None


def box_profile(frame: bytes, w: int, box, bg_luma, ink_luma):
    """Fractions of pixels inside the predicted subtitle box that look like its background and its text."""
    x0, y0, x1, y1 = max(0, box["x0"]), max(0, box["y0"]), min(w, box["x1"]), box["y1"]
    n = bg = ink = 0
    for y in range(y0 + 2, y1 - 2, 2):
        row = frame[y * w:(y + 1) * w]
        for x in range(x0 + 2, x1 - 2, 2):
            v = row[x]
            n += 1
            if bg_luma is not None and abs(v - bg_luma) < 45:
                bg += 1
            if abs(v - ink_luma) < 60:
                ink += 1
    return (bg / n if n else 0.0, ink / n if n else 0.0)


def loudness(mp4: Path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp4), "-map", "0:a:0",
                        "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    txt = r.stderr
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", txt)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", txt)
    return (float(i[-1]) if i else None, float(tp[-1]) if tp else None)


def max_volume(mp4: Path, start_s: float, dur_s: float):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start_s:.3f}", "-t", f"{dur_s:.3f}",
                        "-i", str(mp4), "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"max_volume:\s+(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None


def has_audio(mp4: Path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0", str(mp4)], capture_output=True, text=True)
    return "audio" in r.stdout


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py verify", description=__doc__.splitlines()[0])
    ap.add_argument("--storyboard", default=None)
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    root = sb_path.parent
    theme = common.load_theme(root)
    manifest_p = root / ("manifest-draft.json" if args.draft else "manifest.json")
    if not manifest_p.exists():
        common.die(f"no {manifest_p.name} - run dv.py compose first")
    manifest = common.load_json(manifest_p)
    mp4 = root / "output" / f"{manifest['name']}.mp4"
    if not mp4.exists():
        common.die(f"{mp4} missing")
    w, h = (int(x) for x in manifest["resolution"].split("x"))
    scenes_dir = root / "scenes" / "draft" if args.draft else root / "scenes"
    failures, checks = [], []

    # frames: start / middle / end of each scene, and a tile of the starts
    frame_files = []
    for sc in manifest["scenes"]:
        start, dur = sc["startSec"], sc["durationSec"]
        for label, t in (("start", start + 0.3), ("mid", start + dur / 2), ("end", start + max(0.3, dur - 0.4))):
            f = gray_frame(mp4, t, w, h)
            if f is None:
                failures.append(f"{sc['id']}: no frame at {t:.2f}s")
                continue
            luma = mean_luma(f)
            checks.append({"check": "frame", "scene": sc["id"], "at": round(t, 2), "luma": round(luma, 1)})
            if luma < BLACK_LUMA:
                failures.append(f"{sc['id']}: black frame at {t:.2f}s ({label}, luma {luma:.1f})")
        png = root / "output" / ".verify" / f"{sc['id']}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start + 0.3:.3f}", "-i", str(mp4), "-frames:v", "1",
                        "-vf", "scale=400:-1", str(png)], capture_output=True)
        frame_files.append(png)
    tile = root / "output" / ("verify-tile-draft.png" if args.draft else "verify-tile.png")
    cols = min(5, max(1, len(frame_files)))
    rows = -(-len(frame_files) // cols)
    inputs = []
    for p in frame_files:
        inputs += ["-i", str(p)]
    if frame_files:
        # xstack layout needs explicit offsets; build them from the 400px scaled width and per-row height
        layout = []
        fw, fh = 400, int(round(400 * h / w))
        for i in range(len(frame_files)):
            layout.append(f"{(i % cols) * fw}_{(i // cols) * fh}")
        fc = ("".join(f"[{i}:v]" for i in range(len(frame_files)))
              + f"xstack=inputs={len(frame_files)}:layout={'|'.join(layout)}:fill=black[t]") if len(frame_files) > 1 else "[0:v]copy[t]"
        subprocess.run(["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", fc, "-map", "[t]", str(tile)],
                       capture_output=True)

    # subtitles under zoom: the box the prelude predicted must hold the subtitle's colors on a zoomed
    # frame just as it does on an unzoomed frame of the same cue (SC-004, theme-independent)
    st = theme["subtitle"]
    bg_luma, ink_luma = css_luma(st.get("background", "")), css_luma(st.get("color", "#fff"))
    ink_luma = 255.0 if ink_luma is None else ink_luma
    margin_x, margin_y = w * (1 - theme["safeArea"]["title"]) / 2, h * (1 - theme["safeArea"]["title"]) / 2
    for sc in manifest["scenes"]:
        timing = scenes_dir / f"{sc['id']}.timing.json"
        if not timing.exists():
            continue
        t = common.load_json(timing)
        marks, cues = t.get("marks") or [], t.get("cues") or []
        zin = [m for m in marks if m["type"] == "zoomIn"]
        zout = [m for m in marks if m["type"] == "zoomOut"]
        if not zin:
            continue
        span0 = zin[0]["atMs"] + theme["zoom"]["inMs"] + 100
        span1 = (zout[0]["atMs"] - 100) if zout else span0 + 1000
        best, cue = None, None
        for c in cues:
            lo, hi = max(span0, c["startMs"] + 150), min(span1, (c.get("endMs") or c["startMs"]) - 150)
            if hi > lo and (best is None or hi - lo > best[1] - best[0]):
                best, cue = (lo, hi), c
        if span1 - span0 < 400:
            failures.append(f"{sc['id']}: zoomed span is only {(zout[0]['atMs'] - zin[0]['atMs']) / 1000:.1f}s - "
                            f"put a highlight or hold between zoom and zoomOut, or drop the zoom")
            continue
        if not cue or not cue.get("box"):
            failures.append(f"{sc['id']}: no subtitle cue overlaps the zoomed span (or the cue has no box - re-render)")
            continue
        box = cue["box"]
        zoomed_at = sc["startSec"] + ((best[0] + best[1]) / 2) / 1000
        # unzoomed reference: the same cue before the zoom started, else right after zoomOut
        ref_local = (cue["startMs"] + 150) if cue["startMs"] + 200 < zin[0]["atMs"] else \
            ((zout[0]["atMs"] + zout[0].get("ms", 500) + 150) if zout and (cue.get("endMs") or 0) > zout[0]["atMs"] + 800 else None)
        fz = gray_frame(mp4, zoomed_at, w, h)
        if fz is None:
            failures.append(f"{sc['id']}: no frame at {zoomed_at:.2f}s")
            continue
        bg_z, ink_z = box_profile(fz, w, box, bg_luma, ink_luma)
        checks.append({"check": "subtitle", "scene": sc["id"], "at": round(zoomed_at, 2), "box": [box["x0"], box["y0"], box["x1"], box["y1"]],
                       "bg": round(bg_z, 2), "ink": round(ink_z, 2)})
        if box["x0"] < margin_x or box["x1"] > w - margin_x or box["y1"] > h - margin_y:
            failures.append(f"{sc['id']}: subtitle box {box} leaves the title-safe area")
        if ink_z < 0.02 or (bg_luma is not None and bg_z < 0.3):
            failures.append(f"{sc['id']}: subtitle not found in its box on the zoomed frame at {zoomed_at:.2f}s "
                            f"(bg {bg_z:.2f}, ink {ink_z:.2f}) - it moved or scaled with the page")
        if ref_local is not None:
            fr = gray_frame(mp4, sc["startSec"] + ref_local / 1000, w, h)
            if fr is not None:
                bg_r, ink_r = box_profile(fr, w, box, bg_luma, ink_luma)
                if abs(bg_r - bg_z) > 0.25 or abs(ink_r - ink_z) > 0.15:
                    failures.append(f"{sc['id']}: subtitle box composition differs between unzoomed (bg {bg_r:.2f}/ink {ink_r:.2f}) "
                                    f"and zoomed (bg {bg_z:.2f}/ink {ink_z:.2f}) frames")

    # audio
    audio = has_audio(mp4)
    if audio:
        i_lufs, tp = loudness(mp4)
        checks.append({"check": "loudness", "integratedLufs": i_lufs, "truePeak": tp})
        tgt = theme["audio"]
        if i_lufs is None:
            failures.append("could not measure loudness")
        else:
            if abs(i_lufs - tgt["integratedLufs"]) > 1.0:
                failures.append(f"integrated loudness {i_lufs} LUFS is outside {tgt['integratedLufs']} ±1")
            if tp is not None and tp > tgt["truePeakDbtp"] + 0.5:
                failures.append(f"true peak {tp} dBTP exceeds {tgt['truePeakDbtp']}")
        if manifest.get("narration"):
            srt = root / "output" / f"{manifest['name']}.srt"
            cue_starts = [int(a) * 3600 + int(b) * 60 + int(c) + int(d) / 1000
                          for a, b, c, d in re.findall(r"(\d+):(\d+):(\d+),(\d+) -->", srt.read_text(encoding="utf-8"))] if srt.exists() else []
            if cue_starts:
                v = max_volume(mp4, cue_starts[0] + 0.1, 1.5)
                checks.append({"check": "narrationCue", "at": cue_starts[0], "maxVolumeDb": v})
                if v is None or v < -30:
                    failures.append(f"narration cue at {cue_starts[0]:.1f}s is silent ({v} dB)")
                if not manifest.get("bgm") and cue_starts[0] > 1.0:
                    g = max_volume(mp4, 0.1, min(0.8, cue_starts[0] - 0.2))
                    checks.append({"check": "gap", "maxVolumeDb": g})
                    if g is not None and g > -50:
                        failures.append(f"audio before the first cue is not silent ({g} dB) although there is no BGM")
    else:
        checks.append({"check": "loudness", "skipped": "no audio track"})

    report = {"mp4": str(mp4), "durationSec": manifest["durationSec"], "ok": not failures, "failures": failures,
              "checks": checks, "tile": common.rel(tile, root)}
    common.dump_json(root / "output" / ("verify-draft.json" if args.draft else "verify.json"), report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{mp4.name}  {manifest['durationSec']}s  {manifest['resolution']}  audio: {'yes' if audio else 'no'}")
        for c in checks:
            if c["check"] == "loudness" and "integratedLufs" in c:
                print(f"  loudness {c['integratedLufs']} LUFS, true peak {c['truePeak']} dBTP")
            elif c["check"] in ("narrationCue", "gap"):
                print(f"  {c['check']}: max_volume {c.get('maxVolumeDb')} dB")
        print(f"  frames: {len([c for c in checks if c['check'] == 'frame'])} sampled, tile {common.rel(tile, root)}")
        print(f"  subtitle-under-zoom: {len([c for c in checks if c['check'] == 'subtitle'])} scene(s) checked")
        for f in failures:
            print(f"  FAIL {f}", file=sys.stderr)
        print("verify: " + ("ok - now look at the tile before reporting done" if not failures else f"{len(failures)} failure(s)"))
    return 1 if failures else 0
