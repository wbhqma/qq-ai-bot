param([switch]$Check)
$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not $Check -and -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env'))) {
    & (Join-Path $PSScriptRoot 'configure.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    if ($Check) {
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'bot.py') --check
    }
    else {
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'bot.py')
    }
    $taskExit = $LASTEXITCODE
}
finally { Pop-Location }
exit $taskExit
