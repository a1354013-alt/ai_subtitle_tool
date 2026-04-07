param(
  [string]$OutputZip = "ai_subtitle_tool_release.zip"
)

$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$staging = Join-Path $root ".release_staging"
$zipPath = Join-Path $root $OutputZip

if (Test-Path $staging) {
  Remove-Item -Recurse -Force -LiteralPath $staging
}
New-Item -ItemType Directory -Path $staging | Out-Null

# Stage a clean tree without dev/workspace artifacts.
robocopy $root $staging /MIR `
  /XD ".git" ".release_staging" "release_pkg" `
      "frontend\\node_modules" "frontend\\dist" "frontend\\.vite" `
      "backend\\uploads" "tests\\_tmp" "__pycache__" ".pytest_cache" ".mypy_cache" `
  /XF "*.pyc" "*.pyo" "*.pyd" "*.log" "*.zip" "*.tar.gz" "*.tmp" `
  /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null

# Hard guarantee: release must not contain node_modules even if robocopy misses it.
if (Test-Path (Join-Path $staging "frontend\\node_modules")) {
  Remove-Item -Recurse -Force -LiteralPath (Join-Path $staging "frontend\\node_modules")
}

if (Test-Path $zipPath) {
  Remove-Item -Force -LiteralPath $zipPath
}

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force

# Cleanup staging (avoid leaving misleading artifacts).
Remove-Item -Recurse -Force -LiteralPath $staging

Write-Output "Release zip created: $zipPath"

