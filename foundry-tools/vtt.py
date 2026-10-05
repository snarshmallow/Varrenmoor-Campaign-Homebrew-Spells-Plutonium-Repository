"""Entry point: python foundry-tools/vtt.py <command> ...   (see README.md)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vtt.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
