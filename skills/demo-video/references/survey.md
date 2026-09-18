# Surveying the system

The goal is not a list of URLs. It is enough understanding to say **what this product is for, what a user can do with it, and in what order**, because the scenario, the subtitles and the interaction list are all derived from it. Budget real time here; everything downstream inherits its mistakes.

## 1. Read the code before opening the browser

- **Routes**: router config, pages directory, controllers. The full page inventory, including pages you would never click into.
- **Navigation**: the nav/menu/sidebar component gives the product's own top-level structure - use it, do not invent one.
- **Roles and permissions**: guards, middleware, role checks. An admin-only feature needs the right account or cannot be demoed.
- **Feature naming**: i18n/locale files are the best source of the product's vocabulary. Subtitles must use the product's words.
- **Empty and error states**: know before recording whether data must be seeded (`config.app.resetCommand`).
- **Interaction signals** for the pages the outline will use: drag libraries, dropzones, virtual lists, tooltips, hotkeys, streaming - the source column of `interactions.md`.
- **How the app runs**: dev server, Electron with a web/preview mode, fixtures. The skill never starts the app; if it needs a flag or a fixture mode to be demoable, write it down under `obstacles`.

## 2. Then walk it in the browser

```bash
playwright-cli open --headed
playwright-cli goto <url>
playwright-cli snapshot
```

Per page record the route, what a user can do there in one sentence (the seed of its subtitle), the locators of everything the demo will touch, its density (visible text length, interactive element count), how a user arrives and leaves, and the state it needs. `dv.py brand probe` reads the identity (logo, colors, font) while you are at it.

Locators are **selector strings** `page.locator()` accepts: CSS (`[data-testid=fail-list]`, `.sheet-rw >> nth=0`) or Playwright engines (`role=button[name="열기"]`, `role=tab[name=/생성 이력/]`, `text=...`). A quoted `role` name is an exact match; use a regex for partial names. `validate` refuses any storyboard target that is not in the survey.

Log in once and persist it: `playwright-cli state-save demo/.auth.json`, referenced as `meta.authState`. Credentials go in `demo/.accounts.json` (gitignored) and are used as `ACCOUNTS.<key>.<field>`.

## 3. Write demo/survey.json (schemaVersion 2)

```json
{
  "schemaVersion": 2, "product": "Camino", "surveyedAt": "2026-09-17",
  "vocabulary": ["실패 테스트", "야간 실행", "재실행"],
  "roles": ["QA 담당자"],
  "coreFeatures": ["1. 실패 테스트 확인", "2. 우선순위 드래그 정렬", "3. 결과 파일 드롭 업로드"],
  "obstacles": ["로그인 계정 없음: 데모 계정 필요", "결과 업로드는 파일 2개 이상 시드 필요"],
  "pages": [
    {
      "id": "dashboard", "route": "/index.html", "title": "대시보드",
      "canDo": "야간 실행 결과와 실패 원인을 확인한다",
      "locators": { "failList": "[data-testid=fail-list]", "failRow1": "[data-testid=fail-row-1]" },
      "density": { "textChars": 1650, "interactive": 6 },
      "interactionsSeen": ["scroll", "hover", "key"],
      "needs": "실패 3건 이상"
    }
  ]
}
```

`density.textChars` decides whether a page may be zoomed (FR-022) and how long it stays on first appearance. `page` in a storyboard scene refers to `pages[].id`.

## 4. Report before moving on: G1

State what you found and what is in the way (a 404, a feature without data, a role the account cannot reach, an app that needs a fixture mode), then the 3-5 core features in priority order. Stop. `dv.py approve survey` only after the user confirms.
