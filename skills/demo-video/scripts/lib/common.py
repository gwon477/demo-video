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


ASSETS_DIR = SKILL_DIR / "assets"
USER_THEME = Path.home() / ".config" / "demo-video" / "theme.json"


def _deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _deep_merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load_theme() -> dict:
    """Bundled theme.json, overridden by the user's ~/.config/demo-video/theme.json."""
    theme = load_json(ASSETS_DIR / "theme.json")
    if USER_THEME.exists():
        theme = _deep_merge(theme, load_json(USER_THEME))
    return theme


def schema_version(sb) -> int:
    return int(sb.get("schemaVersion") or 1)


def steps_of(scene):
    """The step list may be called `steps` or `beats` - schemaVersion 1 reads either."""
    return scene.get("beats") or scene.get("steps") or []


def subtitle_steps(scene, version=2):
    """Subtitle-bearing steps in a uniform shape: [{text, holdMs, narration, emphasis}].

    v1 (draft): steps with action == "subtitle". v2: every step carries `subtitle`.
    """
    out = []
    if version >= 2:
        for st in scene.get("steps") or []:
            sub = st.get("subtitle") or {}
            out.append({"text": sub.get("text", ""), "holdMs": st.get("holdMs"),
                        "narration": sub.get("narration", st.get("narration")),
                        "emphasis": sub.get("emphasis"), "step": st})
    else:
        for st in steps_of(scene):
            if st.get("action") == "subtitle":
                out.append({"text": st.get("text", ""), "holdMs": st.get("holdMs"),
                            "narration": st.get("narration"), "emphasis": st.get("emphasis"), "step": st})
    return out


def frame_size(sb) -> tuple:
    if schema_version(sb) >= 2:
        size = (sb.get("meta") or {}).get("size") or [1920, 1080]
        return int(size[0]), int(size[1])
    vid = sb.get("video") or {}
    return int(vid.get("width", 1280)), int(vid.get("height", 720))


def base_url(sb, demo_dir: Path) -> str:
    """v2 takes the app URL from config.json; v1 kept it in the storyboard."""
    if sb.get("baseUrl"):
        return sb["baseUrl"].rstrip("/")
    cfg = demo_dir / "config.json"
    if cfg.exists():
        return ((load_json(cfg).get("app") or {}).get("url") or "").rstrip("/")
    return ""


def name_of(sb) -> str:
    return (sb.get("meta") or {}).get("name") or sb.get("name") or "demo"


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
