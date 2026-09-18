# Feedback routing (G4 and after)

Every request to change the video maps to one file and one re-run range. Never hand-edit a clip, an audio file, or a generated body. After editing the storyboard: `validate --fix` → show → `approve storyboard` → `render` (the hash cache re-records only the changed scenes) → `compose` → `verify` → `review`.

| Feedback | File to change | Re-run |
|---|---|---|
| Subtitle wording, emphasis word | `storyboard.json` that step | (`narrate` if narrated) → `render <scene>` → `compose` |
| Zoom, click, highlight, hold time | `storyboard.json` that step's actions | `render <scene>` → `compose` |
| Scene order, drop a scene | `storyboard.json` scenes[] | `compose` only (clips are cached) |
| Add a scene, show another feature | `scenario.md` → `storyboard.json` | from G2 |
| Intro / outro design or wording, transition type | `storyboard.json` intro/outro/transitionIn, or `dv.py cards` | `render 00-intro 99-outro` (HTML) → `compose` |
| Subtitle or highlight look | `dv.py styles --apply` / `--set` → `demo/theme.json` | `render` (theme is in the cache key: every scene) → `compose` |
| Voice, speaking rate, provider | `config.json` narration → `narrate` | `narrate` → `render` (holds changed) → `compose` |
| BGM track or volume | `dv.py bgm use <id>` / `bgm probe <file>` / `theme.audio` | `compose` only |
| "Show this drag / scroll too", "drop that" | `storyboard.json` that scene's `interactions[]` decision + a step action | `validate` → `render <scene>` → `compose` |
| A locator no longer matches | `survey.json` locators + `storyboard.json` | `render <scene>` → `compose` |
| The core features are wrong | `survey.json` | from G1 |
| Total length | `config.json` targetSec, then scenes | `validate` (warns beyond ±15%) → from G2 |

Length, pacing and style rules are enforced by `validate` and the prelude, not by discussion: if a request breaks a rule (a 40-character subtitle, a 12-second scene), say which rule and offer the compliant version (split the line, split the scene).
