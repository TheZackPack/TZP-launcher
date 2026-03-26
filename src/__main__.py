import sys
from pathlib import Path

# Ensure sibling modules (config, launcher, updater, app) are importable
# regardless of whether we're invoked as `python -m src` or `python src/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import main

main()
