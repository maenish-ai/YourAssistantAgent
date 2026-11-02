$ErrorActionPreference = 'Stop'
try {
  $here = Split-Path -Parent $MyInvocation.MyCommand.Path
  $candidates = @($here, (Split-Path -Parent $here), (Get-Location).Path) | Select-Object -Unique
  $root = $null
  foreach ($dir in $candidates) {
    if ($dir -and (Test-Path (Join-Path $dir '.github/workflows/build-windows.yml')) -and (Test-Path (Join-Path $dir 'android'))) { $root = $dir; break }
  }
  if (-not $root) { throw 'Place both APPLY-FIX files in the root of YourAssistantAgent (next to the android and .github folders), then double-click APPLY-FIX.bat.' }
  $path = Join-Path $root '.github/workflows/build-windows.yml'
  $duplicate = Join-Path $root '.github/workflows/android-female-voice.yml'
  $legacy = Join-Path $root '.github/workflows/windows-build.yml'
  $content = [IO.File]::ReadAllText($path)
  $marker = '      - name: Restore private Android release key when configured'
  $install = @'
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install bundled voice model converter
        run: python -m pip install 'onnx==1.17.0'
'@
  if (-not $content.Contains('Install bundled voice model converter')) {
    if (-not $content.Contains($marker)) { throw 'The Android build step was not found. No changes made.' }
    $content = $content.Replace($marker, $install + "`n" + $marker)
  }
  $backup = $path + '.before-voice-fix.bak'
  if (-not (Test-Path $backup)) { [IO.File]::WriteAllText($backup, [IO.File]::ReadAllText($path)) }
  [IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding($false)))
  if (Test-Path $duplicate) { Remove-Item -LiteralPath $duplicate -Force; Write-Host 'Removed duplicate Android workflow.' }
  if (Test-Path $legacy) { Remove-Item -LiteralPath $legacy -Force; Write-Host 'Removed legacy Windows workflow.' }
  Write-Host 'Added ONNX to the canonical Android job.'
  Write-Host 'Workflow fixed locally. You still must Commit and Push in GitHub Desktop.'
} catch { Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }
