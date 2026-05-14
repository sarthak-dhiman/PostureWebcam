$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

<#
One-click Windows release build:
1) Verifies Python + build files exist
2) Runs build_executable.py with production defaults
3) Verifies ONNX Runtime-safe Inno Setup compression settings
4) Compiles Inno Setup installer if ISCC is installed
#>

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildScript = Join-Path $Root "build_executable.py"
$IssScript = Join-Path $Root "posturecam_setup.iss"
$DistDir = Join-Path $Root "dist"
$AppDir = Join-Path $DistDir "PostureCam"
$InstallerPath = Join-Path $DistDir "PostureCamSetup.exe"
$IsccPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Require-Path([string]$PathValue, [string]$Label) {
    if (-not (Test-Path $PathValue)) {
        throw "$Label not found: $PathValue"
    }
}

function Assert-OnnxSafeInstallerSettings([string]$ScriptPath) {
    $content = Get-Content -Path $ScriptPath -Raw
    $hasNoCompression = $content -match '(?im)^\s*Compression\s*=\s*none\s*$'
    $hasNoSolidCompression = $content -match '(?im)^\s*SolidCompression\s*=\s*no\s*$'
    $hasLzmaSetting = $content -match '(?im)^\s*LZMA'

    if (-not $hasNoCompression -or -not $hasNoSolidCompression -or $hasLzmaSetting) {
        throw @"
Inno Setup compression is not ONNX Runtime-safe in:
  $ScriptPath

Use these settings before compiling the installer:
  Compression=none
  SolidCompression=no

Do not use LZMA/LZMA2 or solid compression for this installer. The app ships
ONNX Runtime native DLL/PYD files, and aggressive installer compression has
caused ONNX Runtime import failures after installation.
"@
    }

    Write-Host "Installer compression: ONNX Runtime-safe (no compression, no solid archive)" -ForegroundColor Green
}

Write-Step "Validating prerequisites"
Require-Path $BuildScript "Build script"
Require-Path $IssScript "Inno Setup script"

$VenvPython = Join-Path $Root "venv310\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCmd) {
        throw "python is not on PATH and venv python was not found at $VenvPython."
    }
    $PythonExe = $PythonCmd.Source
}

Write-Host "Python: $PythonExe" -ForegroundColor DarkGray

Write-Step "Building PostureCam dist with production endpoints"
Push-Location $Root
try {
    & $PythonExe $BuildScript
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

Require-Path $AppDir "Built app directory"
Write-Host "Built app directory: $AppDir" -ForegroundColor Green

Write-Step "Checking installer compression settings"
Assert-OnnxSafeInstallerSettings $IssScript

Write-Step "Compiling installer with Inno Setup"
if (-not (Test-Path $IsccPath)) {
    Write-Warning "Inno Setup compiler not found at: $IsccPath"
    Write-Warning "Install Inno Setup 6, then rerun this script."
    Write-Host "App build is ready at: $AppDir" -ForegroundColor Yellow
    exit 0
}

Push-Location $Root
try {
    & $IsccPath $IssScript
}
finally {
    Pop-Location
}

if (Test-Path $InstallerPath) {
    Write-Host ""
    Write-Host "Release installer ready:" -ForegroundColor Green
    Write-Host "  $InstallerPath" -ForegroundColor Green
} else {
    throw "Installer compile completed but output not found at: $InstallerPath"
}
