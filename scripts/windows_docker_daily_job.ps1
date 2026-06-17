param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [switch]$SendEmail
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

$args = @(
  "compose", "--profile", "job", "run", "--rm", "quant-ai-job",
  "run",
  "--config", "config/default.yaml",
  "--out", "outputs/latest_report.html"
)

if ($SendEmail) {
  $args += "--send-email"
}

docker @args
