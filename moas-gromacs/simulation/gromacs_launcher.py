"""Thin wrapper around run_md.py. Online adaptive MD starts only after post-hoc gain."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run_check():
    return subprocess.call([sys.executable, str(ROOT / "run_md.py"), "--check", "--system", "cln025_unfolded"])
