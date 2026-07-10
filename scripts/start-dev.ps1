param(
    [ValidateSet("ensure-env", "ensure-redis", "backend", "celery", "frontend", "full")]
    [string]$Mode = "full"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendEnv = Join-Path $Root "backend\.env"
$BackendExample = Join-Path $Root "backend\.env.example"
$FrontendEnv = Join-Path $Root "frontend\.env"
$FrontendExample = Join-Path $Root "frontend\.env.example"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$BackendUrl = "http://127.0.0.1:8891"
$LocalCorsOrigins = @(
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://localhost:3000"
)
if (-not (Test-Path $Python)) { $Python = "python" }
$Npm = "npm"
$NpmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($NpmCmd) { $Npm = $NpmCmd.Source }

function Ensure-BackendCorsOrigins {
    param([string]$Content)

    $lines = $Content -split "\r?\n"
    $found = $false
    $updated = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines) {
        if ($line -match "^CORS_ORIGINS=(.*)$") {
            $found = $true
            $origins = New-Object System.Collections.Generic.List[string]
            foreach ($origin in ($Matches[1] -split ",")) {
                $trimmed = $origin.Trim()
                if ($trimmed -and -not $origins.Contains($trimmed)) {
                    $origins.Add($trimmed)
                }
            }
            foreach ($origin in $LocalCorsOrigins) {
                if (-not $origins.Contains($origin)) {
                    $origins.Add($origin)
                }
            }
            $updated.Add("CORS_ORIGINS=$($origins -join ',')")
        } elseif ($line -ne "") {
            $updated.Add($line)
        }
    }
    if (-not $found) {
        $updated.Insert(0, "CORS_ORIGINS=$($LocalCorsOrigins -join ',')")
    }
    return (($updated -join "`r`n") + "`r`n")
}

function Ensure-Env {
    if (-not (Test-Path $BackendEnv)) {
        if (Test-Path $BackendExample) {
            $content = Get-Content -LiteralPath $BackendExample -Raw
            $content = $content.Replace("UPLOAD_DIR=/app/uploads", "UPLOAD_DIR=backend/uploads")
            $content = $content.Replace("OUTPUT_DIR=/app/outputs", "OUTPUT_DIR=backend/outputs")
            $content = $content.Replace("TEMP_DIR=/app/tmp", "TEMP_DIR=backend/tmp")
            $content = $content.Replace("REDIS_URL=redis://redis:6379/0", "REDIS_URL=redis://127.0.0.1:6379/0")
            $content = $content.Replace("CELERY_BROKER_URL=redis://redis:6379/0", "CELERY_BROKER_URL=redis://127.0.0.1:6379/0")
            $content = $content.Replace("CELERY_RESULT_BACKEND=redis://redis:6379/1", "CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1")
            $content = Ensure-BackendCorsOrigins $content
            Set-Content -LiteralPath $BackendEnv -Value $content -Encoding UTF8
            Write-Host "Created backend\.env from backend\.env.example"
        } else {
            Write-Error "backend\.env is missing and backend\.env.example was not found."
        }
    }
    if (-not (Test-Path $FrontendEnv) -and (Test-Path $FrontendExample)) {
        Copy-Item -LiteralPath $FrontendExample -Destination $FrontendEnv
        Write-Host "Created frontend\.env from frontend\.env.example"
    }
    if (Test-Path $FrontendEnv) {
        $frontendContent = Get-Content -LiteralPath $FrontendEnv -Raw
        $updatedFrontendContent = $frontendContent -replace "(?m)^VITE_API_BASE_URL=.*$", "VITE_API_BASE_URL=$BackendUrl"
        if ($updatedFrontendContent -notmatch "(?m)^VITE_API_BASE_URL=") {
            $updatedFrontendContent = "VITE_API_BASE_URL=$BackendUrl`r`n$updatedFrontendContent"
        }
        if ($updatedFrontendContent -ne $frontendContent) {
            Set-Content -LiteralPath $FrontendEnv -Value $updatedFrontendContent -Encoding UTF8
            Write-Host "Updated frontend\.env VITE_API_BASE_URL to $BackendUrl"
        }
    }
    if (Test-Path $BackendEnv) {
        $backendContent = Get-Content -LiteralPath $BackendEnv -Raw
        $updatedBackendContent = Ensure-BackendCorsOrigins $backendContent
        if ($updatedBackendContent -ne $backendContent) {
            Set-Content -LiteralPath $BackendEnv -Value $updatedBackendContent -Encoding UTF8
            Write-Host "Updated backend\.env CORS_ORIGINS for local F5 frontend origins"
        }
    }
}

function Ensure-Redis {
    $redisOpen = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($redisOpen) {
        Write-Host "Redis is available on 127.0.0.1:6379"
        return
    }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($docker) {
        docker compose up -d redis
        Start-Sleep -Seconds 2
        $redisOpen = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($redisOpen) {
            Write-Host "Redis started with docker compose."
            return
        }
    }
    Write-Warning "Redis is not reachable. Use scripts\dev_start.py --redis auto for eager fallback, or start Redis manually."
}

Ensure-Env

switch ($Mode) {
    "ensure-env" { return }
    "ensure-redis" { Ensure-Redis; return }
    "backend" { $env:ENVIRONMENT = "development"; $env:API_PORT = "8891"; & $Python -m uvicorn backend.main:app --host 127.0.0.1 --port 8891 --reload; return }
    "celery" { Ensure-Redis; & $Python -m celery -A backend.celery_app:celery_app worker --loglevel=info; return }
    "frontend" { $env:VITE_API_BASE_URL = $BackendUrl; Push-Location (Join-Path $Root "frontend"); & $Npm run dev -- --host 127.0.0.1 --port 5173; Pop-Location; return }
    "full" { & $Python (Join-Path $Root "scripts\dev_start.py") --redis auto; return }
}
