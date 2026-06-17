param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
  Write-Error "Missing virtualenv Python: $Python. Run: py -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e .[dev]"
}

$env:PYTHONPATH = (Join-Path $Root "src") + ";" + $env:PYTHONPATH
$EnvPath = Join-Path $Root ".env"
if (Test-Path $EnvPath) {
  Get-Content $EnvPath | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
      $name = $matches[1].Trim()
      $value = $matches[2].Trim().Trim('"')
      [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
  }
}

& $Python -m quant_ai_system.cli @Args

