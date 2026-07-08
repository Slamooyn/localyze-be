"""Build the region hierarchy (city -> district -> subdistrict) + demographics.

Geography is synthetic: a COLS x ROWS grid of kecamatan, each split 2x2 into
kelurahan. Demographics are derived deterministically from each kelurahan's
proximity to the commercial corridors, so denser/wealthier areas coincide with
where competitors and anchors cluster — producing coherent, non-uniform scores.
"""
from __future__ import annotations

import random

from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app.models import Demographics, Region
from app.seed import config as C
from app.seed.geobuild import cell_area_km2, haversine_m, point_wkt, rect_multipolygon

AGE_KEYS = ["0_14", "15_24", "25_34", "35_54", "55_plus"]


def _commercial_factor(lng: float, lat: float) -> float:
    """0..1 — closeness to the nearest commercial-corridor vertex."""
    best = 1e9
    for corridor in C.CORRIDORS:
        for cx, cy in corridor:
            best = min(best, haversine_m(lng, lat, cx, cy))
    # 0 m -> ~1.0, 2500 m -> ~0.37, far -> ~0
    return round(2.71828 ** (-best / 2500.0), 4)


def _age_distribution(commercial: float, rng: random.Random) -> dict:
    # Commercial areas skew younger (more 25-34), residential skew older/families.
    young = 0.15 + 0.12 * commercial
    base = {
        "0_14": 0.24 - 0.10 * commercial,
        "15_24": 0.15 + 0.04 * commercial,
        "25_34": young,
        "35_54": 0.28,
        "55_plus": 0.18 - 0.06 * commercial,
    }
    noisy = {k: max(0.02, v + rng.uniform(-0.02, 0.02)) for k, v in base.items()}
    total = sum(noisy.values())
    return {k: round(v / total, 4) for k, v in noisy.items()}


def build_regions(db: Session) -> None:
    bbox = C.BBOX
    cw = (bbox["east"] - bbox["west"]) / C.COLS
    rh = (bbox["north"] - bbox["south"]) / C.ROWS

    city = Region(
        bps_code="3171",
        name="Jakarta Selatan",
        level="city",
        parent_id=None,
        boundary=WKTElement(
            rect_multipolygon(bbox["west"], bbox["south"], bbox["east"], bbox["north"]),
            srid=4326,
        ),
        centroid=WKTElement(
            point_wkt((bbox["west"] + bbox["east"]) / 2, (bbox["south"] + bbox["north"]) / 2),
            srid=4326,
        ),
    )
    db.add(city)
    db.flush()

    kel_index = 0
    for r in range(C.ROWS):
        for c in range(C.COLS):
            kec_name = C.KECAMATAN_GRID[r][c]
            w = bbox["west"] + c * cw
            e = w + cw
            n = bbox["north"] - r * rh
            s = n - rh
            district = Region(
                bps_code=f"3171{r}{c}",
                name=kec_name,
                level="district",
                parent_id=city.id,
                boundary=WKTElement(rect_multipolygon(w, s, e, n), srid=4326),
                centroid=WKTElement(point_wkt((w + e) / 2, (s + n) / 2), srid=4326),
            )
            db.add(district)
            db.flush()

            names = C.KELURAHAN_NAMES.get(
                kec_name, [f"{kec_name} {i}" for i in range(1, 5)]
            )
            # 2x2 kelurahan within the kecamatan cell.
            for qi, (dc, dr) in enumerate([(0, 0), (1, 0), (0, 1), (1, 1)]):
                kw = w + dc * (cw / 2)
                ke = kw + cw / 2
                kn = n - dr * (rh / 2)
                ks = kn - rh / 2
                clng, clat = (kw + ke) / 2, (ks + kn) / 2
                sub = Region(
                    bps_code=f"3171{r}{c}{qi}",
                    name=names[qi],
                    level="subdistrict",
                    parent_id=district.id,
                    boundary=WKTElement(rect_multipolygon(kw, ks, ke, kn), srid=4326),
                    centroid=WKTElement(point_wkt(clng, clat), srid=4326),
                )
                db.add(sub)
                db.flush()

                rng = random.Random(1000 + kel_index)
                commercial = _commercial_factor(clng, clat)
                area = cell_area_km2(kw, ks, ke, kn)
                density = 3500 + 20000 * commercial + rng.uniform(-1500, 1500)
                density = max(1500, round(density, 2))
                population = int(density * area)
                pp = round(0.75 + 0.60 * commercial + rng.uniform(-0.05, 0.05), 2)
                pp = min(1.5, max(0.70, pp))
                db.add(
                    Demographics(
                        region_id=sub.id,
                        population=population,
                        density_per_km2=density,
                        age_distribution=_age_distribution(commercial, rng),
                        purchasing_power_index=pp,
                        is_modeled=True,
                        data_year=C.DATA_YEAR,
                        source="BPS 2024 + modeled-v1",
                    )
                )
                kel_index += 1

    db.commit()
