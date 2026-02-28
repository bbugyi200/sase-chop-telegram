"""Tests for outbound logic."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from sase.notifications.models import Notification
from sase_chop_telegram.outbound import (
    INACTIVE_THRESHOLD_VAR,
    get_unsent_notifications,
    mark_sent,
    should_send,
)

LAST_SENT_TEST_FILE = Path("/tmp/test_last_sent_ts")


@pytest.fixture(autouse=True)
def _patch_last_sent_file():
    """Use a temp file for tests."""
    with patch("sase_chop_telegram.outbound.LAST_SENT_FILE", LAST_SENT_TEST_FILE):
        yield
    if LAST_SENT_TEST_FILE.exists():
        LAST_SENT_TEST_FILE.unlink()


def _make_notification(
    id: str = "abcd1234-0000-0000-0000-000000000000",
    timestamp: str | None = None,
    read: bool = False,
    dismissed: bool = False,
) -> Notification:
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat()
    return Notification(
        id=id,
        timestamp=timestamp,
        sender="test",
        notes=["test note"],
        read=read,
        dismissed=dismissed,
    )


class TestShouldSend:
    @patch("sase_chop_telegram.outbound.is_tui_running", return_value=True)
    @patch("sase_chop_telegram.outbound.get_tui_inactive_seconds")
    def test_inactive_above_threshold(self, mock_inactive, _mock_running):
        mock_inactive.return_value = 700.0
        assert should_send() is True

    @patch("sase_chop_telegram.outbound.is_tui_running", return_value=True)
    @patch("sase_chop_telegram.outbound.get_tui_inactive_seconds")
    def test_active_below_threshold(self, mock_inactive, _mock_running):
        mock_inactive.return_value = 300.0
        assert should_send() is False

    @patch("sase_chop_telegram.outbound.is_tui_running", return_value=True)
    @patch("sase_chop_telegram.outbound.get_tui_inactive_seconds")
    def test_none_returns_false(self, mock_inactive, _mock_running):
        mock_inactive.return_value = None
        assert should_send() is False

    @patch("sase_chop_telegram.outbound.is_tui_running", return_value=True)
    @patch("sase_chop_telegram.outbound.get_tui_inactive_seconds")
    def test_custom_threshold_via_env(self, mock_inactive, _mock_running, monkeypatch):
        mock_inactive.return_value = 50.0
        monkeypatch.setenv(INACTIVE_THRESHOLD_VAR, "30")
        assert should_send() is True

    @patch("sase_chop_telegram.outbound.is_tui_running", return_value=True)
    @patch("sase_chop_telegram.outbound.get_tui_inactive_seconds")
    def test_exactly_at_threshold(self, mock_inactive, _mock_running):
        mock_inactive.return_value = 600.0
        assert should_send() is True

    @patch("sase_chop_telegram.outbound.is_tui_running", return_value=False)
    def test_tui_not_running_returns_true(self, _mock_running):
        assert should_send() is True

    @patch("sase_chop_telegram.outbound.is_tui_running", return_value=True)
    @patch("sase_chop_telegram.outbound.get_tui_inactive_seconds")
    def test_tui_running_and_active_returns_false(self, mock_inactive, _mock_running):
        mock_inactive.return_value = 30.0
        assert should_send() is False

    @patch("sase_chop_telegram.outbound.is_tui_running", return_value=True)
    @patch("sase_chop_telegram.outbound.get_tui_inactive_seconds")
    def test_tui_running_and_inactive_returns_true(self, mock_inactive, _mock_running):
        mock_inactive.return_value = 700.0
        assert should_send() is True


class TestGetUnsentNotifications:
    @patch("sase_chop_telegram.outbound.load_notifications")
    def test_no_file_returns_empty_and_initializes(self, mock_load):
        """First run: no last_sent file, returns empty and creates file."""
        assert not LAST_SENT_TEST_FILE.exists()
        result = get_unsent_notifications()
        assert result == []
        assert LAST_SENT_TEST_FILE.exists()
        mock_load.assert_not_called()

    @patch("sase_chop_telegram.outbound.load_notifications")
    def test_filters_correctly(self, mock_load):
        """Only returns unread, undismissed notifications newer than last sent."""
        old_ts = datetime(2024, 1, 1, tzinfo=UTC).isoformat()
        new_ts = datetime(2025, 6, 1, tzinfo=UTC).isoformat()

        # Set last_sent to midpoint
        midpoint = datetime(2025, 1, 1, tzinfo=UTC).timestamp()
        LAST_SENT_TEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_SENT_TEST_FILE.write_text(str(midpoint))

        n_old = _make_notification(
            id="old00000-0000-0000-0000-000000000000", timestamp=old_ts
        )
        n_new = _make_notification(
            id="new00000-0000-0000-0000-000000000000", timestamp=new_ts
        )
        n_read = _make_notification(
            id="read0000-0000-0000-0000-000000000000", timestamp=new_ts, read=True
        )
        n_dismissed = _make_notification(
            id="dism0000-0000-0000-0000-000000000000", timestamp=new_ts, dismissed=True
        )
        mock_load.return_value = [n_old, n_new, n_read, n_dismissed]

        result = get_unsent_notifications()
        assert len(result) == 1
        assert result[0].id == "new00000-0000-0000-0000-000000000000"


class TestMarkSent:
    def test_writes_timestamp(self):
        """Verify high-water mark is written to latest notification timestamp."""
        LAST_SENT_TEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        ts1 = datetime(2025, 6, 1, tzinfo=UTC).isoformat()
        ts2 = datetime(2025, 7, 1, tzinfo=UTC).isoformat()
        n1 = _make_notification(
            id="n1000000-0000-0000-0000-000000000000", timestamp=ts1
        )
        n2 = _make_notification(
            id="n2000000-0000-0000-0000-000000000000", timestamp=ts2
        )

        mark_sent([n1, n2])

        written = float(LAST_SENT_TEST_FILE.read_text().strip())
        expected = datetime.fromisoformat(ts2).timestamp()
        assert written == pytest.approx(expected, abs=1.0)

    def test_empty_list_noop(self):
        """mark_sent with empty list doesn't create the file."""
        mark_sent([])
        assert not LAST_SENT_TEST_FILE.exists()
