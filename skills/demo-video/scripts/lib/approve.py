"""dv.py approve <stage> - record the user's approval of a stage's file.

    dv.py approve survey        # G1: survey.json
    dv.py approve scenario      # G2: scenario.md
    dv.py approve storyboard    # G3: storyboard.json
    dv.py approve final         # G4: output/<name>.mp4

Run only after the user has said yes. The sha256 goes into demo/state.json and
every downstream command refuses to run while the file differs from it.
"""
import argparse
from pathlib import Path

from . import state


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py approve", description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=list(state.STAGES))
    ap.add_argument("--demo", default="demo", help="demo folder; default ./demo")
    ap.add_argument("--note", default="", help="what the user said, for the record")
    args = ap.parse_args(argv)

    demo_dir = Path(args.demo).resolve()
    entry = state.approve(demo_dir, args.stage, args.note)
    print(f"{state.GATE_NAMES[args.stage]} {args.stage}: approved {entry['file']} "
          f"({entry['sha256'][:12]}) at {entry['at']}")
    return 0
