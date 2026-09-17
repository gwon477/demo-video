"""dv.py render - assemble scene bodies with the prelude and record them via playwright-cli.

    dv.py render                      # all scenes of demo/storyboard.json
    dv.py render 03-dashboard         # one scene
    dv.py render --storyboard demo/storyboard-chat.json

A scene body is `demo/scenes/<id>.body.js` and contains statements only - no
wrapper function. Anything above a `// ---record---` line runs before recording
starts, for setup that must not appear in the clip. This module wraps it as:

    async page => {
      <prelude.js>
      await page.setViewportSize({width, height});   // 프레임과 뷰포트를 맞춘다
      await startRec('demo/scenes/<id>.webm', {width, height});
      try { <body> } finally { await stopRec(); }
      return <elapsed ms>;
    }

so the output path always matches what compose expects and the clip is always
flushed even when a step throws. `BASE` is the storyboard's baseUrl, `ACCOUNTS`
is demo/.accounts.json (gitignored) so no credential is ever written into a
scene body or the storyboard, and `HOLD` is the scene's measured subtitle holds
in beat order (pass `HOLD[n]` to `subtitleSpan`). If demo/prelude.js exists it
is injected too, for app-specific helpers such as a login routine.

The recording keeps writing for up to ~1s after stopRec, leaving a frozen tail
on every clip. The wrapper reports the real elapsed time and this module trims
each clip to it losslessly (`-c copy`), so scene lengths match the storyboard
instead of drifting a second longer each.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from . import common, state

PRELUDE = common.SCRIPTS_DIR / "prelude.js"

# Everything above a `// ---record---` line runs before the recording starts,
# so a scene can arrange its own state - log in, seed a filter, open a modal -
# without that setup showing up in the clip.
RECORD_MARK = re.compile(r"^[ \t]*//[ \t]*-{2,}[ \t]*record[ \t]*-{2,}[ \t]*$", re.MULTILINE)


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def trim(path: Path, seconds: float) -> bool:
    """Cut the frozen tail. Lossless stream copy; leaves the file alone on failure."""
    tmp = path.with_suffix(".trim.webm")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path),
                        "-t", f"{seconds:.3f}", "-c", "copy", str(tmp)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        if tmp.exists():
            tmp.unlink()
        return False
    tmp.replace(path)
    return True


def build_script(sid, scene, body, *, prelude, project_prelude, base, accounts, w, h, rel_webm):
    parts = RECORD_MARK.split(body, maxsplit=1)
    setup, body = (parts[0], parts[1]) if len(parts) == 2 else ("", body)
    # An intro/outro card must not have the previous page flash under its
    # fade-in, so blank the page before the recording starts.
    pre = "await page.goto('about:blank');\n" if scene.get("kind") in ("intro", "outro") else ""
    # The holds narrate measured, in beat order, so a body can pass HOLD[n]
    # to subtitleSpan and never cut its own narration off.
    holds = [b.get("holdMs") or 0 for b in common.steps_of(scene) if b.get("action") == "subtitle"]
    return (
        "async page => {\n"
        f"const BASE = {json.dumps(base)};\n"
        f"const ACCOUNTS = {json.dumps(accounts, ensure_ascii=False)};\n"
        f"const HOLD = {json.dumps(holds)};\n"
        "const __cues = [];\n"
        "let __t0 = 0;\n"
        f"{prelude}\n"
        f"{project_prelude}\n"
        f"{setup}\n"
        f"{pre}"
        # The screencast puts the viewport in the TOP-LEFT of the output frame
        # and pads the rest. A viewport smaller than the video size therefore
        # records the app in a corner with dead margins - match them.
        f"await page.setViewportSize({{ width: {w}, height: {h} }});\n"
        f"await startRec({json.dumps(rel_webm)}, {{ width: {w}, height: {h} }});\n"
        "__t0 = Date.now();\n"
        "let __ms = 0;\n"
        "try {\n"
        f"{body}\n"
        "} finally {\n"
        "  __ms = Date.now() - __t0;\n"
        "  await stopRec();\n"
        "}\n"
        "return JSON.stringify({ ms: __ms, cues: __cues });\n"
        "}\n"
    )


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py render", description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*", help="scene ids to render; default all")
    ap.add_argument("--storyboard", default=None, help="default demo/storyboard.json")
    ap.add_argument("--cwd", default=None, help="dir playwright-cli runs in; default the project root")
    ap.add_argument("--headed", action="store_true", help="show the browser while recording")
    ap.add_argument("--close", action="store_true", help="close the browser when done")
    ap.add_argument("--dry-run", action="store_true", help="assemble scripts, do not record")
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    demo_dir = sb_path.parent
    # G3: no recording before the user approved the storyboard (DESIGN 4절).
    state.require(demo_dir, "storyboard")
    project = Path(args.cwd).resolve() if args.cwd else demo_dir.parent
    scenes_dir = demo_dir / "scenes"
    build_dir = scenes_dir / ".build"
    build_dir.mkdir(parents=True, exist_ok=True)

    prelude = PRELUDE.read_text(encoding="utf-8")
    # Project-local helpers, injected after the skill prelude.
    pp_path = demo_dir / "prelude.js"
    project_prelude = pp_path.read_text(encoding="utf-8") if pp_path.exists() else ""
    # Credentials never belong in a scene body. demo/.accounts.json is gitignored.
    acc_path = demo_dir / ".accounts.json"
    accounts = common.load_json(acc_path) if acc_path.exists() else {}

    vid = sb.get("video") or {}
    w, h = vid.get("width", 1280), vid.get("height", 720)
    base = sb.get("baseUrl", "")

    scenes = sb.get("scenes") or []
    wanted = args.ids or [s["id"] for s in scenes]
    by_id = {s["id"]: s for s in scenes}
    unknown = [i for i in wanted if i not in by_id]
    if unknown:
        common.die("not in storyboard: " + ", ".join(unknown))

    bodies, missing = {}, []
    for sid in wanted:
        p = scenes_dir / f"{sid}.body.js"
        if not p.exists():
            missing.append(common.rel(p, project))
            continue
        bodies[sid] = p.read_text(encoding="utf-8")
    if missing:
        common.die("scene bodies not written yet:\n  " + "\n  ".join(missing))

    built = {}
    for sid, body in bodies.items():
        rel_webm = common.rel(scenes_dir / f"{sid}.webm", project)
        script = build_script(sid, by_id[sid], body, prelude=prelude, project_prelude=project_prelude,
                              base=base, accounts=accounts, w=w, h=h, rel_webm=rel_webm)
        out = build_dir / f"{sid}.js"
        out.write_text(script, encoding="utf-8")
        built[sid] = out

    chk = subprocess.run(["node", "--check", *map(str, built.values())], capture_output=True, text=True)
    if chk.returncode != 0:
        common.die("assembled script has a syntax error - fix the scene body:\n" + chk.stderr.strip())

    if args.dry_run:
        for sid, p in built.items():
            print(f"{sid}: {p}")
        return 0

    open_cmd = ["playwright-cli", "open"] + (["--headed"] if args.headed else [])
    r = run(open_cmd, project)
    if r.returncode != 0:
        common.die("playwright-cli open failed:\n" + (r.stderr or r.stdout).strip())

    auth = sb.get("authState")
    if auth:
        auth_path = Path(auth) if Path(auth).is_absolute() else project / auth
        if auth_path.exists():
            r = run(["playwright-cli", "state-load", auth], project)
            if r.returncode != 0:
                common.die("state-load failed:\n" + (r.stderr or r.stdout).strip())
            print(f"loaded auth state from {auth}")
        else:
            print(f"warning: authState {auth} not found - recording unauthenticated", file=sys.stderr)

    failed = []
    for sid in wanted:
        rel = common.rel(built[sid], project)
        r = run(["playwright-cli", "run-code", "--filename", rel, "--raw"], project)
        webm = scenes_dir / f"{sid}.webm"
        if r.returncode != 0 or not webm.exists():
            failed.append(sid)
            msg = (r.stdout or "") + (r.stderr or "")
            tail = "\n    ".join(msg.strip().splitlines()[-6:])
            print(f"  {sid:<20} FAILED\n    {tail}", file=sys.stderr)
            continue

        raw_dur = common.duration(webm)
        elapsed, cues = None, []
        try:
            payload = json.loads(json.loads(r.stdout.strip()))
            elapsed = float(payload["ms"]) / 1000.0
            cues = payload.get("cues") or []
        except (ValueError, KeyError, TypeError):
            print(f"  warning: {sid} did not report its timing - no cues for narration or srt",
                  file=sys.stderr)

        # Exact subtitle in/out points, for the narration track and the .srt.
        if cues:
            for c in cues:
                if c.get("endMs") is None:
                    c["endMs"] = int(elapsed * 1000) if elapsed else c["startMs"] + 2000
            common.dump_json(scenes_dir / f"{sid}.timing.json", {"sceneId": sid, "cues": cues})

        note = ""
        if elapsed and raw_dur - elapsed > 0.15:
            if trim(webm, elapsed + 0.08):
                note = f"  (trimmed {raw_dur - common.duration(webm):.2f}s tail)"
            else:
                note = f"  (tail trim failed, {raw_dur - elapsed:.2f}s of frozen frame left)"
        actual = common.duration(webm)

        planned = by_id[sid].get("dwellMs") or by_id[sid].get("durationMs")
        if planned:
            note += f"  storyboard {planned / 1000:.2f}s"
        print(f"  {sid:<20} {actual:>6.2f}s{note}")

    if args.close:
        run(["playwright-cli", "close"], project)

    if failed:
        common.die("scenes failed: " + ", ".join(failed))
    print(f"{len(wanted)} scene(s) rendered into {common.rel(scenes_dir, project)}")
    return 0
