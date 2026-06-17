param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$Branch = "main",
  [switch]$SkipPull,
  [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

if (-not (Test-Path ".git")) {
  throw "ProjectRoot is not a Git repository: $ProjectRoot"
}

New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$logFile = Join-Path "logs" ("windows_docker_update_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
Start-Transcript -Path $logFile | Out-Null

try {
  Write-Host "Project root: $ProjectRoot"
  Write-Host "Target branch: $Branch"

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
  Stop-Transcript | Out-Null
}
