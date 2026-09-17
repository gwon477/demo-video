"""Approval state: demo/state.json and the hash gate.

`dv.py approve <stage>` records the sha256 of the stage's file. Downstream
commands call `require(demo_dir, stage)` and stop with exit 1 when the file
was never approved or changed since - the rule "edit after approval means
approve again", enforced in code rather than in a prompt.

The hash of storyboard.json is taken over a canonical form that drops the
fields machines fill in after approval (`holdMs`, `dwellMs`, and a step's
`narration` markup written back by `dv.py narrate`). Without that, phase 3.5
would invalidate the G3 approval it depends on.
"""
import datetime as _dt
import hashlib
import json
from pathlib import Path

from . import common

STAGES = {
    "survey": "survey.json",
    "scenario": "scenario.md",
    "storyboard": "storyboard.json",
    "final": None,  # output/<name>.mp4, resolved from the storyboard
}
GATE_NAMES = {"survey": "G1", "scenario": "G2", "storyboard": "G3", "final": "G4"}
MACHINE_FIELDS = {"holdMs", "dwellMs"}


def state_path(demo_dir: Path) -> Path:
    return Path(demo_dir) / "state.json"


def load(demo_dir: Path) -> dict:
    p = state_path(demo_dir)
    if not p.exists():
        return {"schemaVersion": 1, "approvals": {}}
    return common.load_json(p)


def save(demo_dir: Path, state: dict):
    common.dump_json(state_path(demo_dir), state)


def stage_file(demo_dir: Path, stage: str) -> Path:
    demo_dir = Path(demo_dir)
    if stage not in STAGES:
        common.die(f"unknown stage '{stage}'; expected one of {', '.join(STAGES)}")
    if stage == "final":
        sb_path = demo_dir / "storyboard.json"
        name = "demo"
        if sb_path.exists():
            sb = common.load_json(sb_path)
            name = (sb.get("meta") or {}).get("name") or sb.get("name") or "demo"
        return demo_dir / "output" / f"{name}.mp4"
    return demo_dir / STAGES[stage]


def _strip_machine_fields(node):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in MACHINE_FIELDS:
                continue
            if k == "narration" and isinstance(v, str):
                continue
            out[k] = _strip_machine_fields(v)
        return out
    if isinstance(node, list):
        return [_strip_machine_fields(v) for v in node]
    return node


def file_hash(path: Path) -> str:
    path = Path(path)
    if path.suffix == ".json":
        try:
            data = common.load_json(path)
        except ValueError:
            data = None
        if data is not None:
            canon = json.dumps(_strip_machine_fields(data), sort_keys=True,
                               ensure_ascii=False, separators=(",", ":"))
            return hashlib.sha256(canon.encode("utf-8")).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def approve(demo_dir: Path, stage: str, note: str = "") -> dict:
    path = stage_file(demo_dir, stage)
    if not path.exists():
        common.die(f"nothing to approve: {common.rel(path, Path(demo_dir).parent)} does not exist")
    state = load(demo_dir)
    entry = {
        "file": common.rel(path, demo_dir),
        "sha256": file_hash(path),
        "at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if note:
        entry["note"] = note
    state.setdefault("approvals", {})[stage] = entry
    save(demo_dir, state)
    return entry


def check(demo_dir: Path, stage: str) -> tuple[str, str]:
    """Return (status, detail): status is 'approved', 'stale', or 'missing'."""
    state = load(demo_dir)
    entry = (state.get("approvals") or {}).get(stage)
    path = stage_file(demo_dir, stage)
    if not entry:
        return "missing", f"{stage} was never approved"
    if not path.exists():
        return "stale", f"{entry['file']} no longer exists"
    if file_hash(path) != entry["sha256"]:
        return "stale", f"{entry['file']} changed since approval at {entry['at']}"
    return "approved", f"approved at {entry['at']}"


def require(demo_dir: Path, stage: str):
    status, detail = check(demo_dir, stage)
    if status != "approved":
        gate = GATE_NAMES[stage]
        common.die(f"{gate} not passed: {detail}. Show the {stage} to the user, "
                   f"then run: dv.py approve {stage}")
