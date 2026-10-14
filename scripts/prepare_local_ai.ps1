param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AiRoot = Join-Path $ProjectRoot "assets\local_ai"
$RuntimeDir = Join-Path $AiRoot "runtime"
$ModelsDir = Join-Path $AiRoot "models"
$TempDir = Join-Path $AiRoot "_download"

$LlamaTag = "b11429"
$LlamaAsset = "llama-b11429-bin-win-cpu-x64.zip"
$LlamaUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$LlamaTag/$LlamaAsset"
$LlamaSha256 = "1283323272b04cd07905816a597a0da810918102de958f4ff6f7bbaa70ed2efe"

$Models = @(
    @{
        Id = "general"
        Name = "Qwen3-0.6B GGUF Q4_0"
        File = "Qwen3-0.6B-Q4_0.gguf"
        Url = "https://huggingface.co/ggml-org/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_0.gguf"
        Sha256 = "da2572f16c06133561ce56accaa822216f2391ef4d37fba427801cd6736417d4"
        Source = "https://huggingface.co/ggml-org/Qwen3-0.6B-GGUF"
        License = "Apache-2.0"
    },
    @{
        Id = "arabic"
        Name = "RightNow-Arabic-0.5B-Turbo GGUF Q4_K_M"
        File = "RightNow-Arabic-0.5B-Turbo-q4_k_m.gguf"
        Url = "https://huggingface.co/RightNowAI/RightNow-Arabic-0.5B-Turbo/resolve/main/gguf/RightNow-Arabic-0.5B-Turbo-q4_k_m.gguf"
        Sha256 = "03a58f3cb23af68dbe4247ac2f3f67fdeb8bc3df8bb7e41e0ac0049f8b5211a1"
        Source = "https://huggingface.co/RightNowAI/RightNow-Arabic-0.5B-Turbo"
        License = "Apache-2.0"
    }
)

New-Item -ItemType Directory -Force -Path $RuntimeDir, $ModelsDir, $TempDir | Out-Null

function Assert-Sha256([string]$Path, [string]$Expected) {
    if (-not (Test-Path $Path)) { throw "Missing file: $Path" }
    $Actual = (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected.ToLowerInvariant()) {
        throw "SHA256 mismatch for $Path. Expected $Expected but got $Actual"
    }
}

function Download-File([string]$Url, [string]$OutFile) {
    Write-Host "Downloading $Url" -ForegroundColor Cyan
    & curl.exe -L --fail --retry 5 --retry-delay 3 --output $OutFile $Url
    if ($LASTEXITCODE -ne 0) { throw "Download failed: $Url" }
}

$ServerExe = Join-Path $RuntimeDir "llama-server.exe"
if ($Force -or -not (Test-Path $ServerExe)) {
    $ZipPath = Join-Path $TempDir $LlamaAsset
    if ($Force -or -not (Test-Path $ZipPath)) {
        Download-File $LlamaUrl $ZipPath
    }
    Assert-Sha256 $ZipPath $LlamaSha256

    $ExtractDir = Join-Path $TempDir "llama"
    if (Test-Path $ExtractDir) { Remove-Item $ExtractDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

    $FoundServer = Get-ChildItem $ExtractDir -Recurse -Filter "llama-server.exe" | Select-Object -First 1
    if (-not $FoundServer) { throw "llama-server.exe was not found in $LlamaAsset" }
    if (Test-Path $RuntimeDir) { Remove-Item $RuntimeDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    Copy-Item -Path (Join-Path $FoundServer.Directory.FullName "*") -Destination $RuntimeDir -Recurse -Force
}

foreach ($Model in $Models) {
    $ModelPath = Join-Path $ModelsDir $Model.File
    $NeedModel = $Force -or -not (Test-Path $ModelPath)
    if (-not $NeedModel) {
        try { Assert-Sha256 $ModelPath $Model.Sha256 } catch { $NeedModel = $true }
    }
    if ($NeedModel) {
        if (Test-Path $ModelPath) { Remove-Item $ModelPath -Force }
        Download-File $Model.Url $ModelPath
    }
    Assert-Sha256 $ModelPath $Model.Sha256
    Write-Host "Verified $($Model.Id) model: $ModelPath" -ForegroundColor Green
}

$ModelNotice = ($Models | ForEach-Object {
@"
Model ($($_.Id)): $($_.Name)
Source: $($_.Source)
License: $($_.License)
File: $($_.File)
SHA256: $($_.Sha256)
"@
}) -join "`r`n"

$Notice = @"
Your Assistant Agent Dual Local AI Bundle

Runtime: llama.cpp $LlamaTag
Source: https://github.com/ggml-org/llama.cpp
License: MIT
Pinned asset: $LlamaAsset
SHA256: $LlamaSha256

$ModelNotice
The Windows build downloads and verifies these pinned files before packaging them.
Only one model is loaded at a time. Auto mode uses the Arabic model for Arabic messages
and the general Qwen model for other text. Local inference binds only to 127.0.0.1 and
requires no API token.
"@
Set-Content -Path (Join-Path $AiRoot "THIRD_PARTY_NOTICES.txt") -Value $Notice -Encoding UTF8

if (Test-Path $TempDir) { Remove-Item $TempDir -Recurse -Force }
Write-Host "Dual Local AI bundle is ready." -ForegroundColor Green
Write-Host "Runtime: $ServerExe"
foreach ($Model in $Models) {
    Write-Host ("Model {0}: {1}" -f $Model.Id, (Join-Path $ModelsDir $Model.File))
}
