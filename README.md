# demo-video

실행 중인 웹앱을 읽고 조작하며 녹화해 데모 영상(mp4)을 만드는 Agent Skill. Claude Code, Codex CLI, Grok Build에서 같은 파일을 읽습니다. 조사 → 콘티 → 상세 설계 → 렌더 → 합성 → 레드팀 검토 순서로 진행하며, 네 곳(핵심 기능, 콘티, 상세 설계, 최종본)에서 사용자 승인을 받습니다.

## 설치 (비공개 저장소: GitHub 로그인 또는 SSH 키 필요)

macOS / Linux

```bash
git clone git@github.com:gwon477/demo-video.git ~/.agent-skills/demo-video && ~/.agent-skills/demo-video/install.sh
```

Windows (PowerShell, 개발자 모드가 꺼져 있으면 링크 대신 복사)

```powershell
git clone git@github.com:gwon477/demo-video.git $HOME\.agent-skills\demo-video; & $HOME\.agent-skills\demo-video\install.ps1
```

설치 스크립트는 `~/.claude/skills/demo-video`와 `~/.agents/skills/demo-video`에 링크를 걸고 `dv.py doctor`를 실행해 부족한 도구를 알려줍니다. 필요한 것: Python 3.10+, Node 18+, `npm install -g @playwright/cli`, ffmpeg. 나레이션은 macOS `say` 또는 `pip install edge-tts`.

## 업데이트

```bash
~/.agent-skills/demo-video/install.sh
```

## 사용

데모할 프로젝트 폴더에서 앱을 먼저 띄운 뒤 에이전트에게:

```
이 프로젝트 데모 영상 만들어줘. 앱은 http://localhost:3000 에 떠 있어.
```

에이전트는 `doctor` → `init`(URL·계정·시청자·목표 길이·나레이션·BGM·인트로 영상 여부를 묻습니다) → 조사(G1) → 콘티(G2) → storyboard·시트·스타일·인트로 카드(G3) → 렌더 → 합성 → 검증 → 레드팀 검토 → 최종 확인(G4) 순으로 진행합니다. 산출물은 프로젝트의 `demo/` 아래에 남습니다.

## 스킬을 자동 인식하지 못하는 도구

`AGENTS.md`의 문단을 프로젝트의 AGENTS.md에 붙여 넣으세요. Claude Code만 쓰는 팀원은 `/plugin marketplace add gwon477/demo-video` 경로도 있습니다.

## 저장소 구조

```
skills/demo-video/     SKILL.md, references/, scripts/dv.py + lib/, prelude.js, assets/(theme, intro/outro, styles, bgm)
examples/sample-app/   회귀 테스트용 정적 앱과 기준 storyboard
tests/                 unittest (python3 -m unittest, tests/ 에서 실행)
docs/                  DESIGN.md (설계·구현 문서), PD-STANDARDS.md (수치 근거)
```

설계와 규칙 번호(FR-xxx)는 `docs/DESIGN.md`에 있습니다. 저장소에는 사내 URL, 계정, 제품 화면을 넣지 않습니다.
