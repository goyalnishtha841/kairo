"""Load KEY=VALUE pairs from the repo's .env into os.environ (no extra dependency). Real env vars win."""
import os
from pathlib import Path

_ENV = Path(__file__).resolve().parents[1] / ".env"


def load_env():
    if not _ENV.exists():
        return
    for line in _ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if v.strip():
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
