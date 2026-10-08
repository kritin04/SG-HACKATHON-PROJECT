# Regenerate the synthetic demo repository and reset demo state (keeps the AI cache).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
$wt = Join-Path $root "workspace\doc_heal_worktree"
if (Test-Path $wt) { Remove-Item -Recurse -Force $wt }
& $py (Join-Path $root "demo_data\generate_repo.py")
& $py -c "import sys; sys.path.insert(0, r'$root\backend'); from app.store import Store; Store().reset(); print('Demo state reset (baselines, doc decisions, audit).')"
Write-Host "Done. Restart the backend (or POST /api/admin/refresh) to re-index."
