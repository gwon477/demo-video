"""dv.py bgm - background music: the user's own file, or a track from the bundled catalog.

    dv.py bgm probe <file>                       # register the user's file in config.bgm (FR-070 first choice)
    dv.py bgm pick --mood focused,calm [--energy 2] [--narration] [--top 3]
                                                 # score the catalog (FR-075/076), print the top tracks with reasons
    dv.py bgm use <track-id>                     # fetch + verify sha256 (FR-072), register in config.bgm
    dv.py bgm fetch [<track-id> ...]             # download to the cache without registering
    dv.py bgm list [--mood m]                    # what the catalog holds

The catalog (assets/bgm/catalog.json) is built by assets/bgm/build-catalog.py
from Incompetech's index (Kevin MacLeod, CC BY 4.0). Tracks carry
`verified: "popularity"` - chosen from a source whose public use is documented,
tagged by the composer, not listened to here. `config.bgm.trust` = "listened"
restricts pick to human-verified tracks. CC BY tracks make compose write
output/CREDITS.txt (FR-071); tell the user the credit must appear with the video.
Downloads use urllib and fall back to curl.
"""
import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import common

CATALOG = common.ASSETS_DIR / "bgm" / "catalog.json"


def cache_dir() -> Path:
    d = Path(os.environ.get("DV_BGM_CACHE") or (Path.home() / ".cache" / "demo-video" / "bgm"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_catalog(path: Path = None):
    p = Path(path) if path else CATALOG
    if not p.exists():
        common.die(f"no catalog at {p}")
    return common.load_json(p)


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


def download(url: str, dest: Path):
    src = Path(url)
    if src.exists():                       # local catalogs (tests, offline bundles)
        dest.write_bytes(src.read_bytes())
        return
    try:
        urllib.request.urlretrieve(url, dest)
        return
    except Exception:  # noqa: BLE001
        pass
    r = subprocess.run(["curl", "-sSL", "--max-time", "180", "-o", str(dest), url], capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        common.die(f"download failed: {url}\n{r.stderr.strip()[-200:]}")


def fetch_track(track, verify=True) -> Path:
    dest = cache_dir() / f"{track['id']}.mp3"
    if dest.exists() and (not track.get("sha256") or sha256(dest) == track["sha256"]):
        return dest
    tmp = dest.with_suffix(".part")
    download(track["file"], tmp)
    if verify and track.get("sha256") and sha256(tmp) != track["sha256"]:
        tmp.unlink(missing_ok=True)
        common.die(f"{track['id']}: sha256 mismatch - the source file changed since the catalog was built (FR-072). "
                   f"Rebuild the catalog or pick another track")
    tmp.replace(dest)
    return dest


# ---------------------------------------------------------------- scoring (FR-075, FR-076)
def score(track, moods, energy, narration, trust):
    """Deterministic score and the reasons behind it. None when the track is out."""
    tier = track.get("verified")
    if trust == "listened" and tier != "listened":
        return None, ["not human-verified"]
    if tier not in ("listened", "popularity"):
        return None, ["unverified"]
    if track.get("vocals"):
        return None, ["vocals"]
    if narration and (track.get("energy", 3) > 3 or track.get("density") == "busy"):
        return None, ["too busy under narration (FR-076)"]
    s, why = 0.0, []
    hits = [m for m in moods if m in (track.get("mood") or [])]
    if not hits:
        return None, ["no mood match"]
    s += 10 * len(hits) + (5 if track["mood"][0] in moods else 0)
    why.append("mood " + "+".join(hits))
    if energy is not None:
        d = abs(track.get("energy", 3) - energy)
        s += max(0, 6 - 3 * d)
        why.append(f"energy {track.get('energy')} vs {energy}")
    if tier == "listened":
        s += 4
        why.append("listened")
    if not track.get("requiresAttribution"):
        s += 2
        why.append("no attribution needed")
    dur = track.get("durationSec") or 0
    if dur >= 120:
        s += 1
    return s, why


def cmd_pick(argv):
    ap = argparse.ArgumentParser(prog="dv.py bgm pick")
    ap.add_argument("--mood", required=True, help="comma-separated, from the catalog vocabulary")
    ap.add_argument("--energy", type=int, default=None)
    ap.add_argument("--narration", action="store_true")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--demo", default="demo")
    ap.add_argument("--catalog", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    cat = load_catalog(args.catalog)
    vocab = cat.get("vocabulary", {}).get("mood") or []
    moods = [m.strip() for m in args.mood.split(",") if m.strip()]
    bad = [m for m in moods if vocab and m not in vocab]
    if bad:
        common.die(f"unknown mood {bad}; vocabulary: {', '.join(vocab)}")
    demo_dir = Path(args.demo).resolve()
    cfg_p = demo_dir / "config.json"
    cfg = common.load_json(cfg_p) if cfg_p.exists() else {}
    trust = (cfg.get("bgm") or {}).get("trust") or "popularity"
    ranked = []
    for t in cat.get("tracks") or []:
        s, why = score(t, moods, args.energy, args.narration, trust)
        if s is not None:
            ranked.append((s, t, why))
    ranked.sort(key=lambda r: (-r[0], r[1]["id"]))
    top = ranked[: args.top]
    if not top:
        common.die("no track fits (moods, energy, narration, trust) - relax the profile or add a user file with bgm probe")
    if args.json:
        print(json.dumps([{"id": t["id"], "title": t["title"], "score": s, "why": why, "mood": t["mood"], "energy": t["energy"],
                           "durationSec": t["durationSec"], "license": t["license"], "verified": t["verified"]} for s, t, why in top],
                         ensure_ascii=False, indent=2))
        return 0
    print(f"profile: mood {','.join(moods)}  energy {args.energy}  narration {args.narration}  trust {trust}")
    for i, (s, t, why) in enumerate(top, 1):
        print(f"  {i}. {t['id']:<32} {t['title']:<28} {t['durationSec']:>6}s  energy {t['energy']}  {t['license']}  "
              f"[{t['verified']}]  score {s:.0f}: {', '.join(why)}")
    print(f"next: show these at G2, then `dv.py bgm use <id>`" + ("; CC BY needs a credit line in the description or outro" if any(t.get("requiresAttribution") for _, t, _ in top) else ""))
    return 0


def cmd_use(argv):
    ap = argparse.ArgumentParser(prog="dv.py bgm use")
    ap.add_argument("track")
    ap.add_argument("--demo", default="demo")
    ap.add_argument("--catalog", default=None)
    args = ap.parse_args(argv)
    cat = load_catalog(args.catalog)
    track = next((t for t in cat.get("tracks") or [] if t["id"] == args.track), None)
    if not track:
        common.die(f"no track {args.track} in the catalog (dv.py bgm list)")
    path = fetch_track(track)
    lufs, tp = measure(path)
    demo_dir = Path(args.demo).resolve()
    cfg_p = demo_dir / "config.json"
    cfg = common.load_json(cfg_p) if cfg_p.exists() else {}
    cfg["bgm"] = {"source": "catalog", "id": track["id"], "title": track["title"], "artist": track.get("artist"),
                  "path": str(path), "durationSec": track.get("durationSec"), "loudnessLufs": lufs, "truePeakDbtp": tp,
                  "sha256": track.get("sha256"), "license": track.get("license"), "requiresAttribution": bool(track.get("requiresAttribution")),
                  "attribution": track.get("attribution"), "url": track.get("url"), "verified": track.get("verified"),
                  "trust": (cfg.get("bgm") or {}).get("trust", "popularity"),
                  "probedAt": _dt.datetime.now().astimezone().isoformat(timespec="seconds")}
    common.dump_json(cfg_p, cfg)
    print(f"{track['title']} ({track['license']}, {track['verified']}) -> {common.rel(cfg_p, demo_dir.parent)}; cached at {path}")
    if track.get("requiresAttribution"):
        print("attribution required: compose writes output/CREDITS.txt - the credit must appear in the video description or outro")
    return 0


def cmd_fetch(argv):
    ap = argparse.ArgumentParser(prog="dv.py bgm fetch")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--catalog", default=None)
    args = ap.parse_args(argv)
    cat = load_catalog(args.catalog)
    tracks = [t for t in cat.get("tracks") or [] if not args.ids or t["id"] in args.ids]
    for t in tracks:
        p = fetch_track(t)
        print(f"  {t['id']:<32} {p.stat().st_size / 1e6:.1f} MB  {p}")
    print(f"{len(tracks)} track(s) in {cache_dir()}")
    return 0


def cmd_list(argv):
    ap = argparse.ArgumentParser(prog="dv.py bgm list")
    ap.add_argument("--mood", default=None)
    ap.add_argument("--catalog", default=None)
    args = ap.parse_args(argv)
    cat = load_catalog(args.catalog)
    print(f"catalog {cat.get('generatedAt')}  {len(cat.get('tracks') or [])} tracks  sources: " +
          ", ".join(s["name"] + " (" + s["license"] + ")" for s in cat.get("sources") or []))
    for t in cat.get("tracks") or []:
        if args.mood and args.mood not in t.get("mood", []):
            continue
        print(f"  {t['id']:<32} {t['title']:<28} {','.join(t['mood']):<20} e{t['energy']} {t['density']:<7} {t['durationSec']:>6}s  [{t['verified']}]")
    return 0


def cmd_probe(argv):
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
                  "truePeakDbtp": tp, "sha256": sha256(path), "requiresAttribution": False,
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
    cmds = {"probe": cmd_probe, "pick": cmd_pick, "use": cmd_use, "fetch": cmd_fetch, "list": cmd_list}
    if sub not in cmds:
        common.die(f"unknown bgm subcommand '{sub}' ({' | '.join(cmds)})")
    return cmds[sub](rest)
