import io
import os
import tempfile
from pathlib import Path


def _midi_to_note_name(midi_pitch: int) -> str:
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (midi_pitch // 12) - 1
    note = note_names[midi_pitch % 12]
    return f"{note}{octave}"


def _split_into_valid_durations(ql: float) -> list:
    """큰 duration을 표현 가능한 음표 값들로 분해 (긴 쉼표 채울 때 사용)"""
    VALID_QL = [4.0, 3.0, 2.0, 1.5, 1.0, 0.75, 0.5, 0.25]
    result = []
    remaining = round(ql * 4) / 4  # 16분음표 단위로 반올림
    while remaining >= 0.25:
        for v in VALID_QL:
            if v <= remaining + 0.01:
                result.append(v)
                remaining -= v
                remaining = round(remaining * 4) / 4
                break
        else:
            break
    return result if result else [0.25]


BASS_CLEF_INSTRUMENTS = {'cello', 'contrabass', 'bass guitar', 'tuba', 'bassoon'}
TENOR_CLEF_INSTRUMENTS = {'trombone', 'horn'}
ALTO_CLEF_INSTRUMENTS = {'viola'}


def _get_clef(instrument_en: str):
    from music21 import clef
    name = instrument_en.lower()
    if name in BASS_CLEF_INSTRUMENTS:
        return clef.BassClef()
    if name in ALTO_CLEF_INSTRUMENTS:
        return clef.AltoClef()
    if name in TENOR_CLEF_INSTRUMENTS:
        return clef.TenorClef()
    return clef.TrebleClef()


def _build_music21_score(arrangement_data: dict, instrument_en: str):
    from music21 import stream, note, instrument as m21instrument, tempo, meter

    score = stream.Score()
    part = stream.Part()

    try:
        inst_obj = m21instrument.fromString(instrument_en)
    except Exception:
        inst_obj = m21instrument.Instrument()
        inst_obj.instrumentName = instrument_en
    part.append(inst_obj)

    bpm = arrangement_data.get("tempo", 120)
    ts_str = arrangement_data.get("time_signature", "4/4")
    part.append(_get_clef(instrument_en))   # 음자리표 명시 (자동 변경 방지)
    part.append(tempo.MetronomeMark(number=bpm))
    part.append(meter.TimeSignature(ts_str))

    # 표준 음표 길이 (MusicXML 표현 가능)
    VALID_QL = [4.0, 3.0, 2.0, 1.5, 1.0, 0.75, 0.5, 0.25]

    def snap_ql(ql: float) -> float:
        return min(VALID_QL, key=lambda x: abs(x - ql))

    raw_notes = arrangement_data.get("notes", [])
    total_duration_sec = arrangement_data.get("total_duration", 0.0)
    total_ql = round(total_duration_sec * (bpm / 60) * 4) / 4  # 전체 곡 길이 (QL)

    if not raw_notes:
        part.append(note.Note("C4", quarterLength=1.0))
    else:
        current_ql = 0.0  # 현재 위치 (quarter length)

        for note_data in sorted(raw_notes, key=lambda x: x.get("onset", 0)):
            pitch_midi = int(note_data.get("pitch", 60))
            duration_sec = float(note_data.get("duration", 0.5))
            onset_sec = float(note_data.get("onset", 0))
            velocity = int(note_data.get("velocity", 80))

            # onset을 8분음표 그리드에 스냅
            raw_offset = onset_sec * (bpm / 60)
            offset_ql = round(raw_offset / 0.5) * 0.5

            # 현재 위치보다 앞이면 스킵 (겹침 방지)
            if offset_ql < current_ql:
                offset_ql = current_ql

            # 현재 위치와 onset 사이 갭 → 쉼표로 채움
            gap = round((offset_ql - current_ql) * 4) / 4
            if gap >= 0.25:
                for rest_ql in _split_into_valid_durations(gap):
                    part.append(note.Rest(quarterLength=rest_ql))

            # 음표 추가
            raw_ql = duration_sec * (bpm / 60)
            quarter_length = snap_ql(max(0.25, raw_ql))
            try:
                n = note.Note(_midi_to_note_name(pitch_midi), quarterLength=quarter_length)
                n.volume.velocity = velocity
                part.append(n)
                current_ql = offset_ql + quarter_length
            except Exception:
                current_ql = offset_ql
                continue

        # 마지막 음표 이후 ~ 곡 끝까지 쉼표로 채워 전체 길이 보장
        if total_ql > current_ql + 0.25:
            remaining = round((total_ql - current_ql) * 4) / 4
            for rest_ql in _split_into_valid_durations(remaining):
                part.append(note.Rest(quarterLength=rest_ql))

    score.append(part)
    return score


async def generate_score(arrangement_data: dict, instrument_en: str) -> tuple[bytes, bytes]:
    score = _build_music21_score(arrangement_data, instrument_en)

    with tempfile.TemporaryDirectory() as tmp_dir:
        # MusicXML 생성 — makeMeasures로 마디 구성 (makeNotation은 뒤 쉼표를 잘라냄)
        xml_path = os.path.join(tmp_dir, "score.xml")
        score.makeMeasures(inPlace=True, bestClef=False)
        score.write("musicxml", fp=xml_path)
        xml_bytes = Path(xml_path).read_bytes()

        svg_bytes = b""
        pdf_bytes = b""

        # verovio: MusicXML → SVG 전 페이지 렌더링 후 세로로 합치기
        try:
            import verovio, re as _re
            tk = verovio.toolkit()
            tk.setOptions({
                "pageWidth": 2100,
                "pageHeight": 2970,   # A4 비율, 페이지 분리 허용
                "adjustPageHeight": False,
                "scale": 45,
                "footer": "none",
                "header": "none",
                "spacingSystem": 10,
            })
            tk.loadData(xml_bytes.decode("utf-8"))
            page_count = tk.getPageCount()
            print(f"[score] verovio: {page_count} pages")

            if page_count == 1:
                svg_bytes = tk.renderToSVG(1).encode("utf-8")
            else:
                # 각 페이지 SVG를 세로로 합쳐 하나의 긴 SVG로 만들기
                pages_svg = [tk.renderToSVG(p) for p in range(1, page_count + 1)]
                heights = []
                inner_contents = []
                page_width = 2100
                for svg in pages_svg:
                    vb = _re.search(r'viewBox="[^"]*\s+[^"]*\s+([^\s"]+)\s+([^\s"]+)"', svg)
                    h = float(vb.group(2)) if vb else 2970
                    heights.append(h)
                    inner = _re.search(r'<svg[^>]*>([\s\S]*)</svg>', svg)
                    inner_contents.append(inner.group(1) if inner else "")
                total_h = sum(heights)
                combined = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {page_width} {total_h:.0f}">'
                y = 0.0
                for content, h in zip(inner_contents, heights):
                    combined += f'<g transform="translate(0,{y:.0f})">{content}</g>'
                    y += h
                combined += "</svg>"
                svg_bytes = combined.encode("utf-8")

            print(f"[score] SVG generated: {len(svg_bytes)} bytes")
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
