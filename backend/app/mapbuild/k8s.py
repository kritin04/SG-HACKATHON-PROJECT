"""Read Kubernetes manifests: which services/databases exist, and which settings each one receives."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..engine.evidence import STORE
from .project import Project

HOST_PORT = re.compile(r"^([a-z0-9][a-z0-9-]*):\d+$")
DB_URI = re.compile(r"^(?:jdbc:)?postgres(?:ql)?://(?:[^@/]+@)?([a-z0-9-]+)(?::\d+)?/")


@dataclass
class Workload:
    name: str
    kind: str                     # Deployment | StatefulSet
    path: str                     # manifest file (relative)
    line: int
    env: dict[str, tuple[str, str]] = field(default_factory=dict)  # VAR -> (value, evidence id)
    secret_mounts: list[str] = field(default_factory=list)
    is_database: bool = False


@dataclass
class Manifests:
    workloads: dict[str, Workload] = field(default_factory=dict)
    configmaps: dict[str, dict[str, str]] = field(default_factory=dict)
    k8s_services: set[str] = field(default_factory=set)

    def target_of(self, value: str) -> tuple[str, str] | None:
        """'balancereader:8080' -> ('service', 'balancereader'); a postgres URI -> ('database', host)."""
        m = DB_URI.match(value)
        if m and m.group(1) in self.workloads:
            return "database", m.group(1)
        m = HOST_PORT.match(value)
        if m and m.group(1) in self.workloads:
            return "service", m.group(1)
        return None


def _line_of(text: str, needle: str, start: int = 0) -> int:
    idx = text.find(needle, start)
    return text.count("\n", 0, idx) + 1 if idx >= 0 else 1


def read_manifests(project: Project) -> Manifests:
    out = Manifests()
    docs = []
    short = project.sha[:7]
    for f in sorted(project.manifests_dir.glob("*.yaml")):
        text = project.read(f)
        for doc in yaml.safe_load_all(text):
            if isinstance(doc, dict):
                docs.append((f, text, doc))
    for f, text, doc in docs:
        kind, name = doc.get("kind"), (doc.get("metadata") or {}).get("name")
        if kind == "ConfigMap":
            out.configmaps[name] = {k: str(v) for k, v in (doc.get("data") or {}).items()}
        elif kind == "Service":
            out.k8s_services.add(name)
    for f, text, doc in docs:
        kind, name = doc.get("kind"), (doc.get("metadata") or {}).get("name")
        if kind not in ("Deployment", "StatefulSet") or project.excluded(project.root / "src" / name):
            continue
        rel = project.rel(f)
        wl = Workload(name, kind, rel, _line_of(text, f"name: {name}"))
        for c in doc["spec"]["template"]["spec"].get("containers", []):
            for ef in c.get("envFrom", []) or []:
                cm = (ef.get("configMapRef") or {}).get("name")
                for k, v in out.configmaps.get(cm, {}).items():
                    ev = STORE.add("config", f"ConfigMap {cm}: {k}", f"{k}: {v}", rel, _line_of(text, f"name: {cm}"),
                                   ref=short)
                    wl.env[k] = (v, ev)
            for e in c.get("env", []) or []:
                val = e.get("value")
                if val is None and e.get("valueFrom", {}).get("configMapKeyRef"):
                    ref = e["valueFrom"]["configMapKeyRef"]
                    val = out.configmaps.get(ref["name"], {}).get(ref["key"], "")
                ev = STORE.add("config", f"{name} env {e['name']}", f"{e['name']}: {val}", rel,
                               _line_of(text, f"name: {e['name']}"), ref=short)
                wl.env[e["name"]] = (str(val or ""), ev)
            for vm in c.get("volumeMounts", []) or []:
                if ".ssh" in vm.get("mountPath", ""):
                    wl.secret_mounts.append(vm["mountPath"])
        images = " ".join(c.get("image", "") for c in doc["spec"]["template"]["spec"].get("containers", []))
        wl.is_database = kind == "StatefulSet" or any(k in images for k in ("postgres", "mysql", "mongo", "-db"))
        out.workloads[name] = wl
    return out
