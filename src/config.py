"""TZP Launcher configuration constants."""

import os
import platform
from pathlib import Path

# API endpoints (override with env vars for local testing)
# Examples:
#   TZP_MANIFEST_URL=http://127.0.0.1:8580/files/manifest.json
#   TZP_STATUS_URL=http://127.0.0.1:8580/status
MANIFEST_URL: str = os.getenv(
    "TZP_MANIFEST_URL",
    "https://tzp-production.up.railway.app/api/manifest",
)
STATUS_URL: str = os.getenv(
    "TZP_STATUS_URL",
    "https://tzp-production.up.railway.app/api/status",
)

# Launcher update + account endpoints
LAUNCHER_UPDATE_URL: str = os.getenv(
    "TZP_LAUNCHER_UPDATE_URL",
    "https://tzp-production.up.railway.app/api/launcher/release",
)
ACCOUNT_API_BASE: str = os.getenv(
    "TZP_ACCOUNT_API_BASE",
    "https://tzp-production.up.railway.app/api",
)
CLAIM_CODE_URL: str = os.getenv(
    "TZP_CLAIM_CODE_URL",
    f"{ACCOUNT_API_BASE}/claim",
)
CRASH_REPORT_URL: str = os.getenv(
    "TZP_CRASH_REPORT_URL",
    f"{ACCOUNT_API_BASE}/crash",
)
MODPACK_INFO_URL: str = os.getenv(
    "TZP_MODPACK_INFO_URL",
    "https://tzp-production.up.railway.app/api/modpack/info",
)

# Version picker — users can switch between stable and beta modpacks
# Each version has its own instance directory so switching doesn't wipe mods.
# instance_dir is appended to the base game directory.
VERSIONS: dict[str, dict] = {
    "v1.1.9 (Stable)": {
        "manifest": MANIFEST_URL,
        "server_ip": "15.204.117.31",
        "server_port": 25565,
        "instance_dir": "stable",
    },
    "v2.0.0-alpha (Beta)": {
        "manifest": os.getenv(
            "TZP_MANIFEST_URL_ALPHA",
            "https://raw.githubusercontent.com/TheZackPack/TZP-client/v2.0.0-alpha/manifest.json",
        ),
        "server_ip": os.getenv("TZP_ALPHA_SERVER_IP", "192.99.215.43"),
        "server_port": int(os.getenv("TZP_ALPHA_SERVER_PORT", "25594")),
        "instance_dir": "beta",
    },
}
DEFAULT_VERSION_KEY: str = "v1.1.9 (Stable)"

# App info
APP_NAME: str = "TZP Launcher"
APP_VERSION: str = "1.2.4"

# Minecraft / NeoForge versions
MC_VERSION: str = "1.21.1"
NEOFORGE_VERSION: str = "21.1.220"

# Default JVM memory allocation
DEFAULT_RAM: str = "6G"
RAM_MIN_GB: int = 2
RAM_MAX_GB: int = 16
RAM_OPTIONS: list[str] = ["2G", "4G", "6G", "8G", "10G", "12G", "14G", "16G"]

# Platform-specific storage directories
def get_app_support_dir() -> Path:
    """Return a stable per-user directory for launcher data."""
    system = platform.system()
    if system == "Windows":
        base = Path.home() / "AppData" / "Roaming"
        return base / "TZP Launcher"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "TZP Launcher"
    return Path.home() / ".tzp-launcher"


def get_default_game_dir() -> Path:
    """Return the default game directory based on the current platform."""
    system = platform.system()
    if system == "Windows":
        base = Path.home() / "AppData" / "Roaming"
        return base / ".tzp-minecraft"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "TZP Launcher" / "game"
    return Path.home() / ".tzp-minecraft"

APP_SUPPORT_DIR: Path = get_app_support_dir()
DEFAULT_GAME_DIR: Path = get_default_game_dir()

# ---------------------------------------------------------------------------
# QSS Stylesheet — Clean dark theme — Cursor/Warp.dev inspired
# ---------------------------------------------------------------------------

STYLESHEET = """
/* ---- Global ---- */
QMainWindow {
    background-color: #09090b;
}

QWidget {
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
}

/* ---- Sidebar ---- */
#sidebar {
    background-color: #111111;
    border-right: 1px solid #1e1e1e;
}

#sidebarAccentTop {
    background-color: #3b82f6;
    min-height: 2px;
    max-height: 2px;
}

#sidebarAccentFade {
    background-color: #1e1e1e;
    min-height: 1px;
    max-height: 1px;
}

#brandLabel {
    color: #e5e5e5;
    font-size: 48px;
    font-weight: bold;
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
}

#brandGlow {
    background-color: #3b82f6;
    min-height: 1px;
    max-height: 1px;
}

#subtitleLabel {
    color: #525252;
    font-size: 11px;
    font-weight: bold;
    font-family: "Courier New", "SF Mono", monospace;
    letter-spacing: 2px;
}

#versionPill {
    background-color: #1a1a1a;
    border: 1px solid #262626;
    border-radius: 10px;
    padding: 2px 10px;
}

#versionPillLabel {
    color: #3b82f6;
    font-size: 11px;
    font-weight: bold;
}

/* ---- Sidebar separator ---- */
#sidebarSep {
    background-color: #1e1e1e;
    min-height: 1px;
    max-height: 1px;
}

/* ---- Nav buttons ---- */
#navButton {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    color: #737373;
    font-size: 13px;
    text-align: left;
    padding: 8px 12px;
    min-height: 36px;
}

#navButton:hover {
    background-color: #1a1a1a;
    color: #e5e5e5;
}

#navButtonActive {
    background-color: #1a1a1a;
    border: none;
    border-radius: 8px;
    color: #e5e5e5;
    font-size: 13px;
    text-align: left;
    padding: 8px 12px;
    min-height: 36px;
}

/* ---- Server status card ---- */
#statusCard {
    background-color: #141414;
    border: 1px solid #262626;
    border-radius: 10px;
}

#statusHeader {
    color: #525252;
    font-size: 9px;
    font-weight: bold;
}

#statusDot {
    font-size: 12px;
    color: #525252;
}

#statusLabel {
    color: #737373;
    font-size: 12px;
}

#playerLabel {
    color: #525252;
    font-size: 11px;
}

#creditLabel {
    color: #525252;
    font-size: 10px;
}

/* ---- Main content ---- */
#mainContainer {
    background-color: #09090b;
}

/* ---- Home page ---- */
#titleLabel {
    color: #e5e5e5;
    font-size: 36px;
    font-weight: bold;
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
}

#poweredLabel {
    color: #3b82f6;
    font-size: 13px;
    font-family: "Courier New", "SF Mono", monospace;
}

/* ---- Info pills ---- */
#pillAccent {
    background-color: #1a1a1a;
    border: 1px solid #262626;
    border-radius: 14px;
    padding: 5px 14px;
}

#pillAccentLabel {
    color: #3b82f6;
    font-size: 12px;
    font-weight: bold;
}

#pillDefault {
    background-color: #141414;
    border: 1px solid #262626;
    border-radius: 14px;
    padding: 5px 14px;
}

#pillDefaultLabel {
    color: #737373;
    font-size: 12px;
    font-weight: bold;
}

#pillNether {
    background-color: #1a1a1a;
    border: 1px solid #262626;
    border-radius: 14px;
    padding: 5px 14px;
}

#pillNetherLabel {
    color: #737373;
    font-size: 12px;
    font-weight: bold;
}

/* ---- Play button ---- */
#playButton {
    background-color: #2563eb;
    color: white;
    border: 2px solid #2563eb;
    border-radius: 14px;
    font-size: 22px;
    font-weight: bold;
    padding: 18px 60px;
    min-width: 280px;
    min-height: 60px;
}

#playButton:hover {
    background-color: #3b82f6;
    border: 2px solid #3b82f6;
}

#playButton:pressed {
    background-color: #1d4ed8;
}

#playButton:disabled {
    background-color: #1a1a1a;
    color: #525252;
    border: 2px solid #262626;
}

/* ---- News card ---- */
#newsCard {
    background-color: #141414;
    border: 1px solid #262626;
    border-radius: 12px;
    padding: 8px 14px;
}

#newsDot {
    color: #3b82f6;
    font-size: 8px;
}

#newsTag {
    color: #525252;
    font-size: 9px;
    font-weight: bold;
}

#newsText {
    color: #737373;
    font-size: 12px;
}

/* ---- Progress area ---- */
#progressLabel {
    color: #737373;
    font-size: 12px;
}

#progressPctLabel {
    color: #3b82f6;
    font-size: 12px;
    font-weight: bold;
}

QProgressBar {
    background-color: #1a1a1a;
    border: 1px solid #262626;
    border-radius: 4px;
    max-height: 8px;
    min-height: 8px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 3px;
}

/* ---- About page ---- */
#aboutTitle {
    color: #e5e5e5;
    font-size: 28px;
    font-weight: bold;
}

#aboutKey {
    color: #737373;
    font-size: 13px;
    font-weight: bold;
}

#aboutValue {
    color: #e5e5e5;
    font-size: 13px;
}

/* ---- Settings dialog ---- */
QDialog {
    background-color: #09090b;
    color: #e5e5e5;
}

QDialog QWidget {
    background-color: #09090b;
    color: #e5e5e5;
}

QDialog QLabel {
    background-color: #09090b;
    color: #e5e5e5;
}

QDialog QFrame {
    background-color: #09090b;
}

#settingsTitle {
    color: #e5e5e5;
    font-size: 24px;
    font-weight: bold;
    background-color: #09090b;
}

#sectionLabel {
    color: #525252;
    font-size: 10px;
    font-weight: bold;
    background-color: #09090b;
}

/* ---- Cards (settings) ---- */
#settingsCard {
    background-color: #141414;
    border: 1px solid #262626;
    border-radius: 10px;
}

#settingsCard QWidget {
    background-color: #141414;
}

#settingsCard QLabel {
    background-color: #141414;
    color: #e5e5e5;
}

#cardLabel {
    color: #e5e5e5;
    font-size: 13px;
}

#cardHint {
    color: #525252;
    font-size: 11px;
}

/* ---- Inputs ---- */
QLineEdit {
    background-color: #0f0f0f;
    border: 1px solid #262626;
    border-radius: 6px;
    padding: 8px 12px;
    min-height: 20px;
    color: #e5e5e5;
    font-size: 13px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QLineEdit:focus {
    border-color: #3b82f6;
}

QLineEdit:read-only {
    color: #a3a3a3;
}

/* ---- Slider ---- */
QSlider::groove:horizontal {
    background: #262626;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #3b82f6;
    width: 18px;
    height: 18px;
    margin: -6px 0;
    border-radius: 9px;
}
QSlider::handle:horizontal:hover {
    background: #60a5fa;
}
QSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 3px;
}
QSlider::tick-mark:horizontal {
    background: #404040;
    width: 1px;
    height: 4px;
}

QDialog QLineEdit {
    color: #e5e5e5;
}

QComboBox {
    background-color: #0f0f0f;
    border: 1px solid #262626;
    border-radius: 6px;
    padding: 8px 12px;
    color: #e5e5e5;
    font-size: 13px;
    min-width: 90px;
}

QComboBox:focus {
    border-color: #3b82f6;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #737373;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #141414;
    border: 1px solid #262626;
    color: #e5e5e5;
    selection-background-color: #1a1a1a;
    selection-color: #e5e5e5;
    outline: none;
}

/* ---- Buttons (generic) ---- */
QPushButton {
    background-color: #141414;
    border: 1px solid #262626;
    border-radius: 6px;
    color: #e5e5e5;
    padding: 8px 16px;
    font-size: 13px;
}

QPushButton:hover {
    border-color: #3b82f6;
    background-color: #1a1a1a;
}

QPushButton:pressed {
    background-color: #141414;
}

/* ---- Specific buttons ---- */
#browseButton {
    background-color: #1e1e1e;
    border: none;
    border-radius: 8px;
    color: #e5e5e5;
    padding: 8px 16px;
    font-size: 12px;
    min-width: 70px;
}

#browseButton:hover {
    background-color: #3b82f6;
}

#cancelButton {
    background-color: transparent;
    border: 1px solid #262626;
    border-radius: 10px;
    color: #737373;
    padding: 8px 24px;
    font-size: 13px;
    min-width: 90px;
}

#cancelButton:hover {
    border-color: #3b82f6;
    background-color: #141414;
    color: #e5e5e5;
}

#saveButton {
    background-color: #2563eb;
    border: 1px solid #2563eb;
    border-radius: 10px;
    color: white;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: bold;
    min-width: 90px;
}

#saveButton:hover {
    background-color: #3b82f6;
}

#secondaryActionButton {
    background-color: #141414;
    border: 1px solid #262626;
    border-radius: 10px;
    color: #e5e5e5;
    padding: 8px 18px;
    font-size: 12px;
    font-weight: bold;
}

#secondaryActionButton:hover {
    border-color: #3b82f6;
    background-color: #1a1a1a;
}

#logOutput {
    background-color: #0f0f0f;
    border: 1px solid #262626;
    border-radius: 12px;
    padding: 14px;
    color: #d4d4d4;
    font-family: "SF Mono", "JetBrains Mono", "Menlo", monospace;
    font-size: 12px;
    selection-background-color: #2563eb;
}

/* ---- Scrollbar ---- */
QScrollBar:vertical {
    background: #09090b;
    width: 8px;
    border: none;
}

QScrollBar::handle:vertical {
    background: #404040;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

/* ---- Accent line between sidebar and main ---- */
#accentBorder {
    background-color: #1e1e1e;
    min-width: 1px;
    max-width: 1px;
}

/* ---- Separator in settings ---- */
#settingsSep {
    background-color: #1e1e1e;
    min-height: 1px;
    max-height: 1px;
}
"""
