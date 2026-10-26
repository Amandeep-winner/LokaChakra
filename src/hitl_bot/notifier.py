from typing import Optional, Union, Dict, Any
import structlog
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.config import settings
from src.contracts.schema import HITLEvidenceCard
from src.db.postgres import HITLEvidenceCardModel

logger = structlog.get_logger(__name__)


def build_hitl_inline_keyboard(thread_id: str, card_id: str) -> InlineKeyboardMarkup:
    """
    Builds the 3-button HITL decision keyboard:
    - [ ✅ Confirm & Lock ] -> hitl:approve:<thread_id>:<card_id>
    - [ ❌ Reject Match ]   -> hitl:reject:<thread_id>:<card_id>
    - [ 🤔 Snooze ]         -> hitl:snooze:<thread_id>:<card_id>
    """
    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Confirm & Lock",
                callback_data=f"hitl:approve:{thread_id}:{card_id}",
            ),
            InlineKeyboardButton(
                text="❌ Reject Match",
                callback_data=f"hitl:reject:{thread_id}:{card_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🤔 Snooze",
                callback_data=f"hitl:snooze:{thread_id}:{card_id}",
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_hitl_card_html(card: Union[HITLEvidenceCard, HITLEvidenceCardModel, Dict[str, Any]]) -> str:
    """
    Formats an evidence card into a rich HTML alert for Telegram.
    """
    if isinstance(card, dict):
        action_type = card.get("action_type", "HIDDEN_BRIDGE_DISCOVERY")
        subj_a = card.get("subject_a_name", "Unknown")
        subj_b = card.get("subject_b_name", "Unknown")
        rel = card.get("proposed_relation", "CONNECTED_TO")
        confidence = float(card.get("confidence_score", 0.0))
        evidence = card.get("evidence_summary", "")
        sources = card.get("source_urls", [])
    else:
        action_type = getattr(card, "action_type", "HIDDEN_BRIDGE_DISCOVERY")
        subj_a = getattr(card, "subject_a_name", "Unknown")
        subj_b = getattr(card, "subject_b_name", "Unknown")
        rel = getattr(card, "proposed_relation", "CONNECTED_TO")
        confidence = float(getattr(card, "confidence_score", 0.0))
        evidence = getattr(card, "evidence_summary", "")
        sources = getattr(card, "source_urls", [])

    conf_pct = int(confidence * 100)
    sources_str = "\n".join([f"• <a href='{u}'>{u[:50]}...</a>" if len(u) > 50 else f"• <a href='{u}'>{u}</a>" for u in sources[:3]])
    sources_block = f"\n\n<b>Sources:</b>\n{sources_str}" if sources_str else ""

    return (
        f"🔍 <b>HITL Verification: {action_type}</b>\n\n"
        f"<b>Subject A:</b> {subj_a}\n"
        f"<b>Subject B:</b> {subj_b}\n"
        f"<b>Proposed Edge:</b> <code>{rel}</code>\n"
        f"<b>Confidence:</b> {conf_pct}%\n\n"
        f"<b>Evidence:</b>\n<i>\"{evidence}\"</i>"
        f"{sources_block}"
    )


async def send_hitl_card(
    card: Union[HITLEvidenceCard, HITLEvidenceCardModel, Dict[str, Any]],
    bot: Optional[Bot] = None,
) -> bool:
    """
    Sends the formatted evidence card and inline keyboard to the authorized Telegram user.
    Returns True if sent successfully, False otherwise.
    """
    if isinstance(card, dict):
        thread_id = card.get("langgraph_thread_id") or card.get("thread_id", "")
        card_id = str(card.get("card_id", ""))
    else:
        thread_id = getattr(card, "langgraph_thread_id", "")
        card_id = str(getattr(card, "card_id", ""))

    keyboard = build_hitl_inline_keyboard(thread_id=thread_id, card_id=card_id)
    html_text = format_hitl_card_html(card)

    user_id = settings.TELEGRAM_ALLOWED_USER_ID
    if not user_id:
        logger.info("TELEGRAM_ALLOWED_USER_ID not configured; notification logged locally", card_id=card_id)
        return False

    owns_bot = False
    active_bot = bot
    if active_bot is None:
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.info("TELEGRAM_BOT_TOKEN not configured; skipping Telegram send", card_id=card_id)
            return False
        active_bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        owns_bot = True

    try:
        await active_bot.send_message(
            chat_id=user_id,
            text=html_text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        logger.info("Sent HITL card via Telegram", card_id=card_id, user_id=user_id)
        return True
    except Exception as exc:
        logger.error("Failed to send HITL card to Telegram", card_id=card_id, error=str(exc))
        return False
    finally:
        if owns_bot and active_bot:
            await active_bot.session.close()
