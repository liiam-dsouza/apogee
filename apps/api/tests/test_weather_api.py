import json
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apogee_api.main import create_app
from apogee_api.routers import weather
from apogee_api.settings import get_settings

ROOT = Path(__file__).parents[3]
RESPONSE = json.loads(
    (ROOT / "tests" / "fixtures" / "weather" / "openmeteo-white-cliffs.json").read_text()
)
PAD = {"latitude": -30.66481, "longitude": 143.196302}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APOGEE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APOGEE_QUEUE", "inline")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture
def online(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(weather, "_open_meteo", lambda lat, lon: RESPONSE)


def test_fetch_caches_and_lists_by_site(client: TestClient, online: None) -> None:
    r = client.post("/api/weather/forecasts", json=PAD)
    assert r.status_code == 200, r.text
    info = r.json()
    assert len(info["hours"]) == 3
    assert info["grid_elevation_m"] == 220.0
    listed = client.get("/api/weather/forecasts", params=PAD).json()
    assert [f["id"] for f in listed] == [info["id"]]
    assert client.get("/api/weather/forecasts", params={"latitude": 0, "longitude": 0}).json() == []


def test_profile_from_the_cache(client: TestClient, online: None) -> None:
    info = client.post("/api/weather/forecasts", json=PAD).json()
    r = client.get(
        f"/api/weather/forecasts/{info['id']}/profile",
        params={"valid_utc": info["hours"][1], "elevation_m": 220},
    )
    assert r.status_code == 200, r.text
    profile = r.json()
    assert profile["kind"] == "profile"
    assert profile["valid_utc"] == info["hours"][1]
    assert profile["fetched_utc"] == info["fetched_utc"]
    assert profile["levels"][0]["altitude_m"] == 220


def test_profile_outside_the_forecast_is_a_clear_422(client: TestClient, online: None) -> None:
    info = client.post("/api/weather/forecasts", json=PAD).json()
    r = client.get(
        f"/api/weather/forecasts/{info['id']}/profile",
        params={"valid_utc": "2030-01-01T00:00:00Z", "elevation_m": 220},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "forecast_out_of_range"
    missing = client.get(
        "/api/weather/forecasts/01NOPE/profile",
        params={"valid_utc": "2030-01-01T00:00:00Z", "elevation_m": 220},
    )
    assert missing.status_code == 404


def test_offline_points_at_the_cache(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def offline(*_: Any) -> Any:
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(weather, "_open_meteo", offline)
    r = client.post("/api/weather/forecasts", json=PAD)
    assert r.status_code == 503
    assert "cached forecast" in r.json()["detail"]


def test_effective_profile_blends_the_surface_wind(client: TestClient) -> None:
    standard = client.post(
        "/api/weather/effective", json={"environment": {}, "elevation_m": 220}
    ).json()
    assert standard["levels"] is None
    r = client.post(
        "/api/weather/effective",
        json={
            "environment": {"surface_wind": {"speed_ms": 5, "direction_deg": 270}},
            "elevation_m": 220,
        },
    )
    levels = r.json()["levels"]
    at_2m = next(lv for lv in levels if lv["altitude_m"] == 222)
    assert at_2m["wind_u_ms"] == pytest.approx(5)
