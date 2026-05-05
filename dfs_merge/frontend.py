from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from dfs_merge.utils import ensure_directory


FRONTEND_ROOT = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND_DIST = FRONTEND_ROOT / "dist"
FRONTEND_MANIFEST = FRONTEND_DIST / ".vite" / "manifest.json"


@dataclass(frozen=True, slots=True)
class FrontendAssets:
    entry_js: str
    css_files: tuple[str, ...]


def load_frontend_assets() -> FrontendAssets:
    if not FRONTEND_MANIFEST.exists():
        raise FileNotFoundError(
            "React frontend build assets were not found. Run `npm install` and `npm run build` in "
            f"{FRONTEND_ROOT} before generating reports."
        )

    manifest = json.loads(FRONTEND_MANIFEST.read_text(encoding="utf-8"))
    entry = manifest.get("index.html")
    if not entry or "file" not in entry:
        raise ValueError(f"Unable to find the Vite index.html entry in {FRONTEND_MANIFEST}.")

    return FrontendAssets(
        entry_js=entry["file"],
        css_files=tuple(entry.get("css", [])),
    )


def copy_frontend_assets(destination_root: Path) -> None:
    source_assets_dir = FRONTEND_DIST / "assets"
    if not source_assets_dir.exists():
        raise FileNotFoundError(
            "React frontend asset directory is missing. Run `npm run build` in "
            f"{FRONTEND_ROOT} before generating reports."
        )

    destination_assets_dir = destination_root / "assets"
    if destination_assets_dir.exists():
        shutil.rmtree(destination_assets_dir)
    ensure_directory(destination_root)
    shutil.copytree(source_assets_dir, destination_assets_dir)
