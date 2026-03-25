"""Build script for TZP Launcher -- creates a standalone executable via PyInstaller."""

import os
import platform
from pathlib import Path

import PyInstaller.__main__

REPO_ROOT = Path(__file__).resolve().parent
PYI_CONFIG_DIR = REPO_ROOT / ".pyinstaller"
PYI_CONFIG_DIR.mkdir(exist_ok=True)
os.environ.setdefault("PYINSTALLER_CONFIG_DIR", str(PYI_CONFIG_DIR))

args = [
    "src/app.py",
    "--name=TZP-Launcher",
    "--windowed",
    "--clean",
    "--noconfirm",
    "--paths=src",
]

if platform.system() == "Windows":
    args.append("--onefile")
    args.append("--add-data=src;src")
else:
    args.append("--add-data=src:src")

PyInstaller.__main__.run(args)
