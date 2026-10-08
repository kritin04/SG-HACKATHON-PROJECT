"""Read-only access to a local git repository at any ref (no checkout needed)."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileDiff:
    path: str
    old_path: str | None
    status: str  # A, M, D, R
    patch: str = ""
    added_lines: set[int] = field(default_factory=set)    # line numbers in head
    removed_lines: set[int] = field(default_factory=set)  # line numbers in base


class GitRepo:
    def __init__(self, path: Path):
        self.path = Path(path)

    def run(self, *args: str) -> str:
        out = subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", check=True)
        return out.stdout

    @lru_cache(maxsize=256)
    def rev(self, ref: str) -> str:
        return self.run("rev-parse", f"{ref}^{{commit}}").strip()

    @lru_cache(maxsize=64)
    def ls_files(self, ref: str) -> tuple[str, ...]:
        return tuple(l for l in self.run("ls-tree", "-r", "--name-only", self.rev(ref)).splitlines() if l)

    @lru_cache(maxsize=2048)
    def show(self, ref: str, path: str) -> str | None:
        try:
            return self.run("show", f"{self.rev(ref)}:{path}")
        except subprocess.CalledProcessError:
            return None

    def commit_info(self, ref: str) -> dict:
        sha, author, date, subject = self.run("log", "-1", "--format=%H%x1f%an%x1f%aI%x1f%s", ref).strip().split("\x1f")
        return {"sha": sha, "short": sha[:7], "author": author, "date": date, "subject": subject}

    def log(self, base: str, head: str) -> list[dict]:
        out = self.run("log", "--format=%H%x1f%an%x1f%aI%x1f%s", f"{base}..{head}")
        rows = []
        for line in out.splitlines():
            sha, author, date, subject = line.split("\x1f")
            rows.append({"sha": sha, "short": sha[:7], "author": author, "date": date, "subject": subject})
        return rows

    def diff(self, base: str, head: str) -> list[FileDiff]:
        b, h = self.rev(base), self.rev(head)
        diffs: dict[str, FileDiff] = {}
        for line in self.run("diff", "--name-status", "-M", b, h).splitlines():
            parts = line.split("\t")
            status = parts[0][0]
            if status == "R":
                diffs[parts[2]] = FileDiff(parts[2], parts[1], "R")
            else:
                diffs[parts[1]] = FileDiff(parts[1], None, status)
        for path, fd in diffs.items():
            paths = [fd.old_path, path] if fd.old_path else [path]
            fd.patch = self.run("diff", "-M", "-U3", b, h, "--", *paths)
            _parse_lines(fd)
        return list(diffs.values())

    def is_ancestor(self, a: str, b: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=self.path).returncode == 0


def _parse_lines(fd: FileDiff) -> None:
    old_no = new_no = 0
    in_hunk = False
    for line in fd.patch.splitlines():
        m = HUNK_RE.match(line)
        if m:
            old_no, new_no, in_hunk = int(m.group(1)), int(m.group(3)), True
            continue
        if not in_hunk or line.startswith("\\"):
            continue
        if line.startswith("+"):
            fd.added_lines.add(new_no)
            new_no += 1
        elif line.startswith("-"):
            fd.removed_lines.add(old_no)
            old_no += 1
        else:
            old_no += 1
            new_no += 1


def hunks_for_lines(patch: str, start: int, end: int, side: str = "new") -> str:
    """Return the hunks of a patch that overlap [start, end] on the given side."""
    out, current, keep = [], [], False
    for line in patch.splitlines():
        m = HUNK_RE.match(line)
        if m:
            if current and keep:
                out.extend(current)
            s = int(m.group(3) if side == "new" else m.group(1))
            n = int((m.group(4) if side == "new" else m.group(2)) or 1)
            keep = s <= end and s + max(n, 1) - 1 >= start
            current = [line]
        elif current:
            current.append(line)
    if current and keep:
        out.extend(current)
    return "\n".join(out)
