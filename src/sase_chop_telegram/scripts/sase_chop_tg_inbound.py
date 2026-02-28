"""Inbound chop entry point: poll Telegram for user actions."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from sase_chop_telegram import pending_actions, telegram_client
from sase_chop_telegram.callback_data import decode
from sase_chop_telegram.inbound import (
    ResponseAction,
    clear_awaiting_feedback,
    get_last_offset,
    process_callback,
    process_callback_twostep,
    process_text_message,
    save_awaiting_feedback,
    save_offset,
)


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
    parser.add_argument(
        "--context",
        default=None,
        help="Optional context string for lumberjack compatibility",
    )
    return parser.parse_args(argv)


def _write_response(response: ResponseAction) -> None:
    """Write a response JSON file to disk."""
    response.response_path.parent.mkdir(parents=True, exist_ok=True)
    response.response_path.write_text(json.dumps(response.response_data, indent=2))


def _handle_callback(
    callback_query: Any, pending: dict[str, Any]
) -> None:
    """Handle an inline keyboard button press."""
    data_str: str = callback_query.data

    # Check two-step first (feedback/custom -> save awaiting state)
    twostep = process_callback_twostep(data_str, pending)
    if twostep is not None:
        prefix, action_info = twostep
        save_awaiting_feedback(prefix, action_info)
        telegram_client.answer_callback_query(
            callback_query.id, "Send your feedback as a text message"
        )
        action = pending.get(prefix)
        if action:
            telegram_client.edit_message_reply_markup(
                action["chat_id"], action["message_id"], reply_markup=None
            )
        return

    # Regular one-shot callback
    response = process_callback(data_str, pending)

    if response is None:
        # Unknown or already-handled callback
        try:
            decode(data_str)
        except ValueError:
            telegram_client.answer_callback_query(
                callback_query.id, "Invalid callback"
            )
            return
        telegram_client.answer_callback_query(
            callback_query.id, "This action has already been handled"
        )
        return

    # Check if the response directory still exists (expired request)
    if not response.response_path.parent.exists():
        telegram_client.answer_callback_query(
            callback_query.id, "This request has expired"
        )
        pending_actions.remove(response.notif_id_prefix)
        return

    _write_response(response)
    telegram_client.answer_callback_query(callback_query.id, response.answer_text)

    action = pending.get(response.notif_id_prefix)
    if action:
        telegram_client.edit_message_reply_markup(
            action["chat_id"], action["message_id"], reply_markup=None
        )

    pending_actions.remove(response.notif_id_prefix)


def _handle_text_message(text: str) -> None:
    """Handle a text message (two-step feedback completion)."""
    response = process_text_message(text)
    if response is None:
        return

    _write_response(response)
    clear_awaiting_feedback()
    pending_actions.remove(response.notif_id_prefix)


def main(argv: list[str] | None = None) -> int:
    """Inbound Telegram chop entry point."""
    _parse_args(argv)

    # Clean up stale pending actions
    pending_actions.cleanup_stale()

    pending = pending_actions.list_all()
    offset = get_last_offset()
    updates = telegram_client.get_updates(offset=offset, timeout=0)

    if not updates:
        return 0

    for update in updates:
        if update.callback_query:
            _handle_callback(update.callback_query, pending)
        elif update.message and update.message.text:
            _handle_text_message(update.message.text)

    last_update_id = max(u.update_id for u in updates)
    save_offset(last_update_id + 1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
