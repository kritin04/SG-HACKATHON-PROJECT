"""Learn from git history which services usually change together ("change coupling", as in CodeScene).

If two services were changed in the same commit many times, a change to one often needs a change to the other.
Used as a weak extra signal in impact analysis, always labelled "from git history".
"""
from __future__ import annotations

import subprocess
from collections import Counter
from itertools import combinations

from ..mapbuild.model import ProjectMap
from ..mapbuild.project import Project


def service_cochange(project: Project, pm: ProjectMap, max_commits: int = 600) -> dict:
    paths = {n.props["path"]: n.id for n in pm.nodes.values() if n.type in ("service", "database") and n.props.get("path")}
    try:
        out = subprocess.run(["git", "log", f"-{max_commits}", "--name-only", "--format=@@%H"], cwd=project.root,
                             capture_output=True, text=True, check=True, encoding="utf-8", errors="replace").stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"commits": 0, "pairs": {}, "changes": {}}
    commits, touched = 0, Counter()
    pairs: Counter = Counter()
    for block in out.split("@@")[1:]:
        files = [l for l in block.splitlines()[1:] if l.strip() and l.endswith((".py", ".java", ".sql"))
                 and "/test" not in l]
        svcs = {sid for f in files for p, sid in paths.items() if f.startswith(p + "/")}
        if not svcs or len(svcs) > 4:          # skip empty and repo-wide commits (version bumps, licence headers)
            continue
        commits += 1
        touched.update(svcs)
        for a, b in combinations(sorted(svcs), 2):
            pairs[(a, b)] += 1
    return {"commits": commits, "changes": dict(touched),
            "pairs": {f"{a}|{b}": n for (a, b), n in pairs.items() if n >= 2}}


def coupled_with(cc: dict, sid: str, min_ratio: float = 0.25) -> list[tuple[str, int, float]]:
    """Services that changed together with `sid` in at least min_ratio of sid's commits."""
    total = cc.get("changes", {}).get(sid, 0)
    out = []
    for key, n in cc.get("pairs", {}).items():
        a, b = key.split("|")
        other = b if a == sid else a if b == sid else None
        if other and total and n / total >= min_ratio:
            out.append((other, n, round(n / total, 2)))
    return sorted(out, key=lambda x: -x[2])
