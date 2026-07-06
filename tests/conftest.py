import sys
from pathlib import Path

# Make the project root importable so tests can `from scraper.parsers ...`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
