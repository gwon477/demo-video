// Injected into every scene body by dv.py render. `page` is in scope, so no
// helper takes it as an argument. The run-code sandbox is a bare vm: no
// require, no process, no module. Everything a scene needs lives here.
//
// Layers (DESIGN.md 6절):
//   L3 subtitles, chapter cards, key caps  -> page.screencast overlays. They sit in
//      the browser top layer and never move or scale when the page zooms or scrolls.
//   L2 cursor, ripple, highlight           -> overlays drawn at the target's live
//      boundingBox(), so they follow a zoomed element in place and size.
//   L1 the app                             -> zoomed with transform on <body>.
//
// Timing: a helper that takes a duration blocks for it. Never add your own wait
// after one - it doubles the scene. `__t0`, `__cues`, `__marks`, `THEME`, `FRAME`,
// `BASE`, `ACCOUNTS`, `HOLD` are declared by the wrapper around this file.

const T = THEME;
const FONT = T.subtitle.fontFamily;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const dwell = (ms) => page.waitForTimeout(ms);
const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

// Weighted length per FR-012: hangul 1, everything else 0.5.
function weightedChars(text) {
  let n = 0;
  for (const ch of String(text)) n += /[ᄀ-ᇿ㄰-㆏가-힯]/.test(ch) ? 1 : 0.5;
  return n;
}
// FR-013 reading time.
const readingMs = (text) => clamp(Math.round(weightedChars(text) * T.subtitle.msPerChar + T.subtitle.baseMs),
  T.subtitle.minMs, T.subtitle.maxMs);

// Dwell time from information density (references/storyboard.md).
function dwellFromDensity({ textChars = 0, interactive = 0 }) {
  const reading = (Math.min(textChars, 1800) / 1800) * 4000;
  const scanning = Math.min(interactive, 15) * 200;
  return Math.round(clamp(2000 + reading + scanning, T.scene.minMs, T.scene.maxMs));
}

// ---------------------------------------------------------------- recording
async function startRec(path, opts = {}) {
  await page.screencast.start({ path, size: { width: opts.width ?? FRAME.width, height: opts.height ?? FRAME.height } });
}
const stopRec = () => page.screencast.stop();
const showActions = (opts = {}) => page.screencast.showActions({
  cursor: opts.cursor ?? 'none', duration: opts.duration ?? 900, fontSize: opts.fontSize ?? 20,
  position: opts.position ?? 'top-right',
});
const hideActions = () => page.screencast.hideActions().catch(() => {});

const overlay = (html, ms) => (ms ? page.screencast.showOverlay(html, { duration: ms }) : page.screencast.showOverlay(html));
const mark = (type, extra = {}) => { __marks.push({ type, atMs: Date.now() - __t0, ...extra }); };

// ---------------------------------------------------------------- targets
// A target is a Locator or a selector string. Strings go through page.locator.
const loc = (target) => (typeof target === 'string' ? page.locator(target).first() : target);
async function boxOf(target, what = 'target') {
  const b = await loc(target).boundingBox();
  if (!b) throw new Error(`${what}: no bounding box (hidden or detached)`);
  return b;
}
const center = (b) => ({ x: b.x + b.width / 2, y: b.y + b.height / 2 });

// ---------------------------------------------------------------- L3 subtitle
const SUB_FONT_PX = Math.round(FRAME.height * T.subtitle.fontSizeRatio);
function subtitleHtml(text, emphasis) {
  let inner = String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  if (emphasis && inner.includes(emphasis)) {
    inner = inner.replace(emphasis, `<span style="color:${T.subtitle.emphasisColor}">${emphasis}</span>`);
  }
  // FR-010 bottom 7%, centered. FR-011 one line, 86% max, never clipped with an ellipsis -
  // validate rejects text that would not fit, so overflow here means a rule was bypassed.
  return `
    <style>@keyframes subIn{from{opacity:0;transform:translate(-50%,8px)}to{opacity:1}}</style>
    <div style="position:absolute;left:50%;bottom:${Math.round(FRAME.height * T.subtitle.bottomRatio)}px;
      transform:translateX(-50%);max-width:${Math.round(T.subtitle.maxWidthRatio * 100)}%;padding:${Math.round(SUB_FONT_PX * 0.35)}px ${Math.round(SUB_FONT_PX * 0.7)}px;
      background:${T.subtitle.background};border-radius:${T.subtitle.radius}px;box-shadow:${T.subtitle.shadow ?? 'none'};
      border:${T.subtitle.border ?? 'none'};border-left:${T.subtitle.borderLeft && T.subtitle.borderLeft !== 'none' ? T.subtitle.borderLeft : (T.subtitle.border ?? 'none')};
      color:${T.subtitle.color};font-family:${FONT};font-size:${SUB_FONT_PX}px;font-weight:${T.subtitle.fontWeight ?? 600};line-height:1.25;
      text-shadow:${T.subtitle.textShadow ?? 'none'};text-align:center;letter-spacing:${T.subtitle.letterSpacing ?? '-.2px'};
      white-space:nowrap;animation:subIn .24s ease-out;">${inner}</div>`;
}

// No holdMs -> sticky, caller disposes. With holdMs -> self-removes and blocks.
// Every subtitle records a cue on __cues so render can emit exact timings.
async function subtitle(text, opts = {}) {
  const html = subtitleHtml(text, opts.emphasis);
  const cue = { text, startMs: Date.now() - __t0, endMs: null };
  __cues.push(cue);
  if (opts.holdMs) {
    await overlay(html, opts.holdMs);
    cue.endMs = cue.startMs + opts.holdMs;
    return { dispose: async () => {} };
  }
  const handle = await overlay(html);
  return { dispose: async () => { cue.endMs = Date.now() - __t0; await handle.dispose(); } };
}

// Hold a sticky subtitle for at least `minMs` while `work` runs underneath it.
// This is the primitive for a scene step: the subtitle stays up for its reading
// (or narration) time and the actions happen under it. Pass HOLD[n] as minMs.
async function subtitleSpan(text, minMs, work, opts = {}) {
  const s = await subtitle(text, { emphasis: opts.emphasis });
  const t0 = Date.now();
  if (work) await work();
  const left = (minMs || readingMs(text)) - (Date.now() - t0);
  if (left > 0) await dwell(left);
  await s.dispose();
  if (opts.gapMs !== 0) await dwell(opts.gapMs ?? T.subtitle.gapMs);   // swap must be visible
}

async function subtitles(items, opts = {}) {
  for (const item of items) {
    await subtitle(item.text, { holdMs: item.holdMs ?? readingMs(item.text), emphasis: item.emphasis });
    await dwell(opts.gapMs ?? T.subtitle.gapMs);
  }
}

// Mid-video section break: card over a blurred page. Blocks for durationMs + ~300ms.
const chapter = (title, opts = {}) => page.screencast.showChapter(title, {
  description: opts.description, duration: opts.durationMs ?? 1800,
});

// Key cap overlay, bottom-left (L3). FR: shown for 1s alongside the key press.
function keycapHtml(keys) {
  const caps = keys.map((k) => `<span style="display:inline-block;min-width:${SUB_FONT_PX * 1.2}px;padding:6px 12px;margin-right:8px;
    border:2px solid rgba(255,255,255,.7);border-bottom-width:4px;border-radius:8px;background:rgba(12,14,18,.75);
    color:#fff;font-family:${FONT};font-size:${Math.round(SUB_FONT_PX * 0.8)}px;font-weight:700;text-align:center">${k}</span>`).join('');
  return `<div style="position:absolute;left:${Math.round(FRAME.width * 0.06)}px;bottom:${Math.round(FRAME.height * 0.07)}px;">${caps}</div>`;
}
const KEY_LABELS = { Meta: '⌘', Control: 'Ctrl', Alt: '⌥', Shift: '⇧', Enter: '⏎', Escape: 'Esc', ArrowDown: '↓', ArrowUp: '↑', ArrowLeft: '←', ArrowRight: '→', Backspace: '⌫' };
async function key(combo, opts = {}) {
  const labels = combo.split('+').map((k) => KEY_LABELS[k] || k.toUpperCase());
  const ms = opts.ms ?? T.keycap.ms;
  const h = await overlay(keycapHtml(labels));
  await page.keyboard.press(combo);
  await dwell(ms);
  await h.dispose();
}

// ---------------------------------------------------------------- L2 cursor
const __cursor = { x: Math.round(FRAME.width / 2), y: Math.round(FRAME.height / 2), handle: null, shown: false };
function cursorSvg(pressed) {
  const s = T.cursor.sizePx;
  const ring = pressed ? `<circle cx="6" cy="6" r="14" fill="none" stroke="rgba(56,189,248,.9)" stroke-width="3"/>` : '';
  return `<svg width="${s + 20}" height="${s + 20}" viewBox="-12 -12 ${s + 20} ${s + 20}" style="overflow:visible">${ring}
    <path d="M0 0 L0 ${s * 0.72} L${s * 0.2} ${s * 0.55} L${s * 0.33} ${s * 0.85} L${s * 0.45} ${s * 0.8} L${s * 0.32} ${s * 0.5} L${s * 0.55} ${s * 0.5} Z"
      fill="#fff" stroke="#0f172a" stroke-width="1.5" stroke-linejoin="round" transform="${pressed ? 'scale(.85)' : ''}"/></svg>`;
}
function cursorHtml(from, to, ms, pressed) {
  const anim = ms > 0 ? `<style>@keyframes cmove{from{transform:translate(${from.x}px,${from.y}px)}to{transform:translate(${to.x}px,${to.y}px)}}</style>` : '';
  const style = ms > 0 ? `animation:cmove ${ms}ms ease-in-out forwards;` : `transform:translate(${to.x}px,${to.y}px);`;
  return `${anim}<div style="position:absolute;left:0;top:0;${style}filter:drop-shadow(0 2px 3px rgba(0,0,0,.35));">${cursorSvg(pressed)}</div>`;
}
// Move the visible cursor (and the real mouse, so hover states fire) over 300-500ms.
// FR-030: the cursor never teleports.
async function moveCursor(x, y, opts = {}) {
  const dist = Math.hypot(x - __cursor.x, y - __cursor.y);
  const ms = opts.ms ?? Math.round(clamp(dist / 2, T.cursor.moveMinMs, T.cursor.moveMaxMs));
  const from = { x: __cursor.x, y: __cursor.y }, to = { x, y };
  const next = await overlay(cursorHtml(from, to, __cursor.shown ? ms : 0, opts.pressed));
  if (__cursor.handle) await __cursor.handle.dispose();
  __cursor.handle = next; __cursor.shown = true;
  const mouseMove = page.mouse.move(x, y, { steps: Math.max(4, Math.round(ms / 40)) });
  await Promise.all([mouseMove, dwell(ms)]);
  __cursor.x = x; __cursor.y = y;
}
async function setCursorPressed(pressed) {
  const next = await overlay(cursorHtml(__cursor, __cursor, 0, pressed));
  if (__cursor.handle) await __cursor.handle.dispose();
  __cursor.handle = next;
}
async function hideCursor() {
  if (__cursor.handle) await __cursor.handle.dispose();
  __cursor.handle = null; __cursor.shown = false;
}

// ---------------------------------------------------------------- L2 effects
function rippleHtml(x, y, opts = {}) {
  const color = opts.color ?? T.click.rippleColor;
  const size = opts.sizePx ?? T.click.rippleSizePx;
  const ms = opts.durationMs ?? T.click.rippleMs;
  const r = size / 2;
  return `
    <style>@keyframes rp{0%{transform:scale(.2);opacity:.9}100%{transform:scale(2.6);opacity:0}}</style>
    <div style="position:absolute;left:${x - r}px;top:${y - r}px;width:${size}px;height:${size}px;border-radius:50%;
      background:radial-gradient(circle,rgba(${color},.55),rgba(${color},0) 70%);border:2px solid rgba(${color},.9);
      animation:rp ${ms}ms ease-out forwards;"></div>`;
}
async function ripple(x, y, opts = {}) {
  const ms = opts.durationMs ?? T.click.rippleMs;
  await overlay(rippleHtml(x, y, opts), ms + 20);
}

// FR-030: cursor moves in, ripple shows, then the real click. Use instead of locator.click().
async function click(target, opts = {}) {
  const l = loc(target);
  const c = center(await boxOf(l, 'click'));
  await moveCursor(c.x, c.y);
  const h = await overlay(rippleHtml(c.x, c.y, opts));
  await l.click(opts.clickOptions || {});
  await dwell(opts.settleMs ?? T.cursor.settleMs);
  await h.dispose();
}
const clickRipple = click;   // draft name

async function dblclick(target, opts = {}) {
  const l = loc(target);
  const c = center(await boxOf(l, 'dblclick'));
  await moveCursor(c.x, c.y);
  await overlay(rippleHtml(c.x, c.y, { durationMs: 300 }), 320);
  const h = await overlay(rippleHtml(c.x, c.y, opts));
  await l.dblclick();
  await dwell(opts.settleMs ?? T.cursor.settleMs);
  await h.dispose();
}

async function rightClick(target, opts = {}) {
  const l = loc(target);
  const c = center(await boxOf(l, 'rightClick'));
  await moveCursor(c.x, c.y);
  const h = await overlay(rippleHtml(c.x, c.y, { color: T.click.rightRippleColor, ...opts }));
  await l.click({ button: 'right' });
  await dwell(opts.settleMs ?? T.cursor.settleMs);
  await h.dispose();
}

// FR-032: typed at 60ms per char; secret fields are filled at once and never shown.
async function typeText(target, text, opts = {}) {
  const l = loc(target);
  const c = center(await boxOf(l, 'typeText'));
  await moveCursor(c.x, c.y);
  await l.click();
  if (opts.secret) { await l.fill(text); }
  else { await l.pressSequentially(text, { delay: opts.msPerChar ?? T.type.msPerChar }); }
  await dwell(opts.settleMs ?? 300);
}

// FR-031: 2px border and a dim outside, auto-released after 1.2s. Blocks.
async function highlight(target, opts = {}) {
  const b = await boxOf(target, 'highlight');
  const ms = opts.durationMs ?? T.highlight.ms;
  const pad = 4;
  const label = opts.label
    ? `<div style="position:absolute;top:${b.y + b.height + 10}px;left:${b.x + b.width / 2}px;transform:translateX(-50%);
        padding:8px 14px;background:${T.highlight.color};border-radius:10px;color:#fff;font-family:${FONT};
        font-size:16px;font-weight:600;white-space:nowrap;">${opts.label}</div>` : '';
  const H = T.highlight;
  const dim = opts.dim === false ? 'transparent' : (H.dim ?? 'transparent');
  const glow = H.glow && H.glow !== 'none' ? `, ${H.glow}` : '';
  const x = b.x - pad, y = b.y - pad, w = b.width + pad * 2, h = b.height + pad * 2;
  let box;
  if (H.corners) {
    // Four corner brackets instead of a full border; the dim (if any) still surrounds the box.
    const L = Math.max(14, Math.round(Math.min(w, h) * 0.18)), bw = H.borderPx, c = H.color;
    const corner = (l, t, bt, br) => `<div style="position:absolute;left:${l}px;top:${t}px;width:${L}px;height:${L}px;
      border-top:${bt ? bw : 0}px solid ${c};border-bottom:${bt ? 0 : bw}px solid ${c};border-left:${br ? 0 : bw}px solid ${c};border-right:${br ? bw : 0}px solid ${c};"></div>`;
    box = `<div style="position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;box-shadow:0 0 0 9999px ${dim}${glow};"></div>`
      + corner(x, y, true, false) + corner(x + w - L, y, true, true) + corner(x, y + h - L, false, false) + corner(x + w - L, y + h - L, false, true);
  } else {
    box = `<div style="position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;
      border-radius:${H.radius ?? 8}px;border:${H.borderPx}px ${H.style ?? 'solid'} ${H.color};
      box-shadow:0 0 0 9999px ${dim}${glow};"></div>`;
  }
  await overlay(box + label, ms);
  return ms;
}

// ---------------------------------------------------------------- L1 zoom
const __zoom = { scale: 1 };
// FR-020/021: scale 1.2-2.0 around the target's center, 600ms in. Blocks until settled.
async function zoom(target, opts = {}) {
  const scale = clamp(opts.scale ?? T.zoom.default, T.zoom.min, T.zoom.max);
  const ms = opts.ms ?? T.zoom.inMs;
  const b = await boxOf(target, 'zoom');
  // Origin = center of the part of the target that is on screen. A point inside the
  // viewport stays fixed under scale(), so the target cannot leave the frame.
  const vx0 = clamp(b.x, 0, FRAME.width), vx1 = clamp(b.x + b.width, 0, FRAME.width);
  const vy0 = clamp(b.y, 0, FRAME.height), vy1 = clamp(b.y + b.height, 0, FRAME.height);
  if (vx1 <= vx0 || vy1 <= vy0) throw new Error('zoom: target is outside the viewport - scroll to it first');
  b.x = vx0; b.width = vx1 - vx0; b.y = vy0; b.height = vy1 - vy0;
  await page.evaluate(({ cx, cy, scale, ms }) => {
    const body = document.body, br = body.getBoundingClientRect();
    document.documentElement.style.overflow = 'hidden';
    body.style.transformOrigin = `${cx - br.left}px ${cy - br.top}px`;
    body.style.transition = `transform ${ms}ms ease-in-out`;
    body.style.transform = `scale(${scale})`;
  }, { cx: b.x + b.width / 2, cy: b.y + b.height / 2, scale, ms });
  __zoom.scale = scale;
  mark('zoomIn', { scale, ms });          // atMs = start of the zoom-in transition
  await dwell(ms + 50);
}
async function zoomOut(opts = {}) {
  const ms = opts.ms ?? T.zoom.outMs;
  mark('zoomOut', { ms });                // atMs = start of the zoom-out transition
  await page.evaluate(({ ms }) => {
    document.body.style.transition = `transform ${ms}ms ease-in-out`;
    document.body.style.transform = 'scale(1)';
  }, { ms });
  await dwell(ms + 50);
  await page.evaluate(() => {
    document.body.style.transform = ''; document.body.style.transition = ''; document.body.style.transformOrigin = '';
    document.documentElement.style.overflow = '';
  });
  __zoom.scale = 1;
}

// ---------------------------------------------------------------- interactions
async function pointerPath(from, to, opts = {}) {
  const steps = opts.steps ?? T.drag.steps;
  const ms = opts.ms ?? Math.round(clamp(Math.hypot(to.x - from.x, to.y - from.y) * 2, T.drag.minMs, T.drag.maxMs));
  for (let i = 1; i <= steps; i++) {
    const e = easeInOut(i / steps);
    const x = from.x + (to.x - from.x) * e, y = from.y + (to.y - from.y) * e;
    await page.mouse.move(x, y);
    const next = await overlay(cursorHtml({ x, y }, { x, y }, 0, true));
    if (__cursor.handle) await __cursor.handle.dispose();
    __cursor.handle = next; __cursor.x = x; __cursor.y = y;
    await dwell(Math.round(ms / steps));
  }
}

// drag(source, target, { mode: 'pointer' | 'html5' }). Pointer: press, staged moves,
// release (dnd-kit, SortableJS, pointer handlers). html5: dragstart/dragover/drop
// with a DataTransfer (native draggable). The cursor animates in both modes.
async function drag(source, target, opts = {}) {
  const mode = opts.mode ?? 'pointer';
  const sb = await boxOf(source, 'drag source');
  const from = opts.fromOffset ? { x: sb.x + opts.fromOffset.x, y: sb.y + opts.fromOffset.y } : center(sb);
  await moveCursor(from.x, from.y);
  const tb = await boxOf(target, 'drag target');
  const to = opts.toOffset ? { x: tb.x + opts.toOffset.x, y: tb.y + opts.toOffset.y } : center(tb);
  if (mode === 'pointer') {
    await page.mouse.down();
    await setCursorPressed(true);
    await dwell(120);
    await pointerPath(from, to, opts);
    await dwell(opts.pauseMs ?? T.drag.pauseMs);
    await page.mouse.up();
    await setCursorPressed(false);
  } else if (mode === 'html5') {
    const dt = await page.evaluateHandle(() => new DataTransfer());
    await loc(source).dispatchEvent('dragstart', { dataTransfer: dt });
    await setCursorPressed(true);
    await pointerPath(from, to, opts);
    await loc(target).dispatchEvent('dragenter', { dataTransfer: dt });
    await loc(target).dispatchEvent('dragover', { dataTransfer: dt, clientX: to.x, clientY: to.y });
    await dwell(opts.pauseMs ?? T.drag.pauseMs);
    await loc(target).dispatchEvent('drop', { dataTransfer: dt, clientX: to.x, clientY: to.y });
    await loc(source).dispatchEvent('dragend', { dataTransfer: dt });
    await setCursorPressed(false);
  } else {
    throw new Error(`drag: unknown mode '${mode}' (pointer | html5)`);
  }
  await ripple(to.x, to.y);
  mark('drag', { mode });
}

// dropFile(target, files): a file-icon ghost flies in from off-screen, then the files
// are injected. Files: paths (need an <input type=file> inside or at the target) or
// { name, mimeType, content } objects (dropped via a DataTransfer).
async function dropFile(target, files, opts = {}) {
  const tb = await boxOf(target, 'dropFile');
  const to = center(tb);
  const ms = opts.ms ?? 900;
  const from = { x: -80, y: Math.max(40, to.y - 200) };
  const ghost = `
    <style>@keyframes fly{from{transform:translate(${from.x}px,${from.y}px) scale(.8);opacity:.6}to{transform:translate(${to.x - 24}px,${to.y - 28}px) scale(1);opacity:1}}</style>
    <div style="position:absolute;left:0;top:0;animation:fly ${ms}ms ease-in-out forwards;">
      <svg width="48" height="56" viewBox="0 0 48 56"><path d="M4 2h26l14 14v38H4z" fill="#fff" stroke="#0f172a" stroke-width="2"/><path d="M30 2v14h14" fill="#e2e8f0" stroke="#0f172a" stroke-width="2"/></svg></div>`;
  const l = loc(target);
  await l.dispatchEvent('dragenter');
  const h = await overlay(ghost);
  await dwell(ms);
  const paths = files.filter((f) => typeof f === 'string');
  const blobs = files.filter((f) => typeof f !== 'string');
  if (paths.length) {
    const input = (await l.evaluate((el) => el.matches('input[type=file]'))) ? l : l.locator('input[type=file]').first();
    await input.setInputFiles(paths);
  }
  if (blobs.length) {
    const dt = await page.evaluateHandle((items) => {
      const dt = new DataTransfer();
      for (const it of items) dt.items.add(new File([it.content], it.name, { type: it.mimeType || 'application/octet-stream' }));
      return dt;
    }, blobs);
    await l.dispatchEvent('drop', { dataTransfer: dt });
  }
  await l.dispatchEvent('dragleave');
  await h.dispose();
  await ripple(to.x, to.y);
  mark('dropFile', { count: files.length });
}

// scrollTo(target | 'window', { toRatio | byPx, axis }). Eased, capped at 60% of the
// viewport height per second, then 800ms still. L3 subtitles do not move.
async function scrollTo(target, opts = {}) {
  const axis = opts.axis === 'x' ? 'x' : 'y';
  const isWindow = target === 'window' || target === 'document';
  const selector = isWindow ? null : (typeof target === 'string' ? target : null);
  if (!isWindow && !selector) throw new Error('scrollTo: pass a selector string or "window"');
  const plan = await page.evaluate(({ selector, axis, byPx, toRatio }) => {
    const el = selector ? document.querySelector(selector) : document.scrollingElement;
    if (!el) return null;
    const max = axis === 'x' ? el.scrollWidth - el.clientWidth : el.scrollHeight - el.clientHeight;
    const from = axis === 'x' ? el.scrollLeft : el.scrollTop;
    let to = byPx != null ? from + byPx : Math.round(max * (toRatio ?? 1));
    to = Math.max(0, Math.min(max, to));
    return { from, to, max };
  }, { selector, axis, byPx: opts.byPx ?? null, toRatio: opts.toRatio ?? null });
  if (!plan) throw new Error(`scrollTo: no element matches ${selector}`);
  if (plan.max <= 0) throw new Error(`scrollTo: ${selector || 'window'} does not scroll on ${axis}`);
  const dist = Math.abs(plan.to - plan.from);
  const minMs = Math.round((dist / (FRAME.height * T.scroll.maxViewportPerSec)) * 1000);
  const ms = Math.max(opts.ms ?? 0, minMs, 600);
  const steps = Math.max(10, Math.round(ms / 40));
  for (let i = 1; i <= steps; i++) {
    const v = Math.round(plan.from + (plan.to - plan.from) * easeInOut(i / steps));
    await page.evaluate(({ selector, axis, v }) => {
      const el = selector ? document.querySelector(selector) : document.scrollingElement;
      if (axis === 'x') el.scrollLeft = v; else el.scrollTop = v;
    }, { selector, axis, v });
    await dwell(Math.round(ms / steps));
  }
  await dwell(opts.settleMs ?? T.scroll.settleMs);
  mark('scroll', { axis, from: plan.from, to: plan.to });
  return plan;
}
const scrollPanel = scrollTo;   // draft name

// hoverOn(target): cursor in, real hover, stay at least 1200ms so a tooltip can be read.
async function hoverOn(target, opts = {}) {
  const l = loc(target);
  const c = center(await boxOf(l, 'hoverOn'));
  await moveCursor(c.x, c.y);
  await l.hover();
  await dwell(opts.ms ?? T.hover.minMs);
}

// resize(handle, { dx, dy }): pointer drag of a separator by a delta.
async function resize(handle, opts = {}) {
  const hb = await boxOf(handle, 'resize handle');
  const from = center(hb);
  const to = { x: from.x + (opts.dx ?? 0), y: from.y + (opts.dy ?? 0) };
  await moveCursor(from.x, from.y);
  await page.mouse.down();
  await setCursorPressed(true);
  await pointerPath(from, to, opts);
  await page.mouse.up();
  await setCursorPressed(false);
  await dwell(opts.settleMs ?? 400);
  mark('resize', { dx: opts.dx ?? 0, dy: opts.dy ?? 0 });
}

// slide(range, value): drag the knob of an <input type=range> (or any role=slider
// with aria-valuemin/max) to `value`, so the change is visible and input events fire.
async function slide(target, value, opts = {}) {
  const l = loc(target);
  const b = await boxOf(l, 'slide');
  const { min, max, cur } = await l.evaluate((el) => ({
    min: Number(el.min ?? el.getAttribute('aria-valuemin') ?? 0),
    max: Number(el.max ?? el.getAttribute('aria-valuemax') ?? 100),
    cur: Number(el.value ?? el.getAttribute('aria-valuenow') ?? 0),
  }));
  const xAt = (v) => b.x + 8 + ((v - min) / (max - min)) * (b.width - 16);
  const from = { x: xAt(cur), y: b.y + b.height / 2 }, to = { x: xAt(value), y: from.y };
  await moveCursor(from.x, from.y);
  await page.mouse.down();
  await setCursorPressed(true);
  await pointerPath(from, to, opts);
  await page.mouse.up();
  await setCursorPressed(false);
  const got = await l.evaluate((el) => Number(el.value));
  if (Number.isFinite(got) && Math.abs(got - value) > (max - min) * 0.05) {
    await l.evaluate((el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }, value);
  }
  await dwell(opts.settleMs ?? 400);
  mark('slide', { value });
}

// pan(canvas, { dx, dy }) and wheelZoom(canvas, { deltaY, steps }) for canvas surfaces.
// Not combined with page zoom (FR table): the canvas is the thing that moves.
async function pan(target, opts = {}) {
  const b = await boxOf(target, 'pan');
  const from = center(b), to = { x: from.x + (opts.dx ?? 0), y: from.y + (opts.dy ?? 0) };
  await moveCursor(from.x, from.y);
  await page.mouse.down();
  await setCursorPressed(true);
  await pointerPath(from, to, opts);
  await page.mouse.up();
  await setCursorPressed(false);
  await dwell(opts.settleMs ?? 400);
  mark('pan', { dx: opts.dx ?? 0, dy: opts.dy ?? 0 });
}
async function wheelZoom(target, opts = {}) {
  const c = center(await boxOf(target, 'wheelZoom'));
  await moveCursor(c.x, c.y);
  const steps = opts.steps ?? 5, delta = (opts.deltaY ?? -300) / steps;
  for (let i = 0; i < steps; i++) { await page.mouse.wheel(0, delta); await dwell(opts.stepMs ?? 120); }
  await dwell(opts.settleMs ?? 400);
  mark('wheelZoom', { deltaY: opts.deltaY ?? -300 });
}

// waitStream(target, { until: 'stable' | 'attr' | 'text', attr, value, stableMs, timeoutMs }).
// Waits for a streaming answer or progress state to finish; returns elapsed ms and
// records a `stream` mark so compose can speed up a span longer than 15s (FR table).
async function waitStream(target, opts = {}) {
  const l = loc(target);
  const start = Date.now();
  const timeout = opts.timeoutMs ?? 60000;
  const until = opts.until ?? 'stable';
  if (until === 'attr') {
    await page.waitForFunction(({ sel, attr, value }) => {
      const el = document.querySelector(sel); return el && el.getAttribute(attr) === value;
    }, { sel: typeof target === 'string' ? target : null, attr: opts.attr, value: opts.value }, { timeout });
  } else if (until === 'text') {
    await l.filter({ hasText: opts.value }).waitFor({ timeout });
  } else {
    const stableMs = opts.stableMs ?? 1000;
    let last = null, since = Date.now();
    while (Date.now() - start < timeout) {
      const now = await l.evaluate((el) => el.textContent.length).catch(() => -1);
      if (now !== last) { last = now; since = Date.now(); }
      else if (Date.now() - since >= stableMs && now > 0) break;
      await dwell(150);
    }
  }
  const elapsed = Date.now() - start;
  mark('stream', { startMs: start - __t0, endMs: Date.now() - __t0, speedup: elapsed > T.stream.speedupAfterMs });
  return elapsed;
}

// padTo(ms): hold the last frame until the scene has run `ms` since recording started,
// so a clip is never shorter than its planned dwellMs. Does nothing if already past it.
async function padTo(ms) {
  const left = (ms || 0) - (Date.now() - __t0);
  if (left > 0) await dwell(left);
}

// waitFor(selector | { url } ): the only sanctioned wait (FR-054). No fixed sleeps in bodies.
async function waitFor(target, opts = {}) {
  if (typeof target === 'object' && target.url) return page.waitForURL(target.url, { timeout: opts.timeoutMs ?? 20000 });
  return loc(target).waitFor({ state: opts.state ?? 'visible', timeout: opts.timeoutMs ?? 15000 });
}

// ---------------------------------------------------------------- cards
function cardHtml(title, tagline, brand, outro, cta) {
  const from = outro ? 'scale(1.04)' : 'scale(.94)';
  return `
    <style>
      @keyframes cardIn{from{opacity:0;transform:${from}}to{opacity:1;transform:scale(1)}}
      @keyframes subUp{0%{opacity:0;transform:translateY(12px)}100%{opacity:1}}
    </style>
    <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;
      background:${T.card.background};font-family:${FONT};">
      <div style="display:flex;flex-direction:column;align-items:center;gap:18px;width:100%;animation:cardIn .5s ease-out;">
      ${brand ? `<div style="color:${T.card.brandColor};font-size:${Math.round(FRAME.height * 0.017)}px;font-weight:700;letter-spacing:2px;text-transform:uppercase;">${brand}</div>` : ''}
      <div style="color:${T.card.titleColor};font-size:${Math.round(FRAME.height * 0.052)}px;font-weight:800;letter-spacing:-1.5px;text-align:center;max-width:82%;">${title}</div>
      ${tagline ? `<div style="color:${T.card.taglineColor};font-size:${Math.round(FRAME.height * 0.022)}px;font-weight:500;text-align:center;max-width:74%;animation:subUp .5s ease-out .2s both;">${tagline}</div>` : ''}
      ${cta ? `<div style="margin-top:${Math.round(FRAME.height * 0.03)}px;padding:10px 22px;border:2px solid ${T.card.brandColor};border-radius:999px;color:${T.card.brandColor};font-size:${Math.round(FRAME.height * 0.02)}px;font-weight:600;animation:subUp .5s ease-out .4s both;">${cta}</div>` : ''}
      </div>
    </div>`;
}
async function card(opts) {
  const ms = opts.durationMs ?? opts.holdMs ?? 2500;
  await hideActions();
  await hideCursor();
  await overlay(cardHtml(opts.title, opts.subtitle ?? opts.tagline, opts.brand, !!opts.outro, opts.cta), ms);
}
const intro = (opts) => card({ ...opts, outro: false });
const outro = (opts) => card({ durationMs: 3000, ...opts, outro: true });

// ---------------------------------------------------------------- survey helpers
async function panAcross(locators, opts = {}) {
  const each = opts.eachMs ?? 1100;
  for (const l of locators) await highlight(l, { durationMs: each, label: opts.labels ? opts.labels.shift() : undefined, dim: false });
}
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
    const interactive = [...document.querySelectorAll(sel)].filter((el) => visible(el) && !el.disabled).length;
    return { textChars, interactive };
  });
  return { ...raw, dwellMs: dwellFromDensity(raw) };
}
