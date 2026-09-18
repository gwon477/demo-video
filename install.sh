#!/usr/bin/env bash
# demo-video skill installer (macOS / Linux). Idempotent: run again to update.
#   git clone https://github.com/gwon477/demo-video.git ~/.agent-skills/demo-video && ~/.agent-skills/demo-video/install.sh
set -euo pipefail

REPO_DIR="${DEMO_VIDEO_HOME:-$HOME/.agent-skills/demo-video}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$REPO_DIR/skills/demo-video"
TARGETS=("$HOME/.claude/skills/demo-video" "$HOME/.agents/skills/demo-video")

# 1. clone or update
if [ "$SELF_DIR" != "$REPO_DIR" ] && [ ! -d "$REPO_DIR/.git" ]; then
  echo "cloning into $REPO_DIR"
  git clone "$(git -C "$SELF_DIR" remote get-url origin 2>/dev/null || echo https://github.com/gwon477/demo-video.git)" "$REPO_DIR"
elif [ -d "$REPO_DIR/.git" ]; then
  echo "updating $REPO_DIR"
  git -C "$REPO_DIR" pull --ff-only || echo "warning: could not pull (offline or no credentials) - installing the checkout as is"
fi
[ -f "$SKILL_SRC/SKILL.md" ] || { echo "error: $SKILL_SRC/SKILL.md not found" >&2; exit 1; }

# 2. link (or copy) the skill into each agent's skill folder
for target in "${TARGETS[@]}"; do
  mkdir -p "$(dirname "$target")"
  if [ -L "$target" ]; then
    rm "$target"
  elif [ -d "$target" ]; then
    backup="$target.backup-$(date +%Y%m%d-%H%M%S)"
    echo "existing folder moved to $backup"
    mv "$target" "$backup"
  fi
  if ln -s "$SKILL_SRC" "$target" 2>/dev/null; then
    echo "linked  $target -> $SKILL_SRC"
  else
    cp -R "$SKILL_SRC" "$target"
    echo "copied  $target (symlink failed; re-run install.sh after each update)"
  fi
done

# 3. environment check
echo
python3 "$SKILL_SRC/scripts/dv.py" doctor --offline || {
  echo
  echo "some required tools are missing - install what doctor listed, then run: python3 $SKILL_SRC/scripts/dv.py doctor"
  exit 1
}
echo
echo "done. In a project folder with your app running, tell your agent:"
echo '  "이 프로젝트 데모 영상 만들어줘. 앱은 http://localhost:3000 에 떠 있어."'
