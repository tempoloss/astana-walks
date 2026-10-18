<#
.SYNOPSIS
  One-command launch of the Anyk web UI on http://localhost:8600 (run from anywhere; the script moves to app/).

.PARAMETER Mode
  demo          the local recording / rehearsal configuration (not the public stand): WALKS_ENV=demo, pinned time / weather /
                walking legs (WALKS_DEMO_PIN), replayed LLM answers (WALKS_CACHE_PIN), simulated demand on the City page
                (WALKS_DEMAND_SIM), Google-only LLM chains (the current defaults).
  demo-offline  the same plus WALKS_OFFLINE=1: no network call of any kind.
  jury          no environment at all: exactly what a fresh clone runs.

  The same three modes exist as poe tasks (`uv run poe demo | demo-offline | jury`).
#>
param(
    [ValidateSet("demo", "demo-offline", "jury")]
    [string]$Mode = "demo",
    [int]$Port = 8600
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if ($Mode -ne "jury") {
    $env:WALKS_ENV = "demo"
    $env:WALKS_DEMAND_SIM = "1"
    $env:WALKS_DEMO_PIN = "1"
    $env:WALKS_CACHE_PIN = "1"
    $env:LLM_CHAIN = "gemini:gemini-3.5-flash,gemini:gemini-flash-latest,gemini:gemini-2.5-flash,gemini:gemma-4-26b-a4b-it"
    $env:LLM_INTENT_CHAIN = "gemini:gemini-2.5-flash-lite,gemini:gemini-3.5-flash-lite,gemini:gemma-4-26b-a4b-it"
}
if ($Mode -eq "demo-offline") {
    $env:WALKS_OFFLINE = "1"
}

uv run python -m web --port $Port
exit $LASTEXITCODE
