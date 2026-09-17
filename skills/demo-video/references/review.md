# Red-team review of the finished video

`compose` and `verify` prove the file is well-formed. They do not prove the video is good. Before G4, review the mp4 as three people who would each reject it for a different reason, and write `demo/review.md`. Run the packet first:

```bash
python3 <skill>/scripts/dv.py review        # output/review.json, output/review/<scene>.png, output/review-transitions.png
```

Read every strip image and the transitions strip. Do not review from the storyboard - review what was recorded.

## The three personas

| Persona | Rejects the video when | Looks at |
|---|---|---|
| **PD** (연출) | the cut is not what the storyboard says; an effect is missing, mistimed or on the wrong element; a transition jars; a hold is dead air; the subtitle and the picture disagree | per-scene strips, `findings` of kind effect/timing/static, transitions strip |
| **User** (시청자) | they could not repeat the task after watching; a step is skipped or too fast to see; a subtitle names something not on screen; the product's words are wrong | the subtitle script in order, cue gaps, whether each click/drag/scroll result is visible in the strip |
| **Critic** (평론가) | the opening does not earn attention; the story has no arc (problem → work → proof); the pacing is flat; the ending gives no next step; the video says things it cannot show | opening 10s, scene rhythm (durations), intro/outro, claims vs evidence on screen |

## Checklist (answer each, per persona, with the frame that proves it)

**PD**
1. Every scene in `review.json` has its planned subtitles and effect marks (no `fail` findings).
2. On each `zoomed` frame the zoomed element is the storyboard target and the subtitle is untouched.
3. Each `drag` / `scroll` / `dropFile` / `streamed` frame shows the result of the action, not just the gesture.
4. Transition strip: no boundary shows a half-loaded page, a flash of the previous page, or a cut inside an animation.
5. `static` findings: is each hold intentional (a card, an explanation over a fixed screen) or dead air?
6. Clip lengths within 1.5s of plan; if longer, which action overran.

**User**
7. Could a viewer perform the same flow from what is shown? List the step they could not.
8. Every subtitle refers to something visible in its own frame.
9. Vocabulary matches the product (survey `vocabulary`), no invented names.
10. Nothing important is only readable when zoomed and the zoom did not happen.

**Critic**
11. First 10s: does the hook state the viewer's problem or goal? Is the chapter/intro readable long enough?
12. Arc: setup → work → proof → next step. Where does the arc sag or repeat itself?
13. Rhythm: consecutive scenes with the same length and the same picture read as a slideshow - where?
14. Outro: is the CTA concrete? Does the video make a claim the screen does not back?

## Verdict and routing

Write `demo/review.md`:

```markdown
# 검토: <name>.mp4 (<duration>s)
## 판정: 통과 | 수정 후 통과 | 재구성
## 발견 사항
| # | 페르소나 | 장면 | 심각도 | 내용 | 근거 프레임 | 조치 |
## 수정 계획
(table below)
## 통과한 항목
```

Severity: `fail` (a viewer would notice and be confused - must fix), `warn` (a professional would notice - fix if cheap), `note` (taste - record, do not block).

Route each fix through the feedback table (`references/feedback.md`, DESIGN.md 5절): subtitle or emphasis → storyboard step → render that scene → compose; effect or timing → storyboard step → render that scene → compose; scene order or removal → storyboard scenes[] → compose; missing feature → scenario → G2; wrong locator → survey + storyboard → render that scene. Re-run `validate --fix`, re-approve G3 if the storyboard changed, then `render` (only changed scenes re-record), `compose`, `verify`, `review` again. Stop at G4 only when the review verdict is 통과 or every `fail` is fixed and the remaining items are listed for the user.
