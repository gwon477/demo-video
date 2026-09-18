"""dv.py sheet [--capture] - build demo/sheet.html, the storyboard sheet for the G3 review.

    dv.py sheet --capture     # take one screenshot per scene (and measure targets), then build
    dv.py sheet               # build from existing demo/shots/*.png

One card per step: the page screenshot with the subtitle drawn where the video
will place it, boxes on every action target (zoom targets in a second color),
the action list, and hold time. Each scene shows its interactions[] with
show/skip/blocked badges (FR-064). No recording - seconds, not minutes.
"""
import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

from . import common

CAPTURE_JS = """async page => {
  const out = {};
  const scenes = %(scenes)s;
  await page.setViewportSize({ width: %(w)d, height: %(h)d });
  for (const sc of scenes) {
    try {
      await page.goto(%(base)s + sc.url, { waitUntil: 'networkidle' });
      if (sc.waitFor) await page.locator(sc.waitFor).first().waitFor({ timeout: 15000 });
      await page.screenshot({ path: sc.shot, fullPage: false });
      const boxes = {};
      for (const sel of sc.targets) {
        try {
          // Targets that only exist after an action (a dialog, an answer) are simply not boxed.
          const b = await page.locator(sel).first().boundingBox({ timeout: 1500 });
          if (b) boxes[sel] = b;
        } catch (e) { boxes[sel] = null; }
      }
      out[sc.id] = { ok: true, boxes };
    } catch (e) {
      out[sc.id] = { ok: false, error: String(e).split('\\n')[0] };
    }
  }
  return JSON.stringify(out);
}
"""

CSS = """
body{font-family:-apple-system,'Apple SD Gothic Neo','Pretendard',sans-serif;background:#f1f5f9;color:#0f172a;margin:0;padding:24px}
h1{font-size:22px;margin:0 0 4px} .meta{color:#64748b;margin:0 0 20px;font-size:14px}
.scene{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin-bottom:20px}
.scene h2{font-size:16px;margin:0 0 4px} .scene .url{color:#64748b;font-size:13px;margin:0 0 10px}
.badges{margin:0 0 12px} .badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;margin:0 6px 6px 0;border:1px solid transparent}
.badge.show{background:#dcfce7;color:#166534;border-color:#86efac} .badge.skip{background:#f1f5f9;color:#475569}
.badge.blocked{background:#fee2e2;color:#991b1b;border-color:#fca5a5} .badge small{opacity:.8}
.steps{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:14px}
.step{border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;background:#fff}
.frame{position:relative;width:100%%;aspect-ratio:%(ratio)s;background:#0b1220;overflow:hidden;container-type:inline-size}
.frame img{position:absolute;inset:0;width:100%%;height:100%%;object-fit:cover}
.frame .noshot{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-size:13px}
.frame .sub{position:absolute;left:50%%;bottom:%(sub_bottom).1f%%;transform:translateX(-50%%);max-width:86%%;white-space:nowrap;
  padding:.35em .7em;background:rgba(12,14,18,.62);color:#fff;border-radius:.4em;font-weight:600;font-size:%(sub_font).2fcqw}
.frame .box{position:absolute;border:2px solid #0ea5e9;border-radius:4px;box-sizing:border-box}
.frame .box.zoom{border-color:#f59e0b;border-style:dashed}
.frame .box span{position:absolute;left:0;top:-1.4em;font-size:10px;background:#0ea5e9;color:#fff;padding:1px 4px;border-radius:3px;white-space:nowrap}
.frame .box.zoom span{background:#f59e0b}
.frame .safe{position:absolute;inset:6%%;border:1px dashed rgba(255,255,255,.35);pointer-events:none}
.info{padding:10px 12px;font-size:13px} .info .t{font-weight:600;margin-bottom:6px}
.info ul{margin:0;padding-left:18px;color:#334155} .info .hold{color:#64748b;font-size:12px;margin-top:6px}
.hook{color:#0369a1;font-size:11px;font-weight:700;margin-left:6px}
.totals{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:12px 16px;font-size:14px}
"""


def action_label(a):
    t = a["type"]
    if t == "drag":
        return f"drag ({a.get('mode')}) {a.get('source')} → {a.get('target')}"
    if t == "type":
        return f"type {a.get('target')} ← {'••••' if a.get('secret') else a.get('value')}"
    if t == "key":
        return f"key {a.get('combo')}"
    if t == "zoom":
        return f"zoom ×{a.get('scale', 1.5)} {a.get('target')}"
    if t == "goto":
        return f"goto {a.get('url')}"
    tgt = a.get("target", "")
    extra = " ".join(f"{k}={v}" for k, v in a.items() if k not in ("type", "target"))
    return f"{t} {tgt} {extra}".strip()


def capture(sb, demo_dir: Path, shots_dir: Path):
    project = demo_dir.parent
    w, h = common.frame_size(sb)
    base = common.base_url(sb, demo_dir)
    plan = []
    for sc in sb["scenes"]:
        targets = []
        for st in sc["steps"]:
            for a in st.get("actions") or []:
                for k in ("target", "source"):
                    v = a.get(k)
                    if v and v not in ("window", "document") and v not in targets:
                        targets.append(v)
        plan.append({"id": sc["id"], "url": sc["url"], "waitFor": sc.get("waitFor"),
                     "shot": common.rel(shots_dir / f"{sc['id']}.png", project), "targets": targets})
    script = CAPTURE_JS % {"scenes": json.dumps(plan, ensure_ascii=False), "w": w, "h": h, "base": json.dumps(base)}
    build = shots_dir / ".capture.js"
    build.write_text(script, encoding="utf-8")
    r = subprocess.run(["playwright-cli", "open"], cwd=str(project), capture_output=True, text=True)
    if r.returncode != 0:
        common.die("playwright-cli open failed:\n" + (r.stderr or r.stdout).strip())
    r = subprocess.run(["playwright-cli", "run-code", "--filename", common.rel(build, project), "--raw"],
                       cwd=str(project), capture_output=True, text=True)
    subprocess.run(["playwright-cli", "close"], cwd=str(project), capture_output=True, text=True)
    if r.returncode != 0:
        common.die("capture failed:\n" + (r.stderr or r.stdout).strip()[-600:])
    try:
        result = json.loads(json.loads(r.stdout.strip()))
    except (ValueError, TypeError):
        common.die("capture returned no result")
    for sid, info in result.items():
        if info.get("ok"):
            common.dump_json(shots_dir / f"{sid}.boxes.json", info["boxes"])
        else:
            print(f"warning: {sid}: {info.get('error')}", file=sys.stderr)
    return result


def build_html(sb, demo_dir: Path, shots_dir: Path, theme):
    w, h = common.frame_size(sb)
    s = theme["subtitle"]
    esc = html.escape
    parts = [f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>{esc(common.name_of(sb))} sheet</title>",
             "<style>" + CSS % {"ratio": f"{w}/{h}", "sub_bottom": s["bottomRatio"] * 100,
                                "sub_font": s["fontSizeRatio"] * 100 * h / w} + "</style></head><body>"]
    parts.append(f"<h1>{esc(common.name_of(sb))} · 콘티 시트</h1>")
    intro, outro = sb.get("intro") or {}, sb.get("outro") or {}
    parts.append(f"<p class='meta'>{w}×{h} · 인트로: {esc(intro.get('title') or intro.get('path', ''))} "
                 f"({intro.get('holdMs', 2500) if intro.get('source') == 'html' else 'video'}) · "
                 f"아웃트로: {esc(outro.get('title') or outro.get('path', ''))} · CTA: {esc(outro.get('cta') or '-')}</p>")
    total_ms = 0
    for sc in sb["scenes"]:
        shot = shots_dir / f"{sc['id']}.png"
        boxes_p = shots_dir / f"{sc['id']}.boxes.json"
        boxes = common.load_json(boxes_p) if boxes_p.exists() else {}
        tr = sc.get("transitionIn") or {}
        parts.append(f"<section class='scene'><h2>{esc(sc['id'])}</h2><p class='url'>{esc(sc['url'])} · "
                     f"전환 {esc(tr.get('type', 'fade'))} {tr.get('ms', theme['transition']['defaultMs'])}ms · "
                     f"체류 {sc.get('dwellMs', '?')}ms{' · mutates' if sc.get('mutates') else ''}</p>")
        inter = sc.get("interactions") or []
        if inter:
            parts.append("<div class='badges'>" + "".join(
                f"<span class='badge {esc(i.get('decision', ''))}' title='{esc(i.get('reason', ''))}'>"
                f"{esc(i.get('decision', ''))} · {esc(i.get('kind', ''))} {esc(i.get('target', ''))} "
                f"<small>{esc(i.get('reason', ''))}</small></span>" for i in inter) + "</div>")
        parts.append("<div class='steps'>")
        for j, st in enumerate(sc["steps"]):
            sub = st["subtitle"]
            img = (f"<img src='{esc(common.rel(shot, demo_dir))}' alt=''>" if shot.exists()
                   else "<div class='noshot'>스크린샷 없음 - dv.py sheet --capture</div>")
            box_html = ""
            for a in st.get("actions") or []:
                for k in ("target", "source"):
                    sel = a.get(k)
                    b = boxes.get(sel) if sel else None
                    if not b:
                        continue
                    cls = "box zoom" if a["type"] == "zoom" else "box"
                    box_html += (f"<div class='{cls}' style='left:{b['x'] / w * 100:.2f}%;top:{b['y'] / h * 100:.2f}%;"
                                 f"width:{b['width'] / w * 100:.2f}%;height:{b['height'] / h * 100:.2f}%'>"
                                 f"<span>{esc(a['type'])}</span></div>")
            text = esc(sub["text"])
            if sub.get("emphasis") and sub["emphasis"] in sub["text"]:
                text = text.replace(esc(sub["emphasis"]), f"<b style='color:{theme['subtitle']['emphasisColor']}'>{esc(sub['emphasis'])}</b>")
            parts.append(f"<div class='step'><div class='frame'>{img}<div class='safe'></div>{box_html}"
                         f"<div class='sub'>{text}</div></div><div class='info'>"
                         f"<div class='t'>{j + 1}. {esc(sub['text'])}{'<span class=hook>HOOK</span>' if sub.get('hook') else ''}</div>"
                         f"<ul>{''.join(f'<li>{esc(action_label(a))}</li>' for a in (st.get('actions') or []))}</ul>"
                         f"<div class='hold'>hold {st.get('holdMs', '?')}ms</div></div></div>")
        parts.append("</div></section>")
        total_ms += int(sc.get("dwellMs") or 0)
    est = (total_ms + (intro.get("holdMs", 2500) if intro.get("source") == "html" else 0)
           + (outro.get("holdMs", 3000) if outro.get("source") == "html" else 0)) / 1000
    parts.append(f"<div class='totals'>{len(sb['scenes'])}장면 · 본문 {total_ms / 1000:.1f}s · 예상 총 {est:.1f}s (전환 제외)</div>")
    parts.append("</body></html>")
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py sheet", description=__doc__.splitlines()[0])
    ap.add_argument("--storyboard", default=None)
    ap.add_argument("--capture", action="store_true", help="take screenshots and measure targets first")
    ap.add_argument("--out", default=None, help="default demo/sheet.html")
    args = ap.parse_args(argv)

    sb_path = common.storyboard_path(args.storyboard)
    sb = common.load_json(sb_path)
    demo_dir = sb_path.parent
    if common.schema_version(sb) < 2:
        common.die("sheet needs schemaVersion 2")
    from .validate import validate
    f, _ = validate(sb, demo_dir)
    if f.errors:
        common.die(f"{len(f.errors)} validate error(s) - run dv.py validate first")
    theme = common.load_theme(demo_dir)
    shots_dir = demo_dir / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    if args.capture:
        capture(sb, demo_dir, shots_dir)
    out = Path(args.out).resolve() if args.out else demo_dir / "sheet.html"
    out.write_text(build_html(sb, demo_dir, shots_dir, theme), encoding="utf-8")
    have = sum(1 for sc in sb["scenes"] if (shots_dir / f"{sc['id']}.png").exists())
    print(f"wrote {common.rel(out, demo_dir.parent)} ({len(sb['scenes'])} scenes, {have} with screenshots)")
    return 0
