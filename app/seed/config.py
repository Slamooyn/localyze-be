"""Static configuration for the synthetic Jakarta Selatan seed.

All geography is synthetic-but-plausible: a 5x2 grid of kecamatan over a Jakarta
Selatan bounding box, each split into 2x2 kelurahan (40 subdistricts). Values are
deterministic (seeded RNG) so every teammate gets an identical database.
"""
from __future__ import annotations

# Jakarta Selatan bounding box (approx).
BBOX = {"west": 106.745, "east": 106.860, "south": -6.365, "north": -6.200}
COLS = 5
ROWS = 2

# Kecamatan names laid over the grid. Row 0 = north, left(west) -> right(east).
# Tebet is placed NE so the demo point (-6.2264, 106.8531) resolves to it.
KECAMATAN_GRID = [
    ["Kebayoran Baru", "Kebayoran Lama", "Cilandak", "Setiabudi", "Tebet"],
    ["Pesanggrahan", "Pasar Minggu", "Jagakarsa", "Mampang Prapatan", "Pancoran"],
]

# Realistic kelurahan names for the two demo-relevant kecamatan; others generated.
KELURAHAN_NAMES = {
    "Tebet": ["Tebet Timur", "Tebet Barat", "Kebon Baru", "Menteng Dalam"],
    "Kebayoran Baru": ["Senayan", "Gunung", "Kramat Pela", "Melawai"],
    "Setiabudi": ["Setiabudi", "Karet", "Kuningan Timur", "Menteng Atas"],
}

DATA_YEAR = 2024
SNAPSHOT_DATE = "2026-07-01"

# Commercial corridors (lng, lat) polylines — competitors cluster along these.
CORRIDORS = [
    [(106.823, -6.208), (106.816, -6.224), (106.807, -6.245)],   # Sudirman axis
    [(106.845, -6.224), (106.852, -6.230), (106.858, -6.236)],   # Tebet Raya
    [(106.797, -6.244), (106.804, -6.252), (106.811, -6.261)],   # Blok M / Kebayoran
    [(106.797, -6.290), (106.799, -6.302), (106.801, -6.312)],   # Fatmawati / Cilandak
    [(106.813, -6.258), (106.817, -6.267), (106.821, -6.276)],   # Kemang
    [(106.783, -6.300), (106.790, -6.312), (106.797, -6.322)],   # Pasar Minggu
]

# Category presets — scoring_weights & target_demo_profile (database-schema.md §3.1).
CATEGORIES = [
    {
        "slug": "coffee-grab-go",
        "name": "Kopi Grab-and-Go",
        "google_place_types": ["cafe", "coffee_shop"],
        "decay_tau_m": 600,
        "default_radius_m": 1000,
        "scoring_weights": {
            "pillars": {"demand": 0.55, "competition": 0.45},
            "demand_factors": {
                "population_density": 0.25,
                "demographic_match": 0.20,
                "purchasing_power": 0.20,
                "anchor_poi": 0.35,
            },
            "competition_factors": {
                "weighted_density": 0.50,
                "per_capita_intensity": 0.30,
                "nearest_distance": 0.20,
            },
            "anchor_type_weights": {
                "office": 1.0, "mall": 0.9, "campus": 0.8,
                "station": 0.7, "school": 0.5, "hospital": 0.4,
            },
            "cannibalization": {"max_penalty": 15, "tau_m": 1200},
        },
        "target_demo_profile": {
            "age_weights": {"15_24": 0.35, "25_34": 0.35, "35_54": 0.20, "55_plus": 0.10},
            "min_purchasing_power_index": 0.9,
        },
    },
    {
        "slug": "laundry",
        "name": "Laundry Kiloan",
        "google_place_types": ["laundry"],
        "decay_tau_m": 1000,
        "default_radius_m": 1500,
        "scoring_weights": {
            "pillars": {"demand": 0.70, "competition": 0.30},
            "demand_factors": {
                "population_density": 0.45,
                "demographic_match": 0.20,
                "purchasing_power": 0.15,
                "anchor_poi": 0.20,
            },
            "competition_factors": {
                "weighted_density": 0.50,
                "per_capita_intensity": 0.30,
                "nearest_distance": 0.20,
            },
            "anchor_type_weights": {
                "office": 0.7, "mall": 0.5, "campus": 1.0,
                "station": 0.8, "school": 0.6, "hospital": 0.4,
            },
            "cannibalization": {"max_penalty": 15, "tau_m": 1200},
        },
        "target_demo_profile": {
            "age_weights": {"15_24": 0.30, "25_34": 0.35, "35_54": 0.25, "55_plus": 0.10},
            "min_purchasing_power_index": 0.8,
        },
    },
    {
        "slug": "minimarket",
        "name": "Minimarket",
        "google_place_types": ["convenience_store", "supermarket"],
        "decay_tau_m": 500,
        "default_radius_m": 800,
        "scoring_weights": {
            "pillars": {"demand": 0.50, "competition": 0.50},
            "demand_factors": {
                "population_density": 0.35,
                "demographic_match": 0.15,
                "purchasing_power": 0.20,
                "anchor_poi": 0.30,
            },
            "competition_factors": {
                "weighted_density": 0.35,
                "per_capita_intensity": 0.25,
                "nearest_distance": 0.40,
            },
            "anchor_type_weights": {
                "office": 0.9, "mall": 0.8, "campus": 0.7,
                "station": 1.0, "school": 0.6, "hospital": 0.5,
            },
            "cannibalization": {"max_penalty": 15, "tau_m": 1200},
        },
        "target_demo_profile": {
            "age_weights": {
                "0_14": 0.15, "15_24": 0.20, "25_34": 0.25,
                "35_54": 0.25, "55_plus": 0.15,
            },
            "min_purchasing_power_index": 0.7,
        },
    },
]

# Rough share of the ~400 competitors per category.
CATEGORY_MIX = {"coffee-grab-go": 0.45, "minimarket": 0.35, "laundry": 0.20}
TOTAL_COMPETITORS = 420
