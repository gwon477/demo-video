"""dv.py status - where this demo stands and what to do next.

    dv.py status [--demo demo] [--json]

Reads state.json and the files under demo/ and prints, per gate, whether it is
approved, stale (file changed after approval) or missing, then the next
command. For an agent picking up after a broken session.
"""
import argparse
import json
from pathlib import Path

from . import common, state

ORDER = ["survey", "scenario", "storyboard", "final"]
NEXT = {
    "survey": "write demo/survey.json (phase 1), show the core features, then: dv.py approve survey",
    "scenario": "write demo/scenario.md (phase 2), show the outline, then: dv.py approve scenario",
    "storyboard": "write demo/storyboard.json (phase 3), validate, show the sheet, then: dv.py approve storyboard",
    "final": "dv.py render -> dv.py check-sync -> dv.py compose -> verify, show the video, then: dv.py approve final",
}


def collect(demo_dir: Path):
    rows = []
    for stage in ORDER:
        path = state.stage_file(demo_dir, stage)
        st, detail = state.check(demo_dir, stage)
        rows.append({"stage": stage, "gate": state.GATE_NAMES[stage], "file": common.rel(path, demo_dir),
                     "exists": path.exists(), "status": st, "detail": detail})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py status", description=__doc__.splitlines()[0])
    ap.add_argument("--demo", default="demo")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    demo_dir = Path(args.demo).resolve()
    if not demo_dir.exists():
        common.die(f"no demo folder at {demo_dir} - run dv.py init first")
    cfg_path = demo_dir / "config.json"
    cfg = common.load_json(cfg_path) if cfg_path.exists() else None
    rows = collect(demo_dir)
    scenes_dir = demo_dir / "scenes"
    bodies = sorted(p.name for p in scenes_dir.glob("*.body.js")) if scenes_dir.exists() else []
    clips = sorted(p.name for p in scenes_dir.glob("*.webm")) if scenes_dir.exists() else []

    pending = next((r for r in rows if r["status"] != "approved"), None)
    next_step = NEXT[pending["stage"]] if pending else "done - all four gates approved"
    if pending and pending["status"] == "stale":
        next_step = (f"{pending['file']} changed after approval - show it again, then: "
                     f"dv.py approve {pending['stage']}")

    if args.json:
        print(json.dumps({"config": bool(cfg), "gates": rows, "bodies": len(bodies), "clips": len(clips),
                          "next": next_step}, ensure_ascii=False, indent=2))
        return 0

    print(f"demo: {demo_dir}")
    print(f"config: {'present' if cfg else 'missing - run dv.py init'}"
          + (f"  app {cfg['app']['url']}  {cfg['video']['size'][0]}x{cfg['video']['size'][1]}" if cfg else ""))
    for r in rows:
        mark = {"approved": "OK  ", "stale": "STALE", "missing": "--  "}[r["status"]]
        exists = "" if r["exists"] else "  (file missing)"
        print(f"  {r['gate']} {mark:<5} {r['stage']:<11} {r['file']}{exists}  {r['detail']}")
    print(f"scenes: {len(bodies)} bodies, {len(clips)} clips")
    print(f"next: {next_step}")
    return 0
