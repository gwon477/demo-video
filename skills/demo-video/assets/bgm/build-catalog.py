#!/usr/bin/env python3
"""Build assets/bgm/catalog.json from Incompetech's public track index (Kevin MacLeod, CC BY 4.0).

    python3 build-catalog.py                # downloads pieces.json + the selected mp3s, measures, writes catalog.json
    python3 build-catalog.py --no-audio     # tags only, no download/measure (sha256/loudness stay null)

Selection is deterministic (feel tags, BPM, length, genre) so anyone can rebuild
the same catalog. Tracks are tier "popularity": the source is documented as one
of the most used royalty-free libraries (see popularityEvidence); nobody listened
to them here. A human who listens can raise a track to verified "listened".
Standard library only.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = "https://incompetech.com/music/royalty-free/pieces.json"
MP3 = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
PAGE = "https://incompetech.com/music/royalty-free/index.html?isrc="
GENRES = {2: "African", 3: "Blues", 4: "Classical", 5: "Contemporary", 6: "Disco", 7: "Electronica", 8: "Funk", 9: "Holiday",
          10: "Horror", 11: "Jazz", 12: "Latin", 13: "Modern", 14: "Musical", 15: "Polka", 16: "Pop", 18: "Reggae", 19: "Rock",
          20: "Silent Film Score", 21: "Ska", 22: "Soundtrack", 23: "Stings", 24: "Unclassifiable", 25: "World", 26: "Urban"}
ALLOWED_GENRES = {5, 7, 11, 13, 16, 22, 26}
EXCLUDE_FEELS = {"Eerie", "Unnerving", "Aggressive", "Action", "Suspenseful", "Dark", "Intense", "Ren Faire", "Medieval"}
# mood -> (required feels any-of, forbidden feels, bpm window center, genres or None)
MOODS = {
    "calm":       ({"Calming", "Calm"}, {"Bouncy", "Driving", "Epic"}, 80, None),
    "focused":    ({"Relaxed", "Grooving"}, {"Bouncy", "Epic", "Humorous"}, 100, {5, 7, 11, 13}),
    "warm":       ({"Relaxed", "Bright"}, {"Driving", "Epic", "Mysterious"}, 95, {5, 11, 16}),
    "bright":     ({"Bright", "Uplifting"}, {"Somber", "Mysterious"}, 115, None),
    "confident":  ({"Driving", "Epic"}, {"Humorous", "Bouncy"}, 110, {5, 7, 13, 22, 26}),
    "inspiring":  ({"Uplifting", "Epic"}, {"Humorous", "Somber"}, 105, None),
    "playful":    ({"Bouncy", "Humorous"}, {"Somber", "Mysterious"}, 125, None),
    "futuristic": ({"Mysterious", "Driving", "Grooving"}, {"Humorous", "Bouncy"}, 115, {7, 13}),
    "serious":    ({"Somber", "Mysterious"}, {"Bouncy", "Humorous", "Bright"}, 85, {5, 22}),
}
PER_MOOD = 3
MIN_SEC, MAX_SEC = 90, 360
POPULARITY_EVIDENCE = ("Kevin MacLeod's CC BY library: featured in thousands of films and millions of YouTube videos; "
                       "\"Monkeys Spinning Monkeys\" and \"Electrodoodle\" played 151.8 billion times on TikTok, 2021-2026 "
                       "(Wikipedia, Kevin MacLeod, retrieved 2026-09-18). Source-level evidence; per-track plays are not published.")
ATTRIBUTION = ('"{title}" Kevin MacLeod (incompetech.com)\nLicensed under Creative Commons: By Attribution 4.0 License\n'
               'http://creativecommons.org/licenses/by/4.0/')


def download(url, dest: Path):
    """urllib first; some Python builds reject this site's certificate chain, so fall back to curl."""
    try:
        urllib.request.urlretrieve(url, dest)
        return
    except Exception:  # noqa: BLE001
        pass
    r = subprocess.run(["curl", "-sSL", "--max-time", "120", "-o", str(dest), url], capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(f"download failed: {url}: {r.stderr.strip()[-200:]}")


def seconds(length):
    h, m, s = (int(x) for x in length.split(":"))
    return h * 3600 + m * 60 + s


def energy(bpm, feels):
    e = 1 if bpm < 80 else 2 if bpm < 100 else 3 if bpm < 125 else 4 if bpm < 145 else 5
    if feels & {"Driving", "Intense", "Epic"}:
        e += 1
    if feels & {"Calming", "Calm"}:
        e -= 1
    return max(1, min(5, e))


def density(bpm, feels):
    if feels & {"Calming", "Calm"} and bpm < 100:
        return "sparse"
    if feels & {"Driving", "Epic", "Bouncy"} or bpm >= 130:
        return "busy"
    return "medium"


def select(pieces):
    rows = []
    for p in pieces:
        try:
            bpm, sec, genre = int(p.get("bpm") or 0), seconds(p["length"]), int(p.get("genre") or 0)
        except (ValueError, KeyError):
            continue
        feels = {f.strip() for f in (p.get("feel") or "").split(",") if f.strip()}
        if not bpm or genre not in ALLOWED_GENRES or not (MIN_SEC <= sec <= MAX_SEC) or feels & EXCLUDE_FEELS:
            continue
        rows.append((p, bpm, sec, genre, feels))
    chosen = {}
    for mood, (need, forbid, center, genres) in MOODS.items():
        cands = [r for r in rows if (r[4] & need) and not (r[4] & forbid) and (genres is None or r[3] in genres)]
        cands.sort(key=lambda r: (abs(r[1] - center), r[0]["title"]))
        for r in cands:
            uid = r[0]["uuid"]
            if uid in chosen:
                chosen[uid]["mood"].append(mood)
                continue
            if sum(1 for c in chosen.values() if mood in c["mood"]) >= PER_MOOD:
                break
            p, bpm, sec, genre, feels = r
            chosen[uid] = {
                "id": "inc-" + re.sub(r"[^a-z0-9]+", "-", p["title"].lower()).strip("-"),
                "title": p["title"], "artist": "Kevin MacLeod", "source": "incompetech",
                "url": PAGE + (p.get("isrc") or ""), "file": MP3 + urllib.parse.quote(p["filename"]),
                "license": "CC BY 4.0", "licenseUrl": "https://creativecommons.org/licenses/by/4.0/",
                "licenseEvidence": {"level": "source", "note": "incompetech.com/music/royalty-free/licenses/: Creative Commons - free, requires credit"},
                "licenseCheckedAt": dt.date.today().isoformat(), "requiresAttribution": True,
                "attribution": ATTRIBUTION.format(title=p["title"]),
                "mood": [mood], "feels": sorted(feels), "genre": GENRES.get(genre), "instruments": p.get("instruments"),
                "energy": energy(bpm, feels), "bpm": bpm, "density": density(bpm, feels), "durationSec": sec,
                "loopable": None, "vocals": False,
                "verified": "popularity", "popularityEvidence": POPULARITY_EVIDENCE,
                "sha256": None, "loudnessLufs": None, "truePeakDbtp": None,
            }
    return list(chosen.values())


def measure(track, tmpdir):
    dest = Path(tmpdir) / (track["id"] + ".mp3")
    download(track["file"], dest)
    h = hashlib.sha256(dest.read_bytes()).hexdigest()
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(dest), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dest)],
                       capture_output=True, text=True)
    track.update({"sha256": h, "loudnessLufs": float(i[-1]) if i else None, "truePeakDbtp": float(tp[-1]) if tp else None,
                  "durationSec": round(float(d.stdout.strip() or track["durationSec"]), 1), "bytes": dest.stat().st_size})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--out", default=str(HERE / "catalog.json"))
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        idx = Path(tmp) / "pieces.json"
        download(INDEX, idx)
        pieces = json.loads(idx.read_text(encoding="utf-8"))
    tracks = select(pieces)
    print(f"selected {len(tracks)} tracks from {len(pieces)}")
    if not args.no_audio:
        with tempfile.TemporaryDirectory() as tmp:
            for t in tracks:
                try:
                    measure(t, tmp)
                    print(f"  {t['id']:<32} {t['durationSec']:>6}s {t['loudnessLufs']} LUFS  {','.join(t['mood'])}")
                except Exception as e:  # noqa: BLE001
                    print(f"  {t['id']:<32} measure failed: {e}", file=sys.stderr)
    catalog = {
        "schemaVersion": 2, "generatedAt": dt.date.today().isoformat(), "builder": "assets/bgm/build-catalog.py",
        "vocabulary": {"mood": list(MOODS), "energy": "1(매우 잔잔) ~ 5(매우 강함)", "density": ["sparse", "medium", "busy"],
                       "verified": ["listened", "popularity", False]},
        "policy": {"tiers": "listened: 사람이 전곡 청취해 태그를 확정. popularity: 대중적으로 검증된 출처의 작곡가 태그를 그대로 씀. "
                            "bgm pick은 두 등급을 모두 대상으로 하되 config.bgm.trust로 좁힐 수 있다",
                   "attribution": "CC BY 트랙이 선택되면 compose가 output/CREDITS.txt에 attribution 문구를 쓴다"},
        "sources": [{"name": "Incompetech (Kevin MacLeod)", "url": "https://incompetech.com/music/royalty-free/", "license": "CC BY 4.0",
                     "index": INDEX, "popularityEvidence": POPULARITY_EVIDENCE}],
        "tracks": tracks,
    }
    Path(args.out).write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
