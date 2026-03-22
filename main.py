#!/usr/bin/env python3
"""Backward-compatible entry point.  Use ``python -m lobstergram`` instead."""

from lobstergram.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
