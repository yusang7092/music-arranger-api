import json
import httpx
from app.core.config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# 악기 한국어 → 영어 매핑 (music21용)
INSTRUMENT_MAP = {
    "바이올린": "violin",
    "비올라": "viola",
    "첼로": "cello",
    "콘트라베이스": "contrabass",
    "피아노": "piano",
    "오르간": "organ",
    "하프시코드": "harpsichord",
    "플루트": "flute",
    "클라리넷": "clarinet",
    "오보에": "oboe",
    "바순": "bassoon",
    "색소폰": "saxophone",
    "트럼펫": "trumpet",
    "트롬본": "trombone",
    "호른": "horn",
    "튜바": "tuba",
    "드럼": "drums",
    "팀파니": "timpani",
    "실로폰": "xylophone",
    "마림바": "marimba",
    "일렉기타": "electric guitar",
    "어쿠스틱기타": "acoustic guitar",
    "베이스기타": "bass guitar",
}

# 악기별 음역대 (MIDI pitch)
INSTRUMENT_RANGES = {
    "violin": (55, 103),      # G3 ~ G7
    "viola": (48, 93),         # C3 ~ A6
    "cello": (36, 76),         # C2 ~ E5
    "contrabass": (28, 67),    # E1 ~ G4
    "piano": (21, 108),        # A0 ~ C8
    "flute": (60, 96),         # C4 ~ C7
    "clarinet": (50, 94),      # D3 ~ Bb6
    "oboe": (58, 91),          # Bb3 ~ G6
    "bassoon": (34, 75),       # Bb1 ~ Eb5
    "saxophone": (49, 84),     # Db3 ~ C6
    "trumpet": (52, 82),       # E3 ~ Bb5
    "trombone": (40, 77),      # E2 ~ F5
    "horn": (34, 77),          # Bb1 ~ F5
    "tuba": (18, 62),          # Bb0 ~ Db4
    "drums": (35, 81),
    "electric guitar": (40, 84),
    "acoustic guitar": (40, 84),
    "bass guitar": (28, 60),
}


def _build_quick_prompt(notes_data: dict, instruments: list[str], references: str = "", target_instrument: str = "") -> str:
    # 전체 곡에서 고르게 샘플링 (앞부분만 보내면 AI가 앞부분 위주로 편곡함)
    all_notes = notes_data.get("notes", [])
    if len(all_notes) > 400:
        step = len(all_notes) // 400
        notes_sample = all_notes[::step][:400]
    else:
        notes_sample = all_notes

    instrument_list = []
    for inst in instruments:
        # "바이올린_2" 형태 파싱
        parts = inst.split("_")
        name_kr = parts[0]
        count = int(parts[1]) if len(parts) > 1 else 1
        name_en = INSTRUMENT_MAP.get(name_kr, name_kr)
        instrument_list.append({"korean": name_kr, "english": name_en, "count": count})

    target_en = INSTRUMENT_MAP.get(target_instrument, target_instrument) if target_instrument else ""
    target_section = f"Output notes for **{target_instrument} ({target_en})** only.\n" if target_instrument else ""

    total_dur = notes_data.get('total_duration', 60)
    target_notes = max(150, int(total_dur / 60 * 250))

    ref_block = f"""## Song Reference (from web search)
{references}
→ Use this alongside your own musical judgment. Let it inform the key, tempo, and chord feel,
  but trust your ears on the extracted notes too — blend both sources.
""" if references else ""

    return f"""You are a professional music arranger. Transcribe and adapt the original song faithfully.
{target_section}
{ref_block}
## Extracted Audio Notes ({len(notes_sample)} samples, evenly distributed across full song)
Total duration: {total_dur:.1f} seconds
```json
{json.dumps(notes_sample, indent=2)}
```

## Target Instrument
```json
{json.dumps(instrument_list, indent=2)}
```

## Rules
1. **Key/tempo/time signature**: blend web reference with your analysis of the extracted notes.
2. **Melody**: follow the pitch contour of the extracted notes. Do not invent unrelated melodies.
3. **Instrument range**: transpose octaves as needed, keep intervals intact.
4. **Durations**: use ONLY these values — 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0 (quarter lengths).
5. **Full song coverage**: onset values MUST span 0 → {total_dur:.0f}s. Last note onset near {total_dur:.0f}s.
6. **Note count**: approximately {target_notes} notes.

## Output (STRICT JSON only — no other text)
{{
  "tempo": <bpm>,
  "time_signature": "4/4",
  "instruments": {{
    "<instrument_english_name>": {{
      "role": "lead",
      "notes": [{{"pitch": 60, "onset": 0.0, "duration": 0.5, "velocity": 85}}, ...]
    }}
  }}
}}
pitch = MIDI (0-127), onset = seconds from start."""


def _build_thorough_prompt(stems_notes: dict, instruments: list[str], references: str = "", target_instrument: str = "") -> str:
    instrument_list = []
    for inst in instruments:
        parts = inst.split("_")
        name_kr = parts[0]
        count = int(parts[1]) if len(parts) > 1 else 1
        name_en = INSTRUMENT_MAP.get(name_kr, name_kr)
        pitch_range = INSTRUMENT_RANGES.get(name_en, (48, 84))
        instrument_list.append({
            "korean": name_kr,
            "english": name_en,
            "count": count,
            "pitch_range": {"min": pitch_range[0], "max": pitch_range[1]}
        })

    stems_summary = {}
    total_duration = 0.0
    for stem, notes in stems_notes.items():
        # 스템 전체에서 고르게 100개 샘플링
        if len(notes) > 100:
            step = len(notes) // 100
            sample = notes[::step][:100]
        else:
            sample = notes
        stems_summary[stem] = {
            "note_count": len(notes),
            "sample": sample
        }
        if notes:
            stem_end = max((n.get("onset", 0) + n.get("duration", 0)) for n in notes)
            total_duration = max(total_duration, stem_end)

    target_en = INSTRUMENT_MAP.get(target_instrument, target_instrument) if target_instrument else ""
    target_section = f"Output notes for **{target_instrument} ({target_en})** only.\n" if target_instrument else ""
    target_notes = max(150, int(total_duration / 60 * 250))

    ref_block = f"""## Song Reference (from web search)
{references}
→ Use this alongside your own musical judgment. Let it inform the key, tempo, and chord feel,
  but trust your ears on the extracted notes too — blend both sources.
""" if references else ""

    return f"""You are a professional music arranger. Transcribe and adapt the original song faithfully.
{target_section}
{ref_block}
## Stem Analysis (original audio separated into parts)
Total duration: {total_duration:.1f} seconds
Vocals stem = main melody. Bass stem = bass line. Use these as the melodic source.
```json
{json.dumps(stems_summary, indent=2)}
```

## Target Instrument
```json
{json.dumps(instrument_list, indent=2)}
```

## Rules
1. **Key/tempo/time signature**: blend web reference with your analysis of the stems.
2. **Melody**: follow pitch contour of the vocals stem. Do not invent unrelated melodies.
3. **Instrument range**: transpose octaves as needed, keep intervals intact.
4. **Durations**: use ONLY — 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0 (quarter lengths).
5. **Full song coverage**: onset values MUST span 0 → {total_duration:.0f}s. Last note near {total_duration:.0f}s.
6. **Note count**: approximately {target_notes} notes.

## Output (STRICT JSON only — no other text)
{{
  "tempo": <bpm>,
  "time_signature": "4/4",
  "instruments": {{
    "<instrument_english_name>": {{
      "role": "lead",
      "notes": [{{"pitch": 60, "onset": 0.0, "duration": 0.5, "velocity": 85}}, ...]
    }}
  }}
}}
pitch = MIDI (0-127), onset = seconds from start."""


async def _call_openrouter(prompt: str, model: str) -> dict:
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://music-arranger.vercel.app",
        "X-Title": "Music Arranger"
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 32000,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(OPENROUTER_URL, json=payload, headers=headers)
        response.raise_for_status()

    result = response.json()
    content = result["choices"][0]["message"]["content"]

    # 1차: 마크다운 코드블록 제거
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    # 2차: 직접 파싱 시도
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 3차: 정규식으로 JSON 객체 추출
    import re
    match = re.search(r'\{[\s\S]*\}', content)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"AI 응답을 JSON으로 파싱할 수 없습니다. 응답 앞부분: {content[:200]}")


async def search_song_references(filename: str) -> str:
    """
    곡명을 기반으로 웹에서 악보/편곡 레퍼런스를 검색.
    Perplexity Sonar (웹 검색 가능)를 사용.
    검색 실패 시 빈 문자열 반환 (편곡은 계속 진행).
    """
    # 파일명에서 곡명 추출 (확장자 제거, 특수문자 정리)
    import re
    song_name = re.sub(r'\.[^.]+$', '', filename)  # 확장자 제거
    song_name = re.sub(r'[_\-]+', ' ', song_name).strip()

    if not song_name:
        return ""

    search_prompt = f"""Search for sheet music, musical analysis, and arrangement references for the song: "{song_name}"

Please find:
1. The musical key and time signature of this song
2. Chord progressions and harmonic structure
3. Any notable musical characteristics (genre, tempo, mood)
4. Common arrangements or covers of this song
5. Any sheet music descriptions or analysis available

Provide a concise summary that would help a music arranger create a high-quality arrangement."""

    try:
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://music-arranger.vercel.app",
            "X-Title": "Music Arranger"
        }
        payload = {
            "model": "perplexity/sonar",
            "messages": [{"role": "user", "content": search_prompt}],
            "max_tokens": 1024,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(OPENROUTER_URL, json=payload, headers=headers)
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
    except Exception:
        pass

    return ""


async def revise_instrument(
    current_notes: list,
    instrument_kr: str,
    instrument_en: str,
    feedback: str,
    tempo: int = 120,
    time_signature: str = "4/4",
) -> list:
    """특정 악기의 편곡을 사용자 피드백 기반으로 수정."""
    pitch_range = INSTRUMENT_RANGES.get(instrument_en, (48, 84))
    prompt = f"""You are a professional music arranger. Revise this musical arrangement for {instrument_en} based on the user's feedback.

## Current Arrangement
- Instrument: {instrument_en} ({instrument_kr})
- Tempo: {tempo} BPM
- Time Signature: {time_signature}
- Pitch range (MIDI): {pitch_range[0]} to {pitch_range[1]}

### Current notes (first 60 shown)
{json.dumps(current_notes[:60], indent=2)}

## User Feedback
{feedback}

## Task
Create a revised arrangement that directly addresses the feedback above.
- Keep the same tempo and time signature
- Strictly respect the instrument's pitch range ({pitch_range[0]}–{pitch_range[1]})
- Maintain similar duration and musical coherence
- Return at least 20 notes

## Output Format (STRICT JSON — no other text)
{{
  "notes": [
    {{"pitch": 60, "onset": 0.0, "duration": 0.5, "velocity": 80}},
    ...
  ]
}}"""
    result = await _call_openrouter(prompt, "google/gemini-2.5-flash")
    return result.get("notes", [])


async def arrange_quick(notes_data: dict, instruments: list[str], filename: str = "", target_instrument: str = "") -> dict:
    references = await search_song_references(filename) if filename else ""
    prompt = _build_quick_prompt(notes_data, instruments, references, target_instrument)
    return await _call_openrouter(prompt, "google/gemini-2.5-flash")


async def arrange_thorough(stems_notes: dict, instruments: list[str], filename: str = "", target_instrument: str = "") -> dict:
    references = await search_song_references(filename) if filename else ""
    prompt = _build_thorough_prompt(stems_notes, instruments, references, target_instrument)
    return await _call_openrouter(prompt, "anthropic/claude-sonnet-4-5")
