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

# --- Phase 2 (Wave 2A): disaster risks per kecamatan ------------------------
# InaRISK per-kecamatan index numbers are not published in a citable static form,
# so these are modeled (labeled per spec): flood high along the river corridors
# (Kali Pesanggrahan -> Pesanggrahan/Kebayoran Lama; Ciliwung -> Tebet/Pancoran/
# Pasar Minggu; Kali Krukut -> Mampang/Setiabudi), earthquake uniform 2-3,
# landslide low 1-2 (slightly higher on the southern river-valley kecamatan).
DISASTER_SOURCE = "modeled-v1"
DISASTER_DATA_YEAR = 2025
DISASTER_RISKS = {
    #                     flood  earthquake  landslide
    "Kebayoran Baru":   {"flood": 2, "earthquake": 3, "landslide": 1},
    "Kebayoran Lama":   {"flood": 4, "earthquake": 2, "landslide": 1},
    "Cilandak":         {"flood": 3, "earthquake": 2, "landslide": 2},
    "Setiabudi":        {"flood": 3, "earthquake": 3, "landslide": 1},
    "Tebet":            {"flood": 4, "earthquake": 3, "landslide": 1},
    "Pesanggrahan":     {"flood": 4, "earthquake": 2, "landslide": 2},
    "Pasar Minggu":     {"flood": 3, "earthquake": 2, "landslide": 2},
    "Jagakarsa":        {"flood": 2, "earthquake": 2, "landslide": 2},
    "Mampang Prapatan": {"flood": 3, "earthquake": 3, "landslide": 1},
    "Pancoran":         {"flood": 4, "earthquake": 3, "landslide": 1},
}

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
        # Phase 2: kopi <-> kantor/kampus/stasiun (phase2-backend-spec.md §1.2).
        "synergy_map": {
            "complementary": [
                {
                    "match": {"anchor_type": "office"},
                    "weight": 1.0,
                    "opportunity": "Partnership B2B / voucher karyawan",
                },
                {
                    "match": {"anchor_type": "campus"},
                    "weight": 0.8,
                    "opportunity": "Promo mahasiswa & event kampus",
                },
                {
                    "match": {"anchor_type": "station"},
                    "weight": 0.6,
                    "opportunity": "Grab-and-go komuter pagi",
                },
            ],
            "max_bonus": 5,
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
        # Phase 2: laundry <-> kost/apartemen/kampus (FE spec §2A.2), dipetakan ke
        # anchor_type yang tersedia (campus/hospital/office).
        "synergy_map": {
            "complementary": [
                {
                    "match": {"anchor_type": "campus"},
                    "weight": 1.0,
                    "opportunity": "Paket langganan mahasiswa & kost sekitar kampus",
                },
                {
                    "match": {"anchor_type": "hospital"},
                    "weight": 0.6,
                    "opportunity": "Kontrak linen & seragam staf rumah sakit",
                },
                {
                    "match": {"anchor_type": "office"},
                    "weight": 0.5,
                    "opportunity": "Layanan antar-jemput pekerja kantoran",
                },
            ],
            "max_bonus": 5,
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
        # Phase 2: minimarket <-> perumahan/sekolah/stasiun (FE spec §2A.2);
        # "perumahan" sudah terwakili faktor kepadatan penduduk, sisanya ke anchor.
        "synergy_map": {
            "complementary": [
                {
                    "match": {"anchor_type": "station"},
                    "weight": 1.0,
                    "opportunity": "Kebutuhan harian komuter pagi-sore",
                },
                {
                    "match": {"anchor_type": "school"},
                    "weight": 0.8,
                    "opportunity": "Jajanan & perlengkapan siswa sekolah",
                },
                {
                    "match": {"anchor_type": "hospital"},
                    "weight": 0.6,
                    "opportunity": "Kebutuhan penunggu pasien 24 jam",
                },
            ],
            "max_bonus": 5,
        },
    },
]

# Rough share of the ~400 competitors per category.
CATEGORY_MIX = {"coffee-grab-go": 0.45, "minimarket": 0.35, "laundry": 0.20}
TOTAL_COMPETITORS = 420
