"""Create the demo users and patients.

Usage:
  python scripts/seed_demo.py           # only if the database is empty
  python scripts/seed_demo.py --reset   # wipe the database and start fresh
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.seed import DEMO_ACCOUNTS, seed_demo  # noqa: E402

if __name__ == "__main__":
    seed_demo(reset="--reset" in sys.argv)
    print("Demo data ready. Accounts:")
    for username, password, role in DEMO_ACCOUNTS:
        print(f"  {role:8s} {username:10s} / {password}")
