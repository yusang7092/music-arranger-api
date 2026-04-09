async def extract_notes_basic_pitch(audio_path: str) -> dict:
    """
    Quick mode: use basic-pitch to extract note events from the audio file.

    Args:
        audio_path: Absolute path to the audio file on disk.

    Returns:
        A dict containing detected note events (pitch, onset, duration, etc.)
    """
    # TODO: import basic_pitch and run inference
    pass


async def separate_stems_demucs(audio_path: str) -> dict:
    """
    Thorough mode: use Demucs to separate the audio into stems
    (drums, bass, vocals, other).

    Args:
        audio_path: Absolute path to the audio file on disk.

    Returns:
        A dict mapping stem name -> path of the separated stem file.
    """
    # TODO: import demucs and run separation
    pass
