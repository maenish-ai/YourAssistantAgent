$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$gitDir = Join-Path $repo '.git'
$wfDir = Join-Path $repo '.github\workflows'
$primary = Join-Path $wfDir 'build-windows.yml'
$duplicate = Join-Path $wfDir 'android-female-voice.yml'
if (-not (Test-Path $gitDir) -or -not (Test-Path $primary)) {
  Write-Host 'ERROR: Place both repair files in the repository root (beside .git and .github).' -ForegroundColor Red
  exit 1
}
# Remove the obsolete workflow from the working tree so GitHub Desktop can commit its deletion.
if (Test-Path $duplicate) {
  Remove-Item -LiteralPath $duplicate -Force
  Write-Host 'Removed duplicate Android workflow.' -ForegroundColor Green
} else {
  Write-Host 'Duplicate workflow already absent.'
}
# Remove the brittle validation that aborts Windows builds if another workflow exists.
$content = [System.IO.File]::ReadAllText($primary)
$pattern = '(?ms)^      - name: Ignore legacy workflow from triggering commit\r?\n        shell: pwsh\r?\n        run: \|\r?\n(?:          .*\r?\n|\r?\n)*?(?=      - uses: actions/setup-python@v5)'
$updated = [regex]::Replace($content, $pattern, '', 1)
if ($updated -ne $content) {
  [System.IO.File]::WriteAllText($primary, $updated, (New-Object System.Text.UTF8Encoding($false)))
  Write-Host 'Removed failing one-workflow-only gate from Windows build.' -ForegroundColor Green
} elseif ($content -match 'Expected exactly one active workflow') {
  Write-Host 'ERROR: Validation block not recognized. No workflow edit performed.' -ForegroundColor Red
  exit 1
} else {
  Write-Host 'Windows validation gate already absent.'
}
Write-Host ''
Write-Host 'NEXT: GitHub Desktop -> Commit to main -> Push origin.' -ForegroundColor Cyan
if (Get-Command git -ErrorAction SilentlyContinue) { & git -C $repo status --short }
