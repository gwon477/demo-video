# The user scenario

Between the survey and the storyboard sits one decision: **whose job are we watching get done?** Answer it explicitly, in writing, before any scene exists.

A page-ordered demo ("대시보드입니다. 다음은 상세 화면입니다.") tells the viewer what the screens are called. A scenario-ordered demo shows someone accomplishing something, and the screens explain themselves along the way. Only the second one is worth recording.

## Write demo/scenario.md

```markdown
# 시연 시나리오: 관심 종목 이상 신호 확인

## 사용자
투자 분석 담당자. 매일 아침 관심 종목의 이상 신호를 확인하고 팀에 공유한다.

## 목표
어제 대비 급변한 종목을 찾아 상세 지표를 확인하고 리포트로 내보낸다.

## 성공 기준
시청자가 이 영상만 보고 같은 작업을 스스로 수행할 수 있다.

## 흐름
| # | 페이지 | 사용자가 하는 일 | 왜 이 순서인가 |
|---|---|---|---|
| 1 | 로그인 | 계정으로 진입 | 시작점을 보여줘야 따라 할 수 있다 |
| 2 | 대시보드 | 급변 종목을 발견 | 이상 신호가 눈에 띄는 지점 |
| 3 | 상세 | 지표 추이를 확인 | 발견한 것을 확인하는 자연스러운 다음 행동 |
| 4 | 리포트 | 내보내기 | 작업의 완결 |

## 다루지 않는 것
설정, 사용자 관리 - 이 시나리오와 무관하며 별도 영상 주제.
```

## Rules

**One goal per video.** A scenario with two goals is two videos. If the flow does not fit in about 90 seconds, split it and say so rather than speeding through.

**Every scene must be reachable from the one before it.** If step 3 requires state that step 2 does not produce, the viewer cannot reproduce it. Fix the order or add the missing step.

**Only screens the scenario passes through.** A page that exists but the scenario never needs does not get a scene, however proud you are of it. Put it in "다루지 않는 것" so its absence is a decision rather than an oversight.

**Use the product's vocabulary**, from the i18n files you read during the survey. Every subtitle and every narration line inherits these words.

**Prefer a real starting state.** A scenario that only works on a freshly seeded database is not the user's scenario. Note the data you needed in `needs`.

## From scenario to subtitles

Each row's "사용자가 하는 일" becomes that scene's subtitle, rewritten from the viewer's side:

| Row says | Subtitle says |
|---|---|
| 급변 종목을 발견 | 어제 대비 급변한 종목이 상단에 표시됩니다 |
| 지표 추이를 확인 | 종목을 선택하면 기간별 추이를 볼 수 있습니다 |
| 리포트 내보내기 | 확인한 내용을 리포트로 내보냅니다 |

Describe what the user **can do**, not what the cursor is doing. "월간 버튼을 클릭합니다" narrates the mouse; "기간을 바꾸면 추이가 즉시 갱신됩니다" teaches the product. The click is already visible on screen - the subtitle should add what the picture cannot show.

## Get it approved

Present the scenario and the scene outline with a runtime estimate, and stop. This is the cheapest point to change direction. After this the storyboard, the recordings, and the audio all encode these decisions.
