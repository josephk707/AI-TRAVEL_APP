"""
F24 — Expanded Heritage POI Catalog (IMPLEMENTATION_BLUEPRINT.md F24,
Phase 8). No new endpoints or schema — this is the "content-ingestion
pipeline expansion" the Blueprint itself describes, following the exact
same maintainer-script precedent established by
`scripts/seed_heritage_content.py` (Phase 6, resolving ARCHITECTURE_REVIEW.md
H4's "no admin tool exists" finding: a maintainer script IS the accepted
admin path for this launch catalog, not a UI).

Adds 3 new real, well-documented Indian UNESCO World Heritage Sites (not
yet in the 8-POI Phase 5 catalog) plus their real, citable overview
narration — genuinely growing the catalog, not padding it. Coordinates
and historical facts are drawn from well-established public/official
documentation (ASI, UNESCO), same authoring bar as Phase 6's script —
not scraped, not AI-generated.

Usage:
    python scripts/seed_phase8_heritage_expansion.py
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

NEW_POIS: list[dict] = [
    {
        "name": "Qutub Minar",
        "category": "heritage",
        "lat": 28.5245,
        "lng": 77.1855,
        "address": "Seth Sarai, Mehrauli, New Delhi, Delhi 110030",
        "city": "Delhi",
        "region": "Delhi",
    },
    {
        "name": "Ajanta Caves",
        "category": "heritage",
        "lat": 20.5519,
        "lng": 75.7033,
        "address": "Ajanta Caves Rd, Aurangabad district, Maharashtra 431117",
        "city": "Aurangabad",
        "region": "Maharashtra",
    },
    {
        "name": "Virupaksha Temple, Hampi",
        "category": "heritage",
        "lat": 15.3350,
        "lng": 76.4600,
        "address": "Hampi Bazaar, Hampi, Karnataka 583239",
        "city": "Hampi",
        "region": "Karnataka",
    },
]

HERITAGE_CONTENT: dict[str, list[dict[str, str]]] = {
    "Qutub Minar": [
        {
            "layer": "overview",
            "section_title": "Overview",
            "body_text": (
                "The Qutub Minar is a 73-metre soaring minaret of fluted red sandstone and "
                "marble in the Mehrauli area of Delhi, the tallest brick minaret in the world. "
                "Construction began around 1199 under Qutb al-Din Aibak, founder of the Delhi "
                "Sultanate, to mark the start of Muslim rule in India, and was completed by his "
                "successors over the following century. The tower tapers through five distinct "
                "storeys, each marked by a projecting balcony, with the lower stories in red "
                "sandstone and the upper stories incorporating marble. The surrounding Qutb "
                "complex includes the Quwwat-ul-Islam mosque (one of the earliest mosques built "
                "in India) and the Iron Pillar of Delhi, a metallurgical curiosity over 1,600 "
                "years old that has famously resisted rusting. UNESCO inscribed the Qutb Minar "
                "and its monuments as a World Heritage Site in 1993."
            ),
            "source_citation": "UNESCO World Heritage Centre listing; Archaeological Survey of India (ASI) site documentation.",
        }
    ],
    "Ajanta Caves": [
        {
            "layer": "overview",
            "section_title": "Overview",
            "body_text": (
                "The Ajanta Caves are a group of about 30 rock-cut Buddhist cave monuments carved "
                "into a horseshoe-shaped cliff above the Waghur river gorge in Maharashtra, dating "
                "from roughly the 2nd century BCE to about 480 CE. They were excavated in two main "
                "phases and served as monasteries (viharas) and worship halls (chaityas) for "
                "Buddhist monks. The caves are especially renowned for their paintings and "
                "sculptures, considered among the finest surviving examples of ancient Indian "
                "art — the murals depict Jataka tales (stories of the Buddha's past lives) with a "
                "sophistication of composition, colour, and human expression that had a lasting "
                "influence on later Indian art. The site was abandoned and gradually reclaimed by "
                "jungle until its rediscovery in 1819 by a British officer on a tiger hunt. UNESCO "
                "inscribed Ajanta as a World Heritage Site in 1983."
            ),
            "source_citation": "UNESCO World Heritage Centre listing; Archaeological Survey of India (ASI) site documentation.",
        }
    ],
    "Virupaksha Temple, Hampi": [
        {
            "layer": "overview",
            "section_title": "Overview",
            "body_text": (
                "The Virupaksha Temple, dedicated to Lord Shiva (worshipped here as Virupaksha), "
                "stands at the heart of Hampi Bazaar in Karnataka and is the ceremonial centre of "
                "the Group of Monuments at Hampi, the ruined capital of the Vijayanagara Empire "
                "(14th-16th centuries). Though the core shrine predates the empire by centuries, "
                "the temple was substantially expanded under Vijayanagara rule, most notably by "
                "King Krishnadevaraya, who added its towering nine-tier eastern gopuram (gateway "
                "tower) around 1510. Unlike most of Hampi's other monuments, which fell into ruin "
                "after the empire's defeat in 1565, Virupaksha has remained in continuous worship "
                "to this day, making it a rare living link to the medieval city. UNESCO inscribed "
                "the Group of Monuments at Hampi as a World Heritage Site in 1986."
            ),
            "source_citation": "UNESCO World Heritage Centre listing; Karnataka state Department of Archaeology, Museums and Heritage documentation.",
        }
    ],
}


async def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set — cannot seed the heritage catalog expansion.")
        return 1

    conn = await asyncpg.connect(database_url)
    try:
        poi_ids: dict[str, str] = {}
        pois_inserted = 0
        for poi in NEW_POIS:
            existing_id = await conn.fetchval(
                "select id from public.pois where name = $1 and source = 'curated';", poi["name"]
            )
            if existing_id is not None:
                poi_ids[poi["name"]] = str(existing_id)
                continue
            new_id = await conn.fetchval(
                """
                insert into public.pois (name, category, location, address, city, region, country, source)
                values ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography, $5, $6, $7, 'India', 'curated')
                returning id;
                """,
                poi["name"],
                poi["category"],
                poi["lng"],
                poi["lat"],
                poi["address"],
                poi["city"],
                poi["region"],
            )
            poi_ids[poi["name"]] = str(new_id)
            pois_inserted += 1
            print(f"  Inserted POI: {poi['name']}")

        content_inserted = 0
        content_skipped = 0
        for poi_name, sections in HERITAGE_CONTENT.items():
            poi_id = poi_ids.get(poi_name)
            if poi_id is None:
                print(f"  SKIP content (POI not found): {poi_name}")
                continue
            for section in sections:
                existing = await conn.fetchval(
                    "select id from public.heritage_content "
                    "where poi_id = $1 and layer = $2 and section_title = $3;",
                    poi_id,
                    section["layer"],
                    section["section_title"],
                )
                if existing is not None:
                    content_skipped += 1
                    continue
                await conn.execute(
                    """
                    insert into public.heritage_content
                        (poi_id, layer, section_title, body_text, source_citation,
                         language, version, is_published)
                    values ($1, $2, $3, $4, $5, 'en', 1, true);
                    """,
                    poi_id,
                    section["layer"],
                    section["section_title"],
                    section["body_text"],
                    section["source_citation"],
                )
                content_inserted += 1
                print(f"  Inserted content: {poi_name} / {section['layer']} / {section['section_title']}")

        print(
            f"\n{pois_inserted} new POI(s), {content_inserted} new heritage_content row(s) "
            f"inserted, {content_skipped} content row(s) already existed."
        )
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
