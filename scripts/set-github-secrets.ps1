<#
.SYNOPSIS
  Push the keys from your local .env into this repo's GitHub Actions secrets.

.DESCRIPTION
  Reads .env and sets each required secret via the gh CLI, so the daily workflow
  can run. Run once after filling in .env. Requires `gh auth login`.

.EXAMPLE
  ./scripts/set-github-secrets.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $root ".env"

if (-not (Test-Path $envFile)) {
    throw "No .env found at $envFile. Copy .env.example to .env and fill in your keys first."
}

# Secrets the GitHub Actions workflow expects.
$required = @("AIRTABLE_TOKEN", "YT_AIRTABLE_BASE_ID", "YOUTUBE_API_KEY", "GEMINI_API_KEY")

$values = @{}
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $idx = $line.IndexOf("=")
        $name = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim().Trim('"')
        $values[$name] = $val
    }
}

Set-Location $root
foreach ($key in $required) {
    $v = $values[$key]
    if ([string]::IsNullOrWhiteSpace($v) -or $v -like "*xxx*") {
        Write-Host "SKIP $key — not set in .env" -ForegroundColor Yellow
        continue
    }
    gh secret set $key --body $v
    Write-Host "SET  $key" -ForegroundColor Green
}
Write-Host "`nDone. Verify with: gh secret list" -ForegroundColor Cyan
