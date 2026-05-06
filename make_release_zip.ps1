param(
  [string]$OutputZip = "release.zip"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root
try {
  python .\scripts\make_release_zip.py --out $OutputZip --check
}
finally {
  Pop-Location
}
