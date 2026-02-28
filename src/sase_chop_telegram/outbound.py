"""Core outbound logic: detect inactivity, load unsent notifications, track sent."""

from __future__ import annotations

import os
import time
from pathlib import Path

from sase.ace.tui_activity import (
    get_tui_inactive_seconds,
    get_tui_last_activity,
    is_tui_running,
)
from sase.notifications.models import Notification
from sase.notifications.store import load_notifications

LAST_SENT_FILE = Path.home() / ".sase" / "telegram" / "last_sent_ts"
INACTIVE_THRESHOLD_VAR = "SASE_TELEGRAM_INACTIVE_SECONDS"
DEFAULT_INACTIVE_THRESHOLD = 600


def should_send() -> bool:
    """Return True if user has been inactive long enough to warrant sending.

    Uses the inactivity threshold regardless of whether the TUI is running.
    When the TUI quits it writes the current time as the last activity
    timestamp, so the inactivity clock restarts from that point.
    """
    inactive = get_tui_inactive_seconds()
    if inactive is None:
        return False
    threshold = _get_inactive_threshold()
    return inactive >= threshold


def _get_inactive_threshold() -> int:
    """Return the inactivity threshold in seconds.

    Checks (in order): env var, sase config ``ace.inactive_seconds``, default.
    """
    env_val = os.environ.get(INACTIVE_THRESHOLD_VAR)
    if env_val is not None:
        return int(env_val)

    try:
        from sase.config import load_merged_config

        cfg = load_merged_config()
        ace_cfg = cfg.get("ace", {})
        if isinstance(ace_cfg, dict) and "inactive_seconds" in ace_cfg:
            return int(ace_cfg["inactive_seconds"])
    except Exception:
        pass

    return DEFAULT_INACTIVE_THRESHOLD


def get_unsent_notifications() -> list[Notification]:
    """Return notifications that haven't been sent to Telegram yet.

    Uses a high-water mark timestamp file to track what's already been sent.
    On first run (no file), initializes the file to now and returns empty
    to avoid dumping backlog.
    """
    if not LAST_SENT_FILE.exists():
        # First run — initialize high-water mark, don't dump backlog
        _write_high_water_mark(time.time())
        return []

    last_sent_ts = float(LAST_SENT_FILE.read_text().strip())

    # When the TUI is not running, advance the high-water mark to the TUI
    # quit time (recorded as the last activity timestamp) so notifications
    # received while the TUI was active are not re-sent via Telegram.
    if not is_tui_running():
        quit_ts = get_tui_last_activity()
        if quit_ts is not None and quit_ts > last_sent_ts:
            last_sent_ts = quit_ts
            _write_high_water_mark(quit_ts)

    all_notifs = load_notifications()
    unsent = []
    for n in all_notifs:
        if n.read or n.dismissed:
            continue
        from datetime import datetime

        try:
            ts = datetime.fromisoformat(n.timestamp).timestamp()
        except ValueError:
            continue
        if ts > last_sent_ts:
            unsent.append(n)
    return unsent


def mark_sent(notifications: list[Notification]) -> None:
    """Update the high-water mark to the latest notification timestamp."""
    if not notifications:
        return
    from datetime import datetime

    latest = max(datetime.fromisoformat(n.timestamp).timestamp() for n in notifications)
    _write_high_water_mark(latest)


def _write_high_water_mark(ts: float) -> None:
    """Write a timestamp to the high-water mark file."""
    LAST_SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_SENT_FILE.write_text(str(ts))
