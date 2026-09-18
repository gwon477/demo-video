"""dv.py cards - intro/outro card designs from the product's identity, for the user to pick.

    dv.py cards                      # 4 variants -> demo/assets/intro-<v>.html, outro-<v>.html, gallery demo/cards.png
    dv.py cards --apply brand-dark   # storyboard.intro/outro.template -> assets/intro-<v>.html (source html)
    dv.py cards --list

Needs demo/brand.json (dv.py brand probe) and a storyboard with intro/outro
fields (title, tagline, brand, cta). A variant is plain HTML with the same
contract as the bundled template: {{title}} {{tagline}} {{brand}} {{cta}}
placeholders and animations that start when <body class="play"> is set. Edit
a generated file freely - it is the user's design now. If the user has intro/
outro videos, use `dv.py init --intro/--outro` instead of this.
"""
import argparse
import html
import json
import re
import subprocess
from pathlib import Path

from . import common

VARIANTS = {
    "brand-dark": "잉크색 배경에 강조색 글로우, 로고 위·제목 아래. 어두운 무대형",
    "brand-light": "종이색 배경, 로고와 잉크색 제목, 강조색 밑줄. 문서형",
    "accent-block": "강조색 전면 배경, 흰 로고와 제목. 포스터형",
    "split": "왼쪽 강조색 패널에 로고, 오른쪽 종이색에 제목. 분할형",
}


def hex_rgb(c):
    c = (c or "").strip()
    m = re.fullmatch(r"#([0-9a-f]{6})", c.lower())
    if m:
        return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*[\d.]+)?\)", c.lower().replace(" ", ""))
    if m:
        return tuple(int(x) for x in m.groups())
    return (37, 99, 235)


def rgba(c, a):
    r, g, b = hex_rgb(c)
    return f"rgba({r},{g},{b},{a})"


def darken(c, f=0.55):
    r, g, b = hex_rgb(c)
    return f"rgb({int(r * f)},{int(g * f)},{int(b * f)})"


def logo_html(brand, size_vh, white=False):
    logo = brand.get("logo") or {}
    if logo.get("type") == "svg" and logo.get("svg"):
        svg = logo["svg"]
        svg = re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)
        if white:
            # Invert a colored mark for a colored background: white parts take the accent,
            # every other fill/stroke becomes white.
            accent = brand["accent"]
            svg = re.sub(r'(fill|stroke)="#(?:fff|ffffff)"', r'\1="__ACC__"', svg, flags=re.I)
            svg = re.sub(r'(fill|stroke)="#[0-9A-Fa-f]{3,8}"', r'\1="#ffffff"', svg)
            svg = svg.replace("__ACC__", accent)
        return f"<div class='logo' style='width:{size_vh}vh;height:{size_vh}vh'>{svg}</div>"
    if logo.get("dataUri"):
        return f"<img class='logo' style='height:{size_vh}vh' src='{logo['dataUri']}' alt=''>"
    return ""


def card(variant, kind, brand):
    name, accent, ink, paper, surface, font = (brand["name"], brand["accent"], brand["ink"], brand["paper"],
                                               brand.get("surface", "#fff"), brand["font"])
    outro = kind == "outro"
    cta = "<div class='cta'>{{cta}}</div>" if outro else ""
    common_css = f"""
  html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; }}
  body {{ font-family: {font}; display: flex; align-items: center; justify-content: center; }}
  .card {{ display: flex; flex-direction: column; align-items: center; gap: 1.8vh; width: 100%; opacity: 0; }}
  .logo svg {{ width: 100%; height: 100%; display: block; filter: drop-shadow(0 6px 18px rgba(0,0,0,.18)); }}
  .brand {{ font-size: 1.7vh; font-weight: 700; letter-spacing: .22em; text-transform: uppercase; }}
  .title {{ font-size: 5.4vh; font-weight: 800; letter-spacing: -.03em; text-align: center; max-width: 80%; line-height: 1.2; }}
  .tagline {{ font-size: 2.2vh; font-weight: 500; text-align: center; max-width: 72%; opacity: 0; }}
  .cta {{ margin-top: 2.6vh; padding: 1.2vh 2.8vh; border-radius: 999px; font-size: 2vh; font-weight: 700; opacity: 0; }}
  body.play .card {{ animation: cardIn .6s cubic-bezier(.2,.7,.2,1) forwards; }}
  body.play .tagline {{ animation: up .5s ease-out .25s forwards; }}
  body.play .cta {{ animation: up .5s ease-out .5s forwards; }}
  @keyframes cardIn {{ from {{ opacity: 0; transform: translateY({'-' if outro else ''}14px) scale({1.03 if outro else .96}); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes up {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: none; }} }}
"""
    if variant == "brand-dark":
        css = common_css + f"""
  body {{ background: radial-gradient(120vh 80vh at 50% 110%, {rgba(accent, .45)}, transparent 60%), linear-gradient(160deg, {darken(ink, .9)} 0%, {darken(ink, .6)} 100%); color: #fff; }}
  .brand {{ color: {accent}; }} .tagline {{ color: rgba(255,255,255,.72); }}
  .cta {{ border: 2px solid {accent}; color: #fff; background: {rgba(accent, .18)}; }}"""
        body = f"<div class='card'>{logo_html(brand, 11)}<div class='brand'>{{{{brand}}}}</div><div class='title'>{{{{title}}}}</div><div class='tagline'>{{{{tagline}}}}</div>{cta}</div>"
    elif variant == "brand-light":
        css = common_css + f"""
  body {{ background: {paper}; color: {ink}; }}
  .brand {{ color: {accent}; }} .tagline {{ color: {rgba(ink, .62)}; }}
  .rule {{ width: 9vh; height: .7vh; background: {accent}; border-radius: 999px; margin: .6vh 0; }}
  .cta {{ background: {accent}; color: #fff; }}"""
        body = f"<div class='card'>{logo_html(brand, 10)}<div class='brand'>{{{{brand}}}}</div><div class='title'>{{{{title}}}}</div><div class='rule'></div><div class='tagline'>{{{{tagline}}}}</div>{cta}</div>"
    elif variant == "accent-block":
        css = common_css + f"""
  body {{ background: linear-gradient(160deg, {accent} 0%, {darken(accent, .78)} 100%); color: #fff; }}
  .brand {{ color: rgba(255,255,255,.75); }} .tagline {{ color: rgba(255,255,255,.82); }}
  .logo svg {{ filter: none; }}
  .cta {{ background: #fff; color: {accent}; }}"""
        body = f"<div class='card'>{logo_html(brand, 13, white=True)}<div class='brand'>{{{{brand}}}}</div><div class='title'>{{{{title}}}}</div><div class='tagline'>{{{{tagline}}}}</div>{cta}</div>"
    else:  # split
        css = common_css + f"""
  body {{ background: {paper}; color: {ink}; justify-content: flex-start; }}
  .panel {{ width: 38%; height: 100%; background: linear-gradient(170deg, {accent}, {darken(accent, .8)}); display: flex; align-items: center; justify-content: center; }}
  .card {{ width: 62%; align-items: flex-start; padding-left: 7vw; box-sizing: border-box; }}
  .title, .tagline {{ text-align: left; max-width: 88%; }}
  .brand {{ color: {accent}; }} .tagline {{ color: {rgba(ink, .62)}; }}
  .cta {{ background: {accent}; color: #fff; }}
  .logo svg {{ filter: drop-shadow(0 10px 30px rgba(0,0,0,.25)); }}"""
        body = f"<div class='panel'>{logo_html(brand, 22, white=False)}</div><div class='card'><div class='brand'>{{{{brand}}}}</div><div class='title'>{{{{title}}}}</div><div class='tagline'>{{{{tagline}}}}</div>{cta}</div>"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{{{{title}}}}</title>
<!-- generated by dv.py cards ({variant}, {kind}) from demo/brand.json of {html.escape(name)}. Edit freely. -->
<style>{css}
</style></head>
<body>{body}</body></html>
"""


def fill(text, fields):
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: html.escape(str(fields.get(m.group(1)) or "")), text)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py cards", description=__doc__.splitlines()[0])
    ap.add_argument("--demo", default="demo")
    ap.add_argument("--apply", default=None, help="variant name to use for both intro and outro")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-shot", action="store_true")
    args = ap.parse_args(argv)
    if args.list:
        for k, v in VARIANTS.items():
            print(f"  {k:<13} {v}")
        return 0

    demo_dir = Path(args.demo).resolve()
    project = demo_dir.parent
    sb_path = demo_dir / "storyboard.json"
    sb = common.load_json(sb_path) if sb_path.exists() else {}
    intro, outro = sb.get("intro") or {}, sb.get("outro") or {}

    if args.apply:
        if args.apply not in VARIANTS:
            common.die(f"unknown variant '{args.apply}'. Try: dv.py cards --list")
        if not sb:
            common.die("no storyboard.json to apply to")
        for kind in ("intro", "outro"):
            f = demo_dir / "assets" / f"{kind}-{args.apply}.html"
            if not f.exists():
                common.die(f"{common.rel(f, project)} missing - run dv.py cards first")
            sb[kind]["source"] = "html"
            sb[kind]["template"] = f"assets/{kind}-{args.apply}.html"
            sb[kind].pop("path", None)
        common.dump_json(sb_path, sb)
        print(f"storyboard intro/outro -> assets/intro-{args.apply}.html, assets/outro-{args.apply}.html "
              f"(re-approve G3, then render re-records 00-intro and 99-outro only)")
        return 0

    brand_p = demo_dir / "brand.json"
    if not brand_p.exists():
        common.die("no demo/brand.json - run dv.py brand probe (or write it by hand) first")
    brand = common.load_json(brand_p)
    assets = demo_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    fields = {
        "intro": {"title": intro.get("title") or brand["name"], "tagline": intro.get("tagline", ""), "brand": intro.get("brand") or brand["name"]},
        "outro": {"title": outro.get("title") or brand["name"], "tagline": outro.get("tagline", ""), "brand": outro.get("brand") or brand["name"], "cta": outro.get("cta", "")},
    }
    previews = []
    for v in VARIANTS:
        for kind in ("intro", "outro"):
            src = card(v, kind, brand)
            (assets / f"{kind}-{v}.html").write_text(src, encoding="utf-8")
            prev = assets / f".preview-{kind}-{v}.html"
            prev.write_text(fill(src, fields[kind]).replace("<body>", "<body class='play'>"), encoding="utf-8")
            previews.append((v, kind, prev))
    print(f"wrote {len(previews)} files under {common.rel(assets, project)}")

    if args.no_shot:
        return 0
    w, h = common.frame_size(sb) if sb else (1920, 1080)
    js = assets / ".cards-shot.js"
    lines = [f"async page => {{", f"  await page.setViewportSize({{ width: {w}, height: {h} }});"]
    for v, kind, prev in previews:
        png = assets / f".preview-{kind}-{v}.png"
        lines += [f"  await page.goto({json.dumps(prev.resolve().as_uri())});", "  await page.waitForTimeout(900);",
                  f"  await page.screenshot({{ path: {json.dumps(str(png))} }});"]
    lines += ["  return 'ok';", "}"]
    js.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(["playwright-cli", "-s=dv-cards", "open"], cwd=str(project), capture_output=True, text=True)
    r = subprocess.run(["playwright-cli", "-s=dv-cards", "run-code", "--filename", common.rel(js, project), "--raw"],
                       cwd=str(project), capture_output=True, text=True)
    subprocess.run(["playwright-cli", "-s=dv-cards", "close"], cwd=str(project), capture_output=True, text=True)
    js.unlink(missing_ok=True)
    if r.returncode != 0:
        common.die("card screenshots failed:\n" + (r.stderr or r.stdout).strip()[-400:])
    # gallery: one row per variant (intro | outro), 2 columns
    inputs, layout = [], []
    cw, ch = 800, int(round(800 * h / w))
    i = 0
    for row, v in enumerate(VARIANTS):
        for col, kind in enumerate(("intro", "outro")):
            inputs += ["-i", str(assets / f".preview-{kind}-{v}.png")]
            layout.append(f"{col * (cw + 16)}_{row * (ch + 16)}")
            i += 1
    fc = "".join(f"[{k}:v]scale={cw}:{ch}[p{k}];" for k in range(i)) + "".join(f"[p{k}]" for k in range(i)) + \
         f"xstack=inputs={i}:layout={'|'.join(layout)}:fill=#e2e8f0[t]"
    gallery = demo_dir / "cards.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", fc, "-map", "[t]", str(gallery)], capture_output=True)
    print(f"wrote {common.rel(gallery, project)} - rows top to bottom: " + ", ".join(VARIANTS) + " (left intro, right outro)")
    print("show it, ask which variant (or what to change), then: dv.py cards --apply <variant>")
    return 0
