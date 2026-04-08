param(
  [string]$OutputZip = "ai_subtitle_tool_release.zip"
)

$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$releasePkg = Join-Path $root "release_pkg"
$staging = Join-Path $root ".release_staging"
$zipPath = Join-Path $root $OutputZip

# Rebuild release_pkg from the current working tree (root is source-of-truth).
if (Test-Path $releasePkg) {
  Remove-Item -Recurse -Force -LiteralPath $releasePkg
}
New-Item -ItemType Directory -Path $releasePkg | Out-Null

# Stage a clean tree without dev/workspace artifacts.
$excludeDirNames = @(
  ".git",
  ".release_staging",
  "release_pkg",
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
  $releasePkg,
  "/MIR",
  "/XD"
) + $excludeDirNames + @(
  "/XF",
  "*.pyc",
  "*.pyo",
  "*.pyd",
  "*.log",
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

# Hard guarantee: release must not contain node_modules even if robocopy misses it.
$dangerPaths = @(
  (Join-Path $releasePkg "frontend\\node_modules"),
  (Join-Path $releasePkg "frontend\\dist"),
  (Join-Path $releasePkg "frontend\\.npm-cache"),
  (Join-Path $releasePkg "tests\\_tmp"),
  (Join-Path $releasePkg "tests\\__pycache__")
)
foreach ($p in $dangerPaths) {
  if (Test-Path $p) {
    Remove-Item -Recurse -Force -LiteralPath $p
  }
}

# Fail fast if any forbidden paths still exist inside release_pkg.
$forbiddenPatterns = @(
  "\\.git(\\\\|$)",
  "\\frontend\\node_modules(\\\\|$)",
  "\\frontend\\dist(\\\\|$)",
  "\\frontend\\.npm-cache(\\\\|$)",
  "\\tests\\_tmp(\\\\|$)",
  "\\__pycache__(\\\\|$)"
)
$foundForbidden = @()
foreach ($pattern in $forbiddenPatterns) {
  $matches = Get-ChildItem -LiteralPath $releasePkg -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match $pattern } |
    Select-Object -First 20
  if ($matches) {
    $foundForbidden += $matches
  }
}
if ($foundForbidden.Count -gt 0) {
  Write-Output "Forbidden paths found in release_pkg (showing up to 20):"
  $foundForbidden | ForEach-Object { Write-Output $_.FullName }
  throw "Release package is not clean; aborting."
}

if (Test-Path $zipPath) {
  Remove-Item -Force -LiteralPath $zipPath
}

# Create zip from the freshly regenerated release_pkg so both artifacts are consistent.
Compress-Archive -Path (Join-Path $releasePkg "*") -DestinationPath $zipPath -Force

# Cleanup staging if left from previous runs (avoid misleading artifacts).
if (Test-Path $staging) {
  Remove-Item -Recurse -Force -LiteralPath $staging
}

Write-Output "Release package created: $releasePkg"
Write-Output "Release zip created: $zipPath"
