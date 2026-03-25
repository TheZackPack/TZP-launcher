"""Minecraft launch logic — NeoForge install, Java detection, and game launch."""

from __future__ import annotations

import platform
import shutil
import subprocess
import os
import re
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
    java_path: str | None = None,
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

    java = find_java(java_path)
    if java is None:
        raise FileNotFoundError(
            "Java 21 could not be found. Install OpenJDK 21 or set it in Settings."
        )

    neoforge = minecraft_launcher_lib.mod_loader.get_mod_loader("neoforge")
    neoforge.install(
        MC_VERSION,
        str(game_dir),
        loader_version=NEOFORGE_VERSION,
        callback=cb_dict,
        java=java,
    )

    if callback:
        callback("NeoForge installation complete.")

    return version_id


# ---------------------------------------------------------------------------
# Java detection
# ---------------------------------------------------------------------------

def _java_major_version(java_path: str) -> int | None:
    """Return the detected Java major version for *java_path*."""
    try:
        result = subprocess.run(
            [java_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    text = f"{result.stdout}\n{result.stderr}".strip()
    if not text:
        return None

    first_line = text.splitlines()[0]
    match = re.search(r'(?:(?:openjdk|java|jdk)\s+version\s+")?(\d+)', first_line, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _is_usable_java(java_path: str) -> bool:
    """Return True when *java_path* is an executable Java 21+ binary."""
    path = Path(java_path)
    if not path.is_file():
        return False
    major = _java_major_version(str(path))
    return major is not None and major >= 21


def _brew_openjdk_candidates() -> list[str]:
    """Return likely Homebrew Java 21 paths."""
    candidates: list[str] = []
    brew = shutil.which("brew")
    if brew:
        try:
            prefix = subprocess.run(
                [brew, "--prefix", "openjdk@21"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
            if prefix:
                candidates.append(str(Path(prefix) / "bin" / "java"))
                candidates.append(
                    str(
                        Path(prefix)
                        / "libexec"
                        / "openjdk.jdk"
                        / "Contents"
                        / "Home"
                        / "bin"
                        / "java"
                    )
                )
        except (OSError, subprocess.SubprocessError):
            pass

    candidates += [
        "/opt/homebrew/opt/openjdk@21/bin/java",
        "/usr/local/opt/openjdk@21/bin/java",
        str(Path.home() / ".homebrew" / "opt" / "openjdk@21" / "bin" / "java"),
    ]
    return candidates


def find_java(manual_path: str | None = None) -> str | None:
    """Locate a usable Java 21 executable.

    Checks (in order):
    1. *manual_path* if provided
    2. Common platform-specific locations
    3. ``java`` on PATH
    """
    if manual_path and _is_usable_java(manual_path):
        return manual_path

    candidates: list[str] = []
    system = platform.system()
    java_home = os.getenv("JAVA_HOME")

    if java_home:
        candidates.append(str(Path(java_home) / "bin" / "java"))

    if system == "Darwin":
        candidates += _brew_openjdk_candidates()
        try:
            java_home_21 = subprocess.run(
                ["/usr/libexec/java_home", "-v", "21"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
            if java_home_21:
                candidates.append(str(Path(java_home_21) / "bin" / "java"))
        except (OSError, subprocess.SubprocessError):
            pass
        candidates.append(str(Path.home() / ".sdkman/candidates/java/current/bin/java"))
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
        if _is_usable_java(path):
            return path

    # Fall back to PATH
    java_on_path = shutil.which("java")
    if java_on_path and _is_usable_java(java_on_path):
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
    java = find_java(java_path)
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
