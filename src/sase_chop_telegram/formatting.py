"""Message formatting and MarkdownV2 escaping for Telegram notifications."""

from __future__ import annotations

import json
import re
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from sase.notifications.models import Notification

from sase_chop_telegram import callback_data

# Telegram message limit
MAX_MESSAGE_LENGTH = 4096
# Truncation threshold for plan content
PLAN_TRUNCATION_THRESHOLD = 3000

# Truncation threshold for notes content in non-plan messages
NOTES_TRUNCATION_THRESHOLD = 3500

# Characters that must be escaped in MarkdownV2
_MARKDOWN_V2_SPECIAL = r"_*[]()~`>#+-=|{}.!"


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2 format."""
    return re.sub(r"([" + re.escape(_MARKDOWN_V2_SPECIAL) + r"])", r"\\\1", text)


def _truncate_notes(notes: list[str], threshold: int = NOTES_TRUNCATION_THRESHOLD) -> str:
    """Join notes and truncate if exceeding threshold."""
    text = "\n".join(notes)
    if len(text) > threshold:
        text = text[:threshold] + "\n\n... (see TUI for full output)"
    return text


def format_notification(
    notification: Notification,
) -> tuple[str, InlineKeyboardMarkup | None, list[str]]:
    """Format a notification for Telegram.

    Returns (message_text, keyboard_or_None, attachment_file_paths).
    """
    match notification.action:
        case "PlanApproval":
            return _format_plan_approval(notification)
        case "HITL":
            return _format_hitl(notification)
        case "UserQuestion":
            return _format_user_question(notification)
        case _:
            # Dispatch by sender for non-action notifications
            if notification.sender == "axe" and notification.files:
                return _format_error_digest(notification)
            if notification.sender in (
                "crs",
                "fix-hook",
                "query",
                "run-agent",
                "user-agent",
                "user-workflow",
            ):
                return _format_workflow_complete(notification)
            return _format_generic(notification)


def _notif_prefix(n: Notification) -> str:
    """First 8 chars of notification ID, used in callback data."""
    return n.id[:8]


def _format_plan_approval(
    n: Notification,
) -> tuple[str, InlineKeyboardMarkup | None, list[str]]:
    prefix = _notif_prefix(n)
    notes_text = escape_markdown_v2(_truncate_notes(n.notes))
    attachments: list[str] = []

    plan_content = ""
    if n.files:
        plan_file = n.files[0]
        try:
            plan_content = Path(plan_file).read_text()
        except OSError:
            plan_content = ""

    if plan_content and len(plan_content) <= PLAN_TRUNCATION_THRESHOLD:
        escaped_plan = escape_markdown_v2(plan_content)
        text = f"📋 *Plan Review*\n\n{notes_text}\n\n```\n{escaped_plan}\n```"
    elif plan_content:
        truncated = escape_markdown_v2(
            plan_content[:PLAN_TRUNCATION_THRESHOLD] + "\n\n... (truncated)"
        )
        text = f"📋 *Plan Review*\n\n{notes_text}\n\n```\n{truncated}\n```"
        if n.files:
            attachments.append(n.files[0])
    else:
        text = f"📋 *Plan Review*\n\n{notes_text}"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=callback_data.encode("plan", prefix, "approve"),
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=callback_data.encode("plan", prefix, "reject"),
                ),
            ]
        ]
    )
    return text, keyboard, attachments


def _format_hitl(n: Notification) -> tuple[str, InlineKeyboardMarkup | None, list[str]]:
    prefix = _notif_prefix(n)
    notes_text = escape_markdown_v2(_truncate_notes(n.notes))
    text = f"🔧 *HITL Request*\n\n{notes_text}"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Accept",
                    callback_data=callback_data.encode("hitl", prefix, "accept"),
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=callback_data.encode("hitl", prefix, "reject"),
                ),
                InlineKeyboardButton(
                    "💬 Feedback",
                    callback_data=callback_data.encode("hitl", prefix, "feedback"),
                ),
            ]
        ]
    )
    return text, keyboard, []


def _format_user_question(
    n: Notification,
) -> tuple[str, InlineKeyboardMarkup | None, list[str]]:
    prefix = _notif_prefix(n)
    notes_text = escape_markdown_v2(_truncate_notes(n.notes))
    text = f"❓ *Question*\n\n{notes_text}"

    # Try to load question options from request file
    response_dir = n.action_data.get("response_dir", "")
    buttons: list[list[InlineKeyboardButton]] = []
    if response_dir:
        request_file = Path(response_dir) / "question_request.json"
        try:
            request_data = json.loads(request_file.read_text())
            questions = request_data.get("questions", [])
            if questions:
                # Use first question's options
                options = questions[0].get("options", [])
                for i, opt in enumerate(options):
                    label = opt.get("label", f"Option {i + 1}")
                    buttons.append(
                        [
                            InlineKeyboardButton(
                                label,
                                callback_data=callback_data.encode(
                                    "question", prefix, str(i)
                                ),
                            )
                        ]
                    )
        except (OSError, json.JSONDecodeError):
            pass

    # Always add a Custom button
    buttons.append(
        [
            InlineKeyboardButton(
                "💬 Custom",
                callback_data=callback_data.encode("question", prefix, "custom"),
            )
        ]
    )

    keyboard = InlineKeyboardMarkup(buttons)
    return text, keyboard, []


def _format_workflow_complete(
    n: Notification,
) -> tuple[str, InlineKeyboardMarkup | None, list[str]]:
    notes_text = escape_markdown_v2(_truncate_notes(n.notes))
    agent_name = n.action_data.get("agent_name")
    if agent_name:
        escaped_name = escape_markdown_v2(agent_name)
        text = f"✅ *Workflow Complete* \\[{escaped_name}\\]\n\n{notes_text}"
    else:
        text = f"✅ *Workflow Complete*\n\n{notes_text}"
    attachments = [
        str(p) for f in n.files if (p := Path(f).expanduser()).exists()
    ]
    return text, None, attachments


def _format_error_digest(
    n: Notification,
) -> tuple[str, InlineKeyboardMarkup | None, list[str]]:
    notes_text = escape_markdown_v2(_truncate_notes(n.notes))
    text = f"⚠️ *Error Digest*\n\n{notes_text}"
    attachments = [f for f in n.files if Path(f).exists()]
    return text, None, attachments


def _format_generic(
    n: Notification,
) -> tuple[str, InlineKeyboardMarkup | None, list[str]]:
    sender = escape_markdown_v2(n.sender)
    notes_text = escape_markdown_v2(_truncate_notes(n.notes))
    text = f"🔔 *{sender}*\n\n{notes_text}"
    return text, None, []
