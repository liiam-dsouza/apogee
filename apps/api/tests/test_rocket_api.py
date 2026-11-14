from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apogee_api.main import create_app
from apogee_api.settings import get_settings
from simcore.mission import load_mission, parse_yaml

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APOGEE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APOGEE_QUEUE", "inline")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _calisto(client: TestClient) -> dict[str, Any]:
    """Calisto as JSON, with its drag table stored."""
    table = (CALISTO / "powerOffDragCurve.csv").read_bytes()
    r = client.post(
        "/api/assets",
        files={"file": ("powerOffDragCurve.csv", table)},
        data={"kind": "drag_table"},
    )
    assert r.status_code == 201, r.text
    mission = load_mission(parse_yaml((CALISTO / "calisto.mission.yaml").read_text()))
    return mission.model_dump(mode="json")


def test_drag_shows_the_flown_curve_next_to_the_estimate(client: TestClient) -> None:
    mission = _calisto(client)
    r = client.post("/api/rocket/drag", json={"mission": mission})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["elevation_m"] == 1400
    p = next(p for p in body["points"] if p["mach"] == 0.5)
    assert p["power_off"] == pytest.approx(0.381, abs=0.005)  # Calisto's table
    parts = p["friction"] + p["nose"] + p["tail"] + p["fins"] + p["base"]
    assert parts == pytest.approx(p["estimate_off"])
    assert p["estimate_on"] < p["estimate_off"]
    assert any("thickness" in n for n in body["notes"])


def test_an_estimated_mission_flies_the_estimate(client: TestClient) -> None:
    mission = _calisto(client)
    mission["rocket"]["drag"] = {"multiplier": 1.1}  # both curves default to the estimate
    body = client.post("/api/rocket/drag", json={"mission": mission}).json()
    for p in body["points"]:
        assert p["power_off"] == pytest.approx(p["estimate_off"])
        assert p["power_on"] == pytest.approx(p["estimate_on"])


def test_drag_needs_a_rocket(client: TestClient) -> None:
    r = client.post("/api/rocket/drag", json={"mission": {"meta": {"name": "Empty"}}})
    assert r.status_code == 422
