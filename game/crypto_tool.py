#!/usr/bin/env python3
"""Author-side tool for the encrypted answers file.

  gen-key             print a fresh Fernet key (store as the GAME_KEY secret)
  encrypt             answers.json -> answers.enc   (needs GAME_KEY env)
  decrypt             answers.enc -> stdout         (needs GAME_KEY env)

answers.json is gitignored; only answers.enc is committed.
"""

import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

GAME_DIR = Path(__file__).resolve().parent


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "gen-key":
        print(Fernet.generate_key().decode())
        return
    key = os.environ.get("GAME_KEY")
    if not key:
        sys.exit("GAME_KEY env var required")
    f = Fernet(key.encode())
    if cmd == "encrypt":
        raw = (GAME_DIR / "answers.json").read_bytes()
        json.loads(raw)  # fail fast on malformed JSON
        (GAME_DIR / "answers.enc").write_bytes(f.encrypt(raw))
        print("wrote answers.enc")
    elif cmd == "decrypt":
        print(f.decrypt((GAME_DIR / "answers.enc").read_bytes()).decode())
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
