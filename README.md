# TZP Launcher

TZP Launcher installs and updates the TZP modpack into its own game directory so it does not touch this repo.

## Support Model

- Windows: official installer release
- macOS: development-only via the universal Python package
- Linux: development-only via the universal Python package

## Default Storage Paths

- Windows game files: `%APPDATA%/.tzp-minecraft`
- Windows launcher settings: `%APPDATA%/TZP Launcher/launcher_settings.json`
- macOS game files: `~/Library/Application Support/TZP Launcher/game`
- macOS launcher settings: `~/Library/Application Support/TZP Launcher/launcher_settings.json`
- Linux game files: `~/.tzp-minecraft`
- Linux launcher settings: `~/.tzp-launcher/launcher_settings.json`

## Universal Python Package

The universal package is for macOS, Linux, and development testing.

Requirements:

- Python 3.11+
- Java 21

Run steps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 launch.py
```

The launcher will download mods, configs, and NeoForge into the game directory above, not into the repo.
