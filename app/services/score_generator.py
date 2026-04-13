import io
import os
import tempfile
from pathlib import Path


def _midi_to_note_name(midi_pitch: int) -> str:
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (midi_pitch // 12) - 1
    note = note_names[midi_pitch % 12]
    return f"{note}{octave}"


def _build_music21_score(arrangement_data: dict, instrument_en: str):
    from music21 import stream, note, instrument as m21instrument, tempo, meter

    score = stream.Score()
    part = stream.Part()

    try:
        inst_obj = m21instrument.fromString(instrument_en)
    except Exception:
        inst_obj = m21instrument.Instrument()
        inst_obj.instrumentName = instrument_en
    part.insert(0, inst_obj)

    bpm = arrangement_data.get("tempo", 120)
    ts_str = arrangement_data.get("time_signature", "4/4")
    part.insert(0, tempo.MetronomeMark(number=bpm))
    part.insert(0, meter.TimeSignature(ts_str))

    # 표준 음표 길이 (MusicXML로 표현 가능한 값만)
    VALID_QL = [0.0625, 0.125, 0.25, 0.375, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]

    def snap_ql(ql: float) -> float:
        return min(VALID_QL, key=lambda x: abs(x - ql))

    notes = arrangement_data.get("notes", [])
    if not notes:
        part.append(note.Note("C4", quarterLength=1.0))
    else:
        for note_data in sorted(notes, key=lambda x: x.get("onset", 0)):
            pitch_midi = int(note_data.get("pitch", 60))
            duration_sec = float(note_data.get("duration", 0.5))
            onset_sec = float(note_data.get("onset", 0))
            velocity = int(note_data.get("velocity", 80))
            raw_ql = duration_sec * (bpm / 60)
            quarter_length = snap_ql(max(0.0625, raw_ql))
            # onset도 16분음표(0.25QL) 그리드에 스냅 → 쉼표 duration이 표현 불가한 값이 되는 것 방지
            raw_offset = onset_sec * (bpm / 60)
            offset_ql = round(raw_offset / 0.25) * 0.25
            try:
                n = note.Note(_midi_to_note_name(pitch_midi), quarterLength=quarter_length)
                n.volume.velocity = velocity
                part.insert(offset_ql, n)
            except Exception:
                continue

    score.append(part)
    return score


async def generate_score(arrangement_data: dict, instrument_en: str) -> tuple[bytes, bytes]:
    score = _build_music21_score(arrangement_data, instrument_en)

    with tempfile.TemporaryDirectory() as tmp_dir:
        # MusicXML 생성 — makeNotation()으로 쉼표/마디 duration 정규화
        xml_path = os.path.join(tmp_dir, "score.xml")
        score.makeNotation(inPlace=True)
        score.write("musicxml", fp=xml_path)
        xml_bytes = Path(xml_path).read_bytes()

        svg_bytes = b""
        pdf_bytes = b""

        # verovio: MusicXML → SVG (PNG 역할로 사용, 브라우저가 직접 렌더링)
        try:
            import verovio
            tk = verovio.toolkit()
            tk.setOptions({
                "pageWidth": 2100,
                "adjustPageHeight": True,
                "scale": 45,
                "footer": "none",
                "header": "none",
                "spacingSystem": 12,
            })
            tk.loadData(xml_bytes.decode("utf-8"))
            svg_str = tk.renderToSVG(1)
            svg_bytes = svg_str.encode("utf-8")
            print(f"[score] verovio SVG generated: {len(svg_bytes)} bytes")
        except Exception as e:
            print(f"[score] verovio failed: {e}")

        # PDF: reportlab로 간단한 래퍼 생성
        if svg_bytes:
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib import colors
                from reportlab.platypus import SimpleDocTemplate, Paragraph
                from reportlab.lib.styles import getSampleStyleSheet
                pdf_buf = io.BytesIO()
                doc = SimpleDocTemplate(pdf_buf, pagesize=A4)
                styles = getSampleStyleSheet()
                story = [Paragraph(f"Score: {instrument_en}", styles['Title']),
                         Paragraph("(Open the PNG version to view the full score)", styles['Normal'])]
                doc.build(story)
                pdf_bytes = pdf_buf.getvalue()
            except Exception as e:
                print(f"[score] reportlab PDF failed: {e}")

    # SVG를 png_url로 저장 (Content-Type: image/svg+xml)
    return pdf_bytes, svg_bytes
