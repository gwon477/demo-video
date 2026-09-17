---
name: demo-video
description: Produce a polished product demo / walkthrough video of a real running web app by first understanding the solution's structure and features, then driving a real browser through a scripted user scenario, with an intro and outro card, scene transitions, click ripple effects, an animated cursor, always-on-top Korean subtitles that explain what the user can do on each page, and an optional Korean voice-over narration track plus an .srt sidecar. Use this whenever the user asks for a 시연 영상, 데모 영상, demo video, walkthrough, 화면 녹화, screen recording, product tour, 사용법 영상, release demo, or a video of a feature or a screen - and also when they ask to re-record, re-cut, restyle, or extend an existing demo video, or to write or revise its 콘티 / storyboard. It surveys the system's routes, features, roles and vocabulary first, writes a user scenario and gets it approved, writes a detailed storyboard (intro, outro, per-scene subtitles, effects, dwell time derived from each page's information density), generates narration whose pauses, pace and emphasis are derived from each subtitle's own wording, verifies that page, subtitle and voice stay in sync, renders scene clips with Playwright's screencast API, composes them with ffmpeg transitions into an mp4 with the voice-over muxed in, and files everything under the project's demo/ directory. Also use it when the user asks to add, regenerate, or remove 나레이션 / 음성 / voice-over / TTS / 자막 파일 on a demo.
license: MIT
metadata:
  version: "1.0"
---

# Demo video

Record a demo of a **real, running** web app - not a mockup. The output is an mp4 with an intro card, per-scene subtitles pinned above the page, visible click feedback, and transitions between scenes.

Never skip straight to recording. A demo that was not surveyed and storyboarded first produces a video where the pacing is wrong, the subtitles describe the wrong thing, and the pages are shown for the wrong length of time. Work the five phases in order and get the outline approved before rendering.

## Toolchain

Run `python3 <skill>/scripts/dv.py doctor` first (M1) and trust its report over this table. `<skill>` is the folder holding this SKILL.md. Do not substitute tools:

| Need | Tool |
|---|---|
| Browser driving + recording | `playwright-cli` (`@playwright/cli`) |
| Chapter cards, overlays, subtitles, cursor | `page.screencast.*` (Playwright 1.60+) |
| Scene joining, transitions, audio mux, mp4 | `ffmpeg` |
| Korean voice-over | TTS provider reported by `doctor` (macOS `say` today) |

**Never burn text with ffmpeg**, whatever `doctor` says about `drawtext` or `libass`. All text is rendered in the browser as a screencast overlay so the result does not depend on the ffmpeg build. ffmpeg only concatenates, cross-fades, muxes audio, and transcodes.

Recording output is **WebM / VP8 at 25 fps**, sized by the `size` option. There is no fps option.

Narration is optional. When the user wants it, generate it **before** rendering - see phase 3.5. The `.srt` sidecar comes free with it and is never burned into the picture.

## Phase 0 - Intake

```bash
python3 <skill>/scripts/dv.py doctor                       # environment; fix what it lists before going on
python3 <skill>/scripts/dv.py init --url <app url> --name <name> [--size 1920x1080] [--narration none|say] [--bgm none|<file>] [--intro <mp4>] [--outro <mp4>] [--target-sec 60]
python3 <skill>/scripts/dv.py status                       # any time: which gates are passed, what is next
```

Ask before `init`: the app URL and a demo account, the audience and purpose, the target length, narration yes/no, BGM (none / your file), and whether the user has intro/outro videos. `init` refuses an unreachable URL - the skill never starts the app.

## Approval gates

Four gates, enforced by `demo/state.json`: `render` refuses to run until G3 is approved, and any edit to an approved file makes the gate stale until it is approved again.

```bash
python3 <skill>/scripts/dv.py approve survey       # G1 after the user confirms the core features
python3 <skill>/scripts/dv.py approve scenario     # G2 after the outline is approved
python3 <skill>/scripts/dv.py approve storyboard   # G3 after the storyboard (and sheet) is approved
python3 <skill>/scripts/dv.py approve final        # G4 after the user has seen the video
```

Run `approve` only after the user has actually said yes. Never approve on their behalf.

## Phase 1 - Understand the solution

Not a page list - an understanding of what the product is for and what a user can do with it. Read the routes, the navigation component, the role guards, and the i18n files before opening a browser; those give you the real inventory and, critically, **the product's own vocabulary**, which every subtitle must use. Then walk each page, capture locators from the snapshot, and run `density()`.

Full method, including the `demo/survey.json` shape and the auth-state handling: `references/survey.md`.

Report what you found and what is in the way - a page that 404s, a feature needing data you do not have, a role your credentials cannot reach - before going further. Then present the 3-5 core features in priority order and stop: G1.

## Phase 2 - Write the user scenario, then the outline

Decide whose job the viewer is watching get done. A page-ordered demo names screens; a scenario-ordered demo shows work being completed and the screens explain themselves. Write `demo/scenario.md`: the user, the goal, the flow with a reason for each step's position, and what the video deliberately does not cover. Method and the scenario-to-subtitle rewrite: `references/scenario.md`.

Then present the scene outline with a runtime estimate and **stop for approval** (G2):

```
1. 인트로            2.5s   타이틀 카드
2. 로그인            6s     계정 입력 → 진입
3. 대시보드          9s     급변 종목 발견 (정보량 높음)
4. 상세 조회         7s     기간별 추이 확인
5. 아웃트로          3s     마무리 카드
                    ─────
                    27.5s
```

Over ~90s, propose splitting into multiple videos rather than one long one. This is the cheapest point to change direction - everything after it encodes these decisions.

## Phase 3 - Write the detailed storyboard

Write `demo/storyboard.json`. Schema and the dwell-time formula: `references/storyboard.md`.

Every scene carries its subtitles, its actions, its dwell time, and the transition into the next scene. Subtitles come from the scenario's "사용자가 하는 일" column, rewritten from the viewer's side and in the product's vocabulary - describe what the user **can do**, never what the cursor is doing. A subtitle's duration must be at least its reading time; the formula is in the reference, do not eyeball it.

Mark the one word each line is really about with `"emphasis": "<substring>"` - phase 3.5 uses it.

For each page in the outline, derive its system-specific interactions (drag, scroll, hover, keys, streaming) from source and screen signals, decide `show` / `skip` / `blocked` with a reason, and record them in the scene's `interactions[]` - `references/interactions.md`.

```bash
python3 <skill>/scripts/dv.py validate --fix      # fills holdMs/dwellMs, exit 1 lists the violated rules
python3 <skill>/scripts/dv.py sheet --capture     # demo/sheet.html: screenshots, subtitles, target boxes, interaction badges
```

Fix the storyboard until `validate` passes - never argue with a rule. Show `sheet.html`, the interaction decisions and any `blocked` items to the user and stop: G3. Edits are cheap here and expensive after rendering.

## Phase 3.5 - Narration (only if the demo has voice-over)

```bash
python3 <skill>/scripts/dv.py narrate
python3 <skill>/scripts/dv.py narrate --dry-run   # estimate only
```

Two things happen, both driven by the subtitle text you just finalised:

1. **Delivery is matched to content.** A clause boundary (`~하면`, `~한 후`) gets a 300ms beat so the viewer can look at the screen; a line carrying a number or `오류`/`삭제` slows to 155 wpm; the `emphasis` substring gets stressed. The markup is written back into the storyboard so you can see and tune it, and a line you wrote markup into yourself is never overwritten.
2. **Holds are widened to fit the voice.** Speech is slower than reading, so `holdMs` becomes `max(readingMs, spokenMs + 400)` and `dwellMs` rises if the subtitles no longer fit.

This must run before phase 4 - rendering first means re-rendering. Rules, the override cases, and voice availability: `references/narration.md`.

## Phase 4 - Render scenes

One scene, one `.webm`. Separate files are what make transitions and re-cuts possible - never record the whole demo as a single clip.

`render` generates one body per scene from the storyboard (`demo/scenes/<id>.body.js`, marked `// @generated`) and records it. Write a body by hand only for logic the action list cannot express - remove the marker line and it is kept.

```bash
python3 <skill>/scripts/dv.py render --close
python3 <skill>/scripts/dv.py render 03-dashboard   # one scene
```

`render` refuses to run until G3 is approved. It wraps each body with the helper prelude, starts and stops the recording, names the clip to match the storyboard id, and trims the frozen tail. Helpers (`subtitleSpan`, `click`, `typeText`, `zoom`, `zoomOut`, `highlight`, `drag`, `dropFile`, `scrollTo`, `hoverOn`, `key`, `waitStream`, `waitFor`, `dwell`, `BASE`, `ACCOUNTS`, `HOLD`) are already in scope - **do not `require` anything.** Contract and effects: `references/screencast-api.md`, `references/effects.md`.

`dv.py render` prints each clip's actual length next to the storyboard's. A clip far off its planned length means either an action silently failed or the storyboard's dwell time was never reconciled with the steps you wrote - fix whichever it is before composing.

## Phase 4.5 - Check the sync

```bash
python3 <skill>/scripts/dv.py check-sync
```

Four things must line up for page, subtitle and voice to land together, and this checks all four:

```
storyboard step  ->  subtitle() call in the body   same count, same text
storyboard step  ->  narration line                one audio clip per line
subtitle() call  ->  recorded cue in timing.json   written during the render
cue on-screen    >=  its narration length          the voice fits the subtitle
```

Exit 1 means the video would be out of sync. Fix it and re-render the named scene - do not compose. Run it once after writing the bodies too; catching drift there saves a render.

## Phase 5 - Compose, verify, file

```bash
python3 <skill>/scripts/dv.py compose            # mp4 + srt + manifest; narration and BGM muxed when present
python3 <skill>/scripts/dv.py verify             # exit 1 on black frames, subtitle drift under zoom, loudness off target
```

Produces `demo/output/<name>.mp4` (H.264, encoded once), `<name>.srt`, and `demo/manifest.json`. A user intro/outro video is normalized and letterboxed if its aspect differs - `compose` says so; pass it on. BGM comes from `dv.py bgm probe <file>` (user file; the catalog is not available yet). Details: `references/compose.md`.

For a first look use `render --draft` then `compose --draft` (960px, cuts, no audio) - it takes less than half the time and leaves the full-size cache alone.

`verify` writes `demo/output/verify-tile.png`. **Read it** and confirm the intro card, subtitles, and effects are visible before reporting. Then report the path, runtime, and whether narration and BGM are included. Stop: G4.

Layout:

```
demo/
├── config.json          # phase 0, app url / size / narration / bgm / intro-outro
├── survey.json          # phase 1, pages / features / locators / density
├── scenario.md          # phase 2, whose job the video shows
├── storyboard.json      # phase 3, the source of truth (schemaVersion 2)
├── sheet.html, shots/   # phase 3, the storyboard sheet and its screenshots
├── state.json           # approvals with file hashes
├── narration-<name>.json, audio/   # phase 3.5
├── scenes/              # <id>.body.js (generated), <id>.webm, <id>.timing.json, .build/, draft/
├── output/              # <name>.mp4, .srt, verify-tile.png, verify.json
└── manifest.json
```

## Re-recording

The storyboard is the source of truth. To change the demo, edit `demo/storyboard.json`, run `validate --fix`, get it approved again, re-run `dv.py narrate` if any spoken line changed, then `render` - the hash cache re-records only the scenes that changed - and `compose`. Never hand-edit a rendered clip or an audio file. Feedback routing by type: `references/feedback.md` (M4).
