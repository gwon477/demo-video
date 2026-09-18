"""dv.py body <scene> [--hand] - write a scene's body from the storyboard.

    dv.py body 02-add-project --hand     # take the scene over: no @generated marker, @scene hash marker, edit freely
    dv.py body 02-add-project            # back to generated (the file is regenerated on every render)
    dv.py body 02-add-project --mark     # refresh the @scene marker after you reconciled a hand-written body

Hand-write a body only for logic the action list cannot express (a stubbed
native dialog, a login routine). Keep the statements the generator emitted for
the subtitles so check-sync still matches, and put setup above `// ---record---`.
"""
import argparse
from pathlib import Path

from . import bodygen, common


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py body", description=__doc__.splitlines()[0])
    ap.add_argument("scene")
    ap.add_argument("--storyboard", default=None)
    ap.add_argument("--hand", action="store_true")
    ap.add_argument("--mark", action="store_true", help="only update the @scene marker of an existing hand-written body")
    args = ap.parse_args(argv)
    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    scene = next((s for s in sb.get("scenes") or [] if s["id"] == args.scene), None)
    if not scene:
        common.die(f"no scene {args.scene} in the storyboard")
    out = sb_path.parent / "scenes" / f"{args.scene}.body.js"
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.mark:
        if not out.exists():
            common.die(f"{out} does not exist")
        text = out.read_text(encoding="utf-8")
        now = bodygen.scene_hash(scene)
        lines = [l for l in text.splitlines() if not l.startswith(bodygen.SCENE_MARK.strip())]
        out.write_text("\n".join([bodygen.SCENE_MARK + now] + lines) + "\n", encoding="utf-8")
        print(f"{common.rel(out, sb_path.parent.parent)}: @scene {now}")
        return 0
    if args.hand:
        if out.exists() and not bodygen.is_generated(out.read_text(encoding="utf-8")):
            common.die(f"{out.name} is already hand-written - edit it, or delete it first")
        out.write_text(bodygen.hand_body(scene), encoding="utf-8")
        print(f"wrote {common.rel(out, sb_path.parent.parent)} (hand-written, @scene {bodygen.scene_hash(scene)})")
    else:
        out.write_text(bodygen.scene_body(scene), encoding="utf-8")
        print(f"wrote {common.rel(out, sb_path.parent.parent)} (generated)")
    return 0
