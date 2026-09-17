"""dv.py validate [--fix] - enforce the storyboard schema and the quality rules.

    dv.py validate                 # exit 1 on any rule violation, warnings on stderr
    dv.py validate --fix           # fill holdMs / dwellMs from the formulas, then validate
    dv.py validate --json          # machine-readable findings

Rules live here, not in prompts (DESIGN.md 2절). Each numbered rule has a
pass/fail fixture under tests/. Values come from assets/theme.json.

  schema      schemaVersion 2, required fields, fixed action list
  FR-011/012  one line, weighted 32 chars, width fits 86% of the frame
  FR-013      holdMs = clamp(chars*125+600, 1500, 7000); --fix fills it
  FR-020~022  zoom scale range, one zoom per step, zoomOut before the scene ends,
              no zoom on low-density pages (survey.json)
  FR-032      secret fields only take ACCOUNTS.* references
  FR-043~045  transition types and length, intro/outro/hook, total length vs config targetSec (warning only)
  FR-060~065  interactions[] evidence, decisions, show -> matching action
  locators    every action target must appear in survey.json (warning without survey)
  dwell       dwellMs >= holds + actions; --fix fills it; scene cap 9s
"""
import argparse
import json
import re
import sys
from pathlib import Path

from . import common

ACTION_TYPES = ["goto", "click", "type", "hover", "scroll", "waitFor", "zoom", "zoomOut", "highlight", "chapter",
                "drag", "dropFile", "resize", "slide", "pan", "wheelZoom", "key", "dblclick", "rightClick", "waitStream"]
INTERACTION_KINDS = ["drag", "dropFile", "scroll", "hover", "resize", "slide", "pan", "wheelZoom", "key",
                     "dblclick", "rightClick", "waitStream"]
TARGET_ACTIONS = {"click", "type", "hover", "zoom", "highlight", "dropFile", "resize", "slide", "pan", "wheelZoom",
                  "dblclick", "rightClick", "waitStream"}
HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]")


def weighted_chars(text: str) -> float:
    return sum(1.0 if HANGUL.match(ch) else 0.5 for ch in str(text))


def hold_ms(text: str, theme: dict) -> int:
    s = theme["subtitle"]
    return int(max(s["minMs"], min(s["maxMs"], round(weighted_chars(text) * s["msPerChar"] + s["baseMs"]))))


def dwell_from_density(density, theme):
    reading = (min(int(density.get("textChars", 0)), 1800) / 1800) * 4000
    scanning = min(int(density.get("interactive", 0)), 15) * 200
    return int(max(theme["scene"]["minMs"], min(theme["scene"]["maxMs"], round(2000 + reading + scanning))))


class Findings:
    def __init__(self):
        self.errors, self.warnings, self.blocked, self.fixes = [], [], [], []

    def err(self, rule, where, msg):
        self.errors.append({"rule": rule, "where": where, "msg": msg})

    def warn(self, rule, where, msg):
        self.warnings.append({"rule": rule, "where": where, "msg": msg})


def load_survey(demo_dir: Path):
    p = demo_dir / "survey.json"
    if not p.exists():
        return None
    try:
        return common.load_json(p)
    except ValueError:
        return None


def survey_index(survey):
    """(set of locator strings, {page id: density}) from survey.json."""
    locators, density = set(), {}
    for page in (survey or {}).get("pages") or []:
        for v in (page.get("locators") or {}).values():
            if isinstance(v, str):
                locators.add(v)
        if page.get("id"):
            density[page["id"]] = page.get("density") or {}
        if page.get("route"):
            density[page["route"]] = page.get("density") or {}
    return locators, density


def check_schema(sb, f):
    v = common.schema_version(sb)
    if v != 2:
        f.err("schema", "storyboard", f"schemaVersion {v} is not supported by validate. Migrate to schemaVersion 2 "
                                      f"(references/storyboard.md): meta{{name,size}}, intro/outro objects, "
                                      f"scenes[].steps[].subtitle + actions, transitionIn, interactions[]")
        return False
    meta = sb.get("meta") or {}
    if not meta.get("name"):
        f.err("schema", "meta", "meta.name is required")
    size = meta.get("size")
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(x, int) and x > 0 and x % 2 == 0 for x in size)):
        f.err("schema", "meta", "meta.size must be [width, height] with even integers")
    for k in ("intro", "outro"):
        o = sb.get(k)
        if not isinstance(o, dict):
            f.err("schema", k, f"{k} object is required (source html | video)")
            continue
        if o.get("source") not in ("html", "video"):
            f.err("schema", k, f"{k}.source must be 'html' or 'video'")
        elif o["source"] == "video" and not o.get("path"):
            f.err("schema", k, f"{k}.path is required for source video")
        elif o["source"] == "html" and not o.get("title"):
            f.err("schema", k, f"{k}.title is required for source html")
    scenes = sb.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        f.err("schema", "scenes", "scenes[] must have at least one scene")
        return False
    seen = set()
    for i, sc in enumerate(scenes):
        where = sc.get("id") or f"scenes[{i}]"
        if not sc.get("id") or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", sc["id"]):
            f.err("schema", where, "scene id is required: letters, digits, - and _")
        elif sc["id"] in seen:
            f.err("schema", where, "duplicate scene id")
        seen.add(sc.get("id"))
        if not sc.get("url"):
            f.err("schema", where, "scene.url is required")
        steps = sc.get("steps")
        if not isinstance(steps, list) or not steps:
            f.err("schema", where, "scene.steps[] must have at least one step")
            continue
        for j, st in enumerate(steps):
            sw = f"{where}.steps[{j}]"
            sub = st.get("subtitle")
            if not isinstance(sub, dict) or not isinstance(sub.get("text"), str) or not sub["text"].strip():
                f.err("schema", sw, "step.subtitle.text is required")
            for k, a in enumerate(st.get("actions") or []):
                aw = f"{sw}.actions[{k}]"
                t = a.get("type")
                if t not in ACTION_TYPES:
                    f.err("schema", aw, f"unknown action type '{t}'. Allowed: {', '.join(ACTION_TYPES)}")
                    continue
                if t in TARGET_ACTIONS and not a.get("target"):
                    f.err("schema", aw, f"{t} needs a target selector")
                if t == "drag" and not (a.get("source") and a.get("target")):
                    f.err("schema", aw, "drag needs source and target")
                if t == "drag" and a.get("mode") not in ("pointer", "html5"):
                    f.err("schema", aw, "drag.mode must be 'pointer' or 'html5' (from the source signal)")
                if t == "type" and not isinstance(a.get("value"), str):
                    f.err("schema", aw, "type needs a string value")
                if t == "scroll" and not a.get("target"):
                    f.err("schema", aw, "scroll needs a target selector or 'window'")
                if t == "goto" and not a.get("url"):
                    f.err("schema", aw, "goto needs url")
                if t == "key" and not a.get("combo"):
                    f.err("schema", aw, "key needs combo, e.g. Meta+k")
                if t == "dropFile" and not a.get("files"):
                    f.err("schema", aw, "dropFile needs files[]")
                if t == "waitFor" and not (a.get("target") or a.get("url")):
                    f.err("schema", aw, "waitFor needs target or url")
        for k, it in enumerate(sc.get("interactions") or []):
            iw = f"{where}.interactions[{k}]"
            if it.get("kind") not in INTERACTION_KINDS:
                f.err("schema", iw, f"interaction kind must be one of {', '.join(INTERACTION_KINDS)}")
            if it.get("decision") not in ("show", "skip", "blocked"):
                f.err("schema", iw, "decision must be show | skip | blocked")
    return not f.errors


def check_subtitles(sb, theme, f, fix):
    s = theme["subtitle"]
    w, h = common.frame_size(sb)
    font_px = round(h * s["fontSizeRatio"])
    if s["maxWeightedChars"] * font_px > s["maxWidthRatio"] * w:
        f.err("FR-012", "meta.size", f"{s['maxWeightedChars']} chars at {font_px}px exceed {int(s['maxWidthRatio'] * 100)}% "
                                     f"of a {w}px frame - use a larger frame or a smaller fontSizeRatio in theme.json")
    hook_seen = False
    for sc in sb["scenes"]:
        for j, st in enumerate(sc["steps"]):
            where = f"{sc['id']}.steps[{j}]"
            text = st["subtitle"]["text"]
            if "\n" in text or "<br" in text.lower():
                f.err("FR-011", where, "subtitle must be one line - split into two steps")
            n = weighted_chars(text)
            if n > s["maxWeightedChars"]:
                f.err("FR-012", where, f"subtitle is {n:g} weighted chars (max {s['maxWeightedChars']}): "
                                       f"split the sentence into two steps, do not shorten or wrap")
            need = hold_ms(text, theme)
            narrated = st.get("narrationMs")
            if narrated:
                need = max(need, int(narrated) + theme["narration"]["padMs"])
            cur = st.get("holdMs")
            if cur is None or (fix and cur < need):
                if fix:
                    st["holdMs"] = need
                    f.fixes.append(f"{where}.holdMs = {need}")
                else:
                    f.err("FR-013", where, f"holdMs missing - run dv.py validate --fix" if cur is None
                          else f"holdMs {cur} is under the reading time {need}")
            elif cur < need:
                f.err("FR-013", where, f"holdMs {cur} is under the reading time {need} (run --fix)")
            elif cur > s["maxMs"]:
                f.err("FR-013", where, f"holdMs {cur} exceeds {s['maxMs']} - split the subtitle into two cues")
            if st["subtitle"].get("hook"):
                hook_seen = True
    first = sb["scenes"][0]["steps"][0]["subtitle"]
    if not first.get("hook"):
        f.err("FR-044", f"{sb['scenes'][0]['id']}.steps[0]", "the first subtitle after the intro must state the viewer's goal or "
                                                            "problem and carry \"hook\": true")
    elif not hook_seen:
        pass


def check_zoom(sb, theme, survey_density, f):
    z = theme["zoom"]
    for sc in sb["scenes"]:
        open_zoom = False
        page_density = survey_density.get(sc.get("page") or "", None) or survey_density.get(sc.get("url") or "", None)
        for j, st in enumerate(sc["steps"]):
            where = f"{sc['id']}.steps[{j}]"
            zooms = [a for a in st.get("actions") or [] if a.get("type") == "zoom"]
            if len(zooms) > 1:
                f.err("FR-021", where, "only one zoom per step")
            for a in zooms:
                scale = a.get("scale", z["default"])
                if not (z["min"] <= float(scale) <= z["max"]):
                    f.err("FR-020", where, f"zoom scale {scale} outside {z['min']}-{z['max']}")
                if open_zoom:
                    f.err("FR-021", where, "zoom while already zoomed - add zoomOut first")
                open_zoom = True
                if page_density is None:
                    f.warn("FR-022", where, "no survey density for this page - cannot check that the screen is dense enough for a zoom")
                elif int(page_density.get("textChars", 0)) < theme["density"]["zoomMinTextChars"]:
                    f.err("FR-022", where, f"page density {page_density.get('textChars')} chars is below "
                                           f"{theme['density']['zoomMinTextChars']}: no zoom on a sparse screen")
                if a.get("coverage") and float(a["coverage"]) >= z["coverageWarn"]:
                    f.warn("FR-020", where, f"target already covers {a['coverage']:.0%} of the frame - zoom adds little")
            for a in st.get("actions") or []:
                if a.get("type") == "zoomOut":
                    if not open_zoom:
                        f.warn("FR-021", where, "zoomOut without a zoom")
                    open_zoom = False
        if open_zoom:
            f.err("FR-021", sc["id"], "scene ends zoomed in - add a zoomOut action before the scene ends")


def check_type_secrets(sb, f):
    for sc in sb["scenes"]:
        for j, st in enumerate(sc["steps"]):
            for k, a in enumerate(st.get("actions") or []):
                if a.get("type") != "type":
                    continue
                where = f"{sc['id']}.steps[{j}].actions[{k}]"
                secret = a.get("secret") or "password" in str(a.get("target", "")).lower()
                if secret and not str(a.get("value", "")).startswith("ACCOUNTS."):
                    f.err("FR-032", where, "a secret field must reference ACCOUNTS.<key>.<field>, never a literal")
                if secret and not a.get("secret"):
                    f.err("FR-032", where, "password field: set \"secret\": true so it is filled without typing")


def check_structure(sb, theme, f):
    t, v = theme["transition"], theme["video"]
    intro, outro = sb["intro"], sb["outro"]
    if intro.get("source") == "html":
        hold = intro.get("holdMs", 2500)
        if hold > v["introMaxMs"]:
            f.err("FR-044", "intro", f"intro holdMs {hold} exceeds {v['introMaxMs']}")
    if outro.get("source") == "html":
        hold = outro.get("holdMs", 3000)
        if not (v["outroMinMs"] <= hold <= v["outroMaxMs"]):
            f.err("FR-044", "outro", f"outro holdMs {hold} outside {v['outroMinMs']}-{v['outroMaxMs']}")
        if not outro.get("cta"):
            f.err("FR-044", "outro", "outro needs a cta line (the next action for the viewer)")
    for i, sc in enumerate(sb["scenes"]):
        tr = sc.get("transitionIn")
        if tr is None:
            continue
        if tr.get("type") not in t["types"]:
            f.err("FR-043", sc["id"], f"transitionIn.type '{tr.get('type')}' not in {', '.join(t['types'])}")
        ms = tr.get("ms", t["defaultMs"])
        if tr.get("type") != "cut" and not (t["minMs"] <= ms <= t["maxMs"]):
            f.err("FR-043", sc["id"], f"transition {ms}ms outside {t['minMs']}-{t['maxMs']}")
        if i > 0 and tr.get("type") != "cut" and sc.get("url") == sb["scenes"][i - 1].get("url"):
            f.warn("FR-043", sc["id"], "same page as the previous scene - a cut usually reads better than a fade")


def check_interactions(sb, theme, f):
    for sc in sb["scenes"]:
        actions = [a for st in sc["steps"] for a in (st.get("actions") or [])]
        shows = 0
        for k, it in enumerate(sc.get("interactions") or []):
            where = f"{sc['id']}.interactions[{k}]"
            ev = it.get("evidence") or {}
            if not (ev.get("source") and ev.get("screen")):
                f.err("FR-060", where, "evidence.source and evidence.screen are both required (one signal is not enough)")
            if not it.get("reason"):
                f.err("FR-061", where, "reason is required for the decision")
            if it.get("decision") == "show":
                shows += 1
                kind, target = it.get("kind"), it.get("target")
                # key has no target on the action side: match by kind alone.
                hit = [a for a in actions if a.get("type") == kind and (
                    kind == "key" or not target or target in (a.get("target"), a.get("source")))]
                if not hit:
                    f.err("FR-062", where, f"decision show but no {kind} action on {target or 'any target'} in this scene's steps")
                if kind == "drag" and it.get("mode") and hit and any(a.get("mode") != it["mode"] for a in hit):
                    f.warn("FR-062", where, "drag mode in interactions differs from the action's mode")
            elif it.get("decision") == "blocked":
                f.blocked.append(f"{sc['id']}: {it.get('kind')} {it.get('target', '')} - {it.get('reason', '')}")
        if shows > theme["scene"]["maxShowInteractions"]:
            f.warn("FR-061", sc["id"], f"{shows} interactions marked show (recommended max {theme['scene']['maxShowInteractions']})")


def check_locators(sb, survey_locators, f, has_survey):
    for sc in sb["scenes"]:
        for j, st in enumerate(sc["steps"]):
            for k, a in enumerate(st.get("actions") or []):
                where = f"{sc['id']}.steps[{j}].actions[{k}]"
                for key in ("target", "source"):
                    sel = a.get(key)
                    if not sel or sel in ("window", "document"):
                        continue
                    if not has_survey:
                        f.warn("locators", where, f"no survey.json - cannot confirm '{sel}' was seen on screen")
                        return
                    if sel not in survey_locators:
                        f.err("locators", where, f"'{sel}' is not in survey.json locators - take locators from the survey, never invent one")


def target_sec(demo_dir: Path):
    cfg = demo_dir / "config.json"
    if not cfg.exists():
        return None
    try:
        return int(((common.load_json(cfg).get("video") or {}).get("targetSec")) or 0) or None
    except (ValueError, TypeError):
        return None


def check_dwell(sb, theme, survey_density, f, fix, demo_dir=None):
    sc_t = theme["scene"]
    total = 0
    prev = None
    for sc in sb["scenes"]:
        holds = sum(int(st.get("holdMs") or 0) for st in sc["steps"])
        n_actions = sum(len(st.get("actions") or []) for st in sc["steps"])
        gaps = theme["subtitle"]["gapMs"] * max(0, len(sc["steps"]) - 1)
        need = holds + n_actions * sc_t["actionMs"] + gaps
        density = survey_density.get(sc.get("page") or "", None) or survey_density.get(sc.get("url") or "", None)
        # The density floor is the time to take a screen in when it first appears. A scene
        # that continues the same page with a cut does not pay it again.
        continues = prev is not None and prev.get("url") == sc.get("url") and (sc.get("transitionIn") or {}).get("type") == "cut"
        floor = dwell_from_density(density, theme) if (density and not continues) else sc_t["minMs"]
        prev = sc
        want = max(need, floor)
        cur = sc.get("dwellMs")
        if fix and (cur is None or cur < want):
            sc["dwellMs"] = want
            f.fixes.append(f"{sc['id']}.dwellMs = {want}")
            cur = want
        if cur is None:
            f.err("dwell", sc["id"], "dwellMs missing - run dv.py validate --fix")
        elif cur < need:
            f.err("dwell", sc["id"], f"dwellMs {cur} is under holds+actions {need} (run --fix)")
        elif cur > sc_t["maxMs"]:
            f.err("dwell", sc["id"], f"dwellMs {cur} exceeds {sc_t['maxMs']} - split into two scenes")
        total += cur or 0
    intro_ms = sb["intro"].get("holdMs", 2500) if sb["intro"].get("source") == "html" else 0
    outro_ms = sb["outro"].get("holdMs", 3000) if sb["outro"].get("source") == "html" else 0
    trans = sum((sc.get("transitionIn") or {}).get("ms", theme["transition"]["defaultMs"])
                for sc in sb["scenes"] if (sc.get("transitionIn") or {}).get("type", "fade") != "cut")
    est = (intro_ms + total + outro_ms - trans) / 1000
    v = theme["video"]
    target = target_sec(demo_dir)
    if target:
        # FR-045: the user's target length is the budget. Off by more than 15% either way is worth a
        # word at G3; it is never an error - the length is the user's call.
        tol = v.get("targetTolerance", 0.15)
        if est > target * (1 + tol):
            f.warn("FR-045", "storyboard", f"estimated {est:.0f}s is over the {target}s target by more than {tol:.0%} - "
                                           f"drop or merge scenes, or confirm the longer cut with the user")
        elif est < target * (1 - tol):
            f.warn("FR-045", "storyboard", f"estimated {est:.0f}s is under the {target}s target by more than {tol:.0%} - "
                                           f"the outline may be missing a feature the user asked for")
    elif est > v["warnSec"]:
        f.warn("FR-045", "storyboard", f"estimated {est:.0f}s exceeds the default {v['warnSec']}s - ask the user for a "
                                       f"target length (dv.py init --target-sec) or propose a split")
    return est


def validate(sb, demo_dir: Path, theme=None, fix=False):
    theme = theme or common.load_theme()
    f = Findings()
    if not check_schema(sb, f):
        return f, 0
    survey = load_survey(demo_dir)
    locators, density = survey_index(survey)
    check_subtitles(sb, theme, f, fix)
    check_zoom(sb, theme, density, f)
    check_type_secrets(sb, f)
    check_structure(sb, theme, f)
    check_interactions(sb, theme, f)
    check_locators(sb, locators, f, survey is not None)
    est = check_dwell(sb, theme, density, f, fix, demo_dir)
    return f, est


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py validate", description=__doc__.splitlines()[0])
    ap.add_argument("--storyboard", default=None)
    ap.add_argument("--fix", action="store_true", help="fill holdMs and dwellMs from the formulas")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    f, est = validate(sb, sb_path.parent, fix=args.fix)
    if args.fix and f.fixes:
        common.dump_json(sb_path, sb)

    if args.json:
        print(json.dumps({"ok": not f.errors, "errors": f.errors, "warnings": f.warnings, "blocked": f.blocked,
                          "fixes": f.fixes, "estimatedSec": est}, ensure_ascii=False, indent=2))
    else:
        for x in f.fixes:
            print(f"fixed: {x}")
        for w in f.warnings:
            print(f"warning [{w['rule']}] {w['where']}: {w['msg']}", file=sys.stderr)
        for b in f.blocked:
            print(f"blocked (tell the user at G3): {b}")
        for e in f.errors:
            print(f"error [{e['rule']}] {e['where']}: {e['msg']}", file=sys.stderr)
        if f.errors:
            print(f"\n{len(f.errors)} rule violation(s)", file=sys.stderr)
        else:
            print(f"valid: {len(sb.get('scenes') or [])} scene(s), about {est:.0f}s"
                  + (f", {len(f.warnings)} warning(s)" if f.warnings else ""))
    return 1 if f.errors else 0
