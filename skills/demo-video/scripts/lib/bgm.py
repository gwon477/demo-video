"""dv.py bgm probe <file> - measure a user's BGM file and register it in config.json.

    dv.py bgm probe ~/music/calm.mp3      # duration, integrated loudness -> config.bgm
    dv.py bgm fetch | pick                # catalog features, not available yet (M3 BGM 1차)

FR-070: user file first, then the catalog, then none. FR-078's loop, fades,
ducking and normalization happen in compose; probe only records what the file is.
"""
import argparse
import datetime as _dt
import hashlib
import re
import subprocess
from pathlib import Path

from . import common


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def measure(path: Path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
                        "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    return (float(i[-1]) if i else None, float(tp[-1]) if tp else None)


def probe(argv):
    ap = argparse.ArgumentParser(prog="dv.py bgm probe")
    ap.add_argument("file")
    ap.add_argument("--demo", default="demo")
    args = ap.parse_args(argv)
    path = Path(args.file).expanduser().resolve()
    if not path.exists():
        common.die(f"no such file: {path}")
    dur = common.ffprobe_duration(path)
    if dur <= 0:
        common.die(f"{path.name}: ffprobe found no duration - is it an audio file?")
    lufs, tp = measure(path)
    demo_dir = Path(args.demo).resolve()
    cfg_path = demo_dir / "config.json"
    cfg = common.load_json(cfg_path) if cfg_path.exists() else {}
    cfg["bgm"] = {"source": "file", "path": str(path), "durationSec": round(dur, 2), "loudnessLufs": lufs,
                  "truePeakDbtp": tp, "sha256": sha256(path),
                  "probedAt": _dt.datetime.now().astimezone().isoformat(timespec="seconds")}
    common.dump_json(cfg_path, cfg)
    print(f"{path.name}: {dur:.1f}s, {lufs} LUFS, peak {tp} dBTP - registered in {common.rel(cfg_path, demo_dir.parent)}")
    if dur < 20:
        print("note: short file - compose loops it to the video length; check the loop seam by ear")
    return 0


def main(argv=None):
    argv = list(argv or [])
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    sub, rest = argv[0], argv[1:]
    if sub == "probe":
        return probe(rest)
    if sub in ("fetch", "pick"):
        common.die(f"bgm {sub} needs the verified catalog (M3 BGM 1차, not done yet). "
                   f"Use `dv.py bgm probe <file>` with your own track, or bgm: none")
    common.die(f"unknown bgm subcommand '{sub}' (probe | fetch | pick)")
