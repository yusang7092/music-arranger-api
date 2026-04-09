import httpx
from app.core.config import settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


async def arrange_quick(notes_data: dict, instruments: list[str]) -> dict:
    """
    Quick mode: send note data to Gemini 2.5 Flash via OpenRouter for fast arrangement.

    Args:
        notes_data:   Output from audio_processor.extract_notes_basic_pitch.
        instruments:  Target instrument list, e.g. ["violin", "piano"].

    Returns:
        A dict containing the arranged note events per instrument.
    """
    # TODO: build prompt, call OpenRouter with model="google/gemini-2.5-flash"
    pass


async def arrange_thorough(stems_data: dict, instruments: list[str]) -> dict:
    """
    Thorough mode: send stem analysis to Claude Sonnet via OpenRouter for precise arrangement.

    Args:
        stems_data:  Output from audio_processor.separate_stems_demucs.
        instruments: Target instrument list.

    Returns:
        A dict containing the arranged note events per instrument.
    """
    # TODO: build prompt, call OpenRouter with model="anthropic/claude-sonnet-4-5"
    pass
