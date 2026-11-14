from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apogee_api.main import create_app
from apogee_api.settings import get_settings

SITE = {
    "latitude_deg": -31.05,
    "longitude_deg": 136.53,
    "elevation_m": 160.0,
    "rail_length_m": 6.0,
    "inclination_deg": 84.0,
    "heading_deg": 0.0,
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APOGEE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APOGEE_REDIS_URL", "redis://127.0.0.1:1")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_site_preset_lifecycle(client: TestClient) -> None:
    created = client.post("/api/sites", json={"name": "Club field", "site": SITE})
    assert created.status_code == 201
    preset = created.json()
    assert preset["site"]["rail_length_m"] == 6.0

    preset["site"]["heading_deg"] = 10.0
    updated = client.put(f"/api/sites/{preset['id']}", json=preset).json()
    assert updated["site"]["heading_deg"] == 10.0

    client.post("/api/sites", json={"name": "Away field", "site": SITE})
    assert [p["name"] for p in client.get("/api/sites").json()] == ["Away field", "Club field"]

    assert client.delete(f"/api/sites/{preset['id']}").status_code == 204
    assert client.put(f"/api/sites/{preset['id']}", json=preset).status_code == 404


def test_duplicate_name_is_a_conflict(client: TestClient) -> None:
    first = client.post("/api/sites", json={"name": "Club field", "site": SITE}).json()
    second = client.post("/api/sites", json={"name": "Club field", "site": SITE})
    assert second.status_code == 409
    assert second.json()["code"] == "site_exists"
    # Saving a preset under its own name is not a clash.
    assert client.put(f"/api/sites/{first['id']}", json=first).status_code == 200


def test_pad_inside_hazard_is_refused(client: TestClient) -> None:
    lon, lat = SITE["longitude_deg"], SITE["latitude_deg"]
    box = [
        [lon - 0.01, lat - 0.01],
        [lon + 0.01, lat - 0.01],
        [lon + 0.01, lat + 0.01],
        [lon - 0.01, lat + 0.01],
    ]
    r = client.post("/api/sites", json={"name": "Bad", "site": {**SITE, "hazards": [box]}})
    assert r.status_code == 422
    assert r.json()["issues"][0]["path"] == "site.hazards[0]"


def test_mission_with_extends_is_refused(client: TestClient) -> None:
    r = client.post("/api/missions", json={"meta": {"name": "Child"}, "extends": "base.yaml"})
    assert r.status_code == 422
    assert r.json()["issues"][0]["code"] == "extends_unsupported"
