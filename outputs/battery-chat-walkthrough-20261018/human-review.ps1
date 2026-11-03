# Run this yourself only while all agents/models under this account are stopped.
# Ctrl+C closes the GUI; this script never answers a human checkpoint.
$ErrorActionPreference = 'Stop'
$caseRoot = $PSScriptRoot
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $caseRoot '..\..')).Path
Push-Location -LiteralPath $repoRoot
try {
    Write-Host 'ADR-0022: no agent or model may run under your account while the GUI is open.'
    & python (Join-Path $caseRoot 'runtime_driver.py') advance
    if ($LASTEXITCODE -ne 0) { throw 'Runtime stage failed; review the error before opening the GUI.' }
    Write-Host 'Review the session in the GUI. Close the GUI with Ctrl+C before asking Codex to continue.'
    & python -m frameshift.bootstrap gui --store (Join-Path $caseRoot 'runtime-store') --operator user_local --role decision_owner --port 8765
} finally {
    Pop-Location
}
