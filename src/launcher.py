"""Minecraft setup logic — NeoForge install, Java detection, and profile management."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import minecraft_launcher_lib

from config import MC_VERSION, NEOFORGE_VERSION

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
        # Scan common Windows Java install locations
        program_dirs = [
            Path(r"C:\Program Files"),
            Path(r"C:\Program Files (x86)"),
            Path.home() / "AppData" / "Local" / "Programs",
        ]
        java_patterns = [
            "Eclipse Adoptium/jdk-21*/bin/java.exe",
            "Eclipse Adoptium/jre-21*/bin/java.exe",
            "Java/jdk-21*/bin/java.exe",
            "Java/jre-21*/bin/java.exe",
            "Microsoft/jdk-21*/bin/java.exe",
            "Zulu/zulu-21*/bin/java.exe",
            "Amazon Corretto/jdk21*/bin/java.exe",
            "BellSoft/LibericaJDK-21*/bin/java.exe",
            "ojdkbuild/java-21*/bin/java.exe",
        ]
        import glob as _glob
        for d in program_dirs:
            for pattern in java_patterns:
                for match in _glob.glob(str(d / pattern)):
                    candidates.append(match)

        # Also check the CurseForge bundled Java
        cf_java = Path.home() / "curseforge" / "minecraft" / "Install" / "runtime" / "java-runtime-delta" / "windows-x64" / "java-runtime-delta" / "bin" / "java.exe"
        if cf_java.exists():
            candidates.append(str(cf_java))
        # Minecraft launcher bundled Java
        mc_java = Path.home() / "AppData" / "Local" / "Packages" / "Microsoft.4297127D64EC6_8wekyb3d8bbwe" / "LocalCache" / "Local" / "runtime" / "java-runtime-delta" / "windows-x64" / "java-runtime-delta" / "bin" / "java.exe"
        if mc_java.exists():
            candidates.append(str(mc_java))
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
# Minecraft launcher profile management
# ---------------------------------------------------------------------------

PROFILE_ID = "tzp-modpack"
PROFILE_NAME = "TZP — The Zack Pack"


def _mc_launcher_dir() -> Path:
    """Return the official Minecraft launcher directory."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "minecraft"
    if system == "Windows":
        return Path.home() / "AppData" / "Roaming" / ".minecraft"
    return Path.home() / ".minecraft"


def _profiles_path() -> Path:
    return _mc_launcher_dir() / "launcher_profiles.json"


def ensure_profile(
    game_dir: Path,
    java_path: str | None = None,
    ram: str = "4G",
) -> bool:
    """Create or update a TZP profile in the official Minecraft launcher.

    Returns True if the profile was created/updated, False if launcher_profiles.json
    was not found (Minecraft launcher not installed).
    """
    profiles_file = _profiles_path()
    if not profiles_file.exists():
        return False

    with open(profiles_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    profiles = data.setdefault("profiles", {})
    version_id = _neoforge_version_string()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    java = find_java(java_path)

    # Build JVM args with the user's RAM setting
    jvm_args = (
        f"-Xmx{ram} -Xms{ram} "
        "-XX:+UseG1GC -XX:+UnlockExperimentalVMOptions "
        "-XX:G1NewSizePercent=20 -XX:G1ReservePercent=20 "
        "-XX:MaxGCPauseMillis=50 -XX:G1HeapRegionSize=32M"
    )

    profile = profiles.get(PROFILE_ID, {})
    profile.update({
        "name": PROFILE_NAME,
        "type": "custom",
        "gameDir": str(game_dir),
        "lastVersionId": version_id,
        "lastUsed": now,
        "javaArgs": jvm_args,
        "icon": "data:image/png;base64,",
    })
    if java:
        profile["javaDir"] = java

    profiles[PROFILE_ID] = profile
    data["profiles"] = profiles

    # Set as the selected profile so the MC launcher auto-selects it
    data["selectedProfile"] = PROFILE_ID

    with open(profiles_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True


def open_minecraft_launcher() -> bool:
    """Open the official Minecraft launcher. Returns True if launched."""
    system = platform.system()

    if system == "Darwin":
        candidates = [
            "/Applications/Minecraft.app",
            str(Path.home() / "Applications" / "Minecraft.app"),
        ]
        # Also check common CurseForge location
        cf_app = Path.home() / "Documents" / "curseforge" / "minecraft" / "Install" / "Minecraft.app"
        if cf_app.exists():
            candidates.insert(0, str(cf_app))

        for app in candidates:
            if Path(app).exists():
                subprocess.Popen(["open", app])
                return True

        # Try open by bundle ID
        try:
            subprocess.Popen(["open", "-b", "com.mojang.minecraftlauncher"])
            return True
        except (OSError, subprocess.SubprocessError):
            pass

    elif system == "Windows":
        # Windows Store / MSI launcher
        mc_exe = shutil.which("MinecraftLauncher.exe")
        if mc_exe:
            subprocess.Popen([mc_exe])
            return True
        candidates = [
            r"C:\Program Files (x86)\Minecraft Launcher\MinecraftLauncher.exe",
            str(Path.home() / "AppData" / "Local" / "Programs" / "Minecraft Launcher" / "MinecraftLauncher.exe"),
        ]
        for exe in candidates:
            if Path(exe).exists():
                subprocess.Popen([exe])
                return True

    else:  # Linux
        mc = shutil.which("minecraft-launcher")
        if mc:
            subprocess.Popen([mc])
            return True

    return False

