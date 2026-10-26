import io
from typing import Optional, Any
import structlog
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery
from langgraph.types import Command

from src.config import settings
from src.ingestion.tasks import ingest_voice_task, ingest_text_task

logger = structlog.get_logger(__name__)

router = Router(name="hitl_bot_router")

# Shared compiled OSINT graph app instance
_osint_app: Optional[Any] = None


def get_osint_app():
    global _osint_app
    if _osint_app is None:
        from src.agents.osint_graph import build_osint_graph
        _osint_app = build_osint_graph()
    return _osint_app


def set_osint_app(app: Any) -> None:
    global _osint_app
    _osint_app = app


def is_authorized(user_id: Optional[int]) -> bool:
    """
    Verifies that the incoming message/callback is from the configured allowed user ID.
    If settings.TELEGRAM_ALLOWED_USER_ID is None (e.g. dev/unconfigured), returns False.
    """
    if not settings.TELEGRAM_ALLOWED_USER_ID or not user_id:
        return False
    return user_id == settings.TELEGRAM_ALLOWED_USER_ID


@router.message(F.voice)
async def handle_voice_message(message: Message, bot: Bot) -> None:
    """
    Downloads voice note audio (.ogg), dispatches async Taskiq job,
    and returns immediate confirmation under 300ms.
    """
    if not is_authorized(message.from_user.id if message.from_user else None):
        logger.warning("Unauthorized voice message ignored", user_id=message.from_user.id if message.from_user else None)
        return

    try:
        file_io = io.BytesIO()
        await bot.download(message.voice, destination=file_io)
        audio_bytes = file_io.getvalue()

        # Dispatch async background worker task
        await ingest_voice_task.kiq(
            audio_bytes=audio_bytes,
            message_id=message.message_id,
            filename="telegram_voice.ogg",
        )

        await message.reply("⚡ Logged voice note. Extracting entities & temporal edges...")
    except Exception as exc:
        logger.error("Failed to process voice note in Telegram bot", error=str(exc))
        await message.reply(f"❌ Failed to process voice note: {str(exc)}")


@router.message(F.text)
async def handle_text_message(message: Message) -> None:
    """
    Handles text commands like /path <query> or dispatches raw text notes to ingestion.
    """
    if not is_authorized(message.from_user.id if message.from_user else None):
        logger.warning("Unauthorized text message ignored", user_id=message.from_user.id if message.from_user else None)
        return

    text = message.text.strip() if message.text else ""

    if text.startswith("/path"):
        query = text[5:].strip()
        if not query:
            await message.reply("Usage: <code>/path &lt;Target Name or Company&gt;</code>", parse_mode="HTML")
            return

        try:
            from src.pathfinder.routing import find_warmest_path
            result = await find_warmest_path(target_query=query)
            steps_desc = " ➔ ".join([s.node_name for s in result.steps])
            msg = (
                f"🎯 <b>Warmest Path to '{query}':</b>\n"
                f"<b>Route:</b> {steps_desc}\n"
                f"<b>Total Cost:</b> {result.total_cost:.2f} ({result.hop_count} hops)\n\n"
                f"<b>Recommended Intro Script:</b>\n<i>\"{result.recommended_intro_script}\"</i>"
            )
            await message.reply(msg, parse_mode="HTML")
        except ImportError:
            await message.reply(f"⚡ Pathfinder query queued for '{query}'. Pathfinding engine initializing in Phase 7.")
        except Exception as exc:
            logger.error("Pathfinder execution failed", query=query, error=str(exc))
            await message.reply(f"❌ Pathfinder search failed: {str(exc)}")
        return

    # Standard text note ingestion
    try:
        await ingest_text_task.kiq(raw_text=text, source_type="telegram_text")
        await message.reply("⚡ Logged text note. Extracting entities & temporal edges...")
    except Exception as exc:
        logger.error("Failed to dispatch text ingestion task", error=str(exc))
        await message.reply(f"❌ Failed to log text note: {str(exc)}")


@router.callback_query(F.data.startswith("hitl:"))
async def handle_hitl_callback(callback: CallbackQuery) -> None:
    """
    Handles inline keyboard callbacks from evidence cards:
    - hitl:approve:<thread_id>:<card_id>
    - hitl:reject:<thread_id>:<card_id>
    - hitl:snooze:<thread_id>:<card_id>
    Resumes the LangGraph interrupt and updates message status.
    """
    if not is_authorized(callback.from_user.id if callback.from_user else None):
        logger.warning("Unauthorized callback query ignored", user_id=callback.from_user.id if callback.from_user else None)
        await callback.answer("Unauthorized", show_alert=True)
        return

    try:
        parts = callback.data.split(":")
        if len(parts) < 4:
            await callback.answer("Invalid callback format", show_alert=True)
            return

        _, action, thread_id, card_id = parts[0], parts[1], parts[2], parts[3]

        app = get_osint_app()
        # Resume LangGraph thread with human decision
        await app.ainvoke(
            Command(resume=action),
            config={"configurable": {"thread_id": thread_id}},
        )

        status_emoji = "✅" if action == "approve" else ("❌" if action == "reject" else "💤")
        if callback.message:
            original_text = callback.message.text or ""
            await callback.message.edit_text(
                f"{original_text}\n\n<b>Status:</b> {action.upper()} {status_emoji}",
                parse_mode="HTML",
            )

        await callback.answer(f"Decision registered: {action.upper()} {status_emoji}")
        logger.info("Processed HITL callback", action=action, thread_id=thread_id, card_id=card_id)
    except Exception as exc:
        logger.error("Failed to resume HITL LangGraph workflow", error=str(exc))
        await callback.answer(f"Error resuming workflow: {str(exc)}", show_alert=True)


def create_dispatcher(osint_app_instance: Optional[Any] = None) -> Dispatcher:
    """
    Factory creating a configured aiogram Dispatcher with the HITL router.
    """
    if osint_app_instance is not None:
        set_osint_app(osint_app_instance)

    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def start_bot() -> None:
    """
    Initializes and starts the Telegram HITL long-polling bot session.
    """
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN in ("none", "placeholder", ""):
        print("[HITL Bot] Notice: TELEGRAM_BOT_TOKEN is not configured in .env.")
        print("[HITL Bot] Please set a valid TELEGRAM_BOT_TOKEN to start the Telegram bot.")
        return

    logger.info("Starting Telegram HITL Bot...", user_id=settings.TELEGRAM_ALLOWED_USER_ID)
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = create_dispatcher()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(start_bot())
