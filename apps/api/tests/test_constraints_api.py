import time
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


def _mission(client: TestClient) -> dict[str, Any]:
    for name, kind in (
        ("Cesaroni_M1670.eng", "thrust_curve"),
        ("powerOffDragCurve.csv", "drag_table"),
    ):
        client.post(
            "/api/assets",
            files={"file": (name, (CALISTO / name).read_bytes())},
            data={"kind": kind},
        )
    m = load_mission(parse_yaml((CALISTO / "calisto.mission.yaml").read_text()))
    m.monte_carlo.samples = 20
    return m.model_dump(mode="json")


def test_profiles_are_listed_with_their_rules(client: TestClient) -> None:
    profiles = {p["id"]: p for p in client.get("/api/profiles").json()}
    assert profiles["aurc-2026"]["scoring"]["kind"] == "gaussian"
    assert profiles["irec-2027"]["scoring"]["kind"] == "linear"


def test_board_follows_the_runs_and_ignores_constraint_edits(client: TestClient) -> None:
    mission = _mission(client)
    mission["constraints"] = {
        "additional": [
            {"id": "rail", "metric": "rail_exit_velocity_ms", "min": 20, "evaluate_on": "nominal"},
            {"id": "drift", "metric": "drift_m", "max": 5000},
        ]
    }
    before = client.post("/api/constraints/board", json={"mission": mission}).json()
    assert before["board"]["verdict"] == "incomplete"
    assert before["flight"]["available"] is False

    client.post("/api/sim/flight", json={"mission": mission}, params={"wait_s": 60})
    state = client.post("/api/sim/montecarlo", json={"mission": mission}).json()
    deadline = time.monotonic() + 120
    while client.get(f"/api/campaigns/{state['id']}").json()["state"]["status"] == "running":
        assert time.monotonic() < deadline
        time.sleep(0.2)

    # Tightening a rule must not orphan the runs it is judged on.
    mission["constraints"]["additional"][1]["max"] = 10
    after = client.post("/api/constraints/board", json={"mission": mission}).json()
    rows = {r["id"]: r for r in after["board"]["rows"]}
    assert after["flight"]["available"] is True
    assert after["campaign"]["samples_done"] == 20
    assert rows["rail"]["status"] == "pass"
    assert rows["drift"]["status"] == "fail" and rows["drift"]["violation_share"] == 1.0
    assert after["board"]["verdict"] == "no_go"


def test_bad_settings_are_a_clear_422(client: TestClient) -> None:
    mission = _mission(client)
    mission["constraints"] = {"profile": "no-such-profile"}
    r = client.post("/api/constraints/board", json={"mission": mission})
    assert r.status_code == 422
    assert "no-such-profile" in r.json()["detail"]
