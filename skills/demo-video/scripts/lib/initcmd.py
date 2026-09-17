"""dv.py init - create the demo/ skeleton, config.json and state.json from intake answers.

    dv.py init --url http://localhost:3000 --name camino-demo
    dv.py init --url ... --size 1920x1080 --narration none --bgm none --target-sec 60

Refuses when the app URL does not answer (exit 1) - every later step needs it.
Refuses to overwrite an existing config.json without --force. Adds the render
artifacts and credential files to the project's .gitignore.
"""
import argparse
import datetime as _dt
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import common, state

GITIGNORE_LINES = [
    "demo/scenes/*.webm",
    "demo/scenes/.build/",
    "demo/output/",
    "demo/audio/",
    "demo/.auth/",
    "demo/.auth.json",
    "demo/.accounts.json",
]


def parse_size(text):
    try:
        w, h = text.lower().split("x")
        w, h = int(w), int(h)
    except ValueError:
        common.die(f"--size must look like 1920x1080, got '{text}'")
    if w % 2 or h % 2:
        common.die("--size width and height must be even (H.264 yuv420p)")
    return [w, h]


def url_reachable(url, timeout=8):
    """Any HTTP response counts, including 401/403/404 - the server is up."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False, "not an http(s) URL"
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "demo-video/doctor"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return True, f"HTTP {e.code}"
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        return False, str(getattr(e, "reason", e))


def ensure_gitignore(project: Path):
    gi = project / ".gitignore"
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    add = [l for l in GITIGNORE_LINES if l not in existing]
    if not add:
        return []
    with gi.open("a", encoding="utf-8") as f:
        if existing and existing[-1].strip():
            f.write("\n")
        f.write("# demo-video\n" + "\n".join(add) + "\n")
    return add


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py init", description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True, help="where the running app is")
    ap.add_argument("--name", default=None, help="output name; default from the project folder")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--narration", default="none", choices=["none", "say", "edge-tts"])
    ap.add_argument("--voice", default=None)
    ap.add_argument("--bgm", default="none", help="'none', 'auto', or a path to the user's file")
    ap.add_argument("--intro", default=None, help="user's intro video path; default HTML template")
    ap.add_argument("--outro", default=None, help="user's outro video path; default HTML template")
    ap.add_argument("--target-sec", type=int, default=60)
    ap.add_argument("--audience", default="")
    ap.add_argument("--purpose", default="")
    ap.add_argument("--reset-command", default="", help="shell command that resets seed data")
    ap.add_argument("--demo", default="demo")
    ap.add_argument("--skip-url-check", action="store_true")
    ap.add_argument("--force", action="store_true", help="overwrite an existing config.json")
    args = ap.parse_args(argv)

    demo_dir = Path(args.demo).resolve()
    project = demo_dir.parent
    cfg_path = demo_dir / "config.json"
    if cfg_path.exists() and not args.force:
        common.die(f"{common.rel(cfg_path, project)} exists - pass --force to overwrite")

    if not args.skip_url_check:
        ok, detail = url_reachable(args.url)
        if not ok:
            common.die(f"app URL {args.url} not reachable ({detail}). Start the app first; "
                       f"the skill does not launch it")
        print(f"app: {args.url} ({detail})")

    for label, p in (("intro", args.intro), ("outro", args.outro)):
        if p and not Path(p).exists():
            common.die(f"--{label} file not found: {p}")
    if args.bgm not in ("none", "auto") and not Path(args.bgm).exists():
        common.die(f"--bgm file not found: {args.bgm}")

    name = args.name or project.name.lower().replace(" ", "-") + "-demo"
    config = {
        "schemaVersion": 1,
        "createdAt": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "skillVersion": common.skill_version(),
        "name": name,
        "app": {"url": args.url.rstrip("/"), "resetCommand": args.reset_command},
        "video": {"size": parse_size(args.size), "fps": 25, "targetSec": args.target_sec},
        "narration": {"provider": args.narration, "voice": args.voice},
        "bgm": {"source": "none" if args.bgm == "none" else ("catalog" if args.bgm == "auto" else "file"),
                "path": None if args.bgm in ("none", "auto") else str(Path(args.bgm).resolve())},
        "intro": {"source": "video", "path": str(Path(args.intro).resolve())} if args.intro
                 else {"source": "html", "template": "default"},
        "outro": {"source": "video", "path": str(Path(args.outro).resolve())} if args.outro
                 else {"source": "html", "template": "default"},
        "audience": args.audience,
        "purpose": args.purpose,
    }

    for sub in ("scenes", "output"):
        (demo_dir / sub).mkdir(parents=True, exist_ok=True)
    common.dump_json(cfg_path, config)
    if not state.state_path(demo_dir).exists():
        state.save(demo_dir, {"schemaVersion": 1, "approvals": {}})
    added = ensure_gitignore(project)

    print(f"wrote {common.rel(cfg_path, project)} and {common.rel(state.state_path(demo_dir), project)}")
    if added:
        print(f"added {len(added)} line(s) to .gitignore")
    print("next: survey the app (phase 1), then dv.py approve survey")
    return 0
