"""dv.py render [scene ...] - assemble scene bodies with the prelude and record them via playwright-cli.

    dv.py render                      # all scenes of demo/storyboard.json (needs G3)
    dv.py render 03-dashboard         # one scene
    dv.py render --draft              # 960-wide clips into demo/scenes/draft/ for a first look
    dv.py render --jobs 3             # read-only scenes in parallel browser sessions
    dv.py render --force              # ignore the hash cache

Bodies come from the storyboard (schemaVersion 2, marker `// @generated`) or
from a hand-written `demo/scenes/<id>.body.js`. Each body is wrapped as:

    async page => {
      <prelude.js>
      await page.setViewportSize({width, height});
      await startRec('demo/scenes/<id>.webm', {width, height});
      try { <body> } finally { await stopRec(); }
      return { ms, cues, marks };
    }

Optimizations (DESIGN.md 8절): FR-050 scene hash cache (scene + body + prelude
+ theme + size + holds), FR-052 draft mode, FR-053 saved auth state, FR-055
`--jobs` with `mutates` scenes run sequentially after `config.resetCommand`,
FR-057 intro/outro clips cached by template and fields.

The recorder keeps writing for up to ~1s after stopRec; the wrapper reports the
real elapsed time and the clip is trimmed to it losslessly.
"""
import argparse
import concurrent.futures
import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path

from . import bodygen, common, state

PRELUDE = common.SCRIPTS_DIR / "prelude.js"
RECORD_MARK = re.compile(r"^[ \t]*//[ \t]*-{2,}[ \t]*record[ \t]*-{2,}[ \t]*$", re.MULTILINE)
DRAFT_WIDTH = 960


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def pw(session, *args):
    return ["playwright-cli"] + ([f"-s={session}"] if session else []) + list(args)


def clean_lines(text):
    return [l for l in (text or "").strip().splitlines() if l.strip() and l.lstrip()[0] not in "║╔╚"]


def trim(path: Path, seconds: float) -> bool:
    tmp = path.with_suffix(".trim.webm")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-t", f"{seconds:.3f}", "-c", "copy", str(tmp)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        if tmp.exists():
            tmp.unlink()
        return False
    tmp.replace(path)
    return True


# ---------------------------------------------------------------- cards
def fill_template(text, fields, theme):
    def lookup(key):
        if key.startswith("theme."):
            node = theme
            for part in key.split(".")[1:]:
                node = node.get(part, "") if isinstance(node, dict) else ""
            return str(node)
        return html.escape(str(fields.get(key) or ""))
    return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", lambda m: lookup(m.group(1)), text)


def card_html_path(kind, card, demo_dir: Path, build_dir: Path, theme) -> Path:
    """Fill the intro/outro template. `template` is a bundled name or a path under demo/."""
    template = card.get("template") or "default"
    src = (demo_dir / template) if ("/" in template or template.endswith(".html")) \
        else (common.ASSETS_DIR / kind / f"{template}.html")
    if not src.exists():
        common.die(f"{kind} template not found: {src}")
    out = build_dir / f"{'00-intro' if kind == 'intro' else '99-outro'}.html"
    out.write_text(fill_template(src.read_text(encoding="utf-8"), card, theme), encoding="utf-8")
    return out


def card_body(kind, card, page_path: Path):
    hold = card.get("holdMs", 2500 if kind == "intro" else 3000)
    return (bodygen.GENERATED_MARK + "\n"
            f"await page.goto({json.dumps(page_path.resolve().as_uri())});\n"
            "await page.waitForLoadState('load');\n"
            "// ---record---\n"
            "await page.evaluate(() => document.body.classList.add('play'));\n"
            f"await dwell({int(hold)});\n")


# ---------------------------------------------------------------- scripts
def build_script(scene, body, *, prelude, project_prelude, base, accounts, w, h, rel_webm, theme, version):
    parts = RECORD_MARK.split(body, maxsplit=1)
    setup, body = (parts[0], parts[1]) if len(parts) == 2 else ("", body)
    # A v1 intro/outro card must not have the previous page flash under it.
    pre = "await page.goto('about:blank');\n" if (version < 2 and scene.get("kind") in ("intro", "outro")) else ""
    holds = [st["holdMs"] or 0 for st in common.subtitle_steps(scene, version)]
    return (
        "async page => {\n"
        f"const BASE = {json.dumps(base)};\n"
        f"const ACCOUNTS = {json.dumps(accounts, ensure_ascii=False)};\n"
        f"const HOLD = {json.dumps(holds)};\n"
        f"const DWELL = {json.dumps(scene.get('dwellMs') or 0)};\n"
        f"const THEME = {json.dumps(theme, ensure_ascii=False)};\n"
        f"const FRAME = {{ width: {w}, height: {h} }};\n"
        "const __cues = [];\n"
        "const __marks = [];\n"
        "let __t0 = 0;\n"
        f"{prelude}\n"
        f"{project_prelude}\n"
        f"{setup}\n"
        f"{pre}"
        # The screencast puts the viewport in the top-left of the frame and pads
        # the rest, so the viewport must match the frame size.
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
        "return JSON.stringify({ ms: __ms, cues: __cues, marks: __marks });\n"
        "}\n"
    )


def cache_key(scene, body, prelude, project_prelude, theme, w, h, version):
    payload = json.dumps({"scene": scene, "body": body, "prelude": prelude, "project_prelude": project_prelude,
                          "theme": theme, "size": [w, h], "v": version}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- recording
class Job:
    def __init__(self, sid, scene, script_path, webm, timing, hash_path, key, planned):
        self.sid, self.scene, self.script_path, self.webm = sid, scene, script_path, webm
        self.timing, self.hash_path, self.key, self.planned = timing, hash_path, key, planned


def record(job: Job, session, project: Path, reset_cmd=None):
    """Run one scene in the given browser session. Returns (ok, report line)."""
    if reset_cmd and job.scene.get("mutates"):
        r = subprocess.run(reset_cmd, shell=True, cwd=str(project), capture_output=True, text=True)
        if r.returncode != 0:
            return False, f"  {job.sid:<20} FAILED\n    resetCommand exited {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}"
    rel = common.rel(job.script_path, project)
    r = run(pw(session, "run-code", "--filename", rel, "--raw"), project)
    if r.returncode != 0 or not job.webm.exists():
        tail = "\n    ".join(clean_lines((r.stdout or "") + (r.stderr or ""))[-8:])
        return False, f"  {job.sid:<20} FAILED\n    {tail}"

    raw_dur = common.duration(job.webm)
    elapsed, cues, marks = None, [], []
    try:
        payload = json.loads(json.loads(r.stdout.strip()))
        elapsed = float(payload["ms"]) / 1000.0
        cues, marks = payload.get("cues") or [], payload.get("marks") or []
    except (ValueError, KeyError, TypeError):
        pass
    for c in cues:
        if c.get("endMs") is None:
            c["endMs"] = int(elapsed * 1000) if elapsed else c["startMs"] + 2000
    common.dump_json(job.timing, {"sceneId": job.sid, "cues": cues, "marks": marks,
                                  "elapsedMs": int((elapsed or 0) * 1000)})

    note = ""
    if elapsed and raw_dur - elapsed > 0.15:
        note = f"  (trimmed {raw_dur - elapsed:.2f}s tail)" if trim(job.webm, elapsed + 0.08) else "  (tail trim failed)"
    if elapsed is None:
        note += "  (no timing reported)"
    if job.planned:
        note += f"  storyboard {job.planned / 1000:.2f}s"
    job.hash_path.write_text(job.key, encoding="utf-8")
    return True, f"  {job.sid:<20} {common.duration(job.webm):>6.2f}s{note}"


def open_session(session, project: Path, headed, auth):
    r = run(pw(session, "open", *(["--headed"] if headed else [])), project)
    if r.returncode != 0:
        common.die("playwright-cli open failed:\n" + "\n".join(clean_lines(r.stderr or r.stdout)))
    if auth:
        auth_path = Path(auth) if Path(auth).is_absolute() else project / auth
        if auth_path.exists():
            r = run(pw(session, "state-load", auth), project)
            if r.returncode != 0:
                common.die("state-load failed:\n" + "\n".join(clean_lines(r.stderr or r.stdout)))
        else:
            print(f"warning: authState {auth} not found - recording unauthenticated", file=sys.stderr)


def close_session(session, project: Path):
    run(pw(session, "close"), project)


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py render", description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*", help="scene ids to render; default all")
    ap.add_argument("--storyboard", default=None)
    ap.add_argument("--cwd", default=None, help="dir playwright-cli runs in; default the project root")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--close", action="store_true", help="close the browser when done (single-session mode)")
    ap.add_argument("--dry-run", action="store_true", help="assemble scripts, do not record")
    ap.add_argument("--draft", action="store_true", help=f"{DRAFT_WIDTH}px wide clips into scenes/draft/")
    ap.add_argument("--jobs", type=int, default=1, help="parallel browser sessions for read-only scenes")
    ap.add_argument("--force", action="store_true", help="re-record even when the hash cache matches")
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    demo_dir = sb_path.parent
    state.require(demo_dir, "storyboard")     # G3 (DESIGN 4절)
    project = Path(args.cwd).resolve() if args.cwd else demo_dir.parent
    version = common.schema_version(sb)
    theme = common.load_theme(demo_dir)
    full_w, full_h = common.frame_size(sb)
    w, h = (DRAFT_WIDTH, int(round(DRAFT_WIDTH * full_h / full_w / 2) * 2)) if args.draft else (full_w, full_h)
    scenes_dir = demo_dir / "scenes" / "draft" if args.draft else demo_dir / "scenes"
    build_dir = scenes_dir / ".build"
    build_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = demo_dir / "config.json"
    cfg = common.load_json(cfg_path) if cfg_path.exists() else {}
    reset_cmd = ((cfg.get("app") or {}).get("resetCommand") or "").strip() or None

    prelude = PRELUDE.read_text(encoding="utf-8")
    pp_path = demo_dir / "prelude.js"
    project_prelude = pp_path.read_text(encoding="utf-8") if pp_path.exists() else ""
    acc_path = demo_dir / ".accounts.json"
    accounts = common.load_json(acc_path) if acc_path.exists() else {}
    base = common.base_url(sb, demo_dir)

    scenes = list(sb.get("scenes") or [])
    generated = {}
    if version >= 2:
        if (sb.get("intro") or {}).get("source") == "html":
            page = card_html_path("intro", sb["intro"], demo_dir, build_dir, theme)
            scenes.insert(0, {"id": "00-intro", "kind": "intro", "steps": [], "card": sb["intro"],
                              "holdMs": sb["intro"].get("holdMs", 2500)})
            generated["00-intro"] = card_body("intro", sb["intro"], page)
        if (sb.get("outro") or {}).get("source") == "html":
            page = card_html_path("outro", sb["outro"], demo_dir, build_dir, theme)
            scenes.append({"id": "99-outro", "kind": "outro", "steps": [], "card": sb["outro"],
                           "holdMs": sb["outro"].get("holdMs", 3000)})
            generated["99-outro"] = card_body("outro", sb["outro"], page)
        for sc in sb.get("scenes") or []:
            generated[sc["id"]] = bodygen.scene_body(sc)
    by_id = {s["id"]: s for s in scenes}
    wanted = args.ids or [s["id"] for s in scenes]
    unknown = [i for i in wanted if i not in by_id]
    if unknown:
        common.die("not in storyboard: " + ", ".join(unknown))

    # Bodies: generated unless a hand-written one (no marker) exists.
    bodies, missing, stale = {}, [], []
    body_dir = demo_dir / "scenes"
    for sid in wanted:
        p = body_dir / f"{sid}.body.js"
        existing = p.read_text(encoding="utf-8") if p.exists() else None
        if sid in generated and (existing is None or bodygen.is_generated(existing)):
            if existing != generated[sid]:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(generated[sid], encoding="utf-8")
            bodies[sid] = generated[sid]
        elif existing is None:
            missing.append(common.rel(p, project))
        else:
            # Hand-written: it must have been written for the scene as it is now.
            if version >= 2 and sid in by_id and by_id[sid].get("steps"):
                now, was = bodygen.scene_hash(by_id[sid]), bodygen.body_scene_mark(existing)
                if was is None:
                    print(f"warning: {sid}: hand-written body has no @scene marker - add `{bodygen.SCENE_MARK}{now}` "
                          f"after checking it matches the storyboard", file=sys.stderr)
                elif was != now:
                    stale.append(f"{sid}: storyboard scene changed since the body was written (@scene {was}, now {now}) - "
                                 f"update the body or regenerate it with `dv.py body {sid} --hand`, then set the marker")
            bodies[sid] = existing
    if missing:
        common.die("scene bodies not written yet:\n  " + "\n  ".join(missing))
    if stale:
        common.die("hand-written bodies out of date:\n  " + "\n  ".join(stale))

    jobs, cached = [], []
    for sid in wanted:
        scene = by_id[sid]
        key = cache_key(scene, bodies[sid], prelude, project_prelude, theme, w, h, version)
        webm = scenes_dir / f"{sid}.webm"
        hash_path = build_dir / f"{sid}.hash"
        timing = scenes_dir / f"{sid}.timing.json"
        if not args.force and webm.exists() and timing.exists() and hash_path.exists() \
                and hash_path.read_text(encoding="utf-8").strip() == key:
            cached.append(sid)
            continue
        script = build_script(scene, bodies[sid], prelude=prelude, project_prelude=project_prelude, base=base,
                              accounts=accounts, w=w, h=h, rel_webm=common.rel(webm, project), theme=theme, version=version)
        script_path = build_dir / f"{sid}.js"
        script_path.write_text(script, encoding="utf-8")
        planned = scene.get("dwellMs") or scene.get("durationMs") or scene.get("holdMs")
        jobs.append(Job(sid, scene, script_path, webm, timing, hash_path, key, planned))

    if jobs:
        chk = subprocess.run(["node", "--check", *(str(j.script_path) for j in jobs)], capture_output=True, text=True)
        if chk.returncode != 0:
            common.die("assembled script has a syntax error - fix the scene body:\n" + chk.stderr.strip())
    for sid in cached:
        print(f"  {sid:<20} cached")
    if args.dry_run:
        for j in jobs:
            print(f"{j.sid}: {j.script_path}")
        return 0
    if not jobs:
        print(f"{len(cached)} scene(s) up to date in {common.rel(scenes_dir, project)}")
        return 0

    auth = sb.get("authState") or (sb.get("meta") or {}).get("authState")
    lines, failed = {}, []

    # FR-055: scenes before the first `mutates` one may run in parallel; from the
    # first mutating scene on, order matters and everything runs in one session.
    first_mut = next((i for i, j in enumerate(jobs) if j.scene.get("mutates")), len(jobs))
    parallel, sequential = jobs[:first_mut], jobs[first_mut:]
    n = max(1, min(args.jobs, len(parallel))) if parallel else 1

    if n == 1:
        session = None
        open_session(session, project, args.headed, auth)
        for j in jobs:
            ok, line = record(j, session, project, reset_cmd)
            lines[j.sid] = line
            if not ok:
                failed.append(j.sid)
        if args.close:
            close_session(session, project)
    else:
        buckets = [parallel[i::n] for i in range(n)]

        def worker(idx, bucket):
            session = f"dv-{idx + 1}"
            open_session(session, project, args.headed, auth)
            out = []
            try:
                for j in bucket:
                    out.append((j.sid,) + record(j, session, project, reset_cmd))
            finally:
                close_session(session, project)
            return out

        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            for res in ex.map(lambda ib: worker(*ib), enumerate(buckets)):
                for sid, ok, line in res:
                    lines[sid] = line
                    if not ok:
                        failed.append(sid)
        if sequential:
            session = "dv-seq"
            open_session(session, project, args.headed, auth)
            try:
                for j in sequential:
                    ok, line = record(j, session, project, reset_cmd)
                    lines[j.sid] = line
                    if not ok:
                        failed.append(j.sid)
            finally:
                close_session(session, project)

    for j in jobs:
        print(lines.get(j.sid, f"  {j.sid:<20} ?"), file=sys.stderr if j.sid in failed else sys.stdout)
    if failed:
        common.die("scenes failed: " + ", ".join(failed))
    print(f"{len(jobs)} scene(s) rendered, {len(cached)} cached, into {common.rel(scenes_dir, project)}"
          + (f" ({w}x{h} draft)" if args.draft else ""))
    return 0
