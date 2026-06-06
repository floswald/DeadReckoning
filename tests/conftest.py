import sys
from pathlib import Path

# Allow tests to import test-local modules like fixture_generator
sys.path.insert(0, str(Path(__file__).parent))
