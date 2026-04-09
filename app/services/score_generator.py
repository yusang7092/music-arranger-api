import io
import os
import tempfile
from pathlib import Path


def _midi_to_note_name(midi_pitch: int) -> str:
    """MIDI 음번호 → 음이름 변환 (music21 형식)"""
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (midi_pitch // 12) - 1
    note = note_names[midi_pitch % 12]
    return f"{note}{octave}"


async def generate_score(arrangement_data: dict, instrument_en: str) -> tuple[bytes, bytes]:
    """
    arrangement_data: {"pitch": 60, "onset": 0.0, "duration": 0.5, "velocity": 80} 리스트
    instrument_en: 영어 악기명
    반환: (pdf_bytes, png_bytes)
    """
    import music21
    from music21 import stream, note, instrument as m21instrument, tempo, meter, key

    score = stream.Score()
    part = stream.Part()

    # 악기 설정
    try:
        inst_obj = m21instrument.fromString(instrument_en)
    except Exception:
        inst_obj = m21instrument.Instrument()
        inst_obj.instrumentName = instrument_en
    part.insert(0, inst_obj)

    # 빠르기 및 박자 설정
    bpm = arrangement_data.get("tempo", 120)
    ts = arrangement_data.get("time_signature", "4/4")
    part.insert(0, tempo.MetronomeMark(number=bpm))
    part.insert(0, meter.TimeSignature(ts))

    notes = arrangement_data.get("notes", [])
    if not notes:
        # 빈 악보 방지: C4 하나 추가
        n = note.Note("C4", quarterLength=1.0)
        part.append(n)
    else:
        # onset 기준 정렬
        notes_sorted = sorted(notes, key=lambda x: x.get("onset", 0))

        for note_data in notes_sorted:
            pitch_midi = int(note_data.get("pitch", 60))
            duration_sec = float(note_data.get("duration", 0.5))
            velocity = int(note_data.get("velocity", 80))

            # duration → quarter length (120 BPM 기준: 1 beat = 0.5초)
            quarter_length = max(0.25, duration_sec * (bpm / 60))

            pitch_name = _midi_to_note_name(pitch_midi)
            try:
                n = note.Note(pitch_name, quarterLength=quarter_length)
                n.volume.velocity = velocity
                part.append(n)
            except Exception:
                continue

    score.append(part)

    # 임시 디렉토리에 저장
    with tempfile.TemporaryDirectory() as tmp_dir:
        # PDF 생성 (LilyPond via music21)
        pdf_path = os.path.join(tmp_dir, "score.pdf")
        png_path = os.path.join(tmp_dir, "score.png")

        try:
            # LilyPond으로 PDF 생성
            score.write("lily.pdf", fp=pdf_path)
            pdf_bytes = Path(pdf_path).read_bytes() if os.path.exists(pdf_path) else b""
        except Exception as e:
            pdf_bytes = b""

        try:
            # PNG 생성 (music21 내장 또는 LilyPond)
            score.write("lily.png", fp=png_path)
            # LilyPond은 보통 score.png 형태로 저장
            actual_png = png_path
            if not os.path.exists(actual_png):
                # 파일명 변형 탐색
                for f in Path(tmp_dir).glob("*.png"):
                    actual_png = str(f)
                    break
            png_bytes = Path(actual_png).read_bytes() if os.path.exists(actual_png) else b""
        except Exception as e:
            png_bytes = b""

    return pdf_bytes, png_bytes
