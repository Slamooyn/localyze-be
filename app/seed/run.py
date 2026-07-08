"""Idempotent seed entrypoint:  python -m app.seed.run

Order (database-schema.md §5):
  1. regions + demographics
  2. franchise_categories + brands
  3. places (competitors + anchors)
  4. score_grid_cells precompute (added in M5)
"""
from __future__ import annotations

from sqlalchemy import text

from app.db import SessionLocal
from app.seed.regions import build_regions
from app.seed.synthetic import build_brands, build_categories, build_places

TABLES = [
    "score_grid_cells",
    "analyses",
    "user_outlets",
    "places",
    "demographics",
    "brands",
    "regions",
    "franchise_categories",
]


def reset(db) -> None:
    db.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        print("• resetting tables …")
        reset(db)
        print("• building regions + demographics …")
        build_regions(db)
        print("• building categories …")
        cats = build_categories(db)
        print("• building brands …")
        brands = build_brands(db, cats)
        print("• building places (competitors + anchors) …")
        build_places(db, cats, brands)

        # --- summary ---
        counts = {
            t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in TABLES
        }
        comp = db.execute(
            text("SELECT count(*) FROM places WHERE place_type='competitor'")
        ).scalar()
        anch = db.execute(
            text("SELECT count(*) FROM places WHERE place_type='anchor'")
        ).scalar()
        print("\n✓ seed complete")
        for t in TABLES:
            print(f"    {t:24} {counts[t]}")
        print(f"    (competitors={comp}, anchors={anch})")

        # Grid precompute (M5) — optional, imported lazily so M2 works standalone.
        try:
            from app.seed.grid import build_grid

            print("• precomputing score grid …")
            build_grid(db)
            n = db.execute(text("SELECT count(*) FROM score_grid_cells")).scalar()
            print(f"✓ grid cells: {n}")
        except ImportError:
            print("• (grid precompute not available yet — M5)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
