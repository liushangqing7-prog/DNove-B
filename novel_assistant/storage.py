from __future__ import annotations

import json
import os
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_STRUCTURE = [
    "chapters",
    "cards",
    "prompts",
    "snapshots",
    "drafts",
    "branches/main",
]


@dataclass
class WorkspacePaths:
    root: Path
    chapters: Path
    cards: Path
    prompts: Path
    snapshots: Path
    drafts: Path
    branches: Path


class WorkspaceStorage:
    def __init__(self) -> None:
        self.paths: Optional[WorkspacePaths] = None
        self.fallback_db: Optional[sqlite3.Connection] = None

    def open_workspace(self, root: str) -> WorkspacePaths:
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        try:
            for folder in DEFAULT_STRUCTURE:
                (root_path / folder).mkdir(parents=True, exist_ok=True)
            novel_file = root_path / "novel.json"
            if not novel_file.exists():
                novel_file.write_text(
                    json.dumps(
                        {
                            "title": root_path.name,
                            "created_at": datetime.utcnow().isoformat(),
                            "chapters": [],
                            "branch": "main",
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            self.paths = WorkspacePaths(
                root=root_path,
                chapters=root_path / "chapters",
                cards=root_path / "cards",
                prompts=root_path / "prompts",
                snapshots=root_path / "snapshots",
                drafts=root_path / "drafts",
                branches=root_path / "branches",
            )
            return self.paths
        except PermissionError:
            self._init_sqlite_fallback(root_path)
            return WorkspacePaths(
                root=root_path,
                chapters=root_path,
                cards=root_path,
                prompts=root_path,
                snapshots=root_path,
                drafts=root_path,
                branches=root_path,
            )

    def _init_sqlite_fallback(self, root_path: Path) -> None:
        db_path = root_path / "workspace_fallback.sqlite3"
        self.fallback_db = sqlite3.connect(db_path)
        cur = self.fallback_db.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, content TEXT)"
        )
        self.fallback_db.commit()

    def load_json(self, path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def save_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def read_text(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def list_files(self, folder: Path, suffix: str) -> List[Path]:
        if not folder.exists():
            return []
        return sorted(folder.glob(f"*{suffix}"))

    def create_snapshot(self, label: str, payload: Dict[str, Any]) -> Path:
        if not self.paths:
            raise RuntimeError("Workspace not opened")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        snapshot_file = self.paths.snapshots / f"{timestamp}_{label}.json"
        self.save_json(snapshot_file, payload)
        return snapshot_file

    def list_snapshots(self) -> List[Path]:
        if not self.paths:
            return []
        return sorted(self.paths.snapshots.glob("*.json"), reverse=True)

    def export_zip(self, dest_zip: str) -> None:
        if not self.paths:
            raise RuntimeError("Workspace not opened")
        with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in self.paths.root.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(self.paths.root))

    def import_zip(self, zip_path: str, target_root: str) -> WorkspacePaths:
        target = Path(target_root)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target)
        return self.open_workspace(str(target))

    def export_fallback_sqlite_dump(self, dest_file: str) -> None:
        if not self.fallback_db:
            return
        with open(dest_file, "w", encoding="utf-8") as f:
            for line in self.fallback_db.iterdump():
                f.write(f"{line}\n")

    def switch_branch(self, branch_name: str) -> Path:
        if not self.paths:
            raise RuntimeError("Workspace not opened")
        branch_dir = self.paths.branches / branch_name
        branch_dir.mkdir(parents=True, exist_ok=True)
        return branch_dir
