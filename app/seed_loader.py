"""
Module wrapper so README command `python -m app.seed_loader` works.
"""

from __future__ import annotations

import asyncio
import sys

from scripts.seed_loader import load_seed, resolve_seed_path


def main() -> None:
    cli_path = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(load_seed(resolve_seed_path(cli_path)))


if __name__ == "__main__":
    main()
