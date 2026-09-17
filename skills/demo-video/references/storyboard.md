# Storyboard (schemaVersion 2)

`demo/storyboard.json` is the source of truth. Scene bodies are generated from it by `dv.py render`; it is never generated from them. Every number a machine can compute is filled by `dv.py validate --fix`, never typed by hand.

## Schema

```json
{
  "schemaVersion": 2,
  "meta": { "name": "camino-demo", "size": [1920, 1080], "narration": false, "authState": "demo/.auth.json" },
  "intro": { "source": "html", "template": "default", "brand": "Camino", "title": "실패한 테스트, 아침에 3분이면 끝", "tagline": "E2E 테스트 자동화", "holdMs": 2500 },
  "outro": { "source": "html", "template": "default", "title": "Camino", "cta": "camino.example.com 에서 시작하기", "holdMs": 3000 },
  "scenes": [
    {
      "id": "01-dashboard-fail",
      "url": "/dashboard",
      "page": "dashboard",
      "waitFor": "[data-testid=fail-list]",
      "transitionIn": { "type": "fade", "ms": 400 },
      "mutates": false,
      "setup": [],
      "steps": [
        {
          "subtitle": { "text": "밤새 돌아간 테스트 중 실패한 3건만 먼저 봅니다", "emphasis": "실패한 3건", "hook": true },
          "actions": [
            { "type": "highlight", "target": "[data-testid=stat-fail]" },
            { "type": "zoom", "target": "[data-testid=fail-list]", "scale": 1.5 },
            { "type": "click", "target": "[data-testid=fail-row-1]" },
            { "type": "waitFor", "target": "[data-testid=fail-detail]" },
            { "type": "zoomOut" }
          ],
          "holdMs": 3475
        }
      ],
      "dwellMs": 6867,
      "interactions": [
        { "kind": "scroll", "target": "[data-testid=log-scroll]",
          "evidence": { "source": "app.css: .scroll overflow:auto", "screen": "로그 패널 내부 스크롤" },
          "decision": "skip", "reason": "이 장면의 자막이 다루지 않음" }
      ]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `meta.size` | frame size; even integers. The app URL is not here - it lives in `demo/config.json` (`dv.py init`). |
| `intro` / `outro` | `source: "html"` renders `assets/<intro|outro>/<template>.html` with `title`, `tagline`, `brand`, `cta`; `source: "video"` with `path` is normalized by `compose`. Intro ≤ 2.5s, outro 2-4s with a `cta` (FR-044). |
| `url` | path appended to the app URL. `page` is the survey page id, used for density rules. |
| `waitFor` | selector that must be visible before recording starts. |
| `transitionIn` | how this scene is entered: `fade` 400ms default, `cut` for a scene on the same page. 300-700ms (FR-043). |
| `mutates` | scene changes app data. `render --jobs` runs it and everything after it sequentially; `config.resetCommand` runs before it. |
| `setup` | actions run before recording (off camera). |
| `steps[]` | one subtitle with the actions that happen under it. First subtitle of the video carries `hook: true` (FR-044). |
| `holdMs`, `dwellMs` | filled by `validate --fix`. `holdMs = clamp(chars × 125 + 600, 1500, 7000)`, `dwellMs ≥ Σ holdMs + 600 × actions + gaps`, and at least the density floor when the page first appears (a `cut` scene on the same page pays only the 2.5s minimum). Scene cap 9s. |
| `interactions[]` | FR-060: what the page can do and whether the video shows it. See `interactions.md`. |

## Actions

Selectors are CSS or Playwright selectors as strings and must come from `survey.json` `locators` - `validate` rejects a selector the survey never saw.

| type | fields | plays as |
|---|---|---|
| `goto` | `url` | navigation on camera |
| `click` | `target` | cursor moves 300-500ms, ripple, click, 600ms settle |
| `type` | `target`, `value`, `secret?` | 60ms per char. `secret: true` fills at once and the value must be `ACCOUNTS.<key>.<field>` |
| `hover` | `target`, `ms?` | cursor in, real hover, ≥ 1200ms |
| `scroll` | `target` or `"window"`, `toRatio` or `byPx`, `axis?` | eased, ≤ 60% viewport/s, 800ms still |
| `waitFor` | `target` or `url` | the only wait allowed (FR-054) |
| `zoom` / `zoomOut` | `target`, `scale` 1.2-2.0 | body transform around the target's visible center; one zoom per step, `zoomOut` before the scene ends |
| `highlight` | `target`, `label?` | 2px border, outside dim, 1.2s |
| `chapter` | `title`, `description?` | card over a blurred page |
| `drag` | `source`, `target`, `mode: pointer|html5`, `toOffset?` | see `interactions.md` |
| `dropFile` | `target`, `files[]` | file ghost flies in, then `setInputFiles` (paths) or a DataTransfer drop (`{name, mimeType, content}`) |
| `resize` | `target`, `dx`, `dy` | pointer drag of a separator |
| `slide` | `target`, `value` | drag the knob of a range input |
| `pan` / `wheelZoom` | `target`, `dx`/`dy` or `deltaY` | canvas gestures; never with page `zoom` |
| `key` | `combo` e.g. `Meta+k` | key cap overlay bottom-left + key press |
| `dblclick` / `rightClick` | `target` | two ripples / orange ripple |
| `waitStream` | `target`, `until: stable|attr|text`, `attr`, `value` | waits for streaming to finish; spans over 15s get a `stream` mark for speed-up |

`toOffset: {x, y}` lands a drag at an offset from the target's top-left instead of its center - use it when the app decides "before/after" by pointer position.

## Workflow

```
write storyboard.json  →  dv.py validate --fix  →  dv.py sheet --capture  →  show sheet.html  →  dv.py approve storyboard
```

`validate` exit 1 lists the rule numbers. Fix the storyboard, never the rule. A subtitle over 32 weighted characters (hangul 1, latin/space/punctuation 0.5) is split into two steps, not shortened.

## Migrating from schemaVersion 1

v1 (the draft) had `video{width,height}`, `baseUrl`, `transitionOut`, intro/outro as scenes with `kind`, and steps as `{action: "subtitle"|"clickRipple"|...}`. `validate` refuses v1. Move the app URL to `config.json`, put the intro/outro into their objects, turn each `subtitle` step into a `steps[]` entry whose following actions become its `actions[]`, and let `--fix` fill the times.
