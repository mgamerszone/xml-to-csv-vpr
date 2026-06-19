#!/usr/bin/env python3
"""Backward-compatible wrapper for the VPR supplier sync."""

import os
import sys

import sync


def main():
    if os.environ.get("FEED_URL") and not os.environ.get("VPR_FEED_URL"):
        os.environ["VPR_FEED_URL"] = os.environ["FEED_URL"]

    argv = [sys.argv[0], "--supplier", "vpr"]
    if os.environ.get("BASELINKER_DRY_RUN") in sync.TRUTHY:
        argv.append("--dry-run")
    sys.argv = argv
    sync.main()


if __name__ == "__main__":
    main()
