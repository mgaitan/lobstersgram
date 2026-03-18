"""Pytest configuration: set required environment variables before any module import."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow `import main` from tests/ subdirectory
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("TELEGRAPH_ACCESS_TOKEN", "test_token")
