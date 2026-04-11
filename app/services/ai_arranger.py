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


def _build_quick_prompt(notes_data: dict, instruments: list[str], references: str = "") -> str:
    # 음표 데이터를 압축 (너무 길면 앞 100개만)
    notes_sample = notes_data.get("notes", [])[:100]

    instrument_list = []
    for inst in instruments:
        # "바이올린_2" 형태 파싱
        parts = inst.split("_")
        name_kr = parts[0]
        count = int(parts[1]) if len(parts) > 1 else 1
        name_en = INSTRUMENT_MAP.get(name_kr, name_kr)
        instrument_list.append({"korean": name_kr, "english": name_en, "count": count})

    references_section = f"\n## Song Research & References\n{references}\n" if references else ""

    lead_instrument = instrument_list[0] if instrument_list else None
    supporting_instruments = instrument_list[1:] if len(instrument_list) > 1 else []

    return f"""You are a professional ensemble arranger. Your job is to create a realistic ensemble arrangement where each instrument has a DISTINCT role — NOT all playing the melody.

{references_section}
## Original Audio Notes (sample)
```json
{json.dumps(notes_sample, indent=2)}
```
Pitch range: {notes_data.get('pitch_range', {})}
Total duration: {notes_data.get('total_duration', 0):.1f} seconds

## Instruments & Their Roles

### LEAD instrument (plays the main melody):
- {json.dumps(lead_instrument)}
- This instrument carries the main melody extracted from the audio
- Use the actual melody notes from the extracted data

### SUPPORTING instruments (do NOT play the melody — they enrich and accompany):
{json.dumps(supporting_instruments, indent=2)}

Each supporting instrument must choose ONE of these roles:
- **Harmony/Chords**: Play chord tones that complement the melody (e.g., piano, guitar)
- **Counter-melody**: Play a secondary melodic line that doesn't clash with the lead (e.g., violin, flute)
- **Bass line**: Provide low-end foundation following the harmony (e.g., cello, bass)
- **Rhythm/Texture**: Provide rhythmic pulse or sustained texture (e.g., strings, drums)

## CRITICAL RULES
1. Only the LEAD instrument plays the main melody
2. Supporting instruments MUST NOT duplicate the lead melody note-for-note
3. Each supporting instrument should sound empty without the lead — they exist to make the lead shine
4. Velocity of supporting instruments: 50-70 (softer than lead at 80-100)
5. Assign roles based on instrument characteristics and pitch range

## Output Format (STRICT JSON)
Return ONLY valid JSON, no other text:
{{
  "tempo": 120,
  "time_signature": "4/4",
  "instruments": {{
    "<instrument_english_name>": {{
      "role": "lead|harmony|counter-melody|bass|rhythm",
      "notes": [
        {{"pitch": 60, "onset": 0.0, "duration": 0.5, "velocity": 80}},
        ...
      ]
    }}
  }}
}}

Return at least 30 notes per instrument. Pitch is MIDI number (0-127)."""


def _build_thorough_prompt(stems_notes: dict, instruments: list[str], references: str = "") -> str:
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
    for stem, notes in stems_notes.items():
        stems_summary[stem] = {
            "note_count": len(notes),
            "sample": notes[:30]
        }

    references_section = f"\n## Song Research & References\n{references}\n" if references else ""

    lead_instrument = instrument_list[0] if instrument_list else None
    supporting_instruments = instrument_list[1:] if len(instrument_list) > 1 else []

    return f"""You are a professional orchestral arranger with expertise in voice leading and orchestration.
Your task is to create a REAL ensemble arrangement — each instrument has a distinct role, just like a real band or orchestra.
{references_section}
## Stem Analysis (original audio breakdown)
```json
{json.dumps(stems_summary, indent=2)}
```

## Instruments & Their Roles

### LEAD instrument (carries the main melody):
```json
{json.dumps(lead_instrument)}
```
- Extract the main melodic line from the "vocals" or highest-pitched stem
- This instrument should be clearly heard above the others

### SUPPORTING instruments (enrich and accompany — do NOT copy the lead melody):
```json
{json.dumps(supporting_instruments, indent=2)}
```

Assign each supporting instrument one role:
- **Harmony**: Sustained chord tones, fills gaps between melody phrases
- **Counter-melody**: Independent secondary melody that weaves around the lead
- **Bass**: Root notes and bass movement, follows chord changes
- **Rhythm/Texture**: Rhythmic accompaniment or sustained texture

## CRITICAL RULES
1. Only the LEAD instrument plays the main melody
2. Supporting instruments must NEVER double the lead note-for-note
3. Use proper voice leading between supporting parts
4. Lead velocity: 85-100 | Supporting velocity: 45-70 (always softer)
5. Respect each instrument's physical pitch range strictly

## Output Format (STRICT JSON)
Return ONLY valid JSON, no other text:
{{
  "tempo": 120,
  "time_signature": "4/4",
  "key": "C major",
  "instruments": {{
    "<instrument_english_name>": {{
      "role": "lead|harmony|counter-melody|bass|rhythm",
      "notes": [
        {{"pitch": 60, "onset": 0.0, "duration": 0.5, "velocity": 80}},
        ...
      ]
    }}
  }}
}}

Return at least 30 notes per instrument. Pitch is MIDI number (0-127)."""


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
        "max_tokens": 8192,
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


async def arrange_quick(notes_data: dict, instruments: list[str], filename: str = "") -> dict:
    references = await search_song_references(filename) if filename else ""
    prompt = _build_quick_prompt(notes_data, instruments, references)
    return await _call_openrouter(prompt, "google/gemini-2.5-flash")


async def arrange_thorough(stems_notes: dict, instruments: list[str], filename: str = "") -> dict:
    references = await search_song_references(filename) if filename else ""
    prompt = _build_thorough_prompt(stems_notes, instruments, references)
    return await _call_openrouter(prompt, "anthropic/claude-sonnet-4-5")
