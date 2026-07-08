"""Integration tests — require a seeded database (docker compose up + seed)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TEBET = {"lat": -6.2264, "lng": 106.8531}


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_categories():
    r = client.get("/api/v1/categories")
    assert r.status_code == 200
    slugs = {c["slug"] for c in r.json()}
    assert {"coffee-grab-go", "laundry", "minimarket"} <= slugs


def test_analyze_tebet_full_payload():
    r = client.post(
        "/api/v1/analyses",
        json={**TEBET, "category_slug": "coffee-grab-go"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # shape
    assert "id" in body and "created_at" in body
    assert body["region"]["name"] == "Tebet Barat"
    assert body["score"]["verdict"] in {"prime", "strong", "conditional", "avoid"}
    assert 0 <= body["score"]["composite"] <= 100
    # every factor carries the FE contract fields
    for pillar in ("demand", "competition"):
        factors = body["breakdown"][pillar]["factors"]
        assert factors
        for f in factors:
            for field in ("raw_value", "percentile", "weight", "contribution", "evidence"):
                assert field in f, f"{pillar}.{f['key']} missing {field}"
    # competitors list present with decay weight
    comps = body["breakdown"]["competition"]["competitors_in_radius"]
    assert comps and "decay_weight" in comps[0]


def test_out_of_coverage():
    r = client.post(
        "/api/v1/analyses",
        json={"lat": -7.5, "lng": 110.0, "category_slug": "coffee-grab-go"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "OUT_OF_COVERAGE"


def test_analysis_crud_and_compare():
    a = client.post("/api/v1/analyses", json={**TEBET, "category_slug": "coffee-grab-go"}).json()
    b = client.post(
        "/api/v1/analyses",
        json={"lat": -6.2401, "lng": 106.8100, "category_slug": "coffee-grab-go"},
    ).json()

    # get
    assert client.get(f"/api/v1/analyses/{a['id']}").status_code == 200
    # patch
    r = client.patch(f"/api/v1/analyses/{a['id']}", json={"name": "Kandidat Tebet"})
    assert r.json()["name"] == "Kandidat Tebet"
    # compare
    r = client.get(f"/api/v1/analyses/compare?ids={a['id']},{b['id']}")
    assert r.status_code == 200, r.text
    cmp = r.json()
    assert len(cmp["analyses"]) == 2
    assert "best_composite" in cmp["deltas"]
    assert cmp["deltas"]["factor_winners"]
    # delete
    assert client.delete(f"/api/v1/analyses/{a['id']}").status_code == 204
    assert client.get(f"/api/v1/analyses/{a['id']}").status_code == 404


@pytest.mark.parametrize("q", ["tebet", "kopi"])
def test_geocode(q):
    r = client.get(f"/api/v1/geocode?q={q}")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
