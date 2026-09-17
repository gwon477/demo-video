# Surveying the system

The goal is not a list of URLs. It is enough understanding to say **what this product is for, what a user can do with it, and in what order** - because that is what the scenario, the subtitles, and the narration are all derived from. A demo built on a page list shows screens; a demo built on an understanding shows a job getting done.

Budget real time here. Everything downstream inherits its mistakes.

## 1. Read the code before opening the browser

Faster and more complete than clicking around, and it tells you what exists rather than what you happened to find.

- **Routes**: the router config, the pages directory, the controller/endpoint list. This is the page inventory, including pages you would never have clicked into.
- **Navigation**: the nav/menu/sidebar component. This gives the product's own idea of its top-level structure - use that structure, do not invent your own.
- **Roles and permissions**: guards, middleware, `role`/`permission` checks. A feature only visible to an admin needs the right account or it cannot be demoed.
- **Feature naming**: i18n/locale files are the single best source for the product's own vocabulary. **Subtitles must use the product's words**, not yours. A demo that calls the 거래내역 screen "history" teaches the viewer the wrong name.
- **Empty and error states**: search for the empty-list and error components. A screen with no data is a bad scene; you need to know in advance whether you must seed data.

## 2. Then walk it in the browser

```bash
playwright-cli open --headed
playwright-cli goto <dev-url>
playwright-cli snapshot
```

Per page, record:

- **Route and title**, matched to what you found in the code.
- **What a user can do here**, in one sentence, in the product's own vocabulary. This sentence is the seed of the page's subtitle.
- **Locators** for every element the demo will touch, straight from the snapshot. Never invent a locator later.
- **Density**: run `density()` - `{ textChars, interactive, dwellMs }` - so dwell time comes from what is on screen rather than a guess.
- **Entry and exit**: how a user arrives here and where they can go next. This is what makes scenes connect instead of jump.
- **State it needs**: data that must exist, a role, a prior action. Note anything you had to set up.

Log in once and persist it rather than scripting the login every run:

```bash
playwright-cli state-save demo/.auth.json
playwright-cli state-load demo/.auth.json
```

Add `demo/.auth.json` to `.gitignore` - it holds live session credentials.

## 3. Write demo/survey.json

```json
{
  "product": "RA-DAR",
  "baseUrl": "https://dev.example.com",
  "surveyedAt": "2026-09-03",
  "roles": ["admin", "analyst"],
  "pages": [
    {
      "id": "dashboard",
      "route": "/dashboard",
      "title": "대시보드",
      "canDo": "관심 종목의 지표를 한눈에 확인하고 기간을 바꿔 추이를 봅니다",
      "features": ["지표 카드", "기간 필터", "추이 그래프"],
      "locators": {
        "periodMonthly": "getByRole('button', { name: '월간' })",
        "firstCard": "getByTestId('metric-card').first()"
      },
      "density": { "textChars": 940, "interactive": 12, "dwellMs": 6800 },
      "entryFrom": ["login"],
      "exitTo": ["detail"],
      "needs": "관심 종목 1건 이상",
      "notes": "데이터 없으면 빈 상태 카드만 보임 - 시연 전 시드 필요"
    }
  ]
}
```

## 4. Report before moving on

State plainly what you found and, more importantly, what is in the way: a page that 404s, a feature that needs data you do not have, a role the credentials cannot reach. Raising it now costs a sentence. Raising it after rendering costs the whole video.
