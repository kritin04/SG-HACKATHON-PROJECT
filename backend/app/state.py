"""Application state: the analysed project, its catalog and the built dependency map (cached in memory)."""
from __future__ import annotations

import threading

from . import config
from .engine.catalog import Catalog, load_catalog
from .mapbuild.build import build_map
from .mapbuild.mapcheck import check_map
from .mapbuild.model import ProjectMap
from .mapbuild.project import Project, load_project
from .store import Store


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.store = Store()
        self.project: Project | None = None
        self.catalog: Catalog | None = None
        self.map: ProjectMap | None = None
        self.report: dict = {}
        self.accuracy: dict = {}
        self.jobs: dict[str, dict] = {}
        self._semantic = None

    def semantic_index(self):
        if self._semantic is None:
            from .engine.embeddings import SemanticIndex
            self._semantic = SemanticIndex(self.ensure_map())
        return self._semantic

    def ensure_map(self) -> ProjectMap:
        with self.lock:
            if self.map is None:
                self.rebuild_locked()
            return self.map

    def rebuild_locked(self) -> None:
        self.project = load_project()
        self.catalog = load_catalog(config.DEMO_DATA / "catalog")
        self.map, self.report = build_map(self.project, self.catalog)
        from .mapbuild.enrich import apply_enrichment       # AI layer on top (cached results only)
        apply_enrichment(self.map, self.report, self.store)
        self.accuracy = check_map(self.map)
        self._semantic = None

    def rebuild(self) -> None:
        with self.lock:
            self.rebuild_locked()


STATE = AppState()
