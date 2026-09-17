# Storyboard

`demo/storyboard.json` is the source of truth. Scene scripts are generated from it; it is never generated from them.

## Schema

```json
{
  "name": "radar-user-guide",
  "baseUrl": "https://dev.example.com",
  "video": { "width": 1280, "height": 720 },
  "authState": "demo/.auth.json",
  "narration": { "enabled": true, "voice": "Yuna", "rate": 180 },
  "scenes": [
    {
      "id": "01-intro",
      "kind": "intro",
      "title": "RA-DAR 사용 안내",
      "subtitle": "주요 화면과 사용 흐름",
      "durationMs": 2500,
      "transitionOut": { "type": "fade", "durationMs": 600 }
    },
    {
      "id": "03-dashboard",
      "kind": "scene",
      "url": "/dashboard",
      "chapter": { "title": "대시보드", "description": "지표 확인", "durationMs": 1800 },
      "density": { "textChars": 940, "interactive": 12 },
      "dwellMs": 6800,
      "steps": [
        { "action": "subtitle", "text": "대시보드에서 핵심 지표를 한눈에 확인합니다", "holdMs": 3200 },
        { "action": "subtitle", "text": "기간 변경", "narration": "기간을 바꾸면[[slnc 300]] 그래프가 즉시 갱신됩니다" },
        { "action": "clickRipple", "locator": "getByRole('button', { name: '월간' })" },
        { "action": "subtitle", "text": "기간을 바꾸면 그래프가 즉시 갱신됩니다", "holdMs": 3000 },
        { "action": "wait", "ms": 1200 }
      ],
      "transitionOut": { "type": "slideleft", "durationMs": 500 }
    },
    {
      "id": "09-outro",
      "kind": "outro",
      "title": "감사합니다",
      "subtitle": "문의: 개발팀",
      "durationMs": 3000
    }
  ]
}
```

`kind` is `intro`, `scene`, or `outro`. The last scene has no `transitionOut`.

The step list may be called `steps` or `beats` — the tooling reads either, `beats` first. Use `beats` when a scene carries more than subtitles (scrolls, highlights, fills, selects) and give each one a `why` so the next person knows what the beat is for.

`locator` is a Playwright locator expression as a **string**, written into the scene body as `page.<expr>`. Take it from the phase-1 snapshot; never invent one.

Each scene needs a matching body file at `demo/scenes/<id>.body.js`. The storyboard is the plan; the body is the executable form of that plan. Keep them in step - `dv.py render` reports the drift between a scene's `dwellMs` and the clip it actually produced, and `compose` warns when a clip is too short for the subtitles it carries.

## Dwell time from information density

How long a page stays on screen is decided by how much the viewer has to take in - not by a fixed number. `density()` (from `scripts/prelude.js`, in scope in every scene body) returns `textChars` (visible text length) and `interactive` (count of enabled buttons, links, inputs, selects).

```
dwellMs = clamp(
  2000                                  // floor: time to register the page changed
  + min(textChars, 1800) / 1800 * 4000  // reading load, capped
  + min(interactive, 15) * 200,          // scanning load, capped
  2500, 9000
)
```

Then **override it upward** where a scene has more subtitles than the formula's time allows: the dwell must be at least the sum of its subtitle hold times plus 600ms per action. `compose` warns when a scene's clip is shorter than its subtitles need.

Cap any single scene at 9s. A page that genuinely needs longer is two scenes.

## Subtitle duration

A subtitle that disappears before it can be read is worse than no subtitle.

```
holdMs = max(1800, ceil(chars / 5) * 1000 + 600)
```

5 Korean characters per second is a comfortable read. `readingMs()` is in scope in every scene body - use it rather than guessing.

With narration on, `dv.py narrate` overrides this with `max(readingMs, spokenMs + 400)` after measuring the actual speech. Do not hand-tune `holdMs` afterwards; change the text instead. See `narration.md`.

Other rules:

- One idea per subtitle. Two sentences means two subtitles.
- Under 40 characters. Longer wraps and covers the UI.
- Describe **what the user can do**, not what the mouse is doing. "기간을 바꾸면 그래프가 즉시 갱신됩니다", not "월간 버튼을 클릭합니다".
- Bottom-center, always. Moving subtitles around makes the viewer hunt for them.
- Leave a ≥300ms gap between consecutive subtitles so the swap is visible.

## Pacing

- Intro 2-3s, outro 2-4s. Longer feels like a corporate title sequence.
- 600ms of stillness after a click before the next action, so the result registers.
- Type with `pressSequentially(..., { delay: 50 })`. Instant text looks like a glitch.
- Total under 90s. Past that, split into multiple videos.
