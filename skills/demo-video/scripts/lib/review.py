"""dv.py review - build the red-team review packet for the finished mp4.

    dv.py review              # output/review.json, output/review/<scene>.png, output/review-transitions.png
    dv.py review --draft

The agent reviews the packet as three personas (references/review.md) and writes
demo/review.md. This command does the mechanical part so the review is about
judgment, not eyeballing timestamps:

  plan vs clip     planned dwellMs vs the recorded clip, per scene
  effects          every storyboard action that leaves a mark (zoom, scroll, drag,
                   dropFile, waitStream, resize, slide, pan, wheelZoom) must have one
  cues             subtitle count and text match (same rule as check-sync), cue gaps
  strips           per scene: first frame, each subtitle start, each effect moment,
                   last frame - tiled into one image
  transitions      the frame 200ms before and after every scene boundary
  static spans     runs of 4s+ where the picture does not change and no subtitle
                   changes - dead air unless the scene means to hold
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import common

MARK_FOR_ACTION = {"zoom": "zoomIn", "zoomOut": "zoomOut", "scroll": "scroll", "drag": "drag", "dropFile": "dropFile",
                   "waitStream": "stream", "resize": "resize", "slide": "slide", "pan": "pan", "wheelZoom": "wheelZoom"}
STATIC_SPAN_S = 4.0
STATIC_DIFF = 1.5          # mean abs luma difference per pixel (0-255) below which two frames are "the same"


def frame_png(mp4: Path, at_s: float, out: Path, width=480):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0, at_s):.3f}", "-i", str(mp4), "-frames:v", "1",
                    "-vf", f"scale={width}:-1", str(out)], capture_output=True)
    return out.exists()


def gray_small(mp4: Path, at_s: float, w=160, h=90):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, at_s):.3f}", "-i", str(mp4), "-frames:v", "1",
                        "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    return r.stdout[: w * h] if len(r.stdout) >= w * h else None


def mean_diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a))


def tile(files, out: Path, cols, width=480, height=270):
    files = [f for f in files if f.exists()]
    if not files:
        return False
    if len(files) == 1:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(files[0]), str(out)], capture_output=True)
        return out.exists()
    inputs = []
    for f in files:
        inputs += ["-i", str(f)]
    layout = "|".join(f"{(i % cols) * width}_{(i // cols) * height}" for i in range(len(files)))
    fc = "".join(f"[{i}:v]scale={width}:{height}[p{i}];" for i in range(len(files))) + \
         "".join(f"[p{i}]" for i in range(len(files))) + f"xstack=inputs={len(files)}:layout={layout}:fill=black[t]"
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", fc, "-map", "[t]", str(out)],
                   capture_output=True)
    return out.exists()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py review", description=__doc__.splitlines()[0])
    ap.add_argument("--storyboard", default=None)
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    root = sb_path.parent
    version = common.schema_version(sb)
    theme = common.load_theme(root)
    manifest_p = root / ("manifest-draft.json" if args.draft else "manifest.json")
    if not manifest_p.exists():
        common.die(f"no {manifest_p.name} - run dv.py compose first")
    manifest = common.load_json(manifest_p)
    mp4 = root / "output" / f"{manifest['name']}.mp4"
    if not mp4.exists():
        common.die(f"{mp4} missing")
    scenes_dir = root / "scenes" / "draft" if args.draft else root / "scenes"
    out_dir = root / "output" / ("review-draft" if args.draft else "review")
    out_dir.mkdir(parents=True, exist_ok=True)
    by_id = {s["id"]: s for s in sb.get("scenes") or []}
    findings, scenes_out = [], []
    strip_files = {}

    for entry in manifest["scenes"]:
        sid, start, dur = entry["id"], entry["startSec"], entry["durationSec"]
        sc = by_id.get(sid, {"id": sid, "steps": []})
        timing_p = scenes_dir / f"{sid}.timing.json"
        timing = common.load_json(timing_p) if timing_p.exists() else {}
        cues, marks = timing.get("cues") or [], timing.get("marks") or []
        rec = {"id": sid, "startSec": start, "durationSec": dur, "plannedSec": None, "cues": len(cues), "marks": [m["type"] for m in marks],
               "frames": []}

        # plan vs clip
        planned = sc.get("dwellMs") or (sb.get(sc.get("kind"), {}) or {}).get("holdMs") if sc.get("kind") else sc.get("dwellMs")
        if sid in ("00-intro", "99-outro"):
            planned = (sb.get("intro" if sid == "00-intro" else "outro") or {}).get("holdMs")
        if planned:
            rec["plannedSec"] = planned / 1000
            if dur > planned / 1000 + 1.5:
                findings.append({"scene": sid, "kind": "timing", "severity": "warn",
                                 "msg": f"clip {dur:.1f}s runs {dur - planned / 1000:.1f}s over the planned {planned / 1000:.1f}s - an action took longer than budgeted"})
            elif dur < planned / 1000 - 0.5:
                findings.append({"scene": sid, "kind": "timing", "severity": "warn",
                                 "msg": f"clip {dur:.1f}s is shorter than the planned {planned / 1000:.1f}s"})

        # effects: every marking action needs its mark
        if version >= 2 and sc.get("steps"):
            expected = [MARK_FOR_ACTION[a["type"]] for st in sc["steps"] for a in (st.get("actions") or []) if a.get("type") in MARK_FOR_ACTION]
            got = [m["type"] for m in marks]
            for e in expected:
                if e in got:
                    got.remove(e)
                else:
                    findings.append({"scene": sid, "kind": "effect", "severity": "fail", "msg": f"storyboard has a {e} action but no {e} mark was recorded - the effect did not run"})
            steps = common.subtitle_steps(sc, version)
            if len(cues) != len(steps):
                findings.append({"scene": sid, "kind": "cues", "severity": "fail", "msg": f"{len(steps)} subtitle(s) planned, {len(cues)} recorded"})
            for st, c in zip(steps, cues):
                if st["text"] != c.get("text"):
                    findings.append({"scene": sid, "kind": "cues", "severity": "fail", "msg": f"subtitle text differs: planned '{st['text'][:20]}…' recorded '{(c.get('text') or '')[:20]}…'"})
            for a, b in zip(cues, cues[1:]):
                gap = b["startMs"] - (a.get("endMs") or a["startMs"])
                if gap > theme["subtitle"]["gapMs"] + 700:
                    findings.append({"scene": sid, "kind": "cues", "severity": "warn", "msg": f"{gap / 1000:.1f}s with no subtitle between cue {cues.index(a) + 1} and {cues.index(a) + 2}"})

        # strip: first, each cue start, each mark, last
        moments = [("first", 0.3)]
        for i, c in enumerate(cues):
            moments.append((f"cue{i + 1}", c["startMs"] / 1000 + 0.45))
        for m in marks:
            if m["type"] == "zoomIn":
                moments.append(("zoomed", (m["atMs"] + m.get("ms", 600) + 150) / 1000))
            elif m["type"] in ("drag", "dropFile", "scroll", "resize", "slide", "pan", "wheelZoom"):
                moments.append((m["type"], m["atMs"] / 1000 + 0.1))
            elif m["type"] == "stream":
                moments.append(("streamed", m["endMs"] / 1000 + 0.1))
        moments.append(("last", max(0.3, dur - 0.35)))
        moments = sorted({(lbl, round(min(max(t, 0.05), dur - 0.05), 2)) for lbl, t in moments}, key=lambda x: x[1])
        files = []
        for i, (lbl, t) in enumerate(moments):
            f = out_dir / f"{sid}-{i:02d}-{lbl}.png"
            if frame_png(mp4, start + t, f):
                files.append(f)
                rec["frames"].append({"label": lbl, "atSec": round(start + t, 2), "localSec": t, "file": common.rel(f, root)})
        strip = out_dir / f"{sid}.png"
        if tile(files, strip, cols=min(6, max(1, len(files)))):
            rec["strip"] = common.rel(strip, root)
            strip_files[sid] = strip

        # static spans: sample every second
        samples, prev, t = [], None, 0.5
        while t < dur - 0.3:
            g = gray_small(mp4, start + t)
            samples.append((t, mean_diff(prev, g) if (prev and g) else None))
            prev = g
            t += 1.0
        run_start, run_len = None, 0
        cue_edges = sorted({c["startMs"] / 1000 for c in cues} | {(c.get("endMs") or 0) / 1000 for c in cues})
        for t, d in samples:
            static = d is not None and d < STATIC_DIFF and not any(abs(t - e) < 1.0 for e in cue_edges)
            if static:
                run_start = t - 1.0 if run_start is None else run_start
                run_len = t - run_start
            else:
                if run_len >= STATIC_SPAN_S:
                    findings.append({"scene": sid, "kind": "static", "severity": "info", "msg": f"picture unchanged for {run_len:.0f}s from {run_start:.0f}s - dead air unless the hold is intended"})
                run_start, run_len = None, 0
        if run_len >= STATIC_SPAN_S:
            findings.append({"scene": sid, "kind": "static", "severity": "info", "msg": f"picture unchanged for {run_len:.0f}s from {run_start:.0f}s - dead air unless the hold is intended"})
        scenes_out.append(rec)

    # transitions: 200ms before / after each boundary
    tfiles, boundaries = [], []
    for a, b in zip(manifest["scenes"], manifest["scenes"][1:]):
        edge = b["startSec"]
        f1, f2 = out_dir / f"t-{a['id']}-out.png", out_dir / f"t-{b['id']}-in.png"
        frame_png(mp4, edge - 0.2, f1, width=320)
        frame_png(mp4, edge + 0.25, f2, width=320)
        tfiles += [f1, f2]
        boundaries.append({"from": a["id"], "to": b["id"], "atSec": round(edge, 2),
                           "transition": (by_id.get(b["id"], {}).get("transitionIn") or {}).get("type", "fade")})
    tstrip = root / "output" / ("review-transitions-draft.png" if args.draft else "review-transitions.png")
    tile(tfiles, tstrip, cols=8, width=320, height=180)

    report = {"mp4": str(mp4), "durationSec": manifest["durationSec"], "scenes": scenes_out, "boundaries": boundaries,
              "transitionsStrip": common.rel(tstrip, root), "findings": findings,
              "personas": ["PD", "user", "critic"], "next": "write demo/review.md per references/review.md, then fix or approve final"}
    common.dump_json(root / "output" / ("review-draft.json" if args.draft else "review.json"), report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{mp4.name}  {manifest['durationSec']}s  {len(scenes_out)} scenes")
        print(f"  strips: {common.rel(out_dir, root)}/<scene>.png   transitions: {common.rel(tstrip, root)}")
        fails = [f for f in findings if f["severity"] == "fail"]
        for f in findings:
            print(f"  {f['severity']:<4} {f['scene']:<22} {f['kind']:<7} {f['msg']}")
        print(f"review packet: {len(fails)} fail, {len(findings) - len(fails)} warn/info - now review as PD, user and critic (references/review.md)")
    return 1 if any(f["severity"] == "fail" for f in findings) else 0
