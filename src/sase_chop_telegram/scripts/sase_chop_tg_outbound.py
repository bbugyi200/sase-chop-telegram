"""Outbound chop entry point: send sase notifications to Telegram."""

from __future__ import annotations

import argparse
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sase_chop_tg_outbound",
        description="Send sase notifications to Telegram",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent without actually sending",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Outbound Telegram chop entry point."""
    args = _parse_args(argv)
    print(f"sase_chop_tg_outbound: dry_run={args.dry_run}")
    print("Outbound Telegram chop not yet implemented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
