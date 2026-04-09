async def generate_score(arrangement_data: dict, instrument: str) -> tuple[bytes, bytes]:
    """
    Convert arrangement data for a single instrument into sheet music.

    Uses music21 to build a Score object and LilyPond (via music21) to render it.

    Args:
        arrangement_data: Note events for the given instrument from ai_arranger.
        instrument:       Name of the instrument (e.g. "violin").

    Returns:
        A tuple of (pdf_bytes, png_bytes) for the rendered score.
    """
    # TODO:
    # 1. Build a music21.stream.Score from arrangement_data
    # 2. Write to LilyPond: score.write("lily.pdf", fp=tmp_path)
    # 3. Read back pdf and png bytes
    pass
