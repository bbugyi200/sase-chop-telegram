"""Inbound chop entry point: poll Telegram for user actions."""

from __future__ import annotations

import argparse
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sase_chop_tg_inbound",
        description="Poll Telegram for user action responses",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process pending updates once and exit (no long-polling)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Inbound Telegram chop entry point."""
    args = _parse_args(argv)
    print(f"sase_chop_tg_inbound: once={args.once}")
    print("Inbound Telegram chop not yet implemented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
