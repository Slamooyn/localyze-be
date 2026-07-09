"""Integration tests — require a seeded database (docker compose up + seed)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TEBET = {"lat": -6.2264, "lng": 106.8531}


def register() -> dict:
    """Register a fresh user, return Authorization headers."""
    email = f"t_{uuid.uuid4().hex[:10]}@mail.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"name": "Tester", "email": email, "password": "password123"},
    )
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


# --- auth ---------------------------------------------------------------
def test_register_login_me():
    email = f"u_{uuid.uuid4().hex[:10]}@mail.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"name": "Moym", "email": email, "password": "secret123"},
    )
    assert r.status_code == 201
    assert r.json()["user"]["email"] == email

    # duplicate -> 409
    dup = client.post(
        "/api/v1/auth/register",
        json={"name": "Moym", "email": email, "password": "secret123"},
    )
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "EMAIL_TAKEN"

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "secret123"})
    assert login.status_code == 200
    token = login.json()["token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_login_wrong_password_401():
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@localyze.id", "password": "wrongpass"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_demo_account_has_seeded_analyses():
    login = client.post(
        "/api/v1/auth/login", json={"email": "demo@localyze.id", "password": "demo1234"}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    r = client.get("/api/v1/analyses", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) >= 2  # 2 sample analyses from seed


def test_analyses_require_auth():
    r = client.post("/api/v1/analyses", json={**TEBET, "category_slug": "coffee-grab-go"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "UNAUTHORIZED"


def test_user_isolation():
    a_headers = register()
    b_headers = register()
    created = client.post(
        "/api/v1/analyses",
        json={**TEBET, "category_slug": "coffee-grab-go"},
        headers=a_headers,
    ).json()
    # B cannot read A's analysis
    assert client.get(f"/api/v1/analyses/{created['id']}", headers=b_headers).status_code == 404
    # A can
    assert client.get(f"/api/v1/analyses/{created['id']}", headers=a_headers).status_code == 200
    # B's list does not contain it
    b_list = client.get("/api/v1/analyses", headers=b_headers).json()
    assert all(x["id"] != created["id"] for x in b_list)


# --- public endpoints (no token) ---------------------------------------
def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_categories_public():
    r = client.get("/api/v1/categories")
    assert r.status_code == 200
    slugs = {c["slug"] for c in r.json()}
    assert {"coffee-grab-go", "laundry", "minimarket"} <= slugs


def test_discovery_public_and_varied():
    districts = client.get("/api/v1/regions?level=district").json()
    rid = districts[0]["id"]
    r = client.get(f"/api/v1/discovery?category_slug=coffee-grab-go&region_id={rid}&limit=10")
    assert r.status_code == 200
    top = r.json()["top_locations"]
    scores = [t["score_composite"] for t in top]
    assert scores == sorted(scores, reverse=True)


# --- analysis (with auth) ----------------------------------------------
def test_analyze_tebet_full_payload():
    headers = register()
    r = client.post(
        "/api/v1/analyses",
        json={**TEBET, "category_slug": "coffee-grab-go"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["region"]["name"] == "Tebet Barat"
    assert body["score"]["verdict"] in {"prime", "strong", "conditional", "avoid"}
    for pillar in ("demand", "competition"):
        for f in body["breakdown"][pillar]["factors"]:
            for field in ("raw_value", "percentile", "weight", "contribution", "evidence"):
                assert field in f
    assert body["breakdown"]["competition"]["competitors_in_radius"]


def test_out_of_coverage():
    headers = register()
    r = client.post(
        "/api/v1/analyses",
        json={"lat": -7.5, "lng": 110.0, "category_slug": "coffee-grab-go"},
        headers=headers,
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "OUT_OF_COVERAGE"


def test_crud_and_compare():
    headers = register()
    a = client.post(
        "/api/v1/analyses", json={**TEBET, "category_slug": "coffee-grab-go"}, headers=headers
    ).json()
    b = client.post(
        "/api/v1/analyses",
        json={"lat": -6.2401, "lng": 106.8100, "category_slug": "coffee-grab-go"},
        headers=headers,
    ).json()
    assert client.patch(
        f"/api/v1/analyses/{a['id']}", json={"name": "Kandidat Tebet"}, headers=headers
    ).json()["name"] == "Kandidat Tebet"
    cmp = client.get(
        f"/api/v1/analyses/compare?ids={a['id']},{b['id']}", headers=headers
    ).json()
    assert len(cmp["analyses"]) == 2
    assert cmp["deltas"]["factor_winners"]
    assert client.delete(f"/api/v1/analyses/{a['id']}", headers=headers).status_code == 204


def test_outlet_import_and_cannibalization():
    headers = register()
    before = client.post(
        "/api/v1/analyses",
        json={**TEBET, "category_slug": "coffee-grab-go", "include_cannibalization": True},
        headers=headers,
    ).json()
    csv_body = (
        "name,lat,lng,address\n"
        "Outlet A,-6.2270,106.8535,Jl Tebet\n"
        "Outlet B,-6.2300,106.8500,Jl Tebet Barat\n"
        "Bad,notalat,106.85,broken\n"
    )
    rep = client.post(
        "/api/v1/outlets/import",
        files={"file": ("outlets.csv", csv_body, "text/csv")},
        headers=headers,
    ).json()
    assert rep["imported"] == 2
    assert any(s["reason"] == "invalid lat" for s in rep["skipped"])
    after = client.post(
        "/api/v1/analyses",
        json={**TEBET, "category_slug": "coffee-grab-go", "include_cannibalization": True},
        headers=headers,
    ).json()
    assert after["score"]["cannibalization_penalty"] > 0
    assert after["score"]["composite"] < before["score"]["composite"]
    client.delete("/api/v1/outlets", headers=headers)


@pytest.mark.parametrize("q", ["tebet", "kopi"])
def test_geocode_public(q):
    r = client.get(f"/api/v1/geocode?q={q}")
    assert r.status_code == 200
