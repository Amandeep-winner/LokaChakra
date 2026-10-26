"""Telegram Human-In-The-Loop (HITL) Bot and Notification Bus."""

from typing import Any

from src.hitl_bot.notifier import (
    build_hitl_inline_keyboard,
    format_hitl_card_html,
    send_hitl_card,
)

__all__ = [
    "build_hitl_inline_keyboard",
    "format_hitl_card_html",
    "send_hitl_card",
    "router",
    "create_dispatcher",
    "get_osint_app",
    "set_osint_app",
    "is_authorized",
    "start_bot",
]


def __getattr__(name: str) -> Any:
    """Lazily load bot attributes to avoid circular import warnings when executing

    `python -m src.hitl_bot.bot` directly.
    """
    if name in {
        "router",
        "create_dispatcher",
        "get_osint_app",
        "set_osint_app",
        "is_authorized",
        "start_bot",
    }:
        import src.hitl_bot.bot as bot_mod

        return getattr(bot_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
