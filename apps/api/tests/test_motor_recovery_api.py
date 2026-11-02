from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apogee_api.main import create_app
from apogee_api.settings import get_settings
from simcore.mission import load_mission, parse_yaml

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"
ENG = (CALISTO / "Cesaroni_M1670.eng").read_bytes()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APOGEE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APOGEE_QUEUE", "inline")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_upload_a_motor_and_read_its_curve(client: TestClient) -> None:
    r = client.post("/api/imports/motor", files={"file": ("M1670.eng", ENG)})
    assert r.status_code == 200, r.text
    imported = r.json()
    assert imported["motor"]["kind"] == "generic"
    sha = imported["asset"]["sha256"]
    curve = client.get(f"/api/assets/{sha}/thrust-curve").json()
    assert curve["impulse_class"] == "M"
    assert curve["points"][0] == [0, 0]
    assert curve["max_thrust_n"] > curve["average_thrust_n"] > 0
    bad = client.post("/api/imports/motor", files={"file": ("x.eng", b"nonsense")})
    assert bad.status_code == 422


def _calisto(client: TestClient) -> dict[str, Any]:
    for name, kind in (
        ("Cesaroni_M1670.eng", "thrust_curve"),
        ("powerOffDragCurve.csv", "drag_table"),
    ):
        client.post(
            "/api/assets",
            files={"file": (name, (CALISTO / name).read_bytes())},
            data={"kind": kind},
        )
    return load_mission(parse_yaml((CALISTO / "calisto.mission.yaml").read_text())).model_dump(
        mode="json"
    )


def test_descent_rates_use_the_flight_for_apogee(client: TestClient) -> None:
    mission = _calisto(client)
    before = client.post("/api/recovery/descent", json={"mission": mission}).json()
    assert before["apogee_agl_m"] is None
    drogue = next(d for d in before["devices"] if d["name"] == "Drogue")
    assert drogue["top_agl_m"] is None and drogue["rate_bottom_ms"] > 0

    client.post("/api/sim/flight", json={"mission": mission}, params={"wait_s": 60})
    after = client.post(
        "/api/recovery/descent", json={"mission": mission, "target_rates_ms": {"Drogue": 25}}
    ).json()
    assert after["apogee_agl_m"] == pytest.approx(3305, abs=5)
    drogue = after["devices"][0]
    assert drogue["name"] == "Drogue" and drogue["top_agl_m"] == after["apogee_agl_m"]
    assert drogue["cd_s_for_target_m2"] < drogue["cd_s_m2"]


def test_descent_needs_a_rocket(client: TestClient) -> None:
    r = client.post("/api/recovery/descent", json={"mission": {"meta": {"name": "x"}}})
    assert r.status_code == 422
