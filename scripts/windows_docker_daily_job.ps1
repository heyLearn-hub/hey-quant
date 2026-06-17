param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [switch]$SendEmail,
  [switch]$SendTelegram
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

if ($SendTelegram) {
  $args += "--send-telegram"
}

docker @args
