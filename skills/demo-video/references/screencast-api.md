# Screencast API

`page.screencast` - Playwright 1.60+, driven through `@playwright/cli`. `dv.py doctor` reports the installed versions.

## The execution sandbox

`playwright-cli run-code` evaluates the file in a bare `vm` context. Absent: `require`, `process`, `module`, `__dirname`, dynamic `import()`. Present: standard JS globals (including `Date.now`) and `page`.

You therefore cannot import a helper library. `dv.py render` inlines `scripts/prelude.js` into every scene instead, so its functions are simply in scope.

## Scene bodies

With schemaVersion 2, `dv.py render` generates every body from the storyboard (marker line `// @generated`). Remove the marker to take a body over by hand - only for logic the action list cannot express.

A scene body (`demo/scenes/<id>.body.js`) is **statements only** - no wrapper, no exports:

```js
await page.goto(BASE + '/dashboard');
const sub = await subtitle('대시보드에서 핵심 지표를 확인합니다');
await dwell(4000);
await sub.dispose();
```

`dv.py render` assembles it into:

```js
async page => {
  const BASE = '<app url from config.json>';
  const ACCOUNTS = { /* demo/.accounts.json, gitignored */ };
  const HOLD = [ /* holdMs per step */ ], DWELL = <scene dwellMs>;
  const THEME = { /* assets/theme.json */ }, FRAME = { width, height };
  /* prelude.js */
  await startRec('demo/scenes/<id>.webm', { width, height });
  const __t0 = Date.now();
  let __ms = 0;
  try { /* your body */ } finally { __ms = Date.now() - __t0; await stopRec(); }
  return __ms;
}
```

So: never call `screencast.start()` or `stop()` yourself, and never pick the output path - both are handled. A throw in the body still flushes the clip, which is why a broken scene leaves a short file rather than a corrupt one.

A body may start with off-camera setup. Everything above a `// ---record---` line runs *before* `startRec`, so logging in or opening a modal does not appear in the clip:

```js
await ensureLogin(ACCOUNTS.kim);
await openCase('RA-2026-133');
// ---record---
await subtitleSpan('…', HOLD[0], async () => { … });
```

**Every scene must establish its own state.** Generated bodies go through `about:blank` before their `goto`, because a hash-only navigation keeps a single-page app's memory from the previous scene. Do the same in a hand-written body. `dv.py render` runs scenes in one browser, so state carries over - but a scene that relies on the previous one breaks the moment you re-render it alone, and one failure cascades through the rest. Put a login routine in `demo/prelude.js` (injected into every body) and call it at the top of each scene that needs a session.

Credentials go in `demo/.accounts.json` (add it to `.gitignore`) and are reached as `ACCOUNTS.<key>.<field>`. Never type a password into a scene body or the storyboard.

For a scene whose `kind` is `intro` or `outro`, `dv.py render` navigates to `about:blank` **before** recording starts, so nothing flashes under the card's fade-in. Do not navigate in those bodies.

## Blocking semantics - the one thing that ruins pacing

Measured behaviour (re-measure if a Playwright upgrade changes pacing):

| Call | Behaviour |
|---|---|
| `showOverlay(html)` | returns in ~10ms, overlay is sticky until `.dispose()` |
| `showOverlay(html, { duration })` | **blocks for `duration`**, then self-removes |
| `showChapter(title, { duration })` | **blocks for `duration` + ~300ms** of card animation |
| `start()` / `stop()` | ~1ms / ~40ms |

Any helper that takes a duration therefore already consumes it. Adding `await dwell(sameDuration)` after it doubles the scene. The prelude helpers are written against these semantics - use them rather than calling `screencast.*` directly.

## The frozen tail

The recorder keeps the container running for up to ~1s after `stop()`, freezing the last frame. `dv.py render` measures the real elapsed time and trims each clip to it with a lossless stream copy. If you record by hand, expect every clip to be about a second longer than it looks.

## Methods

| Method | Notes |
|---|---|
| `start({ path, size, quality?, onFrame? })` | `size: { width, height }`. Output is WebM/VP8 at 25 fps. No fps option exists. **The viewport is drawn in the frame's top-left and the rest is padded** - a viewport smaller than `size` records the app in a corner with dead margins. `dv.py render` sets the viewport to the video size for you; never rely on the default (1280x720). |
| `stop()` | Flushes the file. The clip is unusable until this returns. |
| `showChapter(title, { description?, duration?, styleSheet? })` | Full-screen card over a blurred backdrop. **Blocks until `duration` expires** (default 2000ms), then auto-removes. |
| `showOverlay(html, { duration? })` | Arbitrary HTML. Returns a disposable. With `duration` it self-removes; without, it is sticky until `.dispose()`. |
| `showActions({ cursor?, duration?, fontSize?, position? })` | Annotates every subsequent action with a callout naming it and highlighting the target. |
| `hideActions()` | Stops annotating. |
| `hideOverlays()` / `showOverlays()` | Hide/show all overlays without disposing them. |

### showActions options

- `cursor`: `'pointer'` (default) animates a mouse pointer from the previous action point to the next; `'none'` disables it. Added in 1.61.
- `duration`: ms each callout stays. Default 500. Use 800-1000 for a demo - 500 is too fast to read.
- `fontSize`: px. Default 24.
- `position`: `'top-right'` (default), `'top-left'`, `'top'`, `'bottom-left'`, `'bottom'`, `'bottom-right'`. Keep it away from the subtitle: subtitles sit bottom-center, so use a `top-*` position.

Callout text is Playwright's own wording (`Click`, `Type "..."`, `Press "Enter"`) and is **not** customizable. It is English. If the video must be Korean-only, call `hideActions()` and rely on subtitles plus the ripple effect instead.

## Overlays render above everything

Overlays are `pointer-events: none` and are composited above all page content. This is why subtitles stay in front and never block a click. You can keep a sticky subtitle up while clicking, filling, and navigating.

**They do not survive navigation.** Re-show any sticky overlay after `goto`, or show it after the navigation completes.

## Ordering rules

- `start()` before the first `goto` if the navigation itself should be on camera.
- `showChapter()` blocks - it consumes its full `duration`. Budget it in the scene length.
- `stop()` last. Anything after it is not recorded.
- `showActions()` applies to actions that come **after** the call.

## Minimal scene body

```js
await page.goto(BASE + '/dashboard');
await chapter('대시보드', { description: '핵심 지표 확인', durationMs: 1800 });
await showActions();

const sub = await subtitle('대시보드에서 핵심 지표를 한눈에 확인합니다');   // sticky
await clickRipple(page.getByRole('button', { name: '월간' }));
await dwell(1200);
await sub.dispose();

await subtitle('기간을 바꾸면 그래프가 즉시 갱신됩니다', { holdMs: readingMs('기간을 바꾸면 그래프가 즉시 갱신됩니다') });
```

The last call blocks for its own `holdMs`, so the scene ends when the subtitle clears. No trailing `dwell` needed.
