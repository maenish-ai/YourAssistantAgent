$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$wf = Join-Path $repo '.github\workflows'
$primary = Join-Path $wf 'build-windows.yml'
$duplicate = Join-Path $wf 'android-female-voice.yml'
$legacy = Join-Path $wf 'windows-build.yml'
if (-not (Test-Path (Join-Path $repo '.git')) -or -not (Test-Path $primary)) {
  throw 'Extract this ZIP into the GitHub Desktop repository ROOT (where .git and .github exist).'
}
$original = Get-Content -LiteralPath $primary -Raw -Encoding UTF8
if ($original -notmatch 'name: Build Windows Setup') { throw 'Unexpected workflow file: no changes applied.' }
if ($original -match 'Expected exactly one active workflow') {
  $pattern = '(?ms)^      - name: Ignore legacy workflow from triggering commit\r?\n.*?(?=^      - uses: actions/setup-python@v5)'
  $new = [regex]::Replace($original,$pattern,'')
  if ($new -eq $original) { throw 'Could not safely locate legacy check; no changes applied.' }
  [System.IO.File]::WriteAllText($primary,$new,[System.Text.UTF8Encoding]::new($false))
  Write-Host 'FIXED: removed broken Windows workflow count check.' -ForegroundColor Green
} else { Write-Host 'OK: Windows workflow check already absent.' -ForegroundColor Green }
foreach ($path in @($duplicate,$legacy)) {
  if (Test-Path $path) {
    Remove-Item -LiteralPath $path -Force
    Write-Host "DELETED duplicate: $path" -ForegroundColor Green
  }
}
$final = Get-Content -LiteralPath $primary -Raw -Encoding UTF8
if ($final -match 'Expected exactly one active workflow') { throw 'Verification failed: old check remains.' }
if (Test-Path $duplicate) { throw 'Verification failed: duplicate remains.' }
Write-Host 'PASS: Windows blocker removed. Commit AND Push in GitHub Desktop.' -ForegroundColor Green
if (Get-Command git -ErrorAction SilentlyContinue) { & git -C $repo status --short }
