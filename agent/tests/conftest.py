"""Put the agent package root on sys.path so the pure modules import directly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
