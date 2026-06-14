<#
.SYNOPSIS
  Load .env into the process environment and run the engine.

.EXAMPLE
  ./scripts/run.ps1 generate
  ./scripts/run.ps1 repurpose
  ./scripts/run.ps1 all
  $env:YT_DRY_RUN="true"; ./scripts/run.ps1 generate   # safe dry-run

Python reads config from environment variables; this script loads your gitignored
.env so you don't have to export each var by hand.
#>
param([string]$Phase = "all")

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $root ".env"

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $idx = $line.IndexOf("=")
            $name = $line.Substring(0, $idx).Trim()
            $val = $line.Substring($idx + 1).Trim().Trim('"')
            Set-Item -Path "Env:$name" -Value $val
        }
    }
    Write-Host "Loaded .env" -ForegroundColor Green
} else {
    Write-Host "No .env found — relying on existing environment variables." -ForegroundColor Yellow
}

Set-Location $root
python -m yt_content.main $Phase
