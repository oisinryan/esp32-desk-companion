$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    python tools/install.py @args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Pop-Location }
