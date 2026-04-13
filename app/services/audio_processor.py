import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path

async def extract_notes_basic_pitch(audio_path: str) -> dict:
    """Quick 모드: basic-pitch로 전체 음원에서 음표 추출"""
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH

    model_output, midi_data, note_events = predict(
        audio_path,
        ICASSP_2022_MODEL_PATH
    )

    notes = []
    for note in note_events:
        notes.append({
            "pitch": int(note[2]),        # MIDI pitch number
            "onset": float(note[0]),       # start time (seconds)
            "offset": float(note[1]),      # end time (seconds)
            "velocity": float(note[3]) if len(note) > 3 else 64.0,
            "duration": float(note[1] - note[0])
        })

    # 음역대 분석
    pitches = [n["pitch"] for n in notes]

    return {
        "notes": notes,
        "pitch_range": {"min": min(pitches) if pitches else 60, "max": max(pitches) if pitches else 72},
        "total_duration": max(n["offset"] for n in notes) if notes else 0,
        "note_count": len(notes)
    }


async def separate_stems_demucs(audio_path: str) -> dict:
    """Thorough 모드: Demucs로 스템 분리"""
    output_dir = tempfile.mkdtemp()

    # demucs CLI 실행 (subprocess)
    cmd = [
        "python", "-m", "demucs",
        "--out", output_dir,
        "--mp3",  # mp3 출력 (용량 절약)
        audio_path
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)  # 10분 타임아웃
    except asyncio.TimeoutError:
        proc.kill()
        print("[demucs] TIMEOUT after 600s")
        raise RuntimeError("Demucs 스템 분리 시간 초과 (10분)")

    if proc.returncode != 0:
        err_msg = stderr.decode()[-300:] if stderr else "unknown error"
        print(f"[demucs] FAILED (exit {proc.returncode}): {err_msg}")
        raise RuntimeError(f"Demucs 스템 분리 실패: {err_msg[:100]}")

    # 출력 파일 찾기 (demucs는 출력 디렉토리 구조: output_dir/htdemucs/{track_name}/{stem}.mp3)
    stem_files = {}
    for stem in ["drums", "bass", "vocals", "other"]:
        # 재귀적으로 파일 찾기
        for path in Path(output_dir).rglob(f"{stem}.mp3"):
            stem_files[stem] = str(path)
            break

    return {
        "stems": stem_files,
        "output_dir": output_dir
    }


async def extract_notes_from_stems(stems_data: dict) -> dict:
    """각 스템에서 basic-pitch로 음표 추출"""
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH

    results = {}
    for stem_name, stem_path in stems_data["stems"].items():
        if not os.path.exists(stem_path):
            continue
        try:
            _, _, note_events = predict(stem_path, ICASSP_2022_MODEL_PATH)
            notes = []
            for note in note_events:
                notes.append({
                    "pitch": int(note[2]),
                    "onset": float(note[0]),
                    "offset": float(note[1]),
                    "duration": float(note[1] - note[0]),
                    "velocity": float(note[3]) if len(note) > 3 else 64.0
                })
            results[stem_name] = notes
        except Exception as e:
            results[stem_name] = []

    return results
