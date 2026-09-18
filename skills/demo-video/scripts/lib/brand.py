"""dv.py brand probe - read the running app's identity (logo, colors, font, name) into demo/brand.json.

    dv.py brand probe                       # from config.app.url
    dv.py brand probe --url http://... --path /
    dv.py brand show                        # print what was found

What it reads, in this order of trust:
  name     <meta application-name>, then the header brand text, then <title>
  logo     <link rel=icon> (svg inlined, png/ico as data URI), else the first <header> img/svg
  colors   :root custom properties whose value is a color (names with accent/primary/brand win),
           the most common button background, body color and background
  font     body font-family

Values are guesses for the user to confirm. `dv.py cards` uses them; edit demo/brand.json to correct.
"""
import argparse
import json
import subprocess
from pathlib import Path

from . import common

PROBE_JS = r"""async page => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(%(url)s, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const info = await page.evaluate(async () => {
    const isColor = (v) => /^(#[0-9a-f]{3,8}|rgba?\(|hsla?\()/i.test((v || '').trim());
    const vars = {};
    for (const sheet of document.styleSheets) {
      let rules; try { rules = sheet.cssRules; } catch (e) { continue; }
      for (const r of rules) {
        if (!r.selectorText || !/:root|html|body/.test(r.selectorText)) continue;
        for (const name of r.style) if (name.startsWith('--') && isColor(r.style.getPropertyValue(name))) vars[name] = r.style.getPropertyValue(name).trim();
      }
    }
    const cs = getComputedStyle(document.body);
    const count = {};
    for (const b of document.querySelectorAll('button, a.btn, [role=button]')) {
      const bg = getComputedStyle(b).backgroundColor;
      if (!bg || bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent') continue;
      const m = bg.match(/\d+/g); if (!m) continue;
      const [r, g, bl] = m.map(Number); const sat = Math.max(r, g, bl) - Math.min(r, g, bl);
      if (sat < 40) continue;
      count[bg] = (count[bg] || 0) + 1;
    }
    const buttonAccent = Object.entries(count).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
    const meta = document.querySelector('meta[name="application-name"]')?.content;
    const brandEl = document.querySelector('.brand, [class*=brand], [class*=logo], header a[href="/"]');
    const name = meta || (brandEl && brandEl.textContent.trim().slice(0, 40)) || document.title.split(/[-|·]/)[0].trim();
    const icon = document.querySelector('link[rel~="icon"], link[rel="shortcut icon"]');
    let logo = null;
    const href = icon ? new URL(icon.getAttribute('href'), location.href).href : null;
    if (href) {
      try {
        const res = await fetch(href); const type = res.headers.get('content-type') || '';
        if (/svg/.test(type) || href.endsWith('.svg')) logo = { type: 'svg', svg: await res.text(), href };
        else { const buf = await res.arrayBuffer(); const b64 = btoa(String.fromCharCode(...new Uint8Array(buf))); logo = { type: 'png', dataUri: `data:${type || 'image/png'};base64,${b64}`, href }; }
      } catch (e) {}
    }
    if (!logo) {
      const svg = document.querySelector('header svg, .brand svg, [class*=logo] svg');
      if (svg) logo = { type: 'svg', svg: svg.outerHTML, href: null };
      const img = document.querySelector('header img, .brand img, [class*=logo] img');
      if (!logo && img) logo = { type: 'img', dataUri: img.src, href: img.src };
    }
    return { name, logo, vars, buttonAccent, bodyColor: cs.color, bodyBg: cs.backgroundColor, font: cs.fontFamily, title: document.title };
  });
  return JSON.stringify(info);
}
"""


def pick_accent(vars_, button_accent):
    for key in ("--accent", "--primary", "--brand", "--color-primary", "--color-accent", "--brand-color"):
        if key in vars_:
            return vars_[key], key
    for k, v in vars_.items():
        if any(w in k for w in ("accent", "primary", "brand")) and not any(w in k for w in ("soft", "line", "bg", "hover", "press")):
            return v, k
    return (button_accent, "button background") if button_accent else ("#2563eb", "default")


def pick(vars_, names, fallback):
    for n in names:
        if n in vars_:
            return vars_[n], n
    return fallback, "computed"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dv.py brand", description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["probe", "show"])
    ap.add_argument("--demo", default="demo")
    ap.add_argument("--url", default=None)
    ap.add_argument("--path", default="/", help="page to read the identity from")
    args = ap.parse_args(argv)

    demo_dir = Path(args.demo).resolve()
    project = demo_dir.parent
    out = demo_dir / "brand.json"
    if args.action == "show":
        if not out.exists():
            common.die("no demo/brand.json - run dv.py brand probe")
        b = common.load_json(out)
        print(json.dumps({k: v for k, v in b.items() if k != "logo"}, ensure_ascii=False, indent=2))
        print("logo:", (b.get("logo") or {}).get("type"), (b.get("logo") or {}).get("href"))
        return 0

    cfg_p = demo_dir / "config.json"
    base = args.url or (common.load_json(cfg_p).get("app", {}).get("url") if cfg_p.exists() else None)
    if not base:
        common.die("no app URL - pass --url or run dv.py init")
    url = base.rstrip("/") + (args.path if args.path.startswith("/") or args.path.startswith("?") else "/" + args.path)
    js = demo_dir / ".brand-probe.js"
    js.write_text(PROBE_JS % {"url": json.dumps(url)}, encoding="utf-8")
    subprocess.run(["playwright-cli", "-s=dv-brand", "open"], cwd=str(project), capture_output=True, text=True)
    r = subprocess.run(["playwright-cli", "-s=dv-brand", "run-code", "--filename", common.rel(js, project), "--raw"],
                       cwd=str(project), capture_output=True, text=True)
    subprocess.run(["playwright-cli", "-s=dv-brand", "close"], cwd=str(project), capture_output=True, text=True)
    js.unlink(missing_ok=True)
    try:
        info = json.loads(json.loads(r.stdout.strip()))
    except (ValueError, TypeError):
        common.die("brand probe failed:\n" + (r.stderr or r.stdout).strip()[-400:])

    vars_ = info.get("vars") or {}
    accent, accent_src = pick_accent(vars_, info.get("buttonAccent"))
    ink, ink_src = pick(vars_, ["--ink", "--text", "--fg", "--color-text", "--foreground"], info.get("bodyColor"))
    paper, paper_src = pick(vars_, ["--paper", "--bg", "--background", "--color-bg", "--surface-bg"], info.get("bodyBg"))
    surface, _ = pick(vars_, ["--surface", "--card", "--color-surface"], "#ffffff")
    brand = {
        "name": info.get("name") or "Product",
        "accent": accent, "ink": ink, "paper": paper, "surface": surface,
        "font": info.get("font") or "-apple-system, sans-serif",
        "logo": info.get("logo"),
        "sources": {"accent": accent_src, "ink": ink_src, "paper": paper_src, "url": url},
        "vars": vars_,
    }
    common.dump_json(out, brand)
    print(f"wrote {common.rel(out, project)}")
    print(f"  name    {brand['name']}")
    print(f"  accent  {accent}  ({accent_src})")
    print(f"  ink     {ink}  paper {paper}  surface {surface}")
    print(f"  font    {brand['font'][:60]}")
    print(f"  logo    {(brand['logo'] or {}).get('type') or 'none'}  {(brand['logo'] or {}).get('href') or ''}")
    print("confirm these with the user (edit demo/brand.json to correct), then: dv.py cards")
    return 0
