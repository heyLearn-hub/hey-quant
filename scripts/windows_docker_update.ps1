param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$Branch = "main",
  [switch]$SkipPull,
  [switch]$SkipSmokeTest,
  [switch]$OnlyWhenRemoteChanged,
  [int]$LockMaxAgeMinutes = 120
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

if (-not (Test-Path ".git")) {
  throw "ProjectRoot is not a Git repository: $ProjectRoot"
}

New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$lockFile = Join-Path "logs" "windows_docker_update.lock"
if (Test-Path $lockFile) {
  $lockAge = (Get-Date) - (Get-Item $lockFile).LastWriteTime
  if ($lockAge.TotalMinutes -lt $LockMaxAgeMinutes) {
    Write-Host "Another update appears to be running. Lock file: $lockFile"
    exit 0
  }
  Write-Host "Removing stale update lock: $lockFile"
  Remove-Item -Force $lockFile
}
New-Item -ItemType File -Path $lockFile -Force -Value "pid=$PID started=$(Get-Date -Format o)" | Out-Null

$logFile = Join-Path "logs" ("windows_docker_update_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
Start-Transcript -Path $logFile | Out-Null

try {
  Write-Host "Project root: $ProjectRoot"
  Write-Host "Target branch: $Branch"
  Write-Host "Only when remote changed: $OnlyWhenRemoteChanged"

  docker info | Out-Null

  if (-not $SkipPull) {
    $dirty = git status --porcelain
    if ($dirty) {
      Write-Host "Git working tree is not clean:"
      $dirty | ForEach-Object { Write-Host $_ }
      throw "Refusing to pull with local tracked changes. Commit, stash, or revert them first."
    }

    git fetch origin $Branch
    git checkout $Branch
    if ($OnlyWhenRemoteChanged) {
      $currentCommit = (git rev-parse HEAD).Trim()
      $remoteCommit = (git rev-parse "origin/$Branch").Trim()
      Write-Host "Local commit:  $currentCommit"
      Write-Host "Remote commit: $remoteCommit"
      if ($currentCommit -eq $remoteCommit) {
        Write-Host "No remote change detected. Skipping Docker rebuild and restart."
        return
      }
    }
    git pull --ff-only origin $Branch
  }

  docker compose build
  docker compose up -d quant-ai-web

  if (-not $SkipSmokeTest) {
    docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --offline-sample --out outputs/update_smoke_report.html

    Start-Sleep -Seconds 3
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8765/" -UseBasicParsing -TimeoutSec 15
    if ($response.StatusCode -ne 200) {
      throw "Web smoke check failed with status code $($response.StatusCode)."
    }
  }

  docker compose ps
  Write-Host "Update complete."
  Write-Host "Web UI: http://127.0.0.1:8765"
  Write-Host "Log file: $logFile"
}
finally {
  if (Test-Path $lockFile) {
    Remove-Item -Force $lockFile
  }
  Stop-Transcript | Out-Null
}
