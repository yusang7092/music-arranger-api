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


def _build_quick_prompt(notes_data: dict, instruments: list[str]) -> str:
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

    return f"""You are a professional music arranger. Given extracted note data from an audio file, create a musical arrangement for the specified instruments.

## Extracted Notes (sample)
```json
{json.dumps(notes_sample, indent=2)}
```

Pitch range of original: {notes_data.get('pitch_range', {})}
Total duration: {notes_data.get('total_duration', 0):.1f} seconds

## Target Instruments
{json.dumps(instrument_list, indent=2)}

## Task
Create a musical arrangement assigning notes to each instrument. For each instrument:
1. Assign appropriate notes based on the instrument's range and character
2. Maintain musical coherence and harmony
3. Consider the instrument's typical role (melody, harmony, bass, rhythm)

## Output Format (STRICT JSON)
Return ONLY valid JSON, no other text:
{{
  "tempo": 120,
  "time_signature": "4/4",
  "instruments": {{
    "<instrument_english_name>": {{
      "notes": [
        {{"pitch": 60, "onset": 0.0, "duration": 0.5, "velocity": 80}},
        ...
      ]
    }}
  }}
}}

Important: pitch is MIDI number (0-127). Return at least 20 notes per instrument."""


def _build_thorough_prompt(stems_notes: dict, instruments: list[str]) -> str:
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

    return f"""You are a professional orchestral arranger with expertise in voice leading and orchestration.

## Stem Analysis
```json
{json.dumps(stems_summary, indent=2)}
```

## Target Instruments
```json
{json.dumps(instrument_list, indent=2)}
```

## Task
Create a professional orchestral arrangement:
1. Apply proper voice leading principles
2. Respect each instrument's pitch range strictly
3. Use appropriate articulations and dynamics
4. Distribute melody, harmony, and bass parts appropriately
5. If the original has no specific instrument, create an idiomatic arrangement

## Output Format (STRICT JSON)
Return ONLY valid JSON:
{{
  "tempo": 120,
  "time_signature": "4/4",
  "key": "C major",
  "instruments": {{
    "<instrument_english_name>": {{
      "role": "melody|harmony|bass|rhythm",
      "notes": [
        {{"pitch": 60, "onset": 0.0, "duration": 0.5, "velocity": 80}},
        ...
      ]
    }}
  }}
}}

Return at least 30 notes per instrument. Ensure notes respect each instrument's pitch range."""


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
        "max_tokens": 4096,
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(OPENROUTER_URL, json=payload, headers=headers)
        response.raise_for_status()

    result = response.json()
    content = result["choices"][0]["message"]["content"]

    # JSON 파싱 (마크다운 코드블록 제거)
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    return json.loads(content)


async def arrange_quick(notes_data: dict, instruments: list[str]) -> dict:
    prompt = _build_quick_prompt(notes_data, instruments)
    return await _call_openrouter(prompt, "google/gemini-2.5-flash")


async def arrange_thorough(stems_notes: dict, instruments: list[str]) -> dict:
    prompt = _build_thorough_prompt(stems_notes, instruments)
    return await _call_openrouter(prompt, "anthropic/claude-sonnet-4-5")
