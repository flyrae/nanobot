<#
.SYNOPSIS
    Build websocket_im_service into a standalone Windows exe
.DESCRIPTION
    Uses PyInstaller to package the WebSocket IM server + static files
    into a single portable exe. No Python needed on target machine.
.EXAMPLE
    .\build.ps1                # folder mode (recommended)
    .\build.ps1 -OneFile       # single exe
    .\build.ps1 -Clean         # clean + rebuild
#>

param(
    [string]$CondaEnv = "python312",
    [switch]$OneFile,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$AppName    = "nanobot-im"
$AppVersion = "1.0.0"
$EntryPoint = "server.py"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  WebSocket IM Service Builder"          -ForegroundColor Cyan
Write-Host "  Version: $AppVersion"                  -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------------
# Clean
# ------------------------------------------------------------------
if ($Clean) {
    Write-Host "[0/3] Cleaning..." -ForegroundColor Yellow
    foreach ($d in @("build", "dist", "$AppName.spec")) {
        if (Test-Path $d) { Remove-Item -Recurse -Force $d }
    }
    Write-Host "  -> Cleaned." -ForegroundColor Green
}

# ------------------------------------------------------------------
# Resolve conda environment
# ------------------------------------------------------------------
Write-Host "[1/3] Resolving conda environment: $CondaEnv ..." -ForegroundColor Yellow

$CondaEnvPath = $null
$envLines = conda env list 2>&1 | Where-Object { $_ -match "^\s*$CondaEnv\s+" }
if ($envLines) {
    $CondaEnvPath = ($envLines -split '\s+' | Where-Object { $_ -and $_ -ne '*' -and $_ -ne $CondaEnv }) | Select-Object -First 1
}

if (-not $CondaEnvPath -or -not (Test-Path "$CondaEnvPath\python.exe")) {
    $condaBase = (conda info --base 2>$null).Trim()
    $tryPaths = @(
        "$condaBase\envs\$CondaEnv",
        "D:\mambaforge\envs\$CondaEnv"
    )
    foreach ($p in $tryPaths) {
        if (Test-Path "$p\python.exe") { $CondaEnvPath = $p; break }
    }
}

if (-not $CondaEnvPath -or -not (Test-Path "$CondaEnvPath\python.exe")) {
    throw "Cannot find conda environment '$CondaEnv'"
}

$CondaPython       = "$CondaEnvPath\python.exe"
$CondaPip          = "$CondaEnvPath\Scripts\pip.exe"
$CondaPyInstaller  = "$CondaEnvPath\Scripts\pyinstaller.exe"

$PythonVer = & $CondaPython --version 2>&1
Write-Host "  -> Python: $PythonVer ($CondaPython)" -ForegroundColor DarkGray

# Ensure PyInstaller
if (-not (Test-Path $CondaPyInstaller)) {
    Write-Host "  -> Installing PyInstaller..." -ForegroundColor Yellow
    & $CondaPip install pyinstaller --quiet
}

# Prepend conda env to PATH for subprocess compatibility
$env:PATH = "$CondaEnvPath;$CondaEnvPath\Scripts;$CondaEnvPath\Library\bin;" + $env:PATH

Write-Host "  -> Ready." -ForegroundColor Green

# ------------------------------------------------------------------
# Build
# ------------------------------------------------------------------
Write-Host "[2/3] Building with PyInstaller..." -ForegroundColor Yellow

if ($OneFile) {
    Write-Host "  -> Mode: Single File" -ForegroundColor DarkGray
    & $CondaPyInstaller `
        --noconfirm --clean `
        --name $AppName `
        --console `
        --onefile `
        --add-data "static;static" `
        --hidden-import aiohttp `
        --hidden-import aiohttp.web `
        --exclude-module tkinter `
        --exclude-module matplotlib `
        --exclude-module numpy `
        --exclude-module pandas `
        --exclude-module scipy `
        --exclude-module PIL `
        --exclude-module PyQt5 `
        $EntryPoint
} else {
    Write-Host "  -> Mode: Folder" -ForegroundColor DarkGray
    & $CondaPyInstaller `
        --noconfirm --clean `
        --name $AppName `
        --console `
        --add-data "static;static" `
        --hidden-import aiohttp `
        --hidden-import aiohttp.web `
        --exclude-module tkinter `
        --exclude-module matplotlib `
        --exclude-module numpy `
        --exclude-module pandas `
        --exclude-module scipy `
        --exclude-module PIL `
        --exclude-module PyQt5 `
        $EntryPoint
}

if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
Write-Host "  -> Build succeeded." -ForegroundColor Green

# ------------------------------------------------------------------
# Verify
# ------------------------------------------------------------------
Write-Host "[3/3] Verifying..." -ForegroundColor Yellow

$ExePath = if ($OneFile) { "dist\$AppName.exe" } else { "dist\$AppName\$AppName.exe" }

if (Test-Path $ExePath) {
    $size = [math]::Round((Get-Item $ExePath).Length / 1MB, 1)
    Write-Host "  -> OK: $ExePath ($size MB)" -ForegroundColor Green
} else {
    throw "Build failed: $ExePath not found"
}

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Build Complete!"                       -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Output: $ExePath" -ForegroundColor White
Write-Host ""
Write-Host "  Run:    .\$ExePath" -ForegroundColor DarkGray
Write-Host "  Open:   http://localhost:19090" -ForegroundColor DarkGray
Write-Host ""
