$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $taskPython -X utf8 (Join-Path $PSScriptRoot 'configure.py')
    $taskExit = $LASTEXITCODE
}
finally { Pop-Location }
exit $taskExit
