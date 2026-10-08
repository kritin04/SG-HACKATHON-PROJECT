# Clone Bank of Anthos at the pinned commit (safe to run again).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $root "workspace\repos\bank-of-anthos"
$sha = "db35fea9fd090150e2398106aadb475576f80d94"
if (-not (Test-Path (Join-Path $dest ".git"))) {
    New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
    git clone --quiet https://github.com/GoogleCloudPlatform/bank-of-anthos.git $dest
}
git -C $dest fetch --quiet --depth 1 origin $sha
git -C $dest checkout --quiet $sha
Write-Host "Bank of Anthos ready at $dest ($(git -C $dest rev-parse --short HEAD))"
