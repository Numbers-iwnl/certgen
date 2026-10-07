#Requires -Version 5.1
<#
.SYNOPSIS
  Reproducible build for Gerador de Certificados.

.DESCRIPTION
  Creates/reuses a .venv, installs the pinned toolchain from
  requirements-dev.txt, runs the characterization test suite, and (unless
  -SkipBuild is passed) builds the onefile exe via PyInstaller.

  Run from the repo root:
    powershell -ExecutionPolicy Bypass -File build.ps1

.PARAMETER SkipTests
  Build even if the test suite hasn't been run / would be skipped.
  Not recommended -- the whole point of this script is that a build you
  hand to a colleague passed the parity suite first.

.PARAMETER SkipBuild
  Only set up the venv and run tests; don't invoke PyInstaller.
#>
param(
    [switch]$SkipTests,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "Installing pinned dependencies..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r requirements-dev.txt --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

if (-not $SkipTests) {
    Write-Host "Running characterization test suite..." -ForegroundColor Cyan
    & $venvPython -m pytest tests/ -q
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed -- refusing to build. Fix the regression or pass -SkipTests to override."
    }
}

if ($SkipBuild) {
    Write-Host "Done (build skipped)." -ForegroundColor Green
    exit 0
}

Write-Host "Cleaning previous build artifacts..." -ForegroundColor Cyan
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist

Write-Host "Building GeradorCertificados.exe with PyInstaller..." -ForegroundColor Cyan
& $venvPython -m PyInstaller GeradorCertificados.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$exePath = Join-Path $root "dist\GeradorCertificados.exe"
if (-not (Test-Path $exePath)) { throw "Build reported success but exe not found at $exePath" }

$sizeMb = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
Write-Host "`nBuild complete: $exePath ($sizeMb MB)" -ForegroundColor Green
