"""WARLORD — Anno 1300.  Run:  python main.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from warlord.core.app import main  # noqa: E402

if __name__ == "__main__":
    main()
