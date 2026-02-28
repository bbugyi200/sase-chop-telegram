"""Sync wrapper around the async python-telegram-bot library."""

from __future__ import annotations

import asyncio
from typing import Any

from telegram import Bot, InlineKeyboardMarkup, Message, Update

from sase_chop_telegram.credentials import get_bot_token


def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _get_bot() -> Bot:
    """Create a Bot instance with the stored token."""
    return Bot(token=get_bot_token())


def send_message(
    chat_id: str,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    """Send a text message to a Telegram chat."""
    bot = _get_bot()
    return _run_async(
        bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    )


def send_document(
    chat_id: str,
    document: str | bytes,
    caption: str | None = None,
) -> Message:
    """Send a document to a Telegram chat."""
    bot = _get_bot()
    return _run_async(
        bot.send_document(chat_id=chat_id, document=document, caption=caption)
    )


def get_updates(offset: int | None = None, timeout: int = 0) -> list[Update]:
    """Fetch updates (new messages/callbacks) from the Telegram API."""
    bot = _get_bot()
    return _run_async(bot.get_updates(offset=offset, timeout=timeout))


def answer_callback_query(callback_query_id: str, text: str | None = None) -> bool:
    """Answer a callback query from an inline keyboard button press."""
    bot = _get_bot()
    return _run_async(
        bot.answer_callback_query(callback_query_id=callback_query_id, text=text)
    )


def edit_message_reply_markup(
    chat_id: str,
    message_id: int,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message | bool:
    """Edit the reply markup of an existing message."""
    bot = _get_bot()
    return _run_async(
        bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=reply_markup
        )
    )
