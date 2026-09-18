"""dv.py styles - show subtitle and highlight style presets on a real frame, then apply the chosen ones.

    dv.py styles                                  # gallery -> demo/styles.png (+ styles.html) from demo/shots/<first scene>.png
    dv.py styles --shot demo/shots/13-sheet.png --target ".sheet-gp >> nth=0" --text "자막 예시 문장"
    dv.py styles --apply subtitle=solid,highlight=frame     # writes demo/theme.json; later renders use it
    dv.py styles --list

Presets live in assets/styles/presets.json. The gallery is drawn with the same
CSS the prelude uses, so what the user approves is what the video gets. A
project theme (demo/theme.json) overrides the bundled theme and the user theme.
"""
import argparse
import base64
import html
import json
import subprocess
from pathlib import Path

from . import common

PRESETS = common.ASSETS_DIR / "styles" / "presets.json"


def load_presets():
    return common.load_json(PRESETS)


def subtitle_css(sub, w, h):
    font = round(h * sub["fontSizeRatio"])
    bl = sub.get("borderLeft", "none")
    return (f"position:absolute;left:50%;bottom:{round(h * sub['bottomRatio'])}px;transform:translateX(-50%);"
            f"max-width:{round(sub['maxWidthRatio'] * 100)}%;padding:{round(font * 0.35)}px {round(font * 0.7)}px;"
            f"background:{sub['background']};border-radius:{sub['radius']}px;box-shadow:{sub.get('shadow', 'none')};"
            f"border:{sub.get('border', 'none')};border-left:{bl if bl != 'none' else sub.get('border', 'none')};"
            f"color:{sub['color']};font-family:{sub['fontFamily']};font-size:{font}px;font-weight:{sub.get('fontWeight', 600)};"
            f"line-height:1.25;text-shadow:{sub.get('textShadow', 'none')};text-align:center;letter-spacing:{sub.get('letterSpacing', '-.2px')};"
            f"white-space:nowrap;")


def highlight_html(hl, box, pad=4):
    x, y, w, h = box["x"] - pad, box["y"] - pad, box["width"] + pad * 2, box["height"] + pad * 2
    dim = hl.get("dim", "transparent")
    glow = f", {hl['glow']}" if hl.get("glow") and hl["glow"] != "none" else ""
    if hl.get("corners"):
        L, bw, c = max(14, round(min(w, h) * 0.18)), hl["borderPx"], hl["color"]
        def corner(l, t, bt, br):
            return (f"<div style='position:absolute;left:{l}px;top:{t}px;width:{L}px;height:{L}px;"
                    f"border-top:{bw if bt else 0}px solid {c};border-bottom:{0 if bt else bw}px solid {c};"
                    f"border-left:{0 if br else bw}px solid {c};border-right:{bw if br else 0}px solid {c};'></div>")
        return (f"<div style='position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;box-shadow:0 0 0 9999px {dim}{glow};'></div>"
                + corner(x, y, True, False) + corner(x + w - L, y, True, True) + corner(x, y + h - L, False, False) + corner(x + w - L, y + h - L, False, True))
    return (f"<div style='position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;border-radius:{hl.get('radius', 8)}px;"
            f"border:{hl['borderPx']}px {hl.get('style', 'solid')} {hl['color']};box-shadow:0 0 0 9999px {dim}{glow};'></div>")


def build_gallery(theme, presets, shot: Path, box, text, emphasis, w, h, compact=False):
    data = "data:image/png;base64," + base64.b64encode(shot.read_bytes()).decode()
    cards = []
    esc = html.escape
    for kind, title in (("subtitle", "자막 스타일"), ("highlight", "강조 박스 스타일")):
        cards.append(f"<h2>{title}</h2><div class='grid'>")
        items = dict(presets[kind])
        if theme.get("presets", {}).get("custom") or theme.get("presets", {}).get(kind):
            items = {"current": {"label": "현재 프로젝트 설정", "desc": "demo/theme.json", "theme": {}}, **items}
        for key, pr in items.items():
            t = json.loads(json.dumps(theme))
            t[kind].update(pr["theme"])
            inner = esc(text)
            if emphasis and emphasis in text:
                inner = inner.replace(esc(emphasis), f"<span style='color:{t['subtitle']['emphasisColor']}'>{esc(emphasis)}</span>")
            if kind == "subtitle":
                overlay = f"<div style=\"{subtitle_css(t['subtitle'], w, h)}\">{inner}</div>"
            else:
                overlay = highlight_html(t["highlight"], box) + f"<div style=\"{subtitle_css(t['subtitle'], w, h)}\">{inner}</div>"
            frame = (f"<div class='frame' style='width:{w}px;height:{h}px;background:url({data}) 0 0/100% 100% no-repeat;'>{overlay}</div>")
            if compact:
                # Show only the band that matters: the subtitle band, or the area around the highlight box.
                band = 360
                top = (h - band - 40) if kind == "subtitle" else max(0, min(h - band, box["y"] - 90))
                frame = f"<div class='clip' style='width:{w}px;height:{band}px;'><div style='transform:translateY(-{top}px)'>{frame}</div></div>"
            cards.append(f"<figure>{frame}<figcaption><b>{esc(key)}</b> · {esc(pr['label'])}<br><small>{esc(pr['desc'])}</small></figcaption></figure>")
        cards.append("</div>")
    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>styles</title><style>"
            "body{margin:0;padding:24px;background:#e2e8f0;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;color:#0f172a}"
            "h2{font-size:22px;margin:8px 0 12px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;margin-bottom:28px}"
            "figure{margin:0;background:#fff;border-radius:10px;padding:10px;box-shadow:0 2px 8px rgba(0,0,0,.08)}"
            ".frame{position:relative;overflow:hidden;transform-origin:0 0;border-radius:6px}.clip{overflow:hidden;border-radius:6px}"
            "figcaption{padding:10px 4px 2px;font-size:15px}figcaption small{color:#475569}"
            "</style></head><body>" + "".join(cards) + "</body></html>")


def screenshot(html_path: Path, png_path: Path, project: Path, width):
    js = html_path.with_suffix(".shot.js")
    js.write_text(f"""async page => {{
  await page.setViewportSize({{ width: {width}, height: 1200 }});
  await page.goto({json.dumps(html_path.resolve().as_uri())});
  await page.waitForTimeout(300);
  await page.screenshot({{ path: {json.dumps(str(png_path))}, fullPage: true }});
  return 'ok';
}}
""", encoding="utf-8")
    subprocess.run(["playwright-cli", "-s=dv-styles", "open"], cwd=str(project), capture_output=True, text=True)
    r = subprocess.run(["playwright-cli", "-s=dv-styles", "run-code", "--filename", common.rel(js, project), "--raw"],
                       cwd=str(project), capture_output=True, text=True)
    subprocess.run(["playwright-cli", "-s=dv-styles", "close"], cwd=str(project), capture_output=True, text=True)
    js.unlink(missing_ok=True)
    return r.returncode == 0 and png_path.exists()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py styles", description=__doc__.splitlines()[0])
    ap.add_argument("--demo", default="demo")
    ap.add_argument("--shot", default=None, help="frame to draw on; default the first scene's shot")
    ap.add_argument("--target", default=None, help="selector whose box (from shots/<scene>.boxes.json) gets the highlight")
    ap.add_argument("--text", default="케이스를 질의 패널로 끌어 놓으면 참조로 잡힙니다")
    ap.add_argument("--emphasis", default="끌어 놓으면")
    ap.add_argument("--apply", default=None, help="subtitle=<preset>,highlight=<preset>")
    ap.add_argument("--set", default=None, help="custom values, e.g. subtitle.color=#fff,subtitle.fontSizeRatio=0.04,highlight.color=#e8542b")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-shot", action="store_true", help="write styles.html only")
    ap.add_argument("--compact", action="store_true", help="only the subtitle band / the area around the box")
    args = ap.parse_args(argv)

    demo_dir = Path(args.demo).resolve()
    project = demo_dir.parent
    presets = load_presets()
    if args.list:
        for kind in ("subtitle", "highlight"):
            print(kind)
            for k, v in presets[kind].items():
                print(f"  {k:<10} {v['label']:<16} {v['desc']}")
        return 0

    if args.set:
        tp = demo_dir / "theme.json"
        project_theme = common.load_json(tp) if tp.exists() else {}
        bundled = common.load_json(common.ASSETS_DIR / "theme.json")
        for part in args.set.split(","):
            key, _, value = part.strip().partition("=")
            section, _, name = key.partition(".")
            if section not in ("subtitle", "highlight", "zoom", "cursor", "click", "transition") or not name:
                common.die(f"'{key}': use <subtitle|highlight|zoom|cursor|click|transition>.<key>=<value>")
            if name not in bundled.get(section, {}):
                common.die(f"'{key}': unknown key. Known: {', '.join(bundled[section])}")
            ref = bundled[section][name]
            try:
                cast = (float(value) if isinstance(ref, float) else int(value) if isinstance(ref, int) and not isinstance(ref, bool)
                        else value.lower() == "true" if isinstance(ref, bool) else value)
            except ValueError:
                common.die(f"'{key}': expected a {type(ref).__name__}")
            project_theme.setdefault(section, {})[name] = cast
        project_theme.setdefault("presets", {})["custom"] = True
        common.dump_json(tp, project_theme)
        print(f"wrote {common.rel(tp, project)} - re-run `dv.py styles` to preview, render re-records every scene")
        return 0

    if args.apply:
        chosen = {}
        for part in args.apply.split(","):
            kind, _, name = part.strip().partition("=")
            if kind not in presets or name not in presets[kind]:
                common.die(f"unknown preset '{part}'. Try: dv.py styles --list")
            chosen[kind] = name
        tp = demo_dir / "theme.json"
        project_theme = common.load_json(tp) if tp.exists() else {}
        for kind, name in chosen.items():
            project_theme.setdefault(kind, {}).update(presets[kind][name]["theme"])
            project_theme.setdefault("presets", {})[kind] = name
        common.dump_json(tp, project_theme)
        print(f"wrote {common.rel(tp, project)}: " + ", ".join(f"{k}={v}" for k, v in chosen.items())
              + "\nnext: dv.py render (changed theme re-records every scene) -> compose -> verify")
        return 0

    theme = common.load_theme(demo_dir)
    sb_path = demo_dir / "storyboard.json"
    sb = common.load_json(sb_path) if sb_path.exists() else {}
    w, h = common.frame_size(sb) if sb else (1920, 1080)
    shots = demo_dir / "shots"
    if args.shot:
        shot = Path(args.shot).resolve()
    else:
        first = (sb.get("scenes") or [{}])[0].get("id")
        shot = shots / f"{first}.png" if first else None
        if not shot or not shot.exists():
            cands = sorted(shots.glob("*.png")) if shots.exists() else []
            shot = cands[0] if cands else None
    if not shot or not shot.exists():
        common.die("no screenshot to draw on - run dv.py sheet --capture first or pass --shot")
    boxes_p = shot.with_name(shot.stem + ".boxes.json")
    boxes = common.load_json(boxes_p) if boxes_p.exists() else {}
    box = None
    if args.target and boxes.get(args.target):
        box = boxes[args.target]
    elif boxes:
        box = next((b for b in boxes.values() if b), None)
    if not box:
        box = {"x": w * 0.3, "y": h * 0.3, "width": w * 0.4, "height": h * 0.2}

    out_html = demo_dir / ("styles-compact.html" if args.compact else "styles.html")
    out_html.write_text(build_gallery(theme, presets, shot, box, args.text, args.emphasis, w, h, compact=args.compact), encoding="utf-8")
    print(f"wrote {common.rel(out_html, project)} (frame {shot.name}, box {args.target or 'first target'})")
    if not args.no_shot:
        png = demo_dir / ("styles-compact.png" if args.compact else "styles.png")
        if screenshot(out_html, png, project, width=min(2 * w + 100, 3000)):
            print(f"wrote {common.rel(png, project)} - show it and ask which subtitle and highlight preset to use, then: "
                  f"dv.py styles --apply subtitle=<name>,highlight=<name>")
        else:
            print("screenshot failed; open styles.html in a browser instead")
    return 0
