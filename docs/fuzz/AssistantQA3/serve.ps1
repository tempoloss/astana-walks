# Starts one server of the matrix run.  Usage (from anywhere):
#   powershell -NoProfile -File serve.ps1 live 8751      # model on (needs GEMINI_KEY_FILE or .gemini-key)
#   powershell -NoProfile -File serve.ps1 offline 8755   # WALKS_OFFLINE=1, no key, no network
param([string]$Mode = "live", [int]$Port = 8751)
$app = Resolve-Path (Join-Path $PSScriptRoot "../../../app")
Set-Location $app
$tmp = Join-Path $env:TEMP "qa3-profiles-$Port"
New-Item -ItemType Directory -Force $tmp | Out-Null
$env:WALKS_PROFILE_DIR = $tmp
$env:WALKS_REQUEST_LOG = "off"
if ($Mode -eq "offline") {
    $env:WALKS_OFFLINE = "1"
    Remove-Item Env:GEMINI_KEY_FILE -ErrorAction SilentlyContinue
    Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
} else {
    if (-not $env:GEMINI_KEY_FILE) { $env:GEMINI_KEY_FILE = "C:/Users/Anek/Hackathons/.gemini-key" }
}
uv run python -m web --port $Port
