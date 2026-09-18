# demo-video skill installer (Windows PowerShell). Idempotent: run again to update.
#   git clone git@github.com:gwon477/demo-video.git $HOME\.agent-skills\demo-video; & $HOME\.agent-skills\demo-video\install.ps1
$ErrorActionPreference = "Stop"
$RepoDir = if ($env:DEMO_VIDEO_HOME) { $env:DEMO_VIDEO_HOME } else { Join-Path $HOME ".agent-skills\demo-video" }
$SelfDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillSrc = Join-Path $RepoDir "skills\demo-video"
$Targets = @((Join-Path $HOME ".claude\skills\demo-video"), (Join-Path $HOME ".agents\skills\demo-video"))

if ($SelfDir -ne $RepoDir -and -not (Test-Path (Join-Path $RepoDir ".git"))) {
  Write-Host "cloning into $RepoDir"
  git clone git@github.com:gwon477/demo-video.git $RepoDir
} elseif (Test-Path (Join-Path $RepoDir ".git")) {
  Write-Host "updating $RepoDir"
  git -C $RepoDir pull --ff-only
}
if (-not (Test-Path (Join-Path $SkillSrc "SKILL.md"))) { throw "$SkillSrc\SKILL.md not found" }

foreach ($target in $Targets) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
  if (Test-Path $target) {
    $item = Get-Item $target -Force
    if ($item.LinkType) { Remove-Item $target -Force }
    else { $backup = "$target.backup-$(Get-Date -Format yyyyMMdd-HHmmss)"; Write-Host "existing folder moved to $backup"; Move-Item $target $backup }
  }
  try {
    New-Item -ItemType SymbolicLink -Path $target -Target $SkillSrc | Out-Null   # needs Developer Mode or admin
    Write-Host "linked  $target -> $SkillSrc"
  } catch {
    Copy-Item -Recurse -Force $SkillSrc $target
    Write-Host "copied  $target (symlink needs Developer Mode; re-run install.ps1 after each update)"
  }
}

Write-Host ""
$python = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }
& $python (Join-Path $SkillSrc "scripts\dv.py") doctor --offline
if ($LASTEXITCODE -ne 0) { Write-Host "`nsome required tools are missing - install what doctor listed, then run doctor again"; exit 1 }
Write-Host "`ndone. In a project folder with your app running, tell your agent:"
Write-Host '  "이 프로젝트 데모 영상 만들어줘. 앱은 http://localhost:3000 에 떠 있어."'
