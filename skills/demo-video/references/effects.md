# Effects

All effects are screencast overlays - HTML rendered above the page. Nothing here depends on ffmpeg text filters (this build has none).

Every helper below is already in scope in a scene body, takes no `page` argument, and is defined in `scripts/prelude.js`. Nothing is imported.

**A helper that takes a duration blocks for it.** Do not add your own wait afterwards - see `screencast-api.md`.

## Intro / outro

`intro({ title, subtitle?, brand?, durationMs? })` and `outro({ ... })` - blocks for `durationMs` (default 2500 / 3000).

A full-viewport opaque card on a dark gradient: title scales up from 0.94 with a fade, subtitle follows 200ms later, outro reverses the motion. Both call `hideActions()` first so no action callout lands on the card.

Do not navigate in an intro or outro body - `dv.py render` already blanks the page before recording.

Do not use `chapter()` for the intro. Chapter cards blur the page behind them, which reads as a rendering fault on a blank page.

## Chapter break

`chapter(title, { description?, durationMs? })` - blocks for `durationMs` + ~300ms.

Card over a blurred snapshot of the live page. Use it between sections mid-video, where the blurred page is the point.

## Layers

- L3 (subtitles, chapter cards, key caps) are screencast overlays in the browser top layer: they never move or scale when the page zooms or scrolls.
- L2 (cursor, ripple, highlight) are overlays drawn at the target's live `boundingBox()`, so they land on the zoomed element. Inside the overlay container the subtitle sits above them (z-index 30 vs 20/15/10): a highlight's dim never darkens the subtitle.
- L1 (the app) is zoomed with a transform on `<body>` around the target's visible center.

## Cursor and click

`click(target)` - the cursor travels 300-500ms (never teleports), a ring expands from the element's center while the real click happens, then 600ms settle. `dblclick`, `rightClick`, `typeText(target, text, { secret })` follow the same shape. `clickRipple` is an alias kept for older bodies.

The cursor is our own SVG overlay; Playwright's `showActions` callouts are English and off by default.

## Zoom

`zoom(target, { scale })` scales `<body>` 1.2-2.0 (default 1.5) around the visible center of the target over 600ms; `zoomOut()` returns over 500ms. Both block until settled and record `zoomIn` / `zoomOut` marks. Draw highlights after the zoom, not during it.

## Subtitles

`subtitle(text, { holdMs?, position? })` returns a disposable.

- No `holdMs`: **sticky and non-blocking**. Hold it across several actions, then `.dispose()`.
- With `holdMs`: **blocks** for that long, then self-removes. `readingMs(text)` gives the right value.
- Bottom-center by default (`bottom`, `top`, `bottom-left`, `bottom-right`), `pointer-events: none`, above all page content.
- Font stack: `Apple SD Gothic Neo`, `Pretendard`, `Noto Sans KR`, then the system sans-serif. Whichever the machine has first is used; check Korean rendering in the first clip's frame tile.

`subtitles([{ text, holdMs? }, ...])` plays several in order with a 300ms gap and returns when the last clears.

Subtitles do not survive navigation. Re-show after `goto`.

## Element highlight

`highlight(target, { label?, durationMs? })` - blocks for `durationMs` (default 1200).

2px border with the rest of the frame dimmed, optionally a labelled callout under it. For "this is the field that matters". Do not stack it with a subtitle in the same instant - the viewer reads one thing at a time.

## Dwell and density

`dwell(ms)` holds the current view. `density()` returns `{ textChars, interactive, dwellMs }` for the current page - use it to set a scene's dwell time from what is actually on screen rather than guessing.

## Cursor and action callouts

```js
await showActions();   // cursor:'pointer', duration:900, fontSize:20, position:'top-right'
```

Gives an animated pointer travelling between action points plus a callout per action. The callout text is Playwright's own and is **English and not customizable** (`Click`, `Type "..."`, `Press "Enter"`).

For a Korean-only video: `await hideActions()` and carry the explanation in subtitles, keeping the ripple for click feedback. State which choice you made when reporting.

## Interactions

`drag`, `dropFile`, `scrollTo`, `hoverOn`, `resize`, `slide`, `pan`, `wheelZoom`, `key`, `waitStream` - see `interactions.md`.

## Scene transitions

Transitions happen at compose time, not record time - see `compose.md`. Do not try to fake a transition inside a clip with a fading overlay; it will not line up with the cut.
