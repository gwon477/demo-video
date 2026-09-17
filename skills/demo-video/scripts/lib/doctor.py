"""dv.py doctor - check the machine for everything the pipeline needs.

    dv.py doctor            # human-readable report, exit 1 if a required item is missing
    dv.py doctor --json     # machine-readable
    dv.py doctor --offline  # skip the remote VERSION comparison

Checks python, node, playwright-cli (and the Playwright it bundles), a
Playwright browser, ffmpeg/ffprobe with the filters and encoders `compose`
uses, TTS providers, and whether a newer skill version is published. Each
missing item comes with an install command for this OS.
"""
import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import common

MIN_PYTHON = (3, 10)
MIN_NODE = 18
MIN_PLAYWRIGHT = (1, 60)
REQUIRED_FILTERS = ["xfade", "concat", "fps", "scale", "amix", "adelay", "volumedetect"]
OPTIONAL_FILTERS = ["loudnorm", "tile"]
REQUIRED_ENCODERS = ["libx264", "aac"]
OPTIONAL_ENCODERS = ["h264_videotoolbox", "libvpx-vp9"]
NEVER_USED_FILTERS = ["drawtext", "subtitles", "ass"]

OS = platform.system()  # Darwin, Windows, Linux


def install_hint(item):
    hints = {
        "python": {"Darwin": "brew install python@3.12", "Windows": "winget install Python.Python.3.12",
                   "Linux": "sudo apt install python3"},
        "node": {"Darwin": "brew install node", "Windows": "winget install OpenJS.NodeJS.LTS",
                 "Linux": "sudo apt install nodejs npm"},
        "playwright-cli": {"*": "npm install -g @playwright/cli"},
        "browser": {"*": "npx playwright install chromium"},
        "ffmpeg": {"Darwin": "brew install ffmpeg", "Windows": "winget install Gyan.FFmpeg",
                   "Linux": "sudo apt install ffmpeg"},
        "edge-tts": {"*": "pip install edge-tts"},
    }
    h = hints.get(item, {})
    return h.get(OS) or h.get("*") or ""


def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def semver(text):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


class Report:
    def __init__(self):
        self.items = []

    def add(self, name, status, detail="", fix="", required=True):
        self.items.append({"name": name, "status": status, "detail": detail,
                           "fix": fix, "required": required})

    @property
    def failed(self):
        return [i for i in self.items if i["status"] == "FAIL" and i["required"]]


def check_python(rep):
    v = sys.version_info[:3]
    ok = v >= MIN_PYTHON
    rep.add("python", "OK" if ok else "FAIL", ".".join(map(str, v)) + f" at {sys.executable}",
            "" if ok else install_hint("python"))


def check_node(rep):
    exe = shutil.which("node")
    if not exe:
        rep.add("node", "FAIL", "not found", install_hint("node"))
        return
    _, out = run(["node", "--version"])
    v = semver(out)
    ok = bool(v) and v[0] >= MIN_NODE
    rep.add("node", "OK" if ok else "FAIL", f"{out.strip()} at {exe}",
            "" if ok else install_hint("node"))


def check_playwright_cli(rep):
    exe = shutil.which("playwright-cli")
    if not exe:
        rep.add("playwright-cli", "FAIL", "not found", install_hint("playwright-cli"))
        rep.add("playwright", "FAIL", "unknown (no playwright-cli)", install_hint("playwright-cli"))
        return
    # stdout carries the bare version; stderr may carry an update banner.
    try:
        r = subprocess.run(["playwright-cli", "--version"], capture_output=True, text=True, timeout=20)
        cli_v = semver(r.stdout)
    except (OSError, subprocess.TimeoutExpired):
        cli_v = None
    rep.add("playwright-cli", "OK" if cli_v else "WARN",
            f"{'.'.join(map(str, cli_v)) if cli_v else 'version unreadable'} at {exe}")

    # The Playwright it bundles decides whether page.screencast exists (1.60+).
    pw_v, where = None, ""
    _, root = run(["npm", "root", "-g"])
    root = Path(root.strip()) if root.strip() else None
    if root:
        for cand in (root / "@playwright" / "cli" / "node_modules" / "playwright-core" / "package.json",
                     root / "@playwright" / "cli" / "package.json"):
            if cand.exists():
                pkg = common.load_json(cand)
                ver = pkg.get("version") if "playwright-core" in cand.parts else \
                    (pkg.get("dependencies") or {}).get("playwright-core", "")
                pw_v, where = semver(ver), ver
                break
    if pw_v is None:
        rep.add("playwright", "WARN", "could not read the bundled Playwright version; "
                "render will tell you if page.screencast is missing", required=False)
    else:
        ok = pw_v >= MIN_PLAYWRIGHT
        rep.add("playwright", "OK" if ok else "FAIL", f"{where} (need {'.'.join(map(str, MIN_PLAYWRIGHT))}+ for page.screencast)",
                "" if ok else install_hint("playwright-cli"))


def check_browser(rep):
    homes = {
        "Darwin": Path.home() / "Library" / "Caches" / "ms-playwright",
        "Linux": Path.home() / ".cache" / "ms-playwright",
        "Windows": Path.home() / "AppData" / "Local" / "ms-playwright",
    }
    home = homes.get(OS)
    found = sorted(p.name for p in home.iterdir()) if home and home.exists() else []
    chromium = [n for n in found if n.startswith("chromium")]
    if chromium:
        rep.add("browser", "OK", f"{', '.join(chromium)} in {home}")
    else:
        rep.add("browser", "WARN", f"no chromium under {home}; playwright-cli may download one on first open",
                install_hint("browser"), required=False)


def check_ffmpeg(rep):
    exe = shutil.which("ffmpeg")
    probe = shutil.which("ffprobe")
    if not exe or not probe:
        rep.add("ffmpeg", "FAIL", "ffmpeg or ffprobe not found", install_hint("ffmpeg"))
        return
    _, ver = run(["ffmpeg", "-version"])
    rep.add("ffmpeg", "OK", (ver.splitlines() or ["?"])[0].replace("ffmpeg version ", "")[:40] + f" at {exe}")

    _, filters = run(["ffmpeg", "-hide_banner", "-filters"])
    names = {line.split()[1] for line in filters.splitlines() if len(line.split()) > 2 and line.startswith(" ")}
    missing = [f for f in REQUIRED_FILTERS if f not in names]
    rep.add("ffmpeg filters", "FAIL" if missing else "OK",
            ("missing: " + ", ".join(missing)) if missing else ", ".join(REQUIRED_FILTERS),
            install_hint("ffmpeg") if missing else "")
    opt_missing = [f for f in OPTIONAL_FILTERS if f not in names]
    rep.add("ffmpeg optional filters", "WARN" if opt_missing else "OK",
            ("missing: " + ", ".join(opt_missing) + " (loudness normalization / frame tiles degrade)") if opt_missing
            else ", ".join(OPTIONAL_FILTERS), required=False)
    text = [f for f in NEVER_USED_FILTERS if f in names]
    rep.add("ffmpeg text filters", "OK", ("present: " + ", ".join(text) + " - never used, text is rendered in the browser")
            if text else "absent - fine, text is rendered in the browser", required=False)

    _, encs = run(["ffmpeg", "-hide_banner", "-encoders"])
    enames = {line.split()[1] for line in encs.splitlines() if len(line.split()) > 2 and line.startswith(" ")}
    missing = [e for e in REQUIRED_ENCODERS if e not in enames]
    rep.add("ffmpeg encoders", "FAIL" if missing else "OK",
            ("missing: " + ", ".join(missing)) if missing else ", ".join(REQUIRED_ENCODERS),
            install_hint("ffmpeg") if missing else "")
    have = [e for e in OPTIONAL_ENCODERS if e in enames]
    rep.add("ffmpeg optional encoders", "OK", ", ".join(have) if have else "none (compose --videotoolbox unavailable)",
            required=False)


def check_tts(rep):
    providers = []
    if OS == "Darwin" and shutil.which("say"):
        _, out = run(["say", "-v", "?"])
        ko = [line.split()[0] for line in out.splitlines() if "ko_KR" in line]
        providers.append(f"say ({len(ko)} ko_KR voices listed: {', '.join(ko[:4])}{'...' if len(ko) > 4 else ''})")
    if shutil.which("edge-tts"):
        providers.append("edge-tts")
    if providers:
        rep.add("tts", "OK", "; ".join(providers) + ". Listed voices may still be uninstalled; narrate probes before use",
                required=False)
    else:
        rep.add("tts", "WARN", "no provider - narration unavailable (use narration: none)",
                install_hint("edge-tts"), required=False)


def check_version(rep, offline):
    local = common.skill_version()
    if offline:
        rep.add("skill version", "OK", f"{local} (remote check skipped)", required=False)
        return
    repo = common.REPO_DIR
    if not (repo / ".git").exists():
        rep.add("skill version", "OK", f"{local} (not a git checkout, no remote check)", required=False)
        return
    code, remotes = run(["git", "-C", str(repo), "remote"])
    if code != 0 or not remotes.strip():
        rep.add("skill version", "OK", f"{local} (no git remote configured)", required=False)
        return
    code, _ = run(["git", "-C", str(repo), "fetch", "--quiet", "origin"], timeout=30)
    if code != 0:
        rep.add("skill version", "WARN", f"{local} (could not reach origin)", required=False)
        return
    remote = ""
    for ref in ("origin/HEAD", "origin/main", "origin/master"):
        code, out = run(["git", "-C", str(repo), "show", f"{ref}:VERSION"])
        if code == 0:
            remote = out.strip()
            break
    if remote and semver(remote) and semver(local) and semver(remote) > semver(local):
        rep.add("skill version", "WARN", f"{local} installed, {remote} available - run the install script to update",
                required=False)
    else:
        rep.add("skill version", "OK", f"{local}" + (f" (remote {remote})" if remote else ""), required=False)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py doctor", description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--offline", action="store_true", help="skip the remote VERSION comparison")
    args = ap.parse_args(argv)

    rep = Report()
    check_python(rep)
    check_node(rep)
    check_playwright_cli(rep)
    check_browser(rep)
    check_ffmpeg(rep)
    check_tts(rep)
    check_version(rep, args.offline)

    if args.json:
        print(json.dumps({"os": OS, "ok": not rep.failed, "items": rep.items}, ensure_ascii=False, indent=2))
    else:
        print(f"demo-video doctor  ({OS})")
        for it in rep.items:
            print(f"  {it['status']:<4} {it['name']:<24} {it['detail']}")
            if it["fix"] and it["status"] != "OK":
                print(f"       -> {it['fix']}")
        if rep.failed:
            print(f"\n{len(rep.failed)} required item(s) missing", file=sys.stderr)
        else:
            print("\nall required items present")
    return 1 if rep.failed else 0
