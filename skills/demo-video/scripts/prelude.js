// Injected into every scene body by dv.py render. `page` is in scope, so no
// helper takes it as an argument.
//
// The run-code sandbox is a bare vm: no require, no process, no module,
// no __dirname, no dynamic import. Everything a scene needs lives here.
//
// Every effect is a page.screencast overlay: pointer-events:none, composited
// above all page content, and gone on navigation.
//
// Timing (measured; re-measure after a Playwright upgrade) - get this wrong and every duration doubles:
//   showOverlay(html)              non-blocking, sticky until .dispose()
//   showOverlay(html, {duration})  BLOCKS for duration, then self-removes
//   showChapter(title, {duration}) BLOCKS for duration + ~300ms of animation
// So never follow a timed overlay with a wait of its own length.
//
// `__t0` and `__cues` are declared by the wrapper dv.py render builds around this
// file. Do not redeclare them in a scene body.

const FONT = "'Apple SD Gothic Neo','Pretendard','Noto Sans KR',-apple-system,sans-serif";

const SUB_POS = {
  bottom: 'bottom:40px;left:50%;transform:translateX(-50%);',
  top: 'top:40px;left:50%;transform:translateX(-50%);',
  'bottom-left': 'bottom:48px;left:48px;',
  'bottom-right': 'bottom:48px;right:48px;',
};

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// 5 Korean chars/sec is a comfortable read; floor at 1.8s.
const readingMs = (text) => Math.max(1800, Math.ceil(String(text).length / 5) * 1000 + 600);

// Dwell time from information density. Mirrors references/storyboard.md.
function dwellFromDensity({ textChars = 0, interactive = 0 }) {
  const reading = (Math.min(textChars, 1800) / 1800) * 4000;
  const scanning = Math.min(interactive, 15) * 200;
  return Math.round(clamp(2000 + reading + scanning, 2500, 9000));
}

const dwell = (ms) => page.waitForTimeout(ms);

async function startRec(path, opts = {}) {
  await page.screencast.start({
    path,
    size: { width: opts.width ?? 1280, height: opts.height ?? 720 },
  });
}

const stopRec = () => page.screencast.stop();

const showActions = (opts = {}) => page.screencast.showActions({
  cursor: opts.cursor ?? 'pointer',
  duration: opts.duration ?? 900,
  fontSize: opts.fontSize ?? 20,
  position: opts.position ?? 'top-right',
});

const hideActions = () => page.screencast.hideActions();

// Mid-video section break: card over a blurred page.
// Blocks for durationMs + ~300ms of animation.
const chapter = (title, opts = {}) => page.screencast.showChapter(title, {
  description: opts.description,
  duration: opts.durationMs ?? 1800,
});

// 한 줄 고정. 감싸지 않고(nowrap) 얇게, 배경은 화면이 비칠 만큼만.
// 두 줄이 되면 화면을 가리고 시선이 자막으로 끌려간다 — 길면 문구를 줄인다.
function subtitleHtml(text, position = 'bottom') {
  const place = SUB_POS[position] || SUB_POS.bottom;
  return `
    <style>@keyframes subIn{from{opacity:0;transform:translate(-50%,8px)}to{opacity:1}}</style>
    <div style="position:absolute;${place}max-width:92%;padding:9px 24px;
      background:rgba(12,14,18,.62);border-radius:10px;
      box-shadow:0 4px 18px rgba(0,0,0,.22);
      color:#fff;font-family:${FONT};font-size:25px;font-weight:600;
      line-height:1.25;text-align:center;letter-spacing:-.2px;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
      animation:subIn .24s ease-out;">${text}</div>`;
}

// No holdMs -> sticky, caller disposes. With holdMs -> self-removes and blocks.
// Every subtitle records a cue on __cues so dv.py render can emit exact timings
// for the narration track and the .srt sidecar.
async function subtitle(text, opts = {}) {
  const html = subtitleHtml(text, opts.position);
  const cue = { text, startMs: Date.now() - __t0, endMs: null };
  __cues.push(cue);
  if (opts.holdMs) {
    await page.screencast.showOverlay(html, { duration: opts.holdMs });
    cue.endMs = cue.startMs + opts.holdMs;
    return { dispose: async () => {} };
  }
  const handle = await page.screencast.showOverlay(html);
  return {
    dispose: async () => {
      cue.endMs = Date.now() - __t0;
      await handle.dispose();
    },
  };
}

// Hold a sticky subtitle for at least `minMs` while `work` runs underneath it.
// This is the primitive for a narrated scene: the voice needs the subtitle up
// for its whole length, but the highlights and scrolls should happen *under*
// it, not after it. Pass HOLD[n] as minMs - dv.py render injects the holds that
// dv.py narrate measured, so the subtitle can never be shorter than its voice.
async function subtitleSpan(text, minMs, work, opts = {}) {
  const s = await subtitle(text, { position: opts.position });
  const t0 = Date.now();
  if (work) await work();
  const left = (minMs || 0) - (Date.now() - t0);
  if (left > 0) await dwell(left);
  await s.dispose();
  if (opts.gapMs !== 0) await dwell(opts.gapMs ?? 300);   // swap must be visible
}

// Plays subtitles in order with a 300ms gap so each swap is visible.
async function subtitles(items, opts = {}) {
  const gap = opts.gapMs ?? 300;
  for (const item of items) {
    const hold = item.holdMs ?? readingMs(item.text);
    await subtitle(item.text, { holdMs: hold, position: item.position });  // blocks `hold`
    await dwell(gap);
  }
}

function rippleHtml(x, y, opts = {}) {
  const color = opts.color ?? '56,189,248';
  const size = opts.sizePx ?? 60;
  const ms = opts.durationMs ?? 600;
  const r = size / 2;
  return `
    <style>@keyframes rp{0%{transform:scale(.2);opacity:.9}100%{transform:scale(2.6);opacity:0}}</style>
    <div style="position:absolute;left:${x - r}px;top:${y - r}px;
      width:${size}px;height:${size}px;border-radius:50%;
      background:radial-gradient(circle,rgba(${color},.55),rgba(${color},0) 70%);
      border:2px solid rgba(${color},.9);
      animation:rp ${ms}ms ease-out forwards;"></div>`;
}

// Standalone ripple at a coordinate. Blocks for the animation.
async function ripple(x, y, opts = {}) {
  const ms = opts.durationMs ?? 600;
  await page.screencast.showOverlay(rippleHtml(x, y, opts), { duration: ms + 20 });
}

// Ripple at the element's center *while* clicking it, then settle.
// Use instead of locator.click() everywhere in a demo.
async function clickRipple(locator, opts = {}) {
  const b = await locator.boundingBox();
  if (!b) throw new Error('clickRipple: target has no bounding box (hidden or detached)');
  const handle = await page.screencast.showOverlay(
    rippleHtml(b.x + b.width / 2, b.y + b.height / 2, opts));  // sticky: non-blocking
  await locator.click();
  await dwell(opts.settleMs ?? 600);
  await handle.dispose();
}

// Outline an element, optionally with a labelled callout beneath it.
// Blocks for durationMs - do not add a wait after it.
async function highlight(locator, opts = {}) {
  const b = await locator.boundingBox();
  if (!b) throw new Error('highlight: target has no bounding box');
  const ms = opts.durationMs ?? 2000;
  const label = opts.label
    ? `<div style="position:absolute;top:${b.y + b.height + 10}px;left:${b.x + b.width / 2}px;
        transform:translateX(-50%);padding:8px 14px;background:#0ea5e9;border-radius:10px;
        color:#fff;font-family:${FONT};font-size:16px;font-weight:600;
        white-space:nowrap;">${opts.label}</div>`
    : '';
  await page.screencast.showOverlay(`
    <div style="position:absolute;left:${b.x - 4}px;top:${b.y - 4}px;
      width:${b.width + 8}px;height:${b.height + 8}px;border-radius:8px;
      border:3px solid #0ea5e9;box-shadow:0 0 0 6px rgba(14,165,233,.18);"></div>${label}`,
    { duration: ms });
  return ms;
}

// The gradient backdrop is opaque from the first frame; only the text animates,
// so the card never fades up from the blank page underneath it.
function cardHtml(title, subtitleText, brand, outro) {
  const from = outro ? 'scale(1.04)' : 'scale(.94)';
  return `
    <style>
      @keyframes cardIn{from{opacity:0;transform:${from}}to{opacity:1;transform:scale(1)}}
      @keyframes subUp{0%{opacity:0;transform:translateY(12px)}100%{opacity:1}}
    </style>
    <div style="position:absolute;inset:0;display:flex;flex-direction:column;
      align-items:center;justify-content:center;gap:18px;
      background:linear-gradient(150deg,#0b1220 0%,#111c33 55%,#0b1220 100%);
      font-family:${FONT};">
      <div style="display:flex;flex-direction:column;align-items:center;gap:18px;
        width:100%;animation:cardIn .5s ease-out;">
      ${brand ? `<div style="color:#7dd3fc;font-size:18px;font-weight:700;
        letter-spacing:2px;text-transform:uppercase;">${brand}</div>` : ''}
      <div style="color:#fff;font-size:56px;font-weight:800;letter-spacing:-1.5px;
        text-align:center;max-width:82%;">${title}</div>
      ${subtitleText ? `<div style="color:#94a3b8;font-size:24px;font-weight:500;
        text-align:center;max-width:74%;animation:subUp .5s ease-out .2s both;">${subtitleText}</div>` : ''}
      </div>
    </div>`;
}

// Full-screen title card. Needs a loaded page to composite onto (about:blank is fine).
// Blocks for durationMs - do not add a wait after it.
async function card(opts) {
  const ms = opts.durationMs ?? 2500;
  await hideActions().catch(() => {});
  await page.screencast.showOverlay(
    cardHtml(opts.title, opts.subtitle, opts.brand, !!opts.outro), { duration: ms });
}

const intro = (opts) => card({ ...opts, outro: false });
const outro = (opts) => card({ durationMs: 3000, ...opts, outro: true });

// Scroll an inner scroll container so the motion is visible on camera.
// A jump-cut scroll reads as a glitch; step it over `durationMs` instead.
//   scrollPanel('.case-modal-analysis', { toRatio: 0.35 })   // 35% down
//   scrollPanel('.ledger-sheet-scroll', { axis: 'x', toRatio: 1 })
//   scrollPanel('.dashboard-results-scroll', { byPx: 700 })
async function scrollPanel(selector, opts = {}) {
  const axis = opts.axis === 'x' ? 'x' : 'y';
  const durationMs = opts.durationMs ?? 1400;
  const steps = Math.max(10, Math.round(durationMs / 55));

  const plan = await page.evaluate(({ selector, axis, byPx, toRatio }) => {
    const el = document.querySelector(selector);
    if (!el) return null;
    const max = axis === 'x' ? el.scrollWidth - el.clientWidth : el.scrollHeight - el.clientHeight;
    const from = axis === 'x' ? el.scrollLeft : el.scrollTop;
    let to = byPx != null ? from + byPx : Math.round(max * (toRatio ?? 1));
    to = Math.max(0, Math.min(max, to));
    return { from, to, max };
  }, { selector, axis, byPx: opts.byPx ?? null, toRatio: opts.toRatio ?? null });

  if (!plan) throw new Error(`scrollPanel: no element matches ${selector}`);
  if (plan.max <= 0) throw new Error(`scrollPanel: ${selector} does not scroll on ${axis}`);

  for (let i = 1; i <= steps; i++) {
    // ease-in-out so the start and stop do not snap
    const t = i / steps;
    const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    const v = Math.round(plan.from + (plan.to - plan.from) * e);
    await page.evaluate(({ selector, axis, v }) => {
      const el = document.querySelector(selector);
      if (axis === 'x') el.scrollLeft = v; else el.scrollTop = v;
    }, { selector, axis, v });
    await dwell(Math.round(durationMs / steps));
  }
  return plan;
}

// Move the viewer's eye across a row of panels without scrolling: outline each
// in turn. For layouts that fit on screen but read left-to-right.
async function panAcross(locators, opts = {}) {
  const each = opts.eachMs ?? 1100;
  for (const loc of locators) {
    await highlight(loc, { durationMs: each, label: opts.labels ? opts.labels.shift() : undefined });
  }
}

// Visible text volume + interactive element count for the current page.
async function density() {
  const raw = await page.evaluate(() => {
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) return false;
      const s = getComputedStyle(el);
      return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
    };
    const textChars = (document.body.innerText || '').replace(/\s+/g, ' ').trim().length;
    const sel = 'button,a[href],input:not([type=hidden]),select,textarea,[role=button],[role=tab],[role=link]';
    const interactive = [...document.querySelectorAll(sel)]
      .filter((el) => visible(el) && !el.disabled).length;
    return { textChars, interactive };
  });
  return { ...raw, dwellMs: dwellFromDensity(raw) };
}
