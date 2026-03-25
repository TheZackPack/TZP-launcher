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

# App info
APP_NAME: str = "TZP Launcher"
APP_VERSION: str = "1.1.5"

# Minecraft / NeoForge versions
MC_VERSION: str = "1.21.1"
NEOFORGE_VERSION: str = "21.1.220"

# Default JVM memory allocation
DEFAULT_RAM: str = "4G"
RAM_OPTIONS: list[str] = ["2G", "4G", "6G", "8G"]

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
# QSS Stylesheet — Premium dark purple / void / ender theme
# ---------------------------------------------------------------------------

STYLESHEET = """
/* ---- Global ---- */
QMainWindow {
    background-color: #09090F;
}

QWidget {
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
}

/* ---- Sidebar ---- */
#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #1A0E30, stop:0.4 #140A26, stop:1 #0B0518);
    border-right: 1px solid #2A1F45;
}

#sidebarAccentTop {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6A24A8, stop:0.5 #7B2FBE, stop:1 #6A24A8);
    min-height: 2px;
    max-height: 2px;
}

#sidebarAccentFade {
    background-color: #4A1D72;
    min-height: 1px;
    max-height: 1px;
}

#brandLabel {
    color: #F5F0FF;
    font-size: 48px;
    font-weight: bold;
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
}

#brandGlow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7B2FBE, stop:0.5 #9B4FDE, stop:1 #7B2FBE);
    min-height: 3px;
    max-height: 3px;
    border-radius: 1px;
}

#subtitleLabel {
    color: #7A7490;
    font-size: 11px;
    font-weight: bold;
    font-family: "Courier New", "SF Mono", monospace;
    letter-spacing: 2px;
}

#versionPill {
    background-color: #3A1858;
    border: 1px solid #4A1D72;
    border-radius: 10px;
    padding: 2px 10px;
}

#versionPillLabel {
    color: #9B4FDE;
    font-size: 11px;
    font-weight: bold;
}

/* ---- Sidebar separator ---- */
#sidebarSep {
    background-color: #1E1535;
    min-height: 1px;
    max-height: 1px;
}

/* ---- Nav buttons ---- */
#navButton {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    color: #7A7490;
    font-size: 13px;
    text-align: left;
    padding: 8px 12px;
    min-height: 36px;
}

#navButton:hover {
    background-color: #14101F;
    color: #E8E4F0;
}

#navButtonActive {
    background-color: #14101F;
    border: none;
    border-radius: 8px;
    color: #E8E4F0;
    font-size: 13px;
    text-align: left;
    padding: 8px 12px;
    min-height: 36px;
}

/* ---- Server status card ---- */
#statusCard {
    background-color: #14101F;
    border: 1px solid #2A1F45;
    border-radius: 10px;
}

#statusHeader {
    color: #504A65;
    font-size: 9px;
    font-weight: bold;
}

#statusDot {
    font-size: 12px;
    color: #504A65;
}

#statusLabel {
    color: #7A7490;
    font-size: 12px;
}

#playerLabel {
    color: #504A65;
    font-size: 11px;
}

#creditLabel {
    color: #504A65;
    font-size: 10px;
}

/* ---- Main content ---- */
#mainContainer {
    background-color: #09090F;
}

/* ---- Home page ---- */
#titleLabel {
    color: #F5F0FF;
    font-size: 36px;
    font-weight: bold;
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
}

#poweredLabel {
    color: #9B4FDE;
    font-size: 13px;
    font-family: "Courier New", "SF Mono", monospace;
}

/* ---- Info pills ---- */
#pillAccent {
    background-color: #3A1858;
    border: 1px solid #2A1F45;
    border-radius: 14px;
    padding: 5px 14px;
}

#pillAccentLabel {
    color: #9B4FDE;
    font-size: 12px;
    font-weight: bold;
}

#pillDefault {
    background-color: #14101F;
    border: 1px solid #2A1F45;
    border-radius: 14px;
    padding: 5px 14px;
}

#pillDefaultLabel {
    color: #7A7490;
    font-size: 12px;
    font-weight: bold;
}

#pillNether {
    background-color: #3A1858;
    border: 1px solid #2A1F45;
    border-radius: 14px;
    padding: 5px 14px;
}

#pillNetherLabel {
    color: #C44B1A;
    font-size: 12px;
    font-weight: bold;
}

/* ---- Play button ---- */
#playButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6A24A8, stop:1 #7B2FBE);
    color: white;
    border: 2px solid #6A24A8;
    border-radius: 14px;
    font-size: 22px;
    font-weight: bold;
    padding: 18px 60px;
    min-width: 280px;
    min-height: 60px;
}

#playButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7B2FBE, stop:1 #9B4FDE);
    border: 2px solid #7B2FBE;
}

#playButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #5A1A98, stop:1 #6A24A8);
}

#playButton:disabled {
    background-color: #3A1858;
    color: #504A65;
    border: 2px solid #2A1F45;
}

/* ---- News card ---- */
#newsCard {
    background-color: #14101F;
    border: 1px solid #2A1F45;
    border-radius: 12px;
    padding: 8px 14px;
}

#newsDot {
    color: #C44B1A;
    font-size: 8px;
}

#newsTag {
    color: #504A65;
    font-size: 9px;
    font-weight: bold;
}

#newsText {
    color: #7A7490;
    font-size: 12px;
}

/* ---- Progress area ---- */
#progressLabel {
    color: #7A7490;
    font-size: 12px;
}

#progressPctLabel {
    color: #9B4FDE;
    font-size: 12px;
    font-weight: bold;
}

QProgressBar {
    background-color: #1A1428;
    border: 1px solid #2A1F45;
    border-radius: 4px;
    max-height: 8px;
    min-height: 8px;
    text-align: center;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6A24A8, stop:1 #9B4FDE);
    border-radius: 3px;
}

/* ---- About page ---- */
#aboutTitle {
    color: #F5F0FF;
    font-size: 28px;
    font-weight: bold;
}

#aboutKey {
    color: #7A7490;
    font-size: 13px;
    font-weight: bold;
}

#aboutValue {
    color: #E8E4F0;
    font-size: 13px;
}

/* ---- Settings dialog ---- */
QDialog {
    background-color: #09090F;
}

#settingsTitle {
    color: #F5F0FF;
    font-size: 24px;
    font-weight: bold;
}

#sectionLabel {
    color: #504A65;
    font-size: 10px;
    font-weight: bold;
}

/* ---- Cards (settings) ---- */
#settingsCard {
    background-color: #14101F;
    border: 1px solid #2A1F45;
    border-radius: 10px;
}

#cardLabel {
    color: #E8E4F0;
    font-size: 13px;
}

#cardHint {
    color: #504A65;
    font-size: 11px;
}

/* ---- Inputs ---- */
QLineEdit {
    background-color: #0E0B18;
    border: 1px solid #2A1F45;
    border-radius: 6px;
    padding: 8px 12px;
    color: #E8E4F0;
    font-size: 13px;
    selection-background-color: #7B2FBE;
}

QLineEdit:focus {
    border-color: #7B2FBE;
}

QComboBox {
    background-color: #0E0B18;
    border: 1px solid #2A1F45;
    border-radius: 6px;
    padding: 8px 12px;
    color: #E8E4F0;
    font-size: 13px;
    min-width: 90px;
}

QComboBox:focus {
    border-color: #7B2FBE;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #7A7490;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #14101F;
    border: 1px solid #2A1F45;
    color: #E8E4F0;
    selection-background-color: #3A1858;
    selection-color: #E8E4F0;
    outline: none;
}

/* ---- Buttons (generic) ---- */
QPushButton {
    background-color: #14101F;
    border: 1px solid #2A1F45;
    border-radius: 6px;
    color: #E8E4F0;
    padding: 8px 16px;
    font-size: 13px;
}

QPushButton:hover {
    border-color: #7B2FBE;
    background-color: #1C1530;
}

QPushButton:pressed {
    background-color: #14101F;
}

/* ---- Specific buttons ---- */
#browseButton {
    background-color: #4A1D72;
    border: none;
    border-radius: 8px;
    color: #E8E4F0;
    padding: 8px 16px;
    font-size: 12px;
    min-width: 70px;
}

#browseButton:hover {
    background-color: #7B2FBE;
}

#cancelButton {
    background-color: transparent;
    border: 1px solid #3D2D60;
    border-radius: 10px;
    color: #7A7490;
    padding: 8px 24px;
    font-size: 13px;
    min-width: 90px;
}

#cancelButton:hover {
    border-color: #7B2FBE;
    background-color: #14101F;
    color: #E8E4F0;
}

#saveButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6A24A8, stop:1 #7B2FBE);
    border: 1px solid #6A24A8;
    border-radius: 10px;
    color: white;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: bold;
    min-width: 90px;
}

#saveButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7B2FBE, stop:1 #9B4FDE);
}

/* ---- Scrollbar ---- */
QScrollBar:vertical {
    background: #09090F;
    width: 8px;
    border: none;
}

QScrollBar::handle:vertical {
    background: #7B2FBE;
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
    background-color: #2A1F45;
    min-width: 1px;
    max-width: 1px;
}

/* ---- Separator in settings ---- */
#settingsSep {
    background-color: #1E1535;
    min-height: 1px;
    max-height: 1px;
}
"""
