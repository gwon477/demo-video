# The user scenario

Between the survey and the storyboard sits one decision: **whose job are we watching get done?** Answer it in writing before any scene exists. A page-ordered demo tells the viewer what the screens are called; a scenario-ordered demo shows someone finishing something and the screens explain themselves. Only the second is worth recording.

## Write demo/scenario.md

```markdown
# 시연 시나리오: <한 줄>
## 사용자        누구, 매일 무엇을 하는 사람
## 목표          이 영상이 끝나면 시청자가 무엇을 할 수 있는가
## 성공 기준     시청자가 이 영상만 보고 같은 작업을 스스로 수행할 수 있다
## 흐름          | # | 페이지 | 사용자가 하는 일 | 왜 이 순서인가 |
## 다루지 않는 것
## 오프닝 훅     첫 자막이 말할 시청자의 문제 또는 목표 (FR-044)
```

## Rules

- **One goal per video.** Two goals are two videos.
- **The target length is the budget.** `config.video.targetSec` from intake; allocate it over scenes (each 2.5-9s, add scenes rather than stretch them). `validate` warns beyond ±15%. Suggest 60-90s only when the user gave no target.
- **Every scene must be reachable from the one before it.** Scenes record independently (fresh document each), so any state a scene needs is made in its own `setup` or a hand-written body.
- **Only screens the scenario passes through.** Everything else goes under "다루지 않는 것".
- **The product's vocabulary**, from the i18n files. Every subtitle inherits these words.
- **A real starting state.** Note the data each page needs.
- **Long-running work** (an analysis that takes an hour): show the trigger, then explain the process and the wait over the progress screen, then move on to a finished example. Do not fake completion.

## Outline and BGM at G2

Present the scene outline with a runtime estimate per scene and the total against the target. If narration or BGM is on, add the BGM candidates: build the concept profile (audience, tone, domain, narration) and run `dv.py bgm pick`; show the top 3 with reasons. Stop for approval. This is the cheapest point to change direction.

## From scenario to subtitles

Each row's "사용자가 하는 일" becomes that scene's subtitle, rewritten from the viewer's side: what the user **can do**, never what the cursor does. "기간을 바꾸면 추이가 즉시 갱신됩니다", not "월간 버튼을 클릭합니다". One idea per line, under 32 weighted characters, one word marked as `emphasis`. Where the subtitle explains how a result was produced (a model pipeline, a background job), say it over the result screen, grounded in the product's docs - never invent a mechanism.
