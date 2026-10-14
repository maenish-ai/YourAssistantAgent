param(
    [switch]$SkipBrowserInstall,
    [switch]$SkipTests,
    [switch]$SkipLocalAI
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "=== Your Assistant Agent Windows Build ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    py -3 -m venv .venv
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Pip = @($Python, "-m", "pip")

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt

if (-not $SkipTests) {
    Write-Host "Running tests..."
    $env:PYTHONPATH = $ProjectRoot
    & $Python -m pytest -q
}

$BrowserDir = Join-Path $ProjectRoot "assets\playwright-browsers"
if (-not $SkipBrowserInstall) {
    Write-Host "Installing bundled Playwright Chromium..."
    New-Item -ItemType Directory -Force -Path $BrowserDir | Out-Null
    $env:PLAYWRIGHT_BROWSERS_PATH = $BrowserDir
    & $Python -m playwright install chromium
}

Write-Host "Checking required application modules..."
$env:PYTHONPATH = $ProjectRoot
& $Python -c "import your_assistant_agent.github_deploy; import your_assistant_agent.local_ai_runtime; import your_assistant_agent.ui; print('Required modules OK')"

if (-not $SkipLocalAI) {
    Write-Host "Preparing bundled Dual Local AI (llama.cpp + Qwen3-0.6B + RightNow Arabic 0.5B)..."
    & (Join-Path $PSScriptRoot "prepare_local_ai.ps1")
}

Write-Host "Building Windows application..."
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }

$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "YourAssistantAgent",
    "--icon", "assets\icon.ico",
    "--add-data", "assets;assets",
    "--collect-all", "playwright",
    "app.py"
)

& $Python -m PyInstaller @PyInstallerArgs

$DistDir = Join-Path $ProjectRoot "dist\YourAssistantAgent"
if (-not (Test-Path (Join-Path $DistDir "YourAssistantAgent.exe"))) {
    throw "Build failed: YourAssistantAgent.exe was not created."
}

$OutputDir = Join-Path $ProjectRoot "release"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# Optional Inno Setup installer if ISCC exists.
$IsccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if ($Iscc) {
    Write-Host "Building installer with Inno Setup..."
    & $Iscc "installer\YourAssistantAgent.iss"
    Write-Host "Installer build completed." -ForegroundColor Green
} else {
    throw "Inno Setup was not found, so the Setup EXE could not be created."
}

Write-Host "=== Build complete ===" -ForegroundColor Cyan
