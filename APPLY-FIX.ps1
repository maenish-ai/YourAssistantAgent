$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
$workflow = Join-Path $root '.github\workflows\build-windows.yml'
$duplicate = Join-Path $root '.github\workflows\android-female-voice.yml'
if (-not (Test-Path -LiteralPath $workflow)) { throw 'Run this script from the repository root (build-windows.yml not found).' }
if (-not (Test-Path -LiteralPath (Join-Path $root '.git'))) { throw 'Repository .git not found. Open the correct GitHub Desktop repository.' }
# Remove the duplicate from the working tree; git stages its deletion below.
if (Test-Path -LiteralPath $duplicate) {
  Remove-Item -LiteralPath $duplicate -Force
  Write-Host 'Removed duplicate Android workflow.' -ForegroundColor Green
} else {
  Write-Host 'Duplicate workflow already absent.' -ForegroundColor Yellow
}
# Do not alter tests or bypass CI; they should validate the intended repository structure.
$all = @(Get-ChildItem -LiteralPath (Join-Path $root '.github\workflows') -File | Where-Object { $_.Extension -in @('.yml','.yaml') } | Select-Object -ExpandProperty Name)
Write-Host ('Remaining workflow files: ' + ($all -join ', '))
if ($all.Count -ne 1 -or $all[0] -ne 'build-windows.yml') { throw 'Other workflow files remain; review before committing.' }
& git add -A -- '.github/workflows/android-female-voice.yml'
if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
Write-Host 'Git status for workflows:'
& git status --short -- '.github/workflows'
if ($LASTEXITCODE -ne 0) { throw 'git status failed' }
$tracked = @(& git ls-files -- '.github/workflows/android-female-voice.yml')
if ($tracked.Count -gt 0 -and $tracked[0]) { Write-Host 'Deletion is staged; Git still lists the file until the commit. This is expected.' }
Write-Host ''
Write-Host 'NEXT: GitHub Desktop -> Commit to main -> Push origin. Verify the deletion appears in the commit.' -ForegroundColor Cyan
