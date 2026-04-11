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

    notes = arrangement_data.get("notes", [])
    if not notes:
        part.append(note.Note("C4", quarterLength=1.0))
    else:
        for note_data in sorted(notes, key=lambda x: x.get("onset", 0)):
            pitch_midi = int(note_data.get("pitch", 60))
            duration_sec = float(note_data.get("duration", 0.5))
            velocity = int(note_data.get("velocity", 80))
            quarter_length = max(0.25, duration_sec * (bpm / 60))
            try:
                n = note.Note(_midi_to_note_name(pitch_midi), quarterLength=quarter_length)
                n.volume.velocity = velocity
                part.append(n)
            except Exception:
                continue

    score.append(part)
    return score


async def generate_score(arrangement_data: dict, instrument_en: str) -> tuple[bytes, bytes]:
    score = _build_music21_score(arrangement_data, instrument_en)

    with tempfile.TemporaryDirectory() as tmp_dir:
        # MusicXML 생성 (외부 의존성 없음)
        xml_path = os.path.join(tmp_dir, "score.xml")
        score.write("musicxml", fp=xml_path)
        xml_content = Path(xml_path).read_bytes()

        pdf_bytes = b""
        png_bytes = b""

        # verovio로 SVG 생성 → PNG/PDF 변환
        try:
            import verovio
            tk = verovio.toolkit()
            tk.setOptions({
                "pageWidth": 2100,
                "pageHeight": 2970,
                "scale": 40,
                "adjustPageHeight": True,
                "footer": "none",
                "header": "none",
            })
            tk.loadData(xml_content.decode("utf-8"))
            svg_str = tk.renderToSVG(1)

            # SVG → PNG via svglib + reportlab
            try:
                from svglib.svglib import svg2rlg
                from reportlab.graphics import renderPDF, renderPM
                import tempfile as tf

                svg_tmp = tf.NamedTemporaryFile(suffix=".svg", delete=False)
                svg_tmp.write(svg_str.encode("utf-8"))
                svg_tmp.close()

                drawing = svg2rlg(svg_tmp.name)
                os.unlink(svg_tmp.name)

                if drawing:
                    # PNG
                    png_buf = io.BytesIO()
                    renderPM.drawToFile(drawing, png_buf, fmt="PNG")
                    png_bytes = png_buf.getvalue()

                    # PDF
                    pdf_buf = io.BytesIO()
                    renderPDF.drawToFile(drawing, pdf_buf)
                    pdf_bytes = pdf_buf.getvalue()

            except Exception as e:
                print(f"[score] svglib render failed: {e}")
                # SVG를 PNG로 직접 변환 (Pillow + cairosvg fallback)
                try:
                    import cairosvg
                    png_bytes = cairosvg.svg2png(bytestring=svg_str.encode())
                    pdf_bytes = cairosvg.svg2pdf(bytestring=svg_str.encode())
                except Exception as e2:
                    print(f"[score] cairosvg also failed: {e2}")
                    # 마지막 수단: SVG를 PNG URL로 저장
                    png_bytes = svg_str.encode("utf-8")  # SVG를 그대로 저장

        except Exception as e:
            print(f"[score] verovio failed: {e}")
            # LilyPond fallback
            try:
                pdf_path = os.path.join(tmp_dir, "score.pdf")
                score.write("lily.pdf", fp=pdf_path)
                if os.path.exists(pdf_path):
                    pdf_bytes = Path(pdf_path).read_bytes()
                png_path = os.path.join(tmp_dir, "score.png")
                score.write("lily.png", fp=png_path)
                for f in Path(tmp_dir).glob("*.png"):
                    png_bytes = f.read_bytes()
                    break
            except Exception as e2:
                print(f"[score] lilypond also failed: {e2}")

    return pdf_bytes, png_bytes
