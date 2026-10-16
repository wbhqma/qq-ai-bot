$ErrorActionPreference = 'Stop'
$taskOldTemp = $env:TEMP
$taskOldTmp = $env:TMP
$taskOldCache = $env:PIP_CACHE_DIR
$taskExit = 1

function Find-ProjectPython {
    # Each candidate is checked by running it: WindowsApps aliases may exist
    # without pointing to an installed interpreter.
    $taskCandidates = @()
    if ($env:QQBOT_PYTHON) {
        $taskCandidates += @{ Executable = $env:QQBOT_PYTHON; Arguments = @() }
    }
    else {
        foreach ($taskName in @('py', 'python', 'python3')) {
            $taskCommand = Get-Command $taskName -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($taskCommand) {
                $taskArguments = @()
                if ($taskName -eq 'py') { $taskArguments = @('-3') }
                $taskCandidates += @{ Executable = $taskCommand.Source; Arguments = $taskArguments }
            }
        }
        if ($env:LOCALAPPDATA) {
            foreach ($taskPattern in @('Python\pythoncore-*\python.exe', 'Programs\Python\Python*\python.exe')) {
                foreach ($taskFile in @(Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA $taskPattern) -File -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)) {
                    $taskCandidates += @{ Executable = $taskFile.FullName; Arguments = @() }
                }
            }
        }
    }
    foreach ($taskCandidate in $taskCandidates) {
        try {
            $taskExecutable = $taskCandidate.Executable
            $taskArguments = $taskCandidate.Arguments
            $taskProbe = & $taskExecutable @taskArguments -c 'import sys, venv; assert sys.version_info >= (3, 11); print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $taskProbe) {
                return (@($taskProbe)[-1]).Trim()
            }
        }
        catch { continue }
    }
    throw 'Python 3.11+ was not found. Install Python or set QQBOT_PYTHON to its executable path.'
}

Push-Location -LiteralPath $PSScriptRoot
try {
    $taskTemp = Join-Path $PSScriptRoot '.cache\tmp'
    $null = New-Item -ItemType Directory -Path $taskTemp -Force
    $env:TEMP = $taskTemp
    $env:TMP = $taskTemp
    $env:PIP_CACHE_DIR = Join-Path $PSScriptRoot '.cache\pip'
    $taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $taskPython)) {
        $taskBasePython = Find-ProjectPython
        & $taskBasePython -m venv (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create the virtual environment.' }
    }
    $taskRequirements = Join-Path $PSScriptRoot 'requirements.lock'
    if (-not (Test-Path -LiteralPath $taskRequirements)) {
        $taskRequirements = Join-Path $PSScriptRoot 'requirements.txt'
    }
    & $taskPython -m pip install --disable-pip-version-check -r $taskRequirements
    $taskExit = $LASTEXITCODE
}
finally {
    $env:TEMP = $taskOldTemp
    $env:TMP = $taskOldTmp
    $env:PIP_CACHE_DIR = $taskOldCache
    Pop-Location
}
exit $taskExit
