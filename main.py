#!/usr/bin/env python3
"""Backward-compatible entry point.  Use ``uv run lobstergram`` instead."""

from lobstergram.main import main

if __name__ == "__main__":
    raise SystemExit(main())
