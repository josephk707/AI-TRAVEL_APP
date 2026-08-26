"""
Seeds real, curated `phrasebook_entries` rows — F10's static Local Phrase
Assistant (IMPLEMENTATION_BLUEPRINT.md F10, DATABASE_SCHEMA.md §5). Static,
pre-authored content (no AI involved, per F10's own "AI component: None"
row) — distinct from the dynamic Gemini-backed translation built in
Phase 6 (`POST /translate/text`), which handles arbitrary phrases; this
is the fixed, offline-downloadable, always-available baseline set.

Regions are tied to the curated POI cities already seeded in Phase 5
(migration 20260825120017) — Agra/Delhi/Jaipur (Hindi), Mysore (Kannada),
Madurai (Tamil) — so `GET /phrasebook/{region}` has real content for the
same destinations the rest of the app already knows about.

Usage:
    python scripts/seed_phrasebook.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=REPO_ROOT / "backend" / ".env")

# (region, language_code, category, phrase_en, phrase_local_script, phrase_transliteration)
_HINDI = [
    ("directions", "Where is the railway station?", "रेलवे स्टेशन कहाँ है?", "Railway station kahaan hai?"),
    ("directions", "Where is the bathroom?", "बाथरूम कहाँ है?", "Bathroom kahaan hai?"),
    ("directions", "Turn left / Turn right", "बाएँ मुड़िए / दाएँ मुड़िए", "Baayen mudiye / Daayen mudiye"),
    ("prices", "How much does this cost?", "इसकी कीमत क्या है?", "Iski keemat kya hai?"),
    ("prices", "That's too expensive.", "यह बहुत महंगा है।", "Yeh bahut mahenga hai."),
    ("essentials", "Water, please.", "पानी दीजिए।", "Paani dijiye."),
    ("essentials", "I don't understand.", "मुझे समझ नहीं आया।", "Mujhe samajh nahin aaya."),
    ("essentials", "Yes / No", "हाँ / नहीं", "Haan / Nahin"),
    ("courtesy", "Hello", "नमस्ते", "Namaste"),
    ("courtesy", "Thank you", "धन्यवाद", "Dhanyavaad"),
    ("courtesy", "Please", "कृपया", "Kripaya"),
    ("courtesy", "Excuse me", "माफ़ कीजिए", "Maaf kijiye"),
]

_KANNADA = [
    ("directions", "Where is the railway station?", "ರೈಲು ನಿಲ್ದಾಣ ಎಲ್ಲಿದೆ?", "Railu nildaana ellide?"),
    ("directions", "Where is the bathroom?", "ಬಚ್ಚಲುಮನೆ ಎಲ್ಲಿದೆ?", "Bacchalumane ellide?"),
    ("prices", "How much does this cost?", "ಇದರ ಬೆಲೆ ಎಷ್ಟು?", "Idara bele eshtu?"),
    ("essentials", "Water, please.", "ದಯವಿಟ್ಟು ನೀರು ಕೊಡಿ.", "Dayavittu neeru kodi."),
    ("essentials", "I don't understand.", "ನನಗೆ ಅರ್ಥವಾಗುತ್ತಿಲ್ಲ.", "Nanage arthavaaguttilla."),
    ("essentials", "Yes / No", "ಹೌದು / ಇಲ್ಲ", "Haudu / Illa"),
    ("courtesy", "Hello", "ನಮಸ್ಕಾರ", "Namaskara"),
    ("courtesy", "Thank you", "ಧನ್ಯವಾದಗಳು", "Dhanyavaadagalu"),
    ("courtesy", "Please", "ದಯವಿಟ್ಟು", "Dayavittu"),
    ("courtesy", "Excuse me", "ಕ್ಷಮಿಸಿ", "Kshamisi"),
]

_TAMIL = [
    ("directions", "Where is the railway station?", "ரயில் நிலையம் எங்கே?", "Rayil nilaiyam enge?"),
    ("directions", "Where is the bathroom?", "கழிப்பறை எங்கே?", "Kazhipparai enge?"),
    ("prices", "How much does this cost?", "இது எவ்வளவு?", "Ithu evvalavu?"),
    ("essentials", "Water, please.", "தண்ணீர் தயவுசெய்து.", "Thanneer thayavu seithu."),
    ("essentials", "I don't understand.", "எனக்கு புரியவில்லை.", "Enakku puriyavillai."),
    ("essentials", "Yes / No", "ஆம் / இல்லை", "Aam / Illai"),
    ("courtesy", "Hello", "வணக்கம்", "Vanakkam"),
    ("courtesy", "Thank you", "நன்றி", "Nandri"),
    ("courtesy", "Please", "தயவுசெய்து", "Thayavu seithu"),
    ("courtesy", "Excuse me", "மன்னிக்கவும்", "Mannikkavum"),
]

_REGIONS: list[tuple[str, str, list[tuple[str, str, str, str]]]] = [
    ("Agra", "hi-IN", _HINDI),
    ("Delhi", "hi-IN", _HINDI),
    ("Jaipur", "hi-IN", _HINDI),
    ("Mysore", "kn-IN", _KANNADA),
    ("Madurai", "ta-IN", _TAMIL),
]


async def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set — cannot seed phrasebook.")
        return 1

    conn = await asyncpg.connect(database_url)
    try:
        inserted = 0
        skipped = 0
        for region, language_code, entries in _REGIONS:
            for category, phrase_en, phrase_local, phrase_translit in entries:
                existing = await conn.fetchval(
                    "select id from public.phrasebook_entries "
                    "where region = $1 and language_code = $2 and phrase_en = $3;",
                    region,
                    language_code,
                    phrase_en,
                )
                if existing is not None:
                    skipped += 1
                    continue
                await conn.execute(
                    """
                    insert into public.phrasebook_entries
                        (region, language_code, category, phrase_en,
                         phrase_local_script, phrase_transliteration)
                    values ($1, $2, $3, $4, $5, $6);
                    """,
                    region,
                    language_code,
                    category,
                    phrase_en,
                    phrase_local,
                    phrase_translit,
                )
                inserted += 1
        print(f"{inserted} new phrasebook_entries row(s) inserted, {skipped} already existed.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
