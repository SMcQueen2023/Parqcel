param(
    [switch]$Clean,
    [ValidateSet("base", "ml")]
    [string]$Profile = "base",
    [string]$PythonExecutable,
    [string]$InnoCompilerPath,
    [switch]$Installer
)

$ErrorActionPreference = "Stop"

function Get-PythonCommand {
    param(
        [string]$RequestedPython,
        [string]$RepoRoot
    )

    if ($RequestedPython) {
        if (-not (Test-Path $RequestedPython)) {
            throw "Python executable '$RequestedPython' was not found."
        }

        return @($RequestedPython)
    }

    if ($env:VIRTUAL_ENV) {
        $venvPython = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
        if (Test-Path $venvPython) {
            return @($venvPython)
        }
    }

    $localVenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $localVenvPython) {
        return @($localVenvPython)
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }

    throw "Python 3 was not found on PATH. Install Python before building the desktop bundle."
}

function Get-InnoCompiler {
    param(
        [string]$RequestedCompiler
    )

    if ($RequestedCompiler) {
        if (-not (Test-Path $RequestedCompiler)) {
            throw "Inno Setup compiler '$RequestedCompiler' was not found."
        }

        return $RequestedCompiler
    }

    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    return $null
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonCommand = @(Get-PythonCommand -RequestedPython $PythonExecutable -RepoRoot $repoRoot)
$pythonExe = $pythonCommand[0]
$pythonArgs = @()
if ($pythonCommand.Count -gt 1) {
    $pythonArgs = $pythonCommand[1..($pythonCommand.Count - 1)]
}

if ($Clean) {
    $pathsToRemove = @(
        (Join-Path $repoRoot "build\Parqcel"),
        (Join-Path $repoRoot "dist\Parqcel")
    )

    foreach ($path in $pathsToRemove) {
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
        }
    }
}

Push-Location $repoRoot
try {
    $previousProfile = $env:PARQCEL_BUILD_PROFILE
    $env:PARQCEL_BUILD_PROFILE = $Profile

    Write-Host "Building Parqcel desktop bundle with profile '$Profile'"
    Write-Host "Using Python executable '$pythonExe'"
    & $pythonExe @pythonArgs -m PyInstaller --noconfirm (Join-Path $repoRoot "Parqcel.spec")

    $desktopOutput = Join-Path $repoRoot "dist\Parqcel\Parqcel.exe"
    if (-not (Test-Path $desktopOutput)) {
        throw "PyInstaller completed without producing $desktopOutput"
    }

    Write-Host "Standalone bundle created at $desktopOutput"

    if ($Installer) {
        $iscc = Get-InnoCompiler -RequestedCompiler $InnoCompilerPath
        if (-not $iscc) {
            throw "Inno Setup 6 was not found. Install it or run the script again without -Installer."
        }

        & $iscc (Join-Path $repoRoot "installer\parqcel.iss")
        Write-Host "Installer created at $(Join-Path $repoRoot "installer\dist\Parqcel-Installer.exe")"
    }
}
finally {
    if ($null -eq $previousProfile) {
        Remove-Item Env:PARQCEL_BUILD_PROFILE -ErrorAction SilentlyContinue
    }
    else {
        $env:PARQCEL_BUILD_PROFILE = $previousProfile
    }

    Pop-Location
}
