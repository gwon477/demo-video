"""Shared helpers for dv.py subcommands. Standard library only, pathlib only.

Every path is resolved from one of two anchors: the skill folder (this file's
location) for bundled assets, and the target project's `demo/` folder for
work products. Nothing here depends on where the skill was installed.
"""
import json
import subprocess
import sys
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = LIB_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent
REPO_DIR = SKILL_DIR.parent.parent
VERSION_FILE = REPO_DIR / "VERSION"


def skill_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def load_json(path: Path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, data, trailing_newline=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        if trailing_newline:
            f.write("\n")


def storyboard_path(arg=None) -> Path:
    """Resolve the storyboard: an explicit path, else demo/storyboard.json under cwd."""
    p = Path(arg) if arg else Path("demo") / "storyboard.json"
    p = p.resolve()
    if not p.exists():
        die(f"no storyboard at {p}")
    return p


def rel(path: Path, base: Path) -> str:
    """Relative path as a forward-slash string; falls back to absolute outside base."""
    try:
        return Path(path).resolve().relative_to(Path(base).resolve()).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def steps_of(scene):
    """The step list may be called `steps` or `beats` - schemaVersion 1 reads either."""
    return scene.get("beats") or scene.get("steps") or []


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


duration = ffprobe_duration


def duration_ms(path: Path) -> int:
    return int(ffprobe_duration(path) * 1000)
