"""TZP Launcher -- main GUI application using PySide6 (Qt6).

Premium dark-theme UI inspired by Cursor IDE, Claude Desktop, and Warp terminal,
with a Minecraft ender/void/dungeon aesthetic.
"""

from __future__ import annotations

import asyncio
import json
import platform as runtime_platform
import sys
import traceback
import uuid
from datetime import datetime, timezone
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
    QUrl,
)
from PySide6.QtGui import QColor, QFont, QIcon, QDesktopServices
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
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QMessageBox,
    QSizePolicy,
    QSlider,
    QSpacerItem,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_NAME,
    APP_SUPPORT_DIR,
    APP_VERSION,
    CLAIM_CODE_URL,
    CRASH_REPORT_URL,
    DEFAULT_GAME_DIR,
    DEFAULT_RAM,
    DEFAULT_VERSION_KEY,
    LAUNCHER_UPDATE_URL,
    MANIFEST_URL,
    MC_VERSION,
    MODPACK_INFO_URL,
    RAM_MAX_GB,
    RAM_MIN_GB,
    RAM_OPTIONS,
    STATUS_URL,
    STYLESHEET,
    VERSIONS,
)
from launcher import find_java, install_neoforge, ensure_profile, open_minecraft_launcher
from updater import apply_update, fetch_manifest, SyncResult


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
        "device_id": "",
        "session_token": "",
        "account_name": "",
        "last_update_prompt": "",
        "selected_version": "",
    }
    try:
        if SETTINGS_FILE.is_file():
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
            defaults.update(saved)
    except (json.JSONDecodeError, OSError):
        pass
    if not defaults.get("device_id"):
        defaults["device_id"] = uuid.uuid4().hex
    return defaults


def save_settings(settings: dict[str, Any]) -> None:
    """Persist settings to disk."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


# ---------------------------------------------------------------------------
# Crash reporting + queue
# ---------------------------------------------------------------------------

CRASH_QUEUE_FILE = APP_SUPPORT_DIR / "crash_queue.json"
CRASH_STATE_FILE = APP_SUPPORT_DIR / "crash_state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            with open(path, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return default


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def load_crash_queue() -> list[dict[str, Any]]:
    data = _load_json(CRASH_QUEUE_FILE, [])
    return data if isinstance(data, list) else []


def enqueue_crash(entry: dict[str, Any]) -> None:
    queue = load_crash_queue()
    queue.append(entry)
    _save_json(CRASH_QUEUE_FILE, queue)


def load_crash_state() -> dict[str, Any]:
    data = _load_json(CRASH_STATE_FILE, {})
    return data if isinstance(data, dict) else {}


def save_crash_state(state: dict[str, Any]) -> None:
    _save_json(CRASH_STATE_FILE, state)


def _read_file_snippet(path: Path, max_chars: int = 20000) -> str:
    try:
        with open(path, "r", errors="ignore") as f:
            return f.read(max_chars)
    except OSError:
        return ""


def scan_minecraft_crash_reports(game_dir: Path) -> int:
    crash_dir = game_dir / "crash-reports"
    if not crash_dir.is_dir():
        return 0

    state = load_crash_state()
    seen: dict[str, str] = state.get("seen", {}) if isinstance(state.get("seen"), dict) else {}
    new_count = 0

    for path in crash_dir.glob("*.txt"):
        try:
            stat = path.stat()
        except OSError:
            continue

        key = f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}"
        if seen.get(path.name) == key:
            continue

        enqueue_crash(
            {
                "type": "minecraft_crash_report",
                "timestamp": _now_iso(),
                "path": str(path),
                "filename": path.name,
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
                "content": _read_file_snippet(path),
            }
        )
        seen[path.name] = key
        new_count += 1

    save_crash_state({"seen": seen})
    return new_count


def flush_crash_queue(session_token: str | None, device_id: str) -> bool:
    queue = load_crash_queue()
    if not queue:
        return True

    payload = {
        "device_id": device_id,
        "session_token": session_token or "",
        "launcher_version": APP_VERSION,
        "reports": queue,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(CRASH_REPORT_URL, json=payload)
            resp.raise_for_status()
        _save_json(CRASH_QUEUE_FILE, [])
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------


class UpdateWorker(QThread):
    """Runs the update check/download in background, emitting progress signals."""

    progress = Signal(float, str)       # (fraction 0-1, status_text)
    finished = Signal(bool, str)        # (success, summary_message)
    sync_result = Signal(object)        # emits SyncResult when sync completes
    neoforge_status = Signal(str)       # NeoForge install status messages

    def __init__(self, settings: dict[str, Any], manifest_url: str = "", instance_dir: str = "", parent=None):
        super().__init__(parent)
        self.settings = settings
        self.manifest_url = manifest_url or MANIFEST_URL
        self.instance_dir = instance_dir

    def run(self):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._async_update())
        except Exception as exc:
            self.finished.emit(False, f"Update failed: {exc}")
        finally:
            loop.close()

    async def _async_update(self):
        base_dir = Path(self.settings["game_dir"])
        # Each version gets its own instance directory so switching doesn't wipe mods
        if self.instance_dir:
            game_dir = base_dir / "instances" / self.instance_dir
        else:
            game_dir = base_dir
        game_dir.mkdir(parents=True, exist_ok=True)

        self.progress.emit(0.0, "Fetching manifest...")
        manifest = await fetch_manifest(self.manifest_url)

        self.progress.emit(0.05, "Checking for updates...")
        result = await apply_update(manifest, game_dir, self._progress_cb)

        # Emit detailed sync result for log tab
        self.sync_result.emit(result)

        summary = (
            f"Done: {len(result.downloaded)} downloaded, "
            f"{len(result.deleted)} removed, "
            f"{len(result.unchanged)} up to date."
        )
        if result.errors:
            summary += f" ({len(result.errors)} errors)"

        # Install NeoForge into the official MC launcher directory so the
        # launcher can find the version JARs and libraries.  The gameDir
        # profile setting handles redirecting mods/configs/saves to game_dir.
        from launcher import _mc_launcher_dir
        mc_dir = _mc_launcher_dir()
        self.neoforge_status.emit("Verifying NeoForge install...")
        try:
            install_neoforge(
                mc_dir,
                java_path=self.settings.get("java_path", "") or None,
                callback=lambda msg: self.neoforge_status.emit(msg),
            )
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
# Launcher update check
# ---------------------------------------------------------------------------


def _parse_version(raw: str) -> tuple[int, int, int]:
    cleaned = raw.strip().lstrip("v")
    parts = cleaned.split(".")
    nums: list[int] = []
    for part in parts[:3]:
        digits = "".join(ch for ch in part if ch.isdigit())
        if digits:
            nums.append(int(digits))
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])  # type: ignore[return-value]


class UpdateCheckWorker(QThread):
    update_available = Signal(str, str, str)  # (version, url, summary)

    def run(self):
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(
                    LAUNCHER_UPDATE_URL,
                    headers={"Accept": "application/vnd.github+json"},
                )
                resp.raise_for_status()
                data = resp.json()

            latest_tag = str(data.get("version") or data.get("tag_name") or "").strip()
            latest_url = str(
                data.get("windowsUrl")
                if runtime_platform.system() == "Windows"
                else data.get("universalUrl") or data.get("releaseUrl") or data.get("html_url")
            ).strip()
            summary = str(data.get("summary") or data.get("body") or "").strip()

            if not latest_tag or not latest_url:
                return

            if _parse_version(latest_tag) > _parse_version(APP_VERSION):
                self.update_available.emit(latest_tag.lstrip("v"), latest_url, summary)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Account claim code worker
# ---------------------------------------------------------------------------


class ClaimWorker(QThread):
    finished = Signal(bool, str, dict)  # (success, message, payload)

    def __init__(self, claim_code: str, device_id: str, parent=None):
        super().__init__(parent)
        self.claim_code = claim_code
        self.device_id = device_id

    def run(self):
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    CLAIM_CODE_URL,
                    json={
                        "claim_code": self.claim_code,
                        "device_id": self.device_id,
                        "launcher_version": APP_VERSION,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            self.finished.emit(True, "Linked successfully.", data)
        except Exception as exc:
            self.finished.emit(False, f"Link failed: {exc}", {})


# ---------------------------------------------------------------------------
# Modpack info worker (fetches dynamic pill data from API)
# ---------------------------------------------------------------------------


class ModpackInfoWorker(QThread):
    info_fetched = Signal(dict)  # emits the parsed JSON payload

    def run(self):
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(MODPACK_INFO_URL)
                resp.raise_for_status()
                self.info_fetched.emit(resp.json())
        except Exception:
            self.info_fetched.emit({})


# ---------------------------------------------------------------------------
# Crash report worker
# ---------------------------------------------------------------------------


class CrashReportWorker(QThread):
    finished = Signal(int, bool)  # (new_reports, sent_ok)

    def __init__(self, game_dir: Path, session_token: str | None, device_id: str, parent=None):
        super().__init__(parent)
        self.game_dir = game_dir
        self.session_token = session_token
        self.device_id = device_id

    def run(self):
        new_reports = scan_minecraft_crash_reports(self.game_dir)
        sent_ok = flush_crash_queue(self.session_token, self.device_id)
        self.finished.emit(new_reports, sent_ok)


# ---------------------------------------------------------------------------
# Crash watcher thread (monitors for new crash reports while MC is running)
# ---------------------------------------------------------------------------


class CrashWatcherThread(QThread):
    """Watches the crash-reports directory for new files while Minecraft runs."""

    crash_detected = Signal(str)  # emits crash report path

    def __init__(self, game_dir: Path, parent=None):
        super().__init__(parent)
        self.game_dir = game_dir
        self.running = True
        self.known_crashes: set[str] = set()

    def run(self):
        crash_dir = self.game_dir / "crash-reports"
        # Snapshot existing crashes on start so we only detect NEW ones
        if crash_dir.exists():
            self.known_crashes = set(f.name for f in crash_dir.glob("*.txt"))

        while self.running:
            self.msleep(5000)  # Check every 5 seconds
            if not crash_dir.exists():
                continue
            current = set(f.name for f in crash_dir.glob("*.txt"))
            new_crashes = current - self.known_crashes
            if new_crashes:
                newest = sorted(new_crashes)[-1]
                self.crash_detected.emit(str(crash_dir / newest))
                self.known_crashes = current

    def stop(self):
        self.running = False


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
            "log": "\u2630",
            "about": "\u2139",
        }

        self.nav_buttons: dict[str, QPushButton] = {}
        for key, label in [("home", "Home"), ("settings", "Settings"), ("log", "Log"), ("about", "About")]:
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

        # Info pills (dynamic — updated by API fetch, with hardcoded defaults)
        pills_widget = QWidget()
        pills_layout = QHBoxLayout(pills_widget)
        pills_layout.setAlignment(Qt.AlignCenter)
        pills_layout.setSpacing(12)

        # Default pill data — overridden by API response
        pill_data = [
            ("Loading...", "pillAccent", "pillAccentLabel"),
            (f"NeoForge {MC_VERSION}", "pillDefault", "pillDefaultLabel"),
            ("Loading...", "pillNether", "pillNetherLabel"),
        ]

        self.pill_labels: list[QLabel] = []
        for text, frame_id, label_id in pill_data:
            pill = QFrame()
            pill.setObjectName(frame_id)
            pill_inner = QHBoxLayout(pill)
            pill_inner.setContentsMargins(14, 5, 14, 5)
            lbl = QLabel(text)
            lbl.setObjectName(label_id)
            pill_inner.addWidget(lbl)
            pills_layout.addWidget(pill)
            self.pill_labels.append(lbl)

        center_layout.addWidget(pills_widget)

        center_layout.addSpacing(20)

        # Version picker
        version_row = QWidget()
        version_row_layout = QHBoxLayout(version_row)
        version_row_layout.setAlignment(Qt.AlignCenter)
        version_row_layout.setContentsMargins(0, 0, 0, 0)

        version_col = QVBoxLayout()
        version_col.setAlignment(Qt.AlignCenter)
        version_col.setSpacing(4)

        self.version_combo = QComboBox()
        self.version_combo.addItems(list(VERSIONS.keys()))
        self.version_combo.setFixedWidth(240)
        self.version_combo.setFixedHeight(36)
        self.version_combo.setCursor(Qt.PointingHandCursor)
        version_col.addWidget(self.version_combo, alignment=Qt.AlignCenter)

        self.server_ip_label = QLabel("")
        self.server_ip_label.setStyleSheet("color: #525252; font-size: 11px;")
        self.server_ip_label.setAlignment(Qt.AlignCenter)
        version_col.addWidget(self.server_ip_label, alignment=Qt.AlignCenter)

        version_row_layout.addLayout(version_col)
        center_layout.addWidget(version_row)

        center_layout.addSpacing(20)

        # Play button
        play_row = QWidget()
        play_row_layout = QHBoxLayout(play_row)
        play_row_layout.setAlignment(Qt.AlignCenter)

        self.play_btn = QPushButton("SYNC PACK")
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

        self.news_text = QLabel("Loading latest update...")
        self.news_text.setObjectName("newsText")
        news_inner.addWidget(self.news_text)

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

    def update_pills(self, mod_count: str, engine: str, feature: str):
        """Update the info pill labels with dynamic data."""
        if len(self.pill_labels) >= 3:
            self.pill_labels[0].setText(mod_count)
            self.pill_labels[1].setText(engine)
            self.pill_labels[2].setText(feature)


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
            ("Mods", "195+ curated mods"),
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
# Log page
# ---------------------------------------------------------------------------


class LogPage(QWidget):
    """Read-only live event log for update, install, and launch debugging."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 28)
        layout.setSpacing(16)

        title = QLabel("Launcher Log")
        title.setObjectName("aboutTitle")
        layout.addWidget(title)

        hint = QLabel("Live launcher events appear here while you update, install, and launch.")
        hint.setObjectName("aboutValue")
        layout.addWidget(hint)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        actions_layout.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("secondaryActionButton")
        actions_layout.addWidget(self.clear_btn)
        layout.addWidget(actions)

        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.log_output, 1)

    def append_line(self, line: str) -> None:
        self.log_output.appendPlainText(line)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear(self) -> None:
        self.log_output.clear()


# ---------------------------------------------------------------------------
# Update dialog
# ---------------------------------------------------------------------------


class LauncherDownloadWorker(QThread):
    """Downloads a launcher update in the background."""
    progress = Signal(int)  # percent 0-100
    finished = Signal(bool, str)  # (success, file_path_or_error)

    def __init__(self, url: str, dest: Path, parent=None):
        super().__init__(parent)
        self.url = url
        self.dest = dest

    def run(self):
        try:
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                with client.stream("GET", self.url) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    self.dest.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.dest, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=65536):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                self.progress.emit(int(downloaded / total * 100))
            self.finished.emit(True, str(self.dest))
        except Exception as exc:
            self.finished.emit(False, str(exc))


class UpdateDialog(QDialog):
    def __init__(self, version: str, url: str, summary: str, parent=None):
        super().__init__(parent)
        self._url = url
        self._version = version
        self.setWindowTitle("Launcher Update Available")
        self.setFixedSize(520, 340)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        title = QLabel("Update Available")
        title.setObjectName("aboutTitle")
        layout.addWidget(title)

        msg = QLabel(f"Version {version} is ready to install.")
        msg.setWordWrap(True)
        msg.setObjectName("aboutValue")
        layout.addWidget(msg)

        if summary:
            summary_label = QLabel(summary[:320])
            summary_label.setWordWrap(True)
            summary_label.setObjectName("cardHint")
            layout.addWidget(summary_label)

        # Progress bar (hidden until download starts)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        self._progress.setFormat("Downloading... %p%")
        layout.addWidget(self._progress)

        self._status_label = QLabel("")
        self._status_label.setObjectName("cardHint")
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        layout.addStretch()

        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.addStretch()

        self._later_btn = QPushButton("Later")
        self._later_btn.setObjectName("cancelButton")
        self._later_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._later_btn)

        btn_layout.addSpacing(10)

        self._update_btn = QPushButton("Update Now")
        self._update_btn.setObjectName("saveButton")
        self._update_btn.clicked.connect(self._start_download)
        btn_layout.addWidget(self._update_btn)

        layout.addWidget(btn_row)

    def _start_download(self):
        self._update_btn.setEnabled(False)
        self._update_btn.setText("Downloading...")
        self._later_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        # Determine download destination
        if runtime_platform.system() == "Windows":
            dest = APP_SUPPORT_DIR / f"TZP-Launcher-{self._version}-Setup.exe"
        else:
            dest = APP_SUPPORT_DIR / f"TZP-Launcher-{self._version}.zip"

        self._download_dest = dest
        self._worker = LauncherDownloadWorker(self._url, dest, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_download_done)
        self._worker.start()

    def _on_progress(self, pct: int):
        self._progress.setValue(pct)

    def _on_download_done(self, success: bool, result: str):
        if success:
            self._progress.setValue(100)
            self._progress.setFormat("Download complete!")
            self._status_label.setVisible(True)

            if runtime_platform.system() == "Windows":
                # Launch the installer and close the launcher
                self._status_label.setText("Launching installer...")
                import subprocess
                subprocess.Popen([result], shell=True)
                QApplication.quit()
            else:
                # For macOS/Linux — open the containing folder
                self._status_label.setText(f"Saved to: {result}")
                self._update_btn.setText("Open Folder")
                self._update_btn.setEnabled(True)
                self._update_btn.clicked.disconnect()
                self._update_btn.clicked.connect(
                    lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(result).parent)))
                )
                self._later_btn.setText("Close")
                self._later_btn.setEnabled(True)
        else:
            self._progress.setFormat("Download failed")
            self._status_label.setVisible(True)
            self._status_label.setText(f"Error: {result}")
            self._status_label.setStyleSheet("color: #ef4444; font-size: 11px;")
            self._update_btn.setText("Try in Browser")
            self._update_btn.setEnabled(True)
            self._update_btn.clicked.disconnect()
            self._update_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._url)))
            self._later_btn.setEnabled(True)


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------


class SettingsDialog(QDialog):
    def __init__(self, settings: dict[str, Any], parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setFixedSize(600, 660)
        self.setModal(True)
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(4)

        # Title
        title = QLabel("Settings")
        title.setObjectName("settingsTitle")
        layout.addWidget(title)

        layout.addSpacing(20)

        # ACCOUNT section header
        account_header = QLabel("ACCOUNT")
        account_header.setObjectName("sectionLabel")
        layout.addWidget(account_header)

        layout.addSpacing(8)

        account_card = QFrame()
        account_card.setObjectName("settingsCard")
        account_card.setAutoFillBackground(True)
        account_layout = QHBoxLayout(account_card)
        account_layout.setContentsMargins(16, 14, 16, 14)

        status_label = QLabel("Account")
        status_label.setObjectName("cardLabel")
        account_layout.addWidget(status_label)
        account_layout.addStretch()

        account_name = settings.get("account_name", "")
        session_token = settings.get("session_token", "")
        status_text = f"Linked ({account_name})" if session_token else "Not linked — run /link in-game"
        self.account_status = QLabel(status_text)
        self.account_status.setObjectName("cardHint")
        account_layout.addWidget(self.account_status)

        layout.addWidget(account_card)

        layout.addSpacing(16)

        # GAME section header
        game_header = QLabel("GAME")
        game_header.setObjectName("sectionLabel")
        layout.addWidget(game_header)

        layout.addSpacing(8)

        # RAM card with slider
        ram_card = QFrame()
        ram_card.setObjectName("settingsCard")
        ram_card.setAutoFillBackground(True)
        ram_card_layout = QVBoxLayout(ram_card)
        ram_card_layout.setContentsMargins(16, 14, 16, 14)
        ram_card_layout.setSpacing(10)

        ram_header = QHBoxLayout()
        ram_label = QLabel("RAM Allocation")
        ram_label.setObjectName("cardLabel")
        ram_header.addWidget(ram_label)
        ram_header.addStretch()

        current_ram = settings.get("ram", DEFAULT_RAM)
        current_gb = int(current_ram.replace("G", "")) if current_ram.endswith("G") else 6
        current_gb = max(RAM_MIN_GB, min(RAM_MAX_GB, current_gb))

        self.ram_value_label = QLabel(f"{current_gb}G")
        self.ram_value_label.setObjectName("ramValue")
        self.ram_value_label.setStyleSheet("color: #3b82f6; font-size: 16px; font-weight: bold; font-family: 'JetBrains Mono', monospace;")
        ram_header.addWidget(self.ram_value_label)
        ram_card_layout.addLayout(ram_header)

        self.ram_slider = QSlider(Qt.Horizontal)
        self.ram_slider.setMinimum(RAM_MIN_GB)
        self.ram_slider.setMaximum(RAM_MAX_GB)
        self.ram_slider.setSingleStep(2)
        self.ram_slider.setPageStep(2)
        self.ram_slider.setValue(current_gb)
        self.ram_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.ram_slider.setTickInterval(2)
        self.ram_slider.valueChanged.connect(self._on_ram_changed)
        ram_card_layout.addWidget(self.ram_slider)

        ram_range_row = QHBoxLayout()
        ram_min_lbl = QLabel(f"{RAM_MIN_GB}G")
        ram_min_lbl.setStyleSheet("color: #525252; font-size: 10px; font-family: monospace;")
        ram_max_lbl = QLabel(f"{RAM_MAX_GB}G")
        ram_max_lbl.setStyleSheet("color: #525252; font-size: 10px; font-family: monospace;")
        ram_range_row.addWidget(ram_min_lbl)
        ram_range_row.addStretch()
        ram_max_lbl.setAlignment(Qt.AlignRight)
        ram_range_row.addWidget(ram_max_lbl)
        ram_card_layout.addLayout(ram_range_row)

        layout.addWidget(ram_card)

        layout.addSpacing(8)

        # Game directory card
        dir_card = QFrame()
        dir_card.setObjectName("settingsCard")
        dir_card.setAutoFillBackground(True)
        dir_layout = QVBoxLayout(dir_card)
        dir_layout.setContentsMargins(16, 14, 16, 14)
        dir_layout.setSpacing(10)

        dir_label = QLabel("Game Directory")
        dir_label.setObjectName("cardLabel")
        dir_layout.addWidget(dir_label)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)

        self.dir_entry = QLineEdit(settings.get("game_dir", str(DEFAULT_GAME_DIR)))
        self.dir_entry.setCursorPosition(0)
        self.dir_entry.setMinimumHeight(36)
        dir_row.addWidget(self.dir_entry, 1)

        dir_browse = QPushButton("Browse")
        dir_browse.setObjectName("browseButton")
        dir_browse.setCursor(Qt.PointingHandCursor)
        dir_browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(dir_browse)

        dir_layout.addLayout(dir_row)
        layout.addWidget(dir_card)

        layout.addSpacing(20)

        # ADVANCED section header
        adv_header = QLabel("ADVANCED")
        adv_header.setObjectName("sectionLabel")
        layout.addWidget(adv_header)

        layout.addSpacing(8)

        # Java path card
        java_card = QFrame()
        java_card.setObjectName("settingsCard")
        java_card.setAutoFillBackground(True)
        java_layout = QVBoxLayout(java_card)
        java_layout.setContentsMargins(16, 14, 16, 14)
        java_layout.setSpacing(10)

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
        self.java_entry.setCursorPosition(0)
        self.java_entry.setMinimumHeight(36)
        java_row.addWidget(self.java_entry, 1)

        java_browse = QPushButton("Browse")
        java_browse.setObjectName("browseButton")
        java_browse.setCursor(Qt.PointingHandCursor)
        java_browse.clicked.connect(self._browse_java)
        java_row.addWidget(java_browse)

        java_layout.addLayout(java_row)
        layout.addWidget(java_card)

        layout.addSpacing(16)

        # LAUNCHER section
        launcher_header = QLabel("LAUNCHER")
        launcher_header.setObjectName("sectionLabel")
        layout.addWidget(launcher_header)

        layout.addSpacing(8)

        update_card = QFrame()
        update_card.setObjectName("settingsCard")
        update_card.setAutoFillBackground(True)
        update_card_layout = QHBoxLayout(update_card)
        update_card_layout.setContentsMargins(16, 14, 16, 14)

        version_label = QLabel(f"Version {APP_VERSION}")
        version_label.setObjectName("cardLabel")
        update_card_layout.addWidget(version_label)
        update_card_layout.addStretch()

        self.update_check_btn = QPushButton("Check for Updates")
        self.update_check_btn.setObjectName("browseButton")
        self.update_check_btn.setCursor(Qt.PointingHandCursor)
        self.update_check_btn.clicked.connect(self._check_updates)
        update_card_layout.addWidget(self.update_check_btn)

        layout.addWidget(update_card)

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

    def _check_updates(self):
        self.update_check_btn.setEnabled(False)
        self.update_check_btn.setText("Checking...")
        self._update_worker = UpdateCheckWorker(self)
        self._update_worker.update_available.connect(self._on_update_found)
        self._update_worker.finished.connect(self._on_update_check_done)
        self._update_worker.start()

    def _on_update_found(self, version: str, url: str, summary: str):
        self.update_check_btn.setText(f"v{version} available!")
        self.update_check_btn.setStyleSheet("color: #2ECC71; font-weight: bold;")
        # Close settings and show update dialog
        self.accept()
        if self.parent():
            dialog = UpdateDialog(version, url, summary, self.parent())
            dialog.exec()

    def _on_update_check_done(self):
        if self.update_check_btn.text() == "Checking...":
            self.update_check_btn.setText("Up to date!")
            self.update_check_btn.setEnabled(True)

    def _on_ram_changed(self, value: int):
        # Snap to even numbers
        snapped = max(RAM_MIN_GB, min(RAM_MAX_GB, (value // 2) * 2))
        if snapped != value:
            self.ram_slider.setValue(snapped)
            return
        self.ram_value_label.setText(f"{snapped}G")

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Game Directory", self.dir_entry.text())
        if path:
            self.dir_entry.setText(path)

    def _browse_java(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Java Executable")
        if path:
            self.java_entry.setText(path)

    def _claim_code(self):
        code = self.claim_input.text().strip()
        if not code:
            self.claim_status.setText("Enter a claim code.")
            return

        self.claim_button.setEnabled(False)
        self.claim_status.setText("Linking...")

        device_id = self.settings.get("device_id", "")
        if not device_id:
            device_id = uuid.uuid4().hex
            self.settings["device_id"] = device_id

        self._claim_worker = ClaimWorker(code, device_id, self)
        self._claim_worker.finished.connect(self._on_claim_finished)
        self._claim_worker.start()

    def _on_claim_finished(self, success: bool, message: str, payload: dict):
        self.claim_button.setEnabled(True)
        self.claim_status.setText(message)
        if not success:
            return

        token = payload.get("session_token") or payload.get("token") or ""
        account = payload.get("account") or {}
        account_name = account.get("name") or account.get("username") or payload.get("username") or ""

        if token:
            self.settings["session_token"] = token
        if account_name:
            self.settings["account_name"] = account_name

        status_text = f"Linked ({account_name})" if token else "Linked"
        self.account_status.setText(status_text)
        save_settings(self.settings)

    def _save(self):
        self.settings["ram"] = f"{self.ram_slider.value()}G"
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
        save_settings(self.settings)
        self._update_running = False
        self._pack_ready = False
        self._server_online = False
        self._pulse_on = True
        self._device_id = self.settings.get("device_id", "")
        self._last_progress_message = ""
        self._last_neoforge_message = ""

        self._really_quit = False
        self._crash_watcher: CrashWatcherThread | None = None

        self._build_ui()
        self._setup_tray()

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
        QTimer.singleShot(500, self._fetch_modpack_info)
        QTimer.singleShot(800, self._check_launcher_update)
        QTimer.singleShot(1200, self._scan_and_send_crash_reports)
        self._set_sync_prompt()

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

        self.log_page = LogPage()
        self.log_page.clear_btn.clicked.connect(self.log_page.clear)
        self.stack.addWidget(self.log_page)

        self.about_page = AboutPage()
        self.stack.addWidget(self.about_page)

        # Default to home
        self.stack.setCurrentWidget(self.home_page)
        self.sidebar.set_active_nav("home")

        # Initialize version picker from saved settings
        saved_version = self.settings.get("selected_version", "")
        version_keys = list(VERSIONS.keys())
        if saved_version in version_keys:
            self.home_page.version_combo.setCurrentText(saved_version)
        else:
            self.home_page.version_combo.setCurrentText(DEFAULT_VERSION_KEY)
        self._update_server_ip_label()
        self.home_page.version_combo.currentTextChanged.connect(self._on_version_changed)

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self):
        """Create system tray icon with context menu."""
        self._tray = QSystemTrayIcon(self)
        # Use the application icon if available, otherwise a default
        icon = self.windowIcon()
        if icon.isNull():
            icon = QIcon.fromTheme("applications-games")
        self._tray.setIcon(icon)
        self._tray.setToolTip(APP_NAME)

        tray_menu = QMenu()
        show_action = tray_menu.addAction("Show TZP")
        show_action.triggered.connect(self._restore_from_tray)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self._quit_app)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _minimize_to_tray(self):
        self.hide()
        self._tray.showMessage(
            APP_NAME,
            "TZP Launcher is still running in the tray.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _quit_app(self):
        self._really_quit = True
        self.close()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, key: str):
        if key == "settings":
            self._open_settings()
            return

        if key == "home":
            self.stack.setCurrentWidget(self.home_page)
        elif key == "log":
            self.stack.setCurrentWidget(self.log_page)
        elif key == "about":
            self.stack.setCurrentWidget(self.about_page)

        self.sidebar.set_active_nav(key)

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_page.append_line(f"[{timestamp}] {message}")

    # ------------------------------------------------------------------
    # Server status
    # ------------------------------------------------------------------

    def _poll_server_status(self):
        self._log("Polling server status.")
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
            self._log(f"Server online: {players}/{max_players} players.")
        else:
            self.sidebar.status_dot.setStyleSheet("color: #E74C3C; font-size: 12px;")
            self.sidebar.status_label.setText("Offline")
            self.sidebar.status_label.setStyleSheet("color: #E74C3C; font-size: 12px;")
            self.sidebar.player_label.setText("")
            self._pulse_timer.stop()
            self._log("Server offline.")

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
    # Modpack info (dynamic pills)
    # ------------------------------------------------------------------

    def _fetch_modpack_info(self):
        self._log("Fetching modpack info from API.")
        self._modpack_info_worker = ModpackInfoWorker(self)
        self._modpack_info_worker.info_fetched.connect(self._on_modpack_info)
        self._modpack_info_worker.start()

    def _on_modpack_info(self, data: dict):
        if not data:
            # API failed — fall back to hardcoded defaults
            self._log("Modpack info API unavailable, using defaults.")
            self.home_page.update_pills(
                "195+ Mods",
                f"NeoForge {MC_VERSION}",
                "AI Dungeon Master",
            )
            self.home_page.news_text.setText("Could not load latest update info.")
            return

        mod_count = data.get("mod_count", "195+")
        engine = data.get("engine", f"NeoForge {MC_VERSION}")
        feature = data.get("feature", "AI Dungeon Master")
        motd = data.get("motd", "")

        self.home_page.update_pills(
            f"{mod_count} Mods" if isinstance(mod_count, int) else str(mod_count),
            str(engine),
            str(feature),
        )

        # Update news card from API motd
        if motd:
            self.home_page.news_text.setText(str(motd))

        self._log(f"Modpack info loaded: {mod_count} mods, {engine}, {feature}")

    # ------------------------------------------------------------------
    # Update flow
    # ------------------------------------------------------------------

    def _on_version_changed(self, version_key: str):
        """Handle version picker change — save setting and reset sync state."""
        self.settings["selected_version"] = version_key
        save_settings(self.settings)
        self._update_server_ip_label()
        self._set_sync_prompt()
        self._log(f"Switched to {version_key}.")

    def _update_server_ip_label(self):
        """Update the server IP label below the version picker."""
        version_key = self.home_page.version_combo.currentText()
        version_info = VERSIONS.get(version_key, VERSIONS[DEFAULT_VERSION_KEY])
        ip = version_info.get("server_ip", "")
        port = version_info.get("server_port", 25565)
        if ip:
            label = f"Server: {ip}" + (f":{port}" if port != 25565 else "")
            self.home_page.server_ip_label.setText(label)
        else:
            self.home_page.server_ip_label.setText("Server: TBD")

    def _set_sync_prompt(self):
        self._pack_ready = False
        self.home_page.play_btn.setEnabled(True)
        self.home_page.play_btn.setText("SYNC PACK")
        self.home_page.progress_bar.setValue(0)
        self.home_page.progress_pct_label.setText("")
        self.home_page.progress_label.setText("Sync the latest pack when you're ready.")
        self.home_page.progress_label.setStyleSheet("color: #737373; font-size: 12px;")
        self._log("Launcher ready. Waiting for explicit pack sync.")

    def _start_update(self):
        if self._update_running:
            return
        # Resolve manifest URL + instance dir from selected version
        version_key = self.home_page.version_combo.currentText()
        version_info = VERSIONS.get(version_key, VERSIONS[DEFAULT_VERSION_KEY])
        manifest_url = version_info["manifest"]
        instance_dir = version_info.get("instance_dir", "")
        self._log(f"Starting pack sync for {version_key} (instance: {instance_dir or 'default'}).")
        self._update_running = True
        self.home_page.play_btn.setEnabled(False)
        self.home_page.play_btn.setText("UPDATING...")

        self._update_worker = UpdateWorker(self.settings, manifest_url=manifest_url, instance_dir=instance_dir, parent=self)
        self._update_worker.progress.connect(self._update_progress)
        self._update_worker.sync_result.connect(self._on_sync_result)
        self._update_worker.neoforge_status.connect(self._neoforge_status)
        self._update_worker.finished.connect(self._update_finished)
        self._update_worker.start()

    def _check_launcher_update(self):
        self._log("Checking launcher release metadata.")
        self._update_check_worker = UpdateCheckWorker(self)
        self._update_check_worker.update_available.connect(self._show_update_dialog)
        self._update_check_worker.start()

    def _show_update_dialog(self, version: str, url: str, summary: str):
        if self.settings.get("last_update_prompt") == version:
            return
        self._log(f"Launcher update available: v{version} -> {url}")
        dialog = UpdateDialog(version, url, summary, self)
        dialog.exec()
        self.settings["last_update_prompt"] = version
        save_settings(self.settings)

    def _update_progress(self, frac: float, text: str):
        self.home_page.progress_bar.setValue(int(frac * 1000))
        self.home_page.progress_label.setText(text)
        pct = int(frac * 100)
        self.home_page.progress_pct_label.setText(f"{pct}%" if pct > 0 else "")
        if text != self._last_progress_message:
            self._last_progress_message = text
            self._log(f"Update: {text}")

    def _neoforge_status(self, msg: str):
        self.home_page.progress_label.setText(msg)
        if msg != self._last_neoforge_message:
            self._last_neoforge_message = msg
            self._log(f"NeoForge: {msg}")

    def _on_sync_result(self, result: SyncResult):
        """Log detailed sync results to the Log tab."""
        for path in result.downloaded:
            self._log(f"  ADDED    {path}")
        for path in result.deleted:
            self._log(f"  REMOVED  {path}")
        for path in result.unchanged:
            self._log(f"  OK       {path}")
        for err in result.errors:
            self._log(f"  ERROR    {err}")
        self._log(
            f"Sync complete: {len(result.downloaded)} added, "
            f"{len(result.deleted)} removed, "
            f"{len(result.unchanged)} unchanged, "
            f"{len(result.errors)} errors"
        )

    def _update_finished(self, success: bool, message: str):
        self._update_running = False

        if success:
            self._log(f"Pack sync finished successfully. {message}")
            self._pack_ready = True
            self.home_page.progress_bar.setValue(1000)
            self.home_page.progress_pct_label.setText("")
            # Use the instance-specific game directory (matches where UpdateWorker synced)
            base_dir = Path(self.settings["game_dir"])
            version_key = self.home_page.version_combo.currentText()
            version_info = VERSIONS.get(version_key, VERSIONS[DEFAULT_VERSION_KEY])
            instance_dir = version_info.get("instance_dir", "")
            if instance_dir:
                game_dir = base_dir / "instances" / instance_dir
            else:
                game_dir = base_dir
            java_path = self.settings.get("java_path", "") or None
            ram = self.settings.get("ram", DEFAULT_RAM)
            profile_ok = ensure_profile(game_dir, java_path, ram)
            if profile_ok:
                self._log("TZP profile created in Minecraft launcher.")
                self.home_page.progress_label.setText("Ready! Click to launch Minecraft.")
            else:
                self._log("Minecraft launcher not found — open game folder instead.")
                self.home_page.progress_label.setText("Pack synced! Open Minecraft and select the TZP profile.")
            self.home_page.progress_label.setStyleSheet("color: #2ECC71; font-size: 12px;")
            self.home_page.play_btn.setEnabled(True)
            self.home_page.play_btn.setText("LAUNCH MINECRAFT")
            # Start glow animation
            self._glow_timer.start()
        else:
            self._log(f"Pack sync failed. {message}")
            self._pack_ready = False
            self.home_page.progress_bar.setValue(0)
            self.home_page.progress_pct_label.setText("")
            self.home_page.progress_label.setText(message)
            self.home_page.progress_label.setStyleSheet("color: #E74C3C; font-size: 12px;")
            self.home_page.play_btn.setEnabled(True)
            self.home_page.play_btn.setText("RETRY")
            enqueue_crash(
                {
                    "type": "launcher_update_failure",
                    "timestamp": _now_iso(),
                    "message": message,
                    "launcher_version": APP_VERSION,
                }
            )

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
    # Crash reporting
    # ------------------------------------------------------------------

    def _scan_and_send_crash_reports(self):
        game_dir = Path(self.settings.get("game_dir", str(DEFAULT_GAME_DIR)))
        session_token = self.settings.get("session_token", "") or None
        self._log("Scanning for crash reports.")
        self._crash_worker = CrashReportWorker(game_dir, session_token, self._device_id, self)
        self._crash_worker.finished.connect(self._crash_report_finished)
        self._crash_worker.start()

    def _crash_report_finished(self, new_reports: int, sent_ok: bool):
        self._log(
            f"Crash report scan complete. New reports: {new_reports}. Upload successful: {sent_ok}."
        )
        if new_reports > 0 and not sent_ok:
            enqueue_crash(
                {
                    "type": "crash_report_upload_failed",
                    "timestamp": _now_iso(),
                    "message": "Crash report upload failed. Reports queued.",
                    "launcher_version": APP_VERSION,
                }
            )

    # ------------------------------------------------------------------
    # Crash watcher (live detection while MC is running)
    # ------------------------------------------------------------------

    def _start_crash_watcher(self, game_dir: Path):
        """Start watching for new crash reports."""
        if self._crash_watcher is not None and self._crash_watcher.isRunning():
            return
        self._crash_watcher = CrashWatcherThread(game_dir, self)
        self._crash_watcher.crash_detected.connect(self._on_crash_detected)
        self._crash_watcher.start()
        self._log("Crash watcher started.")

    def _on_crash_detected(self, crash_path: str):
        """Handle a newly detected crash report."""
        self._log(f"Crash detected: {crash_path}")

        # Restore from tray so the user sees the dialog
        self._restore_from_tray()

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Minecraft Crashed")
        dialog.setIcon(QMessageBox.Warning)
        dialog.setText("Minecraft crashed!")
        dialog.setInformativeText(
            f"A new crash report was found:\n{Path(crash_path).name}\n\n"
            "Would you like to send the crash report to the TZP team?"
        )
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dialog.setDefaultButton(QMessageBox.Yes)

        if dialog.exec() == QMessageBox.Yes:
            self._log("Uploading crash report...")
            game_dir = Path(self.settings.get("game_dir", str(DEFAULT_GAME_DIR)))
            session_token = self.settings.get("session_token", "") or None
            self._crash_upload_worker = CrashReportWorker(
                game_dir, session_token, self._device_id, self
            )
            self._crash_upload_worker.finished.connect(self._crash_report_finished)
            self._crash_upload_worker.start()
        else:
            self._log("User declined to send crash report.")

    # ------------------------------------------------------------------
    # Play
    # ------------------------------------------------------------------

    def _confirm_sync(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Sync TZP Pack")
        dialog.setIcon(QMessageBox.Question)
        dialog.setText("Download or update the latest TZP pack files now?")
        dialog.setInformativeText(
            "This will sync mods, configs, and KubeJS files into your separate TZP game directory."
        )
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        dialog.setDefaultButton(QMessageBox.Yes)
        return dialog.exec() == QMessageBox.Yes

    def _on_play(self):
        if self._update_running:
            return

        if not self._pack_ready:
            if not self._confirm_sync():
                self._log("User cancelled pack sync.")
                self.home_page.progress_label.setText("Sync cancelled.")
                self.home_page.progress_label.setStyleSheet("color: #737373; font-size: 12px;")
                return
            self._start_update()
            return

        # Use instance-specific game directory
        base_dir = Path(self.settings["game_dir"])
        version_key = self.home_page.version_combo.currentText()
        version_info = VERSIONS.get(version_key, VERSIONS[DEFAULT_VERSION_KEY])
        instance_dir = version_info.get("instance_dir", "")
        game_dir = base_dir / "instances" / instance_dir if instance_dir else base_dir
        java_path = self.settings.get("java_path", "") or None

        # Ensure profile is up to date with current settings
        ram = self.settings.get("ram", DEFAULT_RAM)
        ensure_profile(game_dir, java_path, ram)

        # Try to launch the Minecraft launcher
        if open_minecraft_launcher():
            self._log("Launched Minecraft launcher — select the 'TZP' profile and play.")
            self.home_page.progress_label.setText("Minecraft launcher opened — select TZP profile.")

            # Start crash watcher
            self._start_crash_watcher(game_dir)

            # Minimize to tray after launch
            QTimer.singleShot(1500, self._minimize_to_tray)
        else:
            # Fallback: open the game folder
            self._log("Minecraft launcher not found. Opening game folder.")
            self.home_page.progress_label.setText("Open Minecraft manually and select the TZP profile.")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(game_dir)))

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self):
        self._log("Opening settings dialog.")
        dialog = SettingsDialog(self.settings, self)
        dialog.exec()

    def closeEvent(self, event):
        # Minimize to tray unless user chose Quit from tray menu
        if not self._really_quit and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self._minimize_to_tray()
            return

        # Stop crash watcher if running
        if self._crash_watcher is not None and self._crash_watcher.isRunning():
            self._crash_watcher.stop()
            self._crash_watcher.wait(3000)

        for name in (
            "_status_worker",
            "_update_worker",
            "_update_check_worker",
            "_crash_worker",
            "_crash_upload_worker",
            "_claim_worker",
            "_modpack_info_worker",
        ):
            worker = getattr(self, name, None)
            if isinstance(worker, QThread) and worker.isRunning():
                worker.requestInterruption()
                worker.wait(2000)

        # Hide tray icon
        if hasattr(self, "_tray"):
            self._tray.hide()

        super().closeEvent(event)



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _exception_hook(exc_type, exc, tb):
    trace = "".join(traceback.format_exception(exc_type, exc, tb))
    enqueue_crash(
        {
            "type": "launcher_exception",
            "timestamp": _now_iso(),
            "message": str(exc),
            "traceback": trace,
            "launcher_version": APP_VERSION,
        }
    )
    sys.__excepthook__(exc_type, exc, tb)


def main():
    sys.excepthook = _exception_hook
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
