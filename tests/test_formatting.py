"""Tests for message formatting."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from sase.notifications.models import Notification
from sase_chop_telegram.formatting import (
    NOTES_TRUNCATION_THRESHOLD,
    PLAN_TRUNCATION_THRESHOLD,
    escape_markdown_v2,
    format_notification,
)


def _make_notification(
    action: str | None = None,
    sender: str = "test",
    notes: list[str] | None = None,
    files: list[str] | None = None,
    action_data: dict[str, str] | None = None,
) -> Notification:
    return Notification(
        id="abcd1234-0000-0000-0000-000000000000",
        timestamp="2025-06-01T12:00:00+00:00",
        sender=sender,
        notes=notes or ["Test notification"],
        files=files or [],
        action=action,
        action_data=action_data or {},
    )


class TestEscapeMarkdownV2:
    def test_escapes_all_special_chars(self):
        text = "Hello_World *bold* [link](url) ~strike~ `code` >quote #h +p -m =e |p {b} .d !e"
        result = escape_markdown_v2(text)
        for char in r"_*[]()~`>#+-=|{}.!":
            assert f"\\{char}" in result

    def test_plain_text_unchanged(self):
        assert escape_markdown_v2("hello world") == "hello world"

    def test_empty_string(self):
        assert escape_markdown_v2("") == ""


class TestFormatPlanApproval:
    def test_with_short_plan(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("Short plan content")
            plan_file = f.name

        n = _make_notification(
            action="PlanApproval",
            sender="plan",
            notes=["Plan ready for review: test.md"],
            files=[plan_file],
            action_data={"response_dir": "/tmp/test", "session_id": "s1"},
        )
        text, keyboard, attachments = format_notification(n)

        assert "Plan Review" in text
        assert "Short plan content" in text
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 2  # Approve + Reject
        assert "Approve" in keyboard.inline_keyboard[0][0].text
        assert "Reject" in keyboard.inline_keyboard[0][1].text
        assert attachments == []

        Path(plan_file).unlink()

    def test_with_large_plan(self):
        large_content = "x" * (PLAN_TRUNCATION_THRESHOLD + 500)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(large_content)
            plan_file = f.name

        n = _make_notification(
            action="PlanApproval",
            sender="plan",
            notes=["Plan ready for review: big.md"],
            files=[plan_file],
        )
        text, keyboard, attachments = format_notification(n)

        assert "truncated" in text
        assert plan_file in attachments
        assert keyboard is not None

        Path(plan_file).unlink()

    def test_missing_plan_file(self):
        n = _make_notification(
            action="PlanApproval",
            sender="plan",
            notes=["Plan ready for review"],
            files=["/nonexistent/plan.md"],
        )
        text, keyboard, _ = format_notification(n)
        assert "Plan Review" in text
        assert keyboard is not None


class TestFormatHITL:
    def test_format_and_keyboard(self):
        n = _make_notification(
            action="HITL",
            sender="hitl",
            notes=["HITL waiting: step 'review' in my-workflow"],
        )
        text, keyboard, attachments = format_notification(n)

        assert "HITL Request" in text
        assert "review" in text
        assert keyboard is not None
        buttons = keyboard.inline_keyboard
        assert len(buttons) == 1
        assert len(buttons[0]) == 3  # Accept + Reject + Feedback
        assert "Accept" in buttons[0][0].text
        assert "Reject" in buttons[0][1].text
        assert "Feedback" in buttons[0][2].text
        assert attachments == []


class TestFormatUserQuestion:
    def test_with_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            request_file = Path(tmpdir) / "question_request.json"
            request_data = {
                "questions": [
                    {
                        "question": "Which DB?",
                        "options": [
                            {"label": "PostgreSQL"},
                            {"label": "SQLite"},
                        ],
                    }
                ]
            }
            request_file.write_text(json.dumps(request_data))

            n = _make_notification(
                action="UserQuestion",
                sender="question",
                notes=["Claude is asking a question"],
                action_data={"response_dir": tmpdir, "session_id": "s1"},
            )
            text, keyboard, attachments = format_notification(n)

        assert "Question" in text
        assert keyboard is not None
        buttons = keyboard.inline_keyboard
        # 2 option buttons + 1 Custom button
        assert len(buttons) == 3
        assert "PostgreSQL" in buttons[0][0].text
        assert "SQLite" in buttons[1][0].text
        assert "Custom" in buttons[2][0].text
        assert attachments == []

    def test_without_request_file(self):
        n = _make_notification(
            action="UserQuestion",
            sender="question",
            notes=["Claude is asking a question"],
            action_data={"response_dir": "/nonexistent", "session_id": "s1"},
        )
        text, keyboard, _ = format_notification(n)
        assert "Question" in text
        assert keyboard is not None
        # Only Custom button when request file is missing
        assert len(keyboard.inline_keyboard) == 1
        assert "Custom" in keyboard.inline_keyboard[0][0].text


class TestFormatWorkflowComplete:
    def test_no_keyboard(self):
        n = _make_notification(
            sender="crs",
            notes=["Workflow completed successfully"],
        )
        text, keyboard, attachments = format_notification(n)

        assert "Workflow Complete" in text
        assert keyboard is None
        assert attachments == []


class TestFormatErrorDigest:
    def test_with_digest_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Error details here")
            digest_file = f.name

        n = _make_notification(
            sender="axe",
            notes=["3 error(s) in the last hour"],
            files=[digest_file],
        )
        text, keyboard, attachments = format_notification(n)

        assert "Error Digest" in text
        assert keyboard is None
        assert digest_file in attachments

        Path(digest_file).unlink()

    def test_missing_digest_file(self):
        n = _make_notification(
            sender="axe",
            notes=["2 error(s) in the last hour"],
            files=["/nonexistent/digest.txt"],
        )
        text, keyboard, attachments = format_notification(n)

        assert "Error Digest" in text
        assert attachments == []


class TestFormatGeneric:
    def test_fallback_format(self):
        n = _make_notification(
            sender="unknown-sender",
            notes=["Something happened"],
        )
        text, keyboard, attachments = format_notification(n)

        assert "unknown\\-sender" in text
        assert "Something happened" in text
        assert keyboard is None
        assert attachments == []


class TestNoteTruncation:
    def test_short_notes_not_truncated(self):
        n = _make_notification(
            action="HITL",
            sender="hitl",
            notes=["Short HITL output"],
        )
        text, _, _ = format_notification(n)
        assert "see TUI for full output" not in text

    def test_long_hitl_notes_truncated(self):
        long_note = "x" * (NOTES_TRUNCATION_THRESHOLD + 500)
        n = _make_notification(
            action="HITL",
            sender="hitl",
            notes=[long_note],
        )
        text, _, _ = format_notification(n)
        assert "see TUI for full output" in text

    def test_long_generic_notes_truncated(self):
        long_note = "y" * (NOTES_TRUNCATION_THRESHOLD + 100)
        n = _make_notification(
            sender="unknown",
            notes=[long_note],
        )
        text, _, _ = format_notification(n)
        assert "see TUI for full output" in text

    def test_long_error_digest_notes_truncated(self):
        long_note = "z" * (NOTES_TRUNCATION_THRESHOLD + 100)
        n = _make_notification(
            sender="axe",
            notes=[long_note],
            files=["/nonexistent/digest.txt"],
        )
        text, _, _ = format_notification(n)
        assert "see TUI for full output" in text
