#!/usr/bin/env python3
"""dv.py - single entry point for the demo-video skill.

    python3 <skill>/scripts/dv.py <command> [args]

Run every command from the target project's root; it reads and writes `demo/`.
Standard library only, Python 3.10+.

Commands (M0 set; more land per DESIGN.md section 7):
  render       assemble scene bodies with the prelude and record .webm clips
  check-sync   verify storyboard, bodies, narration and recorded cues agree
  compose      join clips with xfade transitions into an mp4 (+ .srt, narration)
  narrate      generate narration audio and widen subtitle holds to fit it
  version      print the skill version
"""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

COMMANDS = {
    "render": "lib.render",
    "check-sync": "lib.checksync",
    "compose": "lib.compose",
    "narrate": "lib.narrate",
}


def usage(code=2):
    print(__doc__.strip(), file=sys.stderr)
    sys.exit(code)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        usage(0)
    cmd, rest = argv[0], argv[1:]
    if cmd == "version":
        from lib import common
        print(common.skill_version())
        return 0
    if cmd not in COMMANDS:
        print(f"error: unknown command '{cmd}'", file=sys.stderr)
        usage()
    if sys.version_info < (3, 10):
        print(f"error: Python 3.10+ required, found {sys.version.split()[0]}", file=sys.stderr)
        return 1
    mod = importlib.import_module(COMMANDS[cmd])
    return mod.main(rest) or 0


if __name__ == "__main__":
    sys.exit(main())
