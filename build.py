"""Build script for TZP Launcher -- creates a standalone executable via PyInstaller."""

import PyInstaller.__main__

PyInstaller.__main__.run([
    "src/app.py",
    "--name=TZP-Launcher",
    "--onefile",
    "--windowed",
    "--add-data=src:src",
])
