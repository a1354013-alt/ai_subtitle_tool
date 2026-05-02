param(
  [string]$OutputZip = "release_out\\ai_subtitle_tool_release.zip"
)

$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$staging = Join-Path $root ".release_staging"
$zipPath = if ([System.IO.Path]::IsPathRooted($OutputZip)) { $OutputZip } else { Join-Path $root $OutputZip }
$zipDir = Split-Path -Parent $zipPath

if (!(Test-Path $zipDir)) {
  New-Item -ItemType Directory -Path $zipDir | Out-Null
}

# Stage a clean tree without dev/workspace artifacts.
$excludeDirNames = @(
  ".git",
  ".release_staging",
  "release_out",
  "node_modules",
  "dist",
  ".vite",
  ".npm-cache",
  "uploads",
  "_tmp",
  "_tmp_mplconfig",
  "__pycache__",
  ".pytest_cache",
  ".mypy_cache"
)

$robocopyArgs = @(
  $root,
  $staging,
  "/MIR",
  "/XD"
) + $excludeDirNames + @(
  "/XF",
  "*.pyc",
  "*.pyo",
  "*.pyd",
  "*.log",
  "*.mp4",
  "*.srt",
  "*.ass",
  "*.vtt",
  "*.sqlite3",
  "*.db",
  "*.zip",
  "*.tar.gz",
  "*.tmp",
  "tests\\_tmp_file_inventory.txt",
  "/NFL",
  "/NDL",
  "/NJH",
  "/NJS",
  "/NC",
  "/NS",
  "/NP"
)

robocopy @robocopyArgs | Out-Null

$dangerPaths = @(
  (Join-Path $staging "frontend\\node_modules"),
  (Join-Path $staging "frontend\\dist"),
  (Join-Path $staging "frontend\\.npm-cache"),
  (Join-Path $staging "frontend\\coverage"),
  (Join-Path $staging "tests\\_tmp"),
  (Join-Path $staging "tests\\_tmp_mplconfig"),
  (Join-Path $staging "tests\\__pycache__"),
  (Join-Path $staging ".pytest_cache"),
  (Join-Path $staging "htmlcov"),
  (Join-Path $staging ".coverage")
)
foreach ($p in $dangerPaths) {
  if (Test-Path $p) {
    Remove-Item -Recurse -Force -LiteralPath $p
  }
}

# Fail fast if any forbidden paths still exist inside staging.
$forbiddenPatterns = @(
  "\\.git(\\\\|$)",
  "\\frontend\\node_modules(\\\\|$)",
  "\\frontend\\dist(\\\\|$)",
  "\\frontend\\.npm-cache(\\\\|$)",
  "\\frontend\\coverage(\\\\|$)",
  "\\backend\\uploads(\\\\|$)",
  "\\tests\\_tmp(\\\\|$)",
  "\\tests\\_tmp_mplconfig(\\\\|$)",
  "\\__pycache__(\\\\|$)",
  "\\.pytest_cache(\\\\|$)",
  "\\htmlcov(\\\\|$)",
  "\\.coverage(\\\\|$)"
)
$foundForbidden = @()
foreach ($pattern in $forbiddenPatterns) {
  $matches = Get-ChildItem -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match $pattern } |
    Select-Object -First 20
  if ($matches) {
    $foundForbidden += $matches
  }
}
if ($foundForbidden.Count -gt 0) {
  Write-Output "Forbidden paths found in staging (showing up to 20):"
  $foundForbidden | ForEach-Object { Write-Output $_.FullName }
  throw "Release package is not clean; aborting."
}

if (Test-Path $zipPath) {
  Remove-Item -Force -LiteralPath $zipPath
}

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force

# Cleanup staging (avoid leaving misleading artifacts in the source tree).
Remove-Item -Recurse -Force -LiteralPath $staging

Write-Output "Release zip created: $zipPath"
