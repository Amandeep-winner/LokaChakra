import io
import asyncio
from typing import Optional
from groq import AsyncGroq
import structlog

from src.config import settings

logger = structlog.get_logger(__name__)

_local_whisper_model = None


def get_local_whisper_model():
    global _local_whisper_model
    if _local_whisper_model is None:
        from faster_whisper import WhisperModel
        _local_whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _local_whisper_model


def _transcribe_locally(audio_bytes: bytes) -> str:
    model = get_local_whisper_model()
    audio_stream = io.BytesIO(audio_bytes)
    segments, _ = model.transcribe(
        audio_stream,
        beam_size=5,
        initial_prompt="Indian English names, Bengaluru, Mumbai, Delhi, IIT, NIT, BITS, RVCE, Razorpay, Flipkart, Zomato, Swiggy, Peak XV, Stripe, AI startups",
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Transcribes audio using Groq Cloud Whisper with an automatic faster-whisper local fallback."""
    if settings.GROQ_API_KEY and not settings.GROQ_API_KEY.startswith("gsk_your_groq"):
        try:
            groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            response = await groq_client.audio.transcriptions.create(
                file=(filename, audio_bytes),
                model="whisper-large-v3-turbo",
                prompt="Indian English names, Bengaluru, Mumbai, Delhi, IIT, NIT, BITS, RVCE, Razorpay, Flipkart, Zomato, Swiggy, Peak XV, Stripe, AI startups",
                response_format="text",
            )
            text_result = response if isinstance(response, str) else getattr(response, "text", str(response))
            if text_result.strip():
                return text_result.strip()
        except Exception as e:
            logger.warning("Groq Whisper API transcription failed, falling back to local faster-whisper", error=str(e))

    # Automatic local fallback
    logger.info("Executing local faster-whisper transcription fallback")
    try:
        return await asyncio.to_thread(_transcribe_locally, audio_bytes)
    except Exception as e:
        logger.error("Local faster-whisper transcription failed", error=str(e))
        raise RuntimeError(f"Transcription failed across all backends: {e}") from e
