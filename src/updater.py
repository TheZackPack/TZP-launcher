"""TZP Launcher update engine — fetches manifest, diffs local files, downloads updates."""

from __future__ import annotations

import hashlib
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

from config import MANIFEST_URL


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ManifestFile = dict[str, Any]   # {"path": str, "url": str, "sha256": str, "size": int}
Manifest = dict[str, Any]       # {"version": str, "files": list[ManifestFile]}
ProgressCallback = Callable[[float, str], None]  # (fraction 0-1, status_text)


@dataclass
class SyncResult:
    """Detailed result of a sync operation."""
    downloaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

async def fetch_manifest(url: str = MANIFEST_URL) -> Manifest:
    """Download the remote manifest JSON and return it as a dict."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Local file scanning
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest for a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 16)  # 64 KiB
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def scan_local_files(game_dir: Path) -> dict[str, str]:
    """Scan mods/, config/, and kubejs/ directories under *game_dir*.

    Returns a mapping of ``relative_path -> sha256_hex``.
    """
    result: dict[str, str] = {}
    for subdir in ("mods", "config", "kubejs"):
        root = game_dir / subdir
        if not root.is_dir():
            continue
        for file in root.rglob("*"):
            if file.is_file():
                rel = file.relative_to(game_dir).as_posix()
                result[rel] = _sha256_file(file)
    return result


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------

def compute_diff(
    manifest: Manifest,
    local_files: dict[str, str],
) -> tuple[list[ManifestFile], list[str], list[str]]:
    """Compare manifest to local files.

    Returns:
        (to_download, to_delete, unchanged)
        - to_download: list of manifest file entries that need downloading
        - to_delete: list of relative paths to remove (not in manifest)
        - unchanged: list of relative paths that are already up to date
    """
    remote_paths: dict[str, ManifestFile] = {}
    # Collect all entries from files, configs, and kubejs sections
    for section in ("files", "configs", "kubejs"):
        for entry in manifest.get(section, []):
            remote_paths[entry["path"]] = entry

    to_download: list[ManifestFile] = []
    unchanged: list[str] = []

    for path, entry in remote_paths.items():
        local_hash = local_files.get(path)
        # Support both "hash" (legacy) and "sha256" (current) manifest keys
        remote_hash = entry.get("sha256", entry.get("hash", ""))
        if remote_hash.startswith("sha256:"):
            remote_hash = remote_hash[7:]
        if local_hash == remote_hash:
            unchanged.append(path)
        else:
            to_download.append(entry)

    # Files present locally but not in manifest should be removed
    to_delete = [p for p in local_files if p not in remote_paths]

    return to_download, to_delete, unchanged


# ---------------------------------------------------------------------------
# Downloading
# ---------------------------------------------------------------------------

async def download_file(
    url: str,
    dest_path: Path,
    progress_callback: ProgressCallback | None = None,
) -> None:
    """Download a single file from *url* to *dest_path* with optional progress."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(dest_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1 << 16):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total > 0:
                        progress_callback(downloaded / total, dest_path.name)


# ---------------------------------------------------------------------------
# Full update orchestration
# ---------------------------------------------------------------------------

async def apply_update(
    manifest: Manifest,
    game_dir: Path,
    progress_callback: ProgressCallback | None = None,
) -> SyncResult:
    """Run the full update cycle: scan, diff, download, delete.

    Returns a SyncResult with lists of affected file paths.
    """
    result = SyncResult()

    if progress_callback:
        progress_callback(0.0, "Scanning local files...")

    local_files = await asyncio.to_thread(scan_local_files, game_dir)
    to_download, to_delete, unchanged = compute_diff(manifest, local_files)

    result.unchanged = list(unchanged)

    total_steps = len(to_download) + len(to_delete)
    completed = 0

    # Emit summary before starting work
    if progress_callback:
        progress_callback(
            0.0,
            f"Sync: {len(to_download)} to download, {len(to_delete)} to remove, {len(unchanged)} unchanged",
        )

    # Download new / updated files
    for i, entry in enumerate(to_download, 1):
        dest = game_dir / entry["path"]
        rel_path = entry["path"]
        if progress_callback:
            frac = completed / max(total_steps, 1)
            progress_callback(frac, f"Downloading {rel_path} ({i}/{len(to_download)})")

        try:
            await download_file(entry["url"], dest)
            result.downloaded.append(rel_path)
        except Exception as exc:
            result.errors.append(f"{rel_path}: {exc}")
        completed += 1

    # Remove files not in manifest
    for rel_path in to_delete:
        full_path = game_dir / rel_path
        if progress_callback:
            frac = completed / max(total_steps, 1)
            progress_callback(frac, f"Removing {rel_path}")
        try:
            full_path.unlink(missing_ok=True)
            result.deleted.append(rel_path)
        except OSError as exc:
            result.errors.append(f"{rel_path}: {exc}")
        completed += 1

    if progress_callback:
        progress_callback(1.0, "Up to date!")

    return result
