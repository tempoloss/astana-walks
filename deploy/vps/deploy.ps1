# One command from the PC: archive HEAD -> upload -> uv sync -> restart `anyq`, over ONE ssh connection
# (the VPS firewall rate-limits new connections on port 22).
#   $env:ANYQ_SSH = "root@<host>"; .\deploy\vps\deploy.ps1       # HEAD
#   .\deploy\vps\deploy.ps1 -Ref <commit|tag>                     # any committed state, e.g. a rollback
# The host is never stored in the repo. Only committed files are deployed (git archive).
param([string]$Ref = "HEAD")
$ErrorActionPreference = "Stop"

if (-not $env:ANYQ_SSH) { throw "Set ANYQ_SSH to the ssh target with root rights, e.g. root@host" }
$ssh = "C:/Windows/System32/OpenSSH/ssh.exe"
$repo = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
$sha = (git -C $repo rev-parse --short=12 $Ref).Trim()

if ($Ref -eq "HEAD" -and (git -C $repo status --porcelain -- app data collect pyproject.toml uv.lock deploy/vps)) {
    Write-Warning "Uncommitted changes in app/, data/, collect/ or deploy/vps/ are NOT deployed: only HEAD ($sha) is."
}

$remote = "set -e; r=/opt/anyq/$sha; mkdir -p `$r; tar -x -C `$r; bash `$r/deploy/vps/remote.sh $sha"
# cmd carries the binary tar stream: a PowerShell pipeline would re-encode it.
$cmd = "git -C `"$repo`" archive --format=tar $Ref app data collect pyproject.toml uv.lock deploy/vps | `"$ssh`" -o BatchMode=yes $env:ANYQ_SSH `"$remote`""
cmd /c $cmd
if ($LASTEXITCODE -ne 0) { throw "deploy failed (exit $LASTEXITCODE)" }
Write-Host "Deployed $sha"
