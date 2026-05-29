param(
  [string]$OutputZip = "release_out\\ai_subtitle_tool_release.zip"
)

$ErrorActionPreference = "Stop"

python scripts\make_release_zip.py --out $OutputZip --check
