"""TZP Launcher -- main GUI application using PySide6 (Qt6).

Premium dark-theme UI inspired by Cursor IDE, Claude Desktop, and Warp terminal,
with a Minecraft ender/void/dungeon aesthetic.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
from PySide6.QtCore import (
    Qt,
    QThread,
    QTimer,
    Signal,
    QPropertyAnimation,
    QEasingCurve,
    Property,
)
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_NAME,
    APP_SUPPORT_DIR,
    APP_VERSION,
    DEFAULT_GAME_DIR,
    DEFAULT_RAM,
    MANIFEST_URL,
    MC_VERSION,
    RAM_OPTIONS,
    STATUS_URL,
    STYLESHEET,
)
from launcher import find_java, install_neoforge, launch_minecraft
from updater import apply_update, fetch_manifest


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

SETTINGS_FILE = APP_SUPPORT_DIR / "launcher_settings.json"


def load_settings() -> dict[str, Any]:
    """Load saved settings from disk, returning defaults if missing."""
    defaults: dict[str, Any] = {
        "ram": DEFAULT_RAM,
        "game_dir": str(DEFAULT_GAME_DIR),
        "java_path": "",
    }
    try:
        if SETTINGS_FILE.is_file():
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
            defaults.update(saved)
    except (json.JSONDecodeError, OSError):
        pass
    return defaults


def save_settings(settings: dict[str, Any]) -> None:
    """Persist settings to disk."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------


class UpdateWorker(QThread):
    """Runs the update check/download in background, emitting progress signals."""

    progress = Signal(float, str)       # (fraction 0-1, status_text)
    finished = Signal(bool, str)        # (success, summary_message)
    neoforge_status = Signal(str)       # NeoForge install status messages

    def __init__(self, settings: dict[str, Any], parent=None):
        super().__init__(parent)
        self.settings = settings

    def run(self):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._async_update())
        except Exception as exc:
            self.finished.emit(False, f"Update failed: {exc}")
        finally:
            loop.close()

    async def _async_update(self):
        game_dir = Path(self.settings["game_dir"])
        game_dir.mkdir(parents=True, exist_ok=True)

        self.progress.emit(0.0, "Fetching manifest...")
        manifest = await fetch_manifest(MANIFEST_URL)

        self.progress.emit(0.05, "Checking for updates...")
        result = await apply_update(manifest, game_dir, self._progress_cb)

        summary = (
            f"Done: {result['downloaded']} downloaded, "
            f"{result['deleted']} removed, "
            f"{result['unchanged']} up to date."
        )

        # Install NeoForge
        self.neoforge_status.emit("Verifying NeoForge install...")
        try:
            install_neoforge(game_dir, callback=lambda msg: self.neoforge_status.emit(msg))
            self.finished.emit(True, summary)
        except Exception as exc:
            self.finished.emit(False, f"NeoForge install failed: {exc}")

    def _progress_cb(self, frac: float, text: str):
        self.progress.emit(frac, text)


class StatusWorker(QThread):
    """Polls server status periodically."""

    status_updated = Signal(bool, int, int)  # (online, players, max_players)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(STATUS_URL)
                resp.raise_for_status()
                data = resp.json()

            online: bool = data.get("online", False)
            players: int = data.get("players", {}).get("online", 0)
            max_players: int = data.get("players", {}).get("max", 0)
            self.status_updated.emit(online, players, max_players)
        except Exception:
            self.status_updated.emit(False, 0, 0)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


class Sidebar(QFrame):
    """Branded sidebar with nav, status indicator, and version info."""

    nav_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Accent lines at top
        accent_top = QFrame()
        accent_top.setObjectName("sidebarAccentTop")
        layout.addWidget(accent_top)

        accent_fade = QFrame()
        accent_fade.setObjectName("sidebarAccentFade")
        layout.addWidget(accent_fade)

        # Logo area
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(24, 24, 24, 0)
        logo_layout.setSpacing(2)

        self.brand_label = QLabel("TZP")
        self.brand_label.setObjectName("brandLabel")
        logo_layout.addWidget(self.brand_label)

        brand_glow = QFrame()
        brand_glow.setObjectName("brandGlow")
        logo_layout.addWidget(brand_glow)

        logo_layout.addSpacing(6)

        subtitle = QLabel("MODDED MINECRAFT")
        subtitle.setObjectName("subtitleLabel")
        logo_layout.addWidget(subtitle)

        layout.addWidget(logo_container)

        # Version pill
        pill_container = QWidget()
        pill_h = QHBoxLayout(pill_container)
        pill_h.setContentsMargins(24, 10, 24, 0)
        pill_h.setAlignment(Qt.AlignLeft)

        version_pill = QFrame()
        version_pill.setObjectName("versionPill")
        pill_inner = QHBoxLayout(version_pill)
        pill_inner.setContentsMargins(10, 2, 10, 2)
        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setObjectName("versionPillLabel")
        pill_inner.addWidget(version_label)
        pill_h.addWidget(version_pill)

        layout.addWidget(pill_container)

        # Separator
        sep1 = QFrame()
        sep1.setObjectName("sidebarSep")
        sep1_container = QWidget()
        sep1_layout = QVBoxLayout(sep1_container)
        sep1_layout.setContentsMargins(16, 20, 16, 12)
        sep1_layout.addWidget(sep1)
        layout.addWidget(sep1_container)

        # Navigation
        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(12, 0, 12, 0)
        nav_layout.setSpacing(2)

        nav_icons = {
            "home": "\u25C8",
            "settings": "\u2699",
            "about": "\u2139",
        }

        self.nav_buttons: dict[str, QPushButton] = {}
        for key, label in [("home", "Home"), ("settings", "Settings"), ("about", "About")]:
            btn = QPushButton(f"  {nav_icons[key]}   {label}")
            btn.setObjectName("navButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self.nav_clicked.emit(k))
            nav_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        layout.addWidget(nav_container)

        # Separator
        sep2 = QFrame()
        sep2.setObjectName("sidebarSep")
        sep2_container = QWidget()
        sep2_layout = QVBoxLayout(sep2_container)
        sep2_layout.setContentsMargins(16, 12, 16, 12)
        sep2_layout.addWidget(sep2)
        layout.addWidget(sep2_container)

        # Server status card
        status_card = QFrame()
        status_card.setObjectName("statusCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setSpacing(4)

        status_header = QLabel("SERVER STATUS")
        status_header.setObjectName("statusHeader")
        status_layout.addWidget(status_header)

        dot_row = QHBoxLayout()
        dot_row.setSpacing(6)
        self.status_dot = QLabel("\u25CF")
        self.status_dot.setObjectName("statusDot")
        dot_row.addWidget(self.status_dot)

        self.status_label = QLabel("Checking...")
        self.status_label.setObjectName("statusLabel")
        dot_row.addWidget(self.status_label)
        dot_row.addStretch()
        status_layout.addLayout(dot_row)

        self.player_label = QLabel("")
        self.player_label.setObjectName("playerLabel")
        status_layout.addWidget(self.player_label)

        status_card_container = QWidget()
        sc_layout = QVBoxLayout(status_card_container)
        sc_layout.setContentsMargins(16, 0, 16, 4)
        sc_layout.addWidget(status_card)
        layout.addWidget(status_card_container)

        # Spacer
        layout.addStretch(1)

        # Credit
        credit = QLabel("Made by NightMoon_")
        credit.setObjectName("creditLabel")
        credit_container = QWidget()
        cr_layout = QVBoxLayout(credit_container)
        cr_layout.setContentsMargins(24, 4, 24, 16)
        cr_layout.addWidget(credit)
        layout.addWidget(credit_container)

    def set_active_nav(self, key: str):
        """Update nav button styles to highlight the active page."""
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.setObjectName("navButtonActive")
            else:
                btn.setObjectName("navButton")
            # Force style re-evaluation
            btn.style().unpolish(btn)
            btn.style().polish(btn)


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------


class HomePage(QWidget):
    """Main play page with title, info pills, play button, and progress."""

    play_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Center content (stretches)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setAlignment(Qt.AlignCenter)
        center_layout.setSpacing(0)

        center_layout.addStretch(3)

        # Title
        title = QLabel("THE ZACK PACK")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(title)

        center_layout.addSpacing(4)

        # Subtitle
        powered = QLabel("Powered by MadGod AI")
        powered.setObjectName("poweredLabel")
        powered.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(powered)

        center_layout.addSpacing(24)

        # Info pills
        pills_widget = QWidget()
        pills_layout = QHBoxLayout(pills_widget)
        pills_layout.setAlignment(Qt.AlignCenter)
        pills_layout.setSpacing(12)

        pill_data = [
            ("170+ Mods", "pillAccent", "pillAccentLabel"),
            (f"NeoForge {MC_VERSION}", "pillDefault", "pillDefaultLabel"),
            ("AI Dungeon Master", "pillNether", "pillNetherLabel"),
        ]

        for text, frame_id, label_id in pill_data:
            pill = QFrame()
            pill.setObjectName(frame_id)
            pill_inner = QHBoxLayout(pill)
            pill_inner.setContentsMargins(14, 5, 14, 5)
            lbl = QLabel(text)
            lbl.setObjectName(label_id)
            pill_inner.addWidget(lbl)
            pills_layout.addWidget(pill)

        center_layout.addWidget(pills_widget)

        center_layout.addSpacing(32)

        # Play button
        play_row = QWidget()
        play_row_layout = QHBoxLayout(play_row)
        play_row_layout.setAlignment(Qt.AlignCenter)

        self.play_btn = QPushButton("PLAY")
        self.play_btn.setObjectName("playButton")
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self.play_clicked.emit)

        # Opacity effect for subtle glow animation
        self._glow_effect = QGraphicsOpacityEffect(self.play_btn)
        self._glow_effect.setOpacity(1.0)
        self.play_btn.setGraphicsEffect(self._glow_effect)

        play_row_layout.addWidget(self.play_btn)
        center_layout.addWidget(play_row)

        center_layout.addSpacing(20)

        # News card
        news_row = QWidget()
        news_row_layout = QHBoxLayout(news_row)
        news_row_layout.setAlignment(Qt.AlignCenter)

        news_card = QFrame()
        news_card.setObjectName("newsCard")
        news_inner = QHBoxLayout(news_card)
        news_inner.setContentsMargins(14, 10, 16, 10)
        news_inner.setSpacing(0)

        news_dot = QLabel("\u25CF")
        news_dot.setObjectName("newsDot")
        news_inner.addWidget(news_dot)
        news_inner.addSpacing(6)

        news_tag = QLabel("LATEST")
        news_tag.setObjectName("newsTag")
        news_inner.addWidget(news_tag)
        news_inner.addSpacing(8)

        news_text = QLabel("v1.1.0 -- MadGod v2 Event System")
        news_text.setObjectName("newsText")
        news_inner.addWidget(news_text)

        news_row_layout.addWidget(news_card)
        center_layout.addWidget(news_row)

        center_layout.addStretch(4)

        layout.addWidget(center, 1)

        # Bottom progress area
        bottom = QWidget()
        bottom.setFixedHeight(90)
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(40, 0, 40, 24)
        bottom_layout.setSpacing(6)

        # Progress info row
        progress_info = QWidget()
        info_layout = QHBoxLayout(progress_info)
        info_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_label = QLabel("Preparing...")
        self.progress_label.setObjectName("progressLabel")
        info_layout.addWidget(self.progress_label)

        info_layout.addStretch()

        self.progress_pct_label = QLabel("")
        self.progress_pct_label.setObjectName("progressPctLabel")
        info_layout.addWidget(self.progress_pct_label)

        bottom_layout.addWidget(progress_info)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        bottom_layout.addWidget(self.progress_bar)

        layout.addWidget(bottom)


# ---------------------------------------------------------------------------
# About page
# ---------------------------------------------------------------------------


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(6)

        title = QLabel("About TZP")
        title.setObjectName("aboutTitle")
        title.setAlignment(Qt.AlignCenter)
        inner_layout.addWidget(title)

        inner_layout.addSpacing(20)

        lines = [
            ("Project", "The Zack Pack (TZP)"),
            ("Version", f"v{APP_VERSION}"),
            ("Engine", f"NeoForge {MC_VERSION}"),
            ("Mods", "170+ curated mods"),
            ("AI", "MadGod AI Dungeon Master"),
            ("Owner", "NightMoon_ (Zack Grogan)"),
        ]

        for label_text, value_text in lines:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)

            key_label = QLabel(f"{label_text}:")
            key_label.setObjectName("aboutKey")
            key_label.setFixedWidth(80)
            key_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(key_label)

            val_label = QLabel(value_text)
            val_label.setObjectName("aboutValue")
            row_layout.addWidget(val_label)
            row_layout.addStretch()

            inner_layout.addWidget(row)

        layout.addWidget(inner)


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------


class SettingsDialog(QDialog):
    def __init__(self, settings: dict[str, Any], parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setFixedSize(520, 500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(0)

        # Title
        title = QLabel("Settings")
        title.setObjectName("settingsTitle")
        layout.addWidget(title)

        layout.addSpacing(20)

        # GAME section header
        game_header = QLabel("GAME")
        game_header.setObjectName("sectionLabel")
        layout.addWidget(game_header)

        layout.addSpacing(8)

        # RAM card
        ram_card = QFrame()
        ram_card.setObjectName("settingsCard")
        ram_layout = QHBoxLayout(ram_card)
        ram_layout.setContentsMargins(16, 14, 16, 14)

        ram_label = QLabel("RAM Allocation")
        ram_label.setObjectName("cardLabel")
        ram_layout.addWidget(ram_label)
        ram_layout.addStretch()

        self.ram_combo = QComboBox()
        self.ram_combo.addItems(RAM_OPTIONS)
        current_ram = settings.get("ram", DEFAULT_RAM)
        idx = RAM_OPTIONS.index(current_ram) if current_ram in RAM_OPTIONS else 1
        self.ram_combo.setCurrentIndex(idx)
        ram_layout.addWidget(self.ram_combo)

        layout.addWidget(ram_card)

        layout.addSpacing(8)

        # Game directory card
        dir_card = QFrame()
        dir_card.setObjectName("settingsCard")
        dir_layout = QVBoxLayout(dir_card)
        dir_layout.setContentsMargins(16, 14, 16, 14)
        dir_layout.setSpacing(4)

        dir_label = QLabel("Game Directory")
        dir_label.setObjectName("cardLabel")
        dir_layout.addWidget(dir_label)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)

        self.dir_entry = QLineEdit(settings.get("game_dir", str(DEFAULT_GAME_DIR)))
        dir_row.addWidget(self.dir_entry)

        dir_browse = QPushButton("Browse")
        dir_browse.setObjectName("browseButton")
        dir_browse.setCursor(Qt.PointingHandCursor)
        dir_browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(dir_browse)

        dir_layout.addLayout(dir_row)
        layout.addWidget(dir_card)

        layout.addSpacing(8)

        # Separator
        sep = QFrame()
        sep.setObjectName("settingsSep")
        layout.addWidget(sep)

        layout.addSpacing(12)

        # ADVANCED section header
        adv_header = QLabel("ADVANCED")
        adv_header.setObjectName("sectionLabel")
        layout.addWidget(adv_header)

        layout.addSpacing(8)

        # Java path card
        java_card = QFrame()
        java_card.setObjectName("settingsCard")
        java_layout = QVBoxLayout(java_card)
        java_layout.setContentsMargins(16, 14, 16, 14)
        java_layout.setSpacing(4)

        java_header_row = QHBoxLayout()
        java_label = QLabel("Java Path")
        java_label.setObjectName("cardLabel")
        java_header_row.addWidget(java_label)

        java_hint = QLabel("(leave blank to auto-detect)")
        java_hint.setObjectName("cardHint")
        java_header_row.addWidget(java_hint)
        java_header_row.addStretch()
        java_layout.addLayout(java_header_row)

        java_row = QHBoxLayout()
        java_row.setSpacing(8)

        java_detected = find_java(settings.get("java_path") or None)
        java_default = settings.get("java_path", "") or (java_detected or "")
        self.java_entry = QLineEdit(java_default)
        java_row.addWidget(self.java_entry)

        java_browse = QPushButton("Browse")
        java_browse.setObjectName("browseButton")
        java_browse.setCursor(Qt.PointingHandCursor)
        java_browse.clicked.connect(self._browse_java)
        java_row.addWidget(java_browse)

        java_layout.addLayout(java_row)
        layout.addWidget(java_card)

        layout.addStretch()

        # Action buttons
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 20, 0, 0)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        btn_layout.addSpacing(10)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("saveButton")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)

        layout.addWidget(btn_row)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Game Directory", self.dir_entry.text())
        if path:
            self.dir_entry.setText(path)

    def _browse_java(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Java Executable")
        if path:
            self.java_entry.setText(path)

    def _save(self):
        self.settings["ram"] = self.ram_combo.currentText()
        self.settings["game_dir"] = self.dir_entry.text()
        self.settings["java_path"] = self.java_entry.text()
        save_settings(self.settings)
        self.accept()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """Orchestrates sidebar, stacked pages, workers, and state."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1000, 650)
        self.setMinimumSize(900, 550)

        self.settings = load_settings()
        self._update_running = False
        self._game_running = False
        self._server_online = False
        self._pulse_on = True

        self._build_ui()

        # Timers
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_server_status)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_status_dot)
        self._pulse_timer.setInterval(1200)

        # Play button glow animation timer
        self._glow_timer = QTimer(self)
        self._glow_timer.timeout.connect(self._animate_play_glow)
        self._glow_timer.setInterval(50)
        self._glow_val = 1.0
        self._glow_dir = -1

        # Kick off background tasks
        QTimer.singleShot(200, self._poll_server_status)
        QTimer.singleShot(500, self._start_update)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.nav_clicked.connect(self._navigate)
        main_layout.addWidget(self.sidebar)

        # Accent border
        accent = QFrame()
        accent.setObjectName("accentBorder")
        main_layout.addWidget(accent)

        # Main content (stacked)
        self.stack = QStackedWidget()
        self.stack.setObjectName("mainContainer")
        main_layout.addWidget(self.stack, 1)

        # Pages
        self.home_page = HomePage()
        self.home_page.play_clicked.connect(self._on_play)
        self.stack.addWidget(self.home_page)

        self.about_page = AboutPage()
        self.stack.addWidget(self.about_page)

        # Default to home
        self.stack.setCurrentWidget(self.home_page)
        self.sidebar.set_active_nav("home")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, key: str):
        if key == "settings":
            self._open_settings()
            return

        if key == "home":
            self.stack.setCurrentWidget(self.home_page)
        elif key == "about":
            self.stack.setCurrentWidget(self.about_page)

        self.sidebar.set_active_nav(key)

    # ------------------------------------------------------------------
    # Server status
    # ------------------------------------------------------------------

    def _poll_server_status(self):
        self._status_worker = StatusWorker(self)
        self._status_worker.status_updated.connect(self._set_server_status)
        self._status_worker.start()

    def _set_server_status(self, online: bool, players: int, max_players: int):
        self._server_online = online

        if online:
            self.sidebar.status_dot.setStyleSheet("color: #2ECC71; font-size: 12px;")
            self.sidebar.status_label.setText("Online")
            self.sidebar.status_label.setStyleSheet("color: #2ECC71; font-size: 12px;")
            self.sidebar.player_label.setText(f"{players}/{max_players} players online")
            if not self._pulse_timer.isActive():
                self._pulse_on = True
                self._pulse_timer.start()
        else:
            self.sidebar.status_dot.setStyleSheet("color: #E74C3C; font-size: 12px;")
            self.sidebar.status_label.setText("Offline")
            self.sidebar.status_label.setStyleSheet("color: #E74C3C; font-size: 12px;")
            self.sidebar.player_label.setText("")
            self._pulse_timer.stop()

        # Re-check in 30s
        self._status_timer.start(30_000)

    def _pulse_status_dot(self):
        if not self._server_online:
            self._pulse_timer.stop()
            return
        if self._pulse_on:
            self.sidebar.status_dot.setStyleSheet("color: #2ECC71; font-size: 12px;")
        else:
            self.sidebar.status_dot.setStyleSheet("color: #1A7A42; font-size: 12px;")
        self._pulse_on = not self._pulse_on

    # ------------------------------------------------------------------
    # Update flow
    # ------------------------------------------------------------------

    def _start_update(self):
        self._update_running = True
        self.home_page.play_btn.setEnabled(False)
        self.home_page.play_btn.setText("UPDATING...")

        self._update_worker = UpdateWorker(self.settings, self)
        self._update_worker.progress.connect(self._update_progress)
        self._update_worker.neoforge_status.connect(self._neoforge_status)
        self._update_worker.finished.connect(self._update_finished)
        self._update_worker.start()

    def _update_progress(self, frac: float, text: str):
        self.home_page.progress_bar.setValue(int(frac * 1000))
        self.home_page.progress_label.setText(text)
        pct = int(frac * 100)
        self.home_page.progress_pct_label.setText(f"{pct}%" if pct > 0 else "")

    def _neoforge_status(self, msg: str):
        self.home_page.progress_label.setText(msg)

    def _update_finished(self, success: bool, message: str):
        self._update_running = False

        if success:
            self.home_page.progress_bar.setValue(1000)
            self.home_page.progress_pct_label.setText("")
            self.home_page.progress_label.setText("Ready to play!")
            self.home_page.progress_label.setStyleSheet("color: #2ECC71; font-size: 12px;")
            self.home_page.play_btn.setEnabled(True)
            self.home_page.play_btn.setText("PLAY")
            # Start glow animation
            self._glow_timer.start()
        else:
            self.home_page.progress_bar.setValue(0)
            self.home_page.progress_pct_label.setText("")
            self.home_page.progress_label.setText(message)
            self.home_page.progress_label.setStyleSheet("color: #E74C3C; font-size: 12px;")
            self.home_page.play_btn.setEnabled(True)
            self.home_page.play_btn.setText("RETRY")

    # ------------------------------------------------------------------
    # Play button glow animation
    # ------------------------------------------------------------------

    def _animate_play_glow(self):
        """Subtle pulsing opacity on the play button when ready."""
        if not self.home_page.play_btn.isEnabled():
            self._glow_timer.stop()
            return

        self._glow_val += self._glow_dir * 0.008
        if self._glow_val <= 0.85:
            self._glow_dir = 1
        elif self._glow_val >= 1.0:
            self._glow_dir = -1

        self.home_page._glow_effect.setOpacity(self._glow_val)

    # ------------------------------------------------------------------
    # Play
    # ------------------------------------------------------------------

    def _on_play(self):
        if self._update_running:
            return

        # Retry logic
        if self.home_page.play_btn.text() == "RETRY":
            self._start_update()
            return

        if self._game_running:
            return

        game_dir = Path(self.settings["game_dir"])
        ram = self.settings.get("ram", DEFAULT_RAM)
        java_path = self.settings.get("java_path", "") or None

        try:
            self.home_page.play_btn.setEnabled(False)
            self.home_page.play_btn.setText("LAUNCHING...")
            self.home_page.progress_label.setText("Launching Minecraft...")
            self.home_page.progress_label.setStyleSheet("color: #7A7490; font-size: 12px;")
            self._glow_timer.stop()

            proc = launch_minecraft(game_dir, ram, java_path)
            self._game_running = True

            # Monitor process in a thread
            self._launch_worker = _LaunchWatcher(proc, self)
            self._launch_worker.game_exited.connect(self._game_stopped)
            self._launch_worker.start()

        except Exception as exc:
            self.home_page.play_btn.setEnabled(True)
            self.home_page.play_btn.setText("PLAY")
            self.home_page.progress_label.setText(f"Launch failed: {exc}")
            self.home_page.progress_label.setStyleSheet("color: #E74C3C; font-size: 12px;")

    def _game_stopped(self):
        self._game_running = False
        self.home_page.play_btn.setEnabled(True)
        self.home_page.play_btn.setText("PLAY")
        self.home_page.progress_label.setText("Ready to play!")
        self.home_page.progress_label.setStyleSheet("color: #2ECC71; font-size: 12px;")
        self.home_page.progress_pct_label.setText("")
        self.home_page.progress_bar.setValue(1000)
        self._glow_timer.start()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        dialog.exec()


class _LaunchWatcher(QThread):
    """Watches the Minecraft subprocess and emits when it exits."""

    game_exited = Signal()

    def __init__(self, proc, parent=None):
        super().__init__(parent)
        self.proc = proc

    def run(self):
        self.proc.wait()
        self.game_exited.emit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
