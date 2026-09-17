# 전문 PD 기준과 스킬 설정값

기준일: 2026-09-17 · 목적: 데모 영상 제작에서 전문 PD(연출·편집·자막·사운드)가 지키는 수치 기준을 조사하고, 스킬이 코드로 강제할 설정값으로 옮긴다. DESIGN.md 6절의 FR 번호와 대응시키며, DESIGN.md와 값이 다른 항목은 "변경 제안"으로 표시한다.

## 1. 조사 결과 요약

| 영역 | 전문 기준 | 출처 |
| --- | --- | --- |
| 자막 줄 길이 (한국어) | 한 줄 16자, 최대 2줄. 라틴 문자·공백·문장부호는 0.5자로 센다 | Netflix Korean Timed Text Style Guide |
| 자막 읽기 속도 (한국어) | 성인 최대 12자/초 (SDH 14자/초, 아동 9자/초) | Netflix Korean TTSG |
| 자막 노출 시간 | 최소 5/6초, 최대 7초. 중앙 정렬, 화면 하단 | Netflix TTSG General Requirements |
| 자막 사이 간격 | 2~4프레임 (BBC 규격 3프레임). 말이 끊기는 구간은 1초 이상 | BBC Subtitle Guidelines |
| 자막 읽기 속도 (영문) | 160~180 wpm, 단어당 0.33~0.375초 | BBC Subtitle Guidelines |
| 안전 영역 | 액션 세이프 93%, 타이틀(그래픽) 세이프 88% | EBU R95 |
| 줌 배율과 완급 | 1.5x가 안전, 2x는 1440p 소스 기준. 500ms 이상 ease-in-out | Screen Studio 가이드, 리뷰 |
| 디졸브 길이 | 영화 문법 기준 24~48프레임(1~2초). 짧을수록 컷에 가깝다 | Boris FX, Adobe |
| 컷 vs 디졸브 | 같은 흐름은 컷, 시간·장소 전환은 디졸브 | StudioBinder, Videomaker |
| 영상 길이 | 60~90초. 이탈은 첫 8~10초에 집중 | demosmith, ngram, demopolish |
| 오프닝 | 첫 5초는 로고가 아니라 시청자의 문제로 시작. 문제→해결→증거 구조 | demopolish, hyltonmedia |
| 라우드니스 (웹) | YouTube 정규화 목표 -14 LUFS. 음성 콘텐츠 -14~-16 LUFS | audioforgepro, criticallisteninglab |
| BGM 레벨 | 나레이션 아래 -18~-25 dB, 나레이션 없을 때 -12~-14 dB | vidpros |
| 나레이션 속도 (한국어) | 뉴스 아나운서 약 355 음절/분(5.9/초). 발표 300자/분, 중요 내용 200~250자/분 | 한국언어치료학회 논문, ROBERIN |

## 2. 스킬 설정값 (강제 위치 포함)

값은 `assets/theme.json`에 두고, `validate`·`prelude.js`·`compose`가 읽는다. 에이전트는 값을 고를 수 없다.

### 자막

| 항목 | 설정값 | 근거 | 강제 | DESIGN |
| --- | --- | --- | --- | --- |
| 글자 수 상한 | 가중 32자 (한글 1, 라틴·공백·부호 0.5) | Netflix 16자×2줄을 한 줄에 담는 상한. 폭 계산(40px×32=1280px)이 86% 폭 안에 들어감 | `validate` FR-012 | 유지. "가중 카운트" 추가 |
| 노출 시간 | `holdMs = clamp(글자수 × 125 + 600, 1500, 7000)` | 8자/초. Netflix 상한 12자/초의 2/3. 시청자는 화면도 봐야 하므로 상한을 그대로 쓰지 않는다. 7초 초과는 두 큐로 분할 | `validate --fix` FR-013 | **변경 제안**: 90ms→125ms/자, 상한 7000 추가 |
| 최소 노출 | 1500ms | Netflix 최소 833ms에 화면 인지 시간을 더함 | `validate` | 유지 |
| 큐 간격 | 300ms (7.5프레임) | BBC 3프레임 이상. 화면 전환이 함께 일어나므로 여유를 둠 | `prelude.js` | 추가 |
| 위치 | 하단 7% 위, 가로 중앙 | EBU R95 타이틀 세이프 6% 안쪽 | `prelude.js` FR-010 | 유지 |
| 최대 폭 | 86% | 타이틀 세이프 88% 안쪽 | `prelude.js` FR-011 | 유지 |
| 폰트 | 40px @1080p (해상도 비례 3.7%), 흰색, 반투명 어두운 박스 | Netflix: 흰색, 해상도 비례 크기 | `theme.json` FR-014 | 유지 |
| 줄 수 | 1줄, `nowrap`. ellipsis 금지 | 잘린 자막은 오류. 초안의 `text-overflow: ellipsis`는 제거 | `prelude.js` + `validate` | 유지 |

### 줌·커서·효과

| 항목 | 설정값 | 근거 | 강제 | DESIGN |
| --- | --- | --- | --- | --- |
| 줌 배율 | 기본 1.5, 범위 1.2~2.0 | 1.5x 안전, 2x는 1080p 소스에서 픽셀이 보이기 시작 | `validate` FR-020 | 유지 |
| 줌 완급 | 진입 600ms, 복귀 500ms ease-in-out | 500ms 이상 권장 | `prelude.js` FR-021 | 유지 |
| 커서 이동 | 300~500ms ease, 순간이동 금지 | 커서 스무딩이 전문 툴의 기본값 | `prelude.js` FR-030 | 유지 |
| 클릭 후 정지 | 600ms | 결과 인지 시간 | `prelude.js` | 유지 |

### 편집·구조

| 항목 | 설정값 | 근거 | 강제 | DESIGN |
| --- | --- | --- | --- | --- |
| 장면 전환 | 페이지 이동 `fade` 400ms, 같은 페이지 `cut` | 영화 디졸브(1~2초)는 데모에서 느리다. 짧은 페이드는 컷과 시간 전환의 중간 | `validate` + `compose` FR-043 | 유지 |
| 전환 범위 | 300~700ms | 그 밖은 내용을 잠식 | `validate` | 추가 |
| 장면 길이 | 2.5~9초 | 초안 공식. 9초 초과는 두 장면 | `validate --fix` | 유지 |
| 총 길이 | 사용자 목표(`targetSec`)가 기준, ±15% 벗어나면 경고. 목표 없을 때만 90초 초과 경고 | 60~90초는 시청 이탈 통계에 근거한 기본값이지 상한이 아니다 | `validate` | 개정 |
| 인트로 | 2.5초 이하 | 첫 5초 안에 문제 제시가 나와야 함 | `validate` | 추가 |
| 오프닝 훅 | 인트로 다음 첫 자막은 시청자의 목표 또는 문제 문장 (`scenario.md`의 "목표"에서 옴) | 문제→해결→증거 | `references/scenario.md` + `validate`가 `scenes[0].steps[0].hook: true` 요구 | 추가 |
| 아웃트로 | 다음 행동(CTA) 한 줄 포함, 2~4초 | 증거·다음 행동으로 마무리 | 템플릿 필드 | 추가 |

### 사운드

| 항목 | 설정값 | 근거 | 강제 | DESIGN |
| --- | --- | --- | --- | --- |
| 최종 라우드니스 | 통합 -16 LUFS, 트루피크 -1 dBTP | 웹 배포 기준. -24 LUFS는 방송(ATSC A/85) 기준이라 웹에서 작게 들린다 | `compose` loudnorm | **변경 제안**: FR-078 -24 → -16 |
| BGM 단독 | 최종 -16 LUFS 기준으로 BGM을 마스터 | 나레이션 없으면 BGM이 유일한 오디오 | `compose` | 추가 |
| BGM 더킹 | 나레이션 구간 -18 dB, 어택 300ms, 릴리즈 800ms | -18~-25 dB 권장 범위의 상단 | `compose` FR-078 | 수치 추가 |
| 페이드 | 인 1.5초, 아웃 2초 | 유지 | `compose` | 유지 |
| 나레이션 속도 | 기본 약 350 음절/분 (`say` rate 140~150), 숫자·오류 문구 250 음절/분 | 아나운서 355 SPM, 중요 내용 200~250자/분. 초안 rate 180은 약 456자/분으로 빠름 | `narrate` (M4) | **변경 제안**: 기본 rate 180 → 150, careful 155 → 120 |
| 검증 | `verify`가 통합 LUFS와 트루피크를 측정해 ±1 LU 밖이면 실패 | 종료 코드 0을 믿지 않는다 | `verify` | 추가 |

## 3. theme.json 초안

```json
{
  "schemaVersion": 1,
  "frame": { "width": 1920, "height": 1080, "fps": 25 },
  "safeArea": { "action": 0.93, "title": 0.88 },
  "subtitle": {
    "fontFamily": "'Apple SD Gothic Neo','Pretendard','Noto Sans KR',sans-serif",
    "fontSizeRatio": 0.037,
    "maxWidthRatio": 0.86,
    "bottomRatio": 0.07,
    "maxWeightedChars": 32,
    "charWeights": { "hangul": 1, "other": 0.5 },
    "msPerChar": 125, "baseMs": 600, "minMs": 1500, "maxMs": 7000,
    "gapMs": 300,
    "color": "#ffffff", "background": "rgba(12,14,18,.62)", "radius": 10
  },
  "zoom": { "default": 1.5, "min": 1.2, "max": 2.0, "inMs": 600, "outMs": 500 },
  "cursor": { "moveMinMs": 300, "moveMaxMs": 500, "settleMs": 600 },
  "transition": { "default": "fade", "defaultMs": 400, "minMs": 300, "maxMs": 700 },
  "scene": { "minMs": 2500, "maxMs": 9000 },
  "video": { "warnSec": 90, "errorSec": 120, "introMaxMs": 2500, "outroMinMs": 2000, "outroMaxMs": 4000 },
  "audio": { "integratedLufs": -16, "truePeakDbtp": -1, "duckDb": -18, "duckAttackMs": 300, "duckReleaseMs": 800, "fadeInMs": 1500, "fadeOutMs": 2000 },
  "narration": { "rate": 150, "carefulRate": 120, "padMs": 400 }
}
```

## 4. DESIGN.md 변경 제안 (승인 필요)

1. FR-013: `max(1500, 글자수 × 90ms + 600)` → `clamp(글자수 × 125ms + 600, 1500, 7000)`. 초과 시 두 큐로 분할.
2. FR-012: 글자 수는 가중 카운트(한글 1, 그 외 0.5)로 32자 고정. "폰트 크기에서 계산" 문구는 삭제하고 폭 검사(`32 × fontSize ≤ 0.86 × W`)를 별도 규칙으로 둔다.
3. FR-078: 음량 정규화 -24 LUFS → 통합 -16 LUFS, 트루피크 -1 dBTP. 더킹 -18 dB, 어택 300ms, 릴리즈 800ms 명시.
4. FR-043에 전환 길이 범위 300~700ms 추가.
5. 신규 FR-044: 인트로 2.5초 이하, 인트로 다음 첫 자막은 `hook: true`로 표시된 목표·문제 문장이어야 한다. 아웃트로는 CTA 한 줄을 갖는다.
6. 신규 FR-045: 총 길이 90초 초과 경고, 120초 초과 실패.
7. 7절 `verify`에 통합 LUFS·트루피크 측정과 자막 안전 영역 검사 추가.
8. 2절 나레이션 행에 기본 rate 150, careful 120 명시 (M4에서 반영).

## 5. 출처

- [Netflix Korean Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/216001127-Korean-Timed-Text-Style-Guide)
- [Netflix Timed Text Style Guide: General Requirements](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements)
- [BBC Subtitling Guidelines (Clevercast 요약)](https://www.clevercast.com/bbc-subtitling-guidelines/)
- [Subtitle Reading Speed: CPS & WPM Limits](https://www.closedcaptioncreator.com/blog/articles/subtitle-reading-speed.html)
- [EBU R95 Safe areas for 16:9 television production](https://tech.ebu.ch/publications/r095)
- [Screen Studio manual zoom guide](https://screen.studio/guide/manual-zoom)
- [Best Screen Recorders with Auto-Zoom](https://www.screenify.studio/blog/2026-04-16-best-screen-recorder-auto-zoom)
- [Boris FX: Dissolve transition tutorial](https://borisfx.com/blog/dissolve-transition-tutorial-2024-what-are-dissolves/)
- [Videomaker: Common video transitions](https://www.videomaker.com/video/watch/tips-and-techniques/447-common-video-transitions-cut-fade-and-dissolve/)
- [SaaS Demo Video Best Practices (demopolish)](https://demopolish.com/blog/saas-demo-video-best-practices/)
- [How Long Should a Demo Video Be (ngram)](https://www.ngram.com/blog/demo-video-length)
- [How Long Should a Product Demo Video Be (demosmith)](https://demosmith.ai/blog/how-long-should-demo-video-be)
- [YouTube LUFS normalization guide (audioforgepro)](https://audioforgepro.com/blog/youtube-lufs-normalization-guide)
- [YouTube loudness normalization (Critical Listening Lab)](https://www.criticallisteninglab.com/en/learn/loudness/youtube)
- [Music is too loud in video (vidpros)](https://vidpros.com/fix-background-music-too-loud-video/)
- [TV뉴스 아나운서의 음도, 음도 범위, 말속도에 관한 연구](https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART002743897)
- [발표시간 계산기 (ROBERIN)](https://roberin.com/projects/presentation-calc-wrapper/)
