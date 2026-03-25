"""Minecraft launch logic — NeoForge install, Java detection, and game launch."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path
from typing import Callable

import minecraft_launcher_lib

from config import MC_VERSION, NEOFORGE_VERSION, DEFAULT_RAM

StatusCallback = Callable[[str], None]


# ---------------------------------------------------------------------------
# NeoForge installation
# ---------------------------------------------------------------------------

def _neoforge_version_string() -> str:
    """Return the NeoForge version ID as minecraft-launcher-lib generates it."""
    return f"neoforge-{NEOFORGE_VERSION}"


def is_neoforge_installed(game_dir: Path) -> bool:
    """Check whether the required NeoForge version is already installed."""
    version_id = _neoforge_version_string()
    installed = minecraft_launcher_lib.utils.get_installed_versions(str(game_dir))
    return any(v["id"] == version_id for v in installed)


def install_neoforge(
    game_dir: Path,
    callback: StatusCallback | None = None,
) -> str:
    """Install NeoForge into *game_dir*. Returns the version ID string."""
    game_dir.mkdir(parents=True, exist_ok=True)
    version_id = _neoforge_version_string()

    if is_neoforge_installed(game_dir):
        if callback:
            callback("NeoForge already installed.")
        return version_id

    if callback:
        callback(f"Installing NeoForge {NEOFORGE_VERSION} ...")

    cb_dict: dict = {}
    if callback:
        cb_dict["setStatus"] = lambda text: callback(text)

    neoforge = minecraft_launcher_lib.mod_loader.get_mod_loader("neoforge")
    neoforge.install(
        MC_VERSION,
        str(game_dir),
        loader_version=NEOFORGE_VERSION,
        callback=cb_dict,
    )

    if callback:
        callback("NeoForge installation complete.")

    return version_id


# ---------------------------------------------------------------------------
# Java detection
# ---------------------------------------------------------------------------

def find_java(manual_path: str | None = None) -> str | None:
    """Locate a usable Java 21 executable.

    Checks (in order):
    1. *manual_path* if provided
    2. Common platform-specific locations
    3. ``java`` on PATH
    """
    if manual_path and Path(manual_path).is_file():
        return manual_path

    candidates: list[str] = []
    system = platform.system()

    if system == "Darwin":
        # Homebrew, SDKMAN, and system locations
        candidates += [
            "/usr/local/opt/openjdk@21/bin/java",
            "/opt/homebrew/opt/openjdk@21/bin/java",
            str(Path.home() / ".sdkman/candidates/java/current/bin/java"),
        ]
    elif system == "Windows":
        candidates += [
            r"C:\Program Files\Eclipse Adoptium\jdk-21\bin\java.exe",
            r"C:\Program Files\Java\jdk-21\bin\java.exe",
            r"C:\Program Files\Microsoft\jdk-21\bin\java.exe",
        ]
    else:
        candidates += [
            "/usr/lib/jvm/java-21/bin/java",
            "/usr/lib/jvm/java-21-openjdk-amd64/bin/java",
        ]

    for path in candidates:
        if Path(path).is_file():
            return path

    # Fall back to PATH
    java_on_path = shutil.which("java")
    if java_on_path:
        return java_on_path

    return None


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def build_launch_command(
    game_dir: Path,
    version_id: str,
    ram: str = DEFAULT_RAM,
    java_path: str | None = None,
) -> list[str]:
    """Build the full command-line list to launch Minecraft.

    Uses offline-mode auth with a placeholder username.
    Microsoft auth is planned for Phase 2.
    """
    java = java_path or find_java()
    if java is None:
        raise FileNotFoundError(
            "Java 21 could not be found. Please install it or set the path in Settings."
        )

    # Offline-mode login options (placeholder)
    options: dict = {
        "username": "TZP_Player",
        "uuid": "00000000-0000-0000-0000-000000000000",
        "token": "0",
        "jvmArguments": [
            f"-Xmx{ram}",
            f"-Xms{ram}",
            "-XX:+UseG1GC",
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:G1NewSizePercent=20",
            "-XX:G1ReservePercent=20",
            "-XX:MaxGCPauseMillis=50",
            "-XX:G1HeapRegionSize=32M",
        ],
        "executablePath": java,
    }

    command = minecraft_launcher_lib.command.get_minecraft_command(
        version_id,
        str(game_dir),
        options,
    )
    return command


def launch_minecraft(
    game_dir: Path,
    ram: str = DEFAULT_RAM,
    java_path: str | None = None,
) -> subprocess.Popen:
    """Launch Minecraft as a detached subprocess and return the Popen handle."""
    version_id = _neoforge_version_string()

    if not is_neoforge_installed(game_dir):
        raise RuntimeError(
            "NeoForge is not installed. Run the updater first."
        )

    command = build_launch_command(game_dir, version_id, ram, java_path)

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(game_dir),
    )
    return process
