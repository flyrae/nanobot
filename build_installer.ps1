<#
.SYNOPSIS
    Build nanobot Windows installer (one-click script)
.DESCRIPTION
    1. Activate conda environment (reuse existing dependencies)
    2. Ensure PyInstaller is installed
    3. PyInstaller -> dist/nanobot/
    4. Inno Setup  -> installer_output/nanobot-x.x.x-win64-setup.exe
.NOTES
    Prerequisites:
      - Conda with python312 environment (or specify -CondaEnv <name>)
      - Inno Setup 6 (optional, for .exe installer)
    
    The script will use your existing conda environment directly,
    no need to re-download dependencies.
#>

param(
    [string]$CondaEnv = "python312",
    [switch]$SkipInnoSetup,
    [switch]$OneFile,
    [switch]$Clean,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$AppVersion = "0.1.3"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  nanobot Windows Installer Builder"     -ForegroundColor Cyan
Write-Host "  Version: $AppVersion"                  -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------------
# Step 0: Clean previous build (optional)
# ------------------------------------------------------------------
if ($Clean) {
    Write-Host "[0/4] Cleaning previous build artifacts..." -ForegroundColor Yellow
    if (Test-Path "build")            { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist")             { Remove-Item -Recurse -Force "dist" }
    if (Test-Path "installer_output") { Remove-Item -Recurse -Force "installer_output" }
    Write-Host "  -> Cleaned." -ForegroundColor Green
}

# ------------------------------------------------------------------
# Step 1: Activate conda environment & check dependencies
# ------------------------------------------------------------------
Write-Host "[1/4] Setting up conda environment: $CondaEnv ..." -ForegroundColor Yellow

# Resolve conda environment path and Python executable
$CondaEnvPath = $null

# Method 1: Parse conda env list to find the environment path
$envLines = conda env list 2>&1 | Where-Object { $_ -match "^\s*$CondaEnv\s+" }
if ($envLines) {
    $CondaEnvPath = ($envLines -split '\s+' | Where-Object { $_ -and $_ -ne '*' -and $_ -ne $CondaEnv }) | Select-Object -First 1
}

# Method 2: Try common conda paths
if (-not $CondaEnvPath -or -not (Test-Path $CondaEnvPath)) {
    $condaBase = (conda info --base 2>$null).Trim()
    $tryPaths = @(
        "$condaBase\envs\$CondaEnv",
        "$env:USERPROFILE\.conda\envs\$CondaEnv",
        "$env:USERPROFILE\miniconda3\envs\$CondaEnv",
        "$env:USERPROFILE\anaconda3\envs\$CondaEnv",
        "D:\mambaforge\envs\$CondaEnv"
    )
    foreach ($p in $tryPaths) {
        if (Test-Path "$p\python.exe") { $CondaEnvPath = $p; break }
    }
}

if (-not $CondaEnvPath -or -not (Test-Path "$CondaEnvPath\python.exe")) {
    throw "Cannot find Python in conda environment '$CondaEnv'. Please check conda env name."
}

$CondaPython = "$CondaEnvPath\python.exe"
$CondaPip = "$CondaEnvPath\Scripts\pip.exe"
$CondaPyInstaller = "$CondaEnvPath\Scripts\pyinstaller.exe"

# Show Python info
Write-Host "  -> Env path: $CondaEnvPath" -ForegroundColor DarkGray

$PythonVer = & $CondaPython --version 2>&1
Write-Host "  -> Python:   $PythonVer ($CondaPython)" -ForegroundColor DarkGray

# Only install deps if explicitly requested (by default reuse existing env)
if ($InstallDeps) {
    Write-Host "  -> Installing dependencies into conda env (--InstallDeps)..." -ForegroundColor Yellow
    & $CondaPip install -r requirements.txt --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to install requirements" }
}

# Ensure PyInstaller is available
if (-not (Test-Path $CondaPyInstaller)) {
    & $CondaPython -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  -> PyInstaller not found, installing into conda env..." -ForegroundColor Yellow
        & $CondaPip install pyinstaller --quiet
        if ($LASTEXITCODE -ne 0) { throw "Failed to install PyInstaller" }
    }
    # Re-check
    $CondaPyInstaller = "$CondaEnvPath\Scripts\pyinstaller.exe"
}

Write-Host "  -> PyInstaller: $CondaPyInstaller" -ForegroundColor DarkGray
Write-Host "  -> Environment ready." -ForegroundColor Green

# ------------------------------------------------------------------
# Step 2: Build with PyInstaller
# ------------------------------------------------------------------
Write-Host "[2/4] Building with PyInstaller..." -ForegroundColor Yellow

# Set Python path so PyInstaller subprocess uses correct interpreter
$env:PATH = "$CondaEnvPath;$CondaEnvPath\Scripts;$CondaEnvPath\Library\bin;" + $env:PATH

if ($OneFile) {
    Write-Host "  -> Mode: Single File (.exe)" -ForegroundColor DarkGray

    # Resolve Playwright browser paths (chromium + ffmpeg only)
    $PwBrowsersPath = Join-Path $env:LOCALAPPDATA "ms-playwright"
    $PwDataArgs = @()
    if (Test-Path $PwBrowsersPath) {
        Get-ChildItem $PwBrowsersPath -Directory | Where-Object { $_.Name -match '^(chromium-|ffmpeg-)' } | ForEach-Object {
            $PwDataArgs += '--add-data'
            $PwDataArgs += "$($_.FullName);ms-playwright/$($_.Name)"
        }
        Write-Host "  -> Bundling Playwright browsers: $($PwDataArgs.Count / 2) dirs" -ForegroundColor DarkGray
    } else {
        Write-Host "  -> Warning: ms-playwright not found, browser-use may require 'playwright install chromium'" -ForegroundColor DarkYellow
    }

    & $CondaPyInstaller `
        --noconfirm `
        --clean `
        --name nanobot `
        --console `
        --onefile `
        --add-data "nanobot/skills;nanobot/skills" `
        --add-data "workspace;workspace" `
        --runtime-hook "runtime_hook_playwright.py" `
        --collect-all litellm `
        --collect-all openai `
        --collect-all tiktoken `
        --collect-all tiktoken_ext `
        --collect-all httpx `
        --collect-all httpcore `
        --collect-all browser_use `
        --collect-all playwright `
        --hidden-import typer `
        --hidden-import click `
        --hidden-import pydantic `
        --hidden-import pydantic_settings `
        --hidden-import loguru `
        --hidden-import rich `
        --hidden-import croniter `
        --hidden-import mss `
        --hidden-import pyautogui `
        --hidden-import aiohttp `
        --hidden-import websockets `
        --hidden-import websocket `
        --hidden-import yaml `
        --hidden-import dotenv `
        --hidden-import PIL `
        --hidden-import lxml `
        --hidden-import readability `
        --hidden-import bs4 `
        --hidden-import socksio `
        --hidden-import dingtalk_stream `
        --hidden-import telegram `
        --hidden-import lark_oapi `
        --hidden-import slack_sdk `
        --hidden-import botpy `
        --hidden-import email `
        --hidden-import importlib.resources `
        --hidden-import importlib.metadata `
        --exclude-module tkinter `
        --exclude-module matplotlib `
        @PwDataArgs `
        nanobot/__main__.py
} else {
    Write-Host "  -> Mode: Folder (recommended)" -ForegroundColor DarkGray
    & $CondaPyInstaller --noconfirm --clean nanobot.spec

}

if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
Write-Host "  -> PyInstaller build succeeded." -ForegroundColor Green

# ------------------------------------------------------------------
# Step 3: Verify the build
# ------------------------------------------------------------------
Write-Host "[3/4] Verifying build..." -ForegroundColor Yellow

$ExePath = if ($OneFile) { "dist\nanobot.exe" } else { "dist\nanobot\nanobot.exe" }

if (-not (Test-Path $ExePath)) {
    throw "Build verification failed: $ExePath not found"
}

& $ExePath --version 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  -> Build verified: $ExePath" -ForegroundColor Green
} else {
    Write-Host "  -> Warning: exe built but 'version' command returned non-zero" -ForegroundColor DarkYellow
}

# ------------------------------------------------------------------
# Step 4: Build Inno Setup installer (optional)
# ------------------------------------------------------------------
if (-not $SkipInnoSetup -and -not $OneFile) {
    Write-Host "[4/4] Building Inno Setup installer..." -ForegroundColor Yellow

    # Try common Inno Setup paths
    $IsccPaths = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )

    $IsccExe = $null
    foreach ($p in $IsccPaths) {
        if (Test-Path $p) { $IsccExe = $p; break }
    }

    if ($null -eq $IsccExe) {
        # Try to find in PATH
        $IsccExe = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    }

    if ($null -ne $IsccExe) {
        & $IsccExe installer.iss
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed" }
        Write-Host "  -> Installer created in installer_output/" -ForegroundColor Green
    } else {
        Write-Host "  -> Inno Setup not found. Skipping installer creation." -ForegroundColor DarkYellow
        Write-Host "     Download from: https://jrsoftware.org/isdl.php" -ForegroundColor DarkGray
        Write-Host "     You can build it later:  ISCC.exe installer.iss" -ForegroundColor DarkGray
    }
} elseif ($OneFile) {
    Write-Host "[4/4] Single-file mode: Installer step skipped." -ForegroundColor DarkGray
    Write-Host "  -> Portable exe: dist\nanobot.exe" -ForegroundColor Green
} else {
    Write-Host "[4/4] Skipped (--SkipInnoSetup)." -ForegroundColor DarkGray
}

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

if ($OneFile) {
    Write-Host "  Portable EXE:  dist\nanobot.exe" -ForegroundColor White
} else {
    Write-Host "  Folder build:  dist\nanobot\" -ForegroundColor White
    if (Test-Path "installer_output") {
        $setupFile = Get-ChildItem "installer_output\*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($setupFile) {
            Write-Host "  Installer:     $($setupFile.FullName)" -ForegroundColor White
        }
    }
}
Write-Host ""
