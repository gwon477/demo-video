Demo video

Record a demo of a real, running web app - not a mockup. The output is an mp4 with an intro card, per-scene subtitles pinned above the page, visible click feedback, and transitions between scenes.

Never skip straight to recording. A demo that was not surveyed and storyboarded first produces a video where the pacing is wrong, the subtitles describe the wrong thing, and the pages are shown for the wrong length of time. Work the five phases in order and get the outline approved before rendering.

Toolchain

Verified on this machine - do not substitute:

Need	Tool
Browser driving + recording	playwright-cli (@playwright/cli, installed globally)
Chapter cards, overlays, subtitles, cursor	page.screencast.* (Playwright 1.60+)
Scene joining, transitions, audio mux, mp4	ffmpeg
Korean voice-over	macOS say (voice Yuna)

ffmpeg on this machine has no libass and no libfreetype - the subtitles, ass, and drawtext filters do not exist. Never try to burn text with ffmpeg. All text is rendered in the browser as a screencast overlay. ffmpeg only concatenates, cross-fades, and transcodes. Verify with ffmpeg -filters | grep drawtext before assuming otherwise.

Recording output is WebM / VP8 at 25 fps, sized by the size option. There is no fps option.

Narration is optional. When the user wants it, generate it before rendering - see phase 3.5. The .srt sidecar comes free with it and cannot be burned into the picture for the same libass reason.

Phase 1 - Understand the solution

Not a page list - an understanding of what the product is for and what a user can do with it. Read the routes, the navigation component, the role guards, and the i18n files before opening a browser; those give you the real inventory and, critically, the product's own vocabulary, which every subtitle must use. Then walk each page, capture locators from the snapshot, an

<!-- 원문 손상: 위 문장이 "an"에서 끊김. 이어지는 내용(정보 밀도 기록 등으로 추정)이 유실됨 -->

Full method, including the demo/survey.json shape and the auth-state handling: references/survey.md.

Report what you found and what is in the way - a page that 404s, a feature needing data you do not have, a role your credentials cannot reach - before going further.

Phase 2 - Write the user scenario, then the outline

Decide whose job the viewer is watching get done. A page-ordered demo names screens; a scenario-ordered demo shows work being completed and the screens explain themselves. Write demo/scenario.md: the user, the goal, the flow with a reason for each step's position, and what the video d. Method and thescenario-to-subtitle rewrite: references/scenario.md.

<!-- 원문 손상: "what the video d" 뒤가 유실되고 다음 문장과 붙음. 추정: "...and what the video deliberately leaves out. Method and the scenario-to-subtitle rewrite: ..." -->

Then present the scene outline with a runtime estimate and stop for approval:

1. 인트로            2.5s   타이틀 카드
2. 로그인            6s     계정 입력 → 진입
3. 대시보드          9s     급변 종목 발견 (정보량 높음)
4. 상세 조회         7s     기간별 추이 확인
5. 아웃트로          3s     마무리 카드
                    ─────
                    27.5s

Over ~90s, propose splitting into multiple videos rather than one long one. This is the cheapest point to change direction - everything after it encodes these decisions.

Phase 3 - Write the detailed storyboard

Write demo/storyboard.json. Schema and the dwell-time formula: references/storyboard.md.

Every scene carries its subtitles, its actions, its dwell time, and the transition into the next scene. Subtitles come자가 하는 일" column,rewritten from the viewer's side and in the product's vocabulary - describe what the user can do, never what the cursor is doing. A subtitle's duration must be at least its reading time; the formula is in the reference, do not eyeball it.

<!-- 원문 손상: "Subtitles come" 뒤가 유실됨. 추정: "Subtitles come from the scenario's "사용자가 하는 일" column, rewritten from the viewer's side ..." -->

Mark the one word each line is really about with "emphasis": "<substring>" - phase 3.5 uses it.

Show the storyboard to the user. Edits are cheap here and expensive after rendering.

Phase 3.5 - Narration (only if the demo has voice-over)
bash
python3 ~/.claude/skills/demo-video/scripts/narrate.py demo/storyboard.json
python3 ~/.claude/skills/demo-video/scripts/narrate.py demo/storyboard.json --dry-run   # estimate only

Two things happen, both driven by the subtitle text you just finalised:

Delivery is matched to content. A clause boundary (~하면, ~한 후) gets a 300ms beat so the viewer can look at the screen; a line carrying a number or 오류/삭제 slows to 155 wpm; the emphasis substring gets stressed. The markup is written back into the storyboard so you can see and tune it, and a line you wrote markup into yourself is never overwritten.
Holds are widened to fit the voice. Speech is slower than reading, so holdMs becomes max(readingMs, spokenMs + 400) and dwellMs rises if the subtitles no longer fit.

This must run before phase 4 - rendering first means re-rendering. Rules, the override cases, and voice availability: references/narration.md.

Phase 4 - Render scenes

One scene, one .webm. Separate files are what make transitions and re-cuts possible - never record the whole demo as a single clip.

Write one scene body per scene: demo/scenes/<id>.body.js, containing statements only - no wrapper function, no imports. Then:

bash
python3 ~/.claude/skills/demo-mo/storyboard.json --close
python3 ~/.claude/skills/demo-video/scripts/render.py demo/storyboard.json 03-dashboard   # one scene
<!-- 원문 손상: 첫 줄의 경로가 깨짐. 추정: python3 ~/.claude/skills/demo-video/scripts/render.py demo/storyboard.json --close -->

render.py wraps each body with the helper prelude, starts and stops the recording, names the clip to match the storyboard id, and trims the frozen tail the recorder leaves behind. Helper functions (intro, subtitle, clickRipple, chapter, highlight, density, dwell, BASE) are already in scope - do not require anything. The sandbox has no require, no process, no module.

API contract and effect recipes: references/screencast-api.md and references/effects.md. Read them before writing a body - the timed overlay calls block for their own duration, fter one silently doubles every

<!-- 원문 손상: 문장 중간과 끝이 유실됨. 추정: "...block for their own duration, and a wait added after one silently doubles every hold." 또한 이 지점에 Phase 4.5(싱크 검사) 제목과 check-sync.py 실행 명령이 있었던 것으로 보임. 한국어 설명 기준 추정: ## Phase 4.5 - Check sync python3 ~/.claude/skills/demo-video/scripts/check-sync.py demo/storyboard.json -->

Four things must line up for page, subtitle and voice to land together, and this checks all four:

storyboard step  ->  subtitle() call in the body   same count, same text
storyboard step  ->  narration line                one audio clip per line
subtitle() call  ->  recorded cue in timing.json   written during the render
cue on-screen    >=  its narration length          the voice fits the subtitle

Exit 1 means the video would be out of sync. Fix it and re-render the named scene - do not compose. Run it once after writing the bodies too; catching drift there saves a render.

Phase 5 - Compose and file
bash
python3 ~/.claude/skills/demo-video/scripts/compose.py demo/storyboard.json

Produces demo/output/<name>.mp4 (H.264), a .srt sidecar, and - when demo/narration.json exists - the voice-over muxed in as AAC, each line placed at the exact moment its subtitle appeared. Details and transition options: references/compose.md.

Layout:

demo/
├── survey.json          # phase 1, routes / features / locators / density
├── scenario.md          # phase 2, whose job the video shows
├── storyboard.json      # phase 3, the source of truth
├── narration.json       # phase 3.5, generated line index + durations
├── scenes/              # <id>.body.js sources + rendered <id>.webm
│   ├── <id>.timing.json # exact subtitle cues, written at render time
│   └── .build/          # ass disposable)
<!-- 원문 손상: 레이아웃 트리의 마지막 줄이 깨지고 이후 줄(output/ 등)이 유실됨. 추정: "│ └── .build/ # wrapped bodies (disposable)" 다음에 "└── output/ # <name>.mp4, <name>.srt" 또한 이 뒤에 "종료 코드 대신 프레임 타일 이미지로 실제 결과를 확인하라"는 단락이 있었던 것으로 보임(한국어 설명 Phase 5 참고) -->

With narration, also confirm the audio is where it should be - a muxed track that is silent throughout still exits 0:

bash
ffmpeg -hide_banner -nostats -ss <cue start> -t 2 -i demo/output/<name>.mp4 \
  -af volumedetect -f null - 2>&1 | grep max_volume

Around -7 dB means speech; -91 dB is silence. Check one cue and one gap. Then report the path, runtime, and whether narration is included.

Re-recording

The storyboard is the source of truth. To change the demo, edit demo/storyboard.json, re-run narrate.py if any spoken line changed, re-render only the affected scenes, and re-run compose. Never hand-edit a rendered clip or an audio file.

설명 (첨부 원문의 한국어 요약)

실제 실행 중인 웹앱을 Playwright로 조작하며 녹화해 시연 영상(mp4)을 만드는 스킬입니다. 핵심은 "녹화부터 하지 말고 5단계를 순서대로" 입니다.

도구: playwright-cli(브라우저 조작·녹화), page.screencast.*(자막·커서·카드 오버레이), ffmpeg(이어붙이기·전환·mp4 변환), macOS say(한국어 나레이션). 이 머신의 ffmpeg는 텍스트 렌더 불가라 자막은 전부 브라우저 오버레이로 그림.
Phase 1 조사: 라우트·내비·권 기능 목록을 파악 → demo/survey.json. 막히는 점(404, 데이터 없음 등) 먼저 보고. <!-- 원문 손상: "권" 뒤 유실. 추정: "라우트·내비·권한 가드·i18n을 읽어 기능 목록을 파악" -->
Phase 2 시나리오·아웃라인: 화면 나열이 아니라 "누구의 어떤 작업"인지 정의 → demo/scenario.md. 장면별 시간 추정을 제시하고 승인 대기. 90초 초과면 분할 제안.
Phase 3 스토리보드: demo/storyboard.json이 단일 진실 소스. 장면마다 자막·동작·체류 시간·전환. 자막은 "사용자가 로, 커서 동작 묘사 금지. 자막길이는 읽기 시간 공식으로 계산. <!-- 원문 손상: "사용자가" 뒤 유실. 추정: "자막은 '사용자가 할 수 있는 일'을 제품 용어로, 커서 동작 묘사 금지" -->
Phase 3.5 나레이션(선택): narrate.py가 자막 문구를 기반으로 쉼·속도·강조를 자동 부여하고, 음성 길이에 맞춰 hold/dwell을 늘림. 렌더 전에 실행해야 함.
Phase 4 렌더: 장면당 .body.js 하나 → render.py가 웹m 하나씩 생성. 헬퍼(intro, subtitle, clickRipple 등)는 이미 스코프에 있어 require 금지. 타이머 오버레이 호출은 스스로 대기하므로 추가 wait 넣으면 시간이 2배됨.
Phase 4.5 싱크 검사: check-sync.py로 스토리보드 ↔ body 자막 ↔ 나레이션 ↔ 실제 큐 타이밍 4개 정합성 확인. 실패 시 해당 장면만 재렌더.
Phase 5 합성: compose.py로 mp4 + .srt + (있으면) AAC 나레이션 mux. 종료 코드 대신 프레임 타일 이미지와 볼륨 측정으로 실제 확인 후 보고.
재녹화: 스토리보드만 수정하고 영향받은 장면만 재렌더. 렌더된 클립·오디오 직접 편집 금지.