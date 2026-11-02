import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apogee_api.main import create_app
from apogee_api.settings import get_settings
from simcore.mission import load_mission, parse_yaml

ROOT = Path(__file__).parents[3]
CALISTO = ROOT / "tests" / "fixtures" / "calisto"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APOGEE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APOGEE_QUEUE", "inline")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _calisto(client: TestClient, samples: int) -> dict[str, Any]:
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        kind = "thrust_curve" if name.endswith(".eng") else "drag_table"
        client.post(
            "/api/assets",
            files={"file": (name, (CALISTO / name).read_bytes())},
            data={"kind": kind},
        )
    mission = load_mission(parse_yaml((CALISTO / "calisto.mission.yaml").read_text()))
    mission.monte_carlo.samples = samples
    return mission.model_dump(mode="json")


def _wait(client: TestClient, campaign_id: str, timeout_s: float = 120) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while True:
        body: dict[str, Any] = client.get(f"/api/campaigns/{campaign_id}").json()
        if body["state"]["status"] != "running" or time.monotonic() > deadline:
            return body
        time.sleep(0.2)


def test_campaign_runs_summarises_and_exports(client: TestClient) -> None:
    mission = _calisto(client, samples=24)  # two chunks
    r = client.post("/api/sim/montecarlo", json={"mission": mission})
    assert r.status_code == 200, r.text
    state = r.json()
    assert state["samples"] == 24
    result = _wait(client, state["id"])
    assert result["state"]["status"] == "done", result["state"]
    assert result["state"]["samples_done"] == 24
    assert result["summary"]["done"] == 24
    assert len(result["points"]) == 24
    names = {s["name"] for s in result["summary"]["stats"]}
    assert {"apogee_agl_m", "drift_m", "rail_exit_velocity_ms"} <= names
    assert [e["probability"] for e in result["summary"]["ellipses"]] == [0.6827, 0.9545, 0.9973]

    csv_text = client.get(f"/api/campaigns/{state['id']}/samples.csv").text
    lines = list(csv_text.splitlines())
    assert len(lines) == 25
    assert lines[0].startswith("index,error,impulse_scale")

    dists = {d["name"]: d for d in client.get(f"/api/campaigns/{state['id']}/distributions").json()}
    assert len(dists["apogee_agl_m"]["values"]) == 24
    assert dists["apogee_agl_m"]["units"] == "m"

    # Same mission: same campaign, nothing re-run.
    again = client.post("/api/sim/montecarlo", json={"mission": mission}).json()
    assert again["id"] == state["id"] and again["status"] == "done"


def test_campaign_settings_change_the_campaign_not_the_flight(client: TestClient) -> None:
    mission = _calisto(client, samples=10)
    a = client.post("/api/sim/flight", json={"mission": mission}).json()
    mission["monte_carlo"]["seed"] = 2
    b = client.post("/api/sim/flight", json={"mission": mission}).json()
    assert a["result_id"] == b["result_id"]
    c1 = client.post("/api/sim/montecarlo", json={"mission": mission}).json()
    mission["monte_carlo"]["seed"] = 3
    c2 = client.post("/api/sim/montecarlo", json={"mission": mission}).json()
    assert c1["id"] != c2["id"]


def test_unknown_campaign_is_404(client: TestClient) -> None:
    assert client.get("/api/campaigns/nope").status_code == 404


def test_unrunnable_mission_is_422(client: TestClient) -> None:
    r = client.post("/api/sim/montecarlo", json={"mission": {"meta": {"name": "empty"}}})
    assert r.status_code == 422
    assert r.json()["code"] == "not_runnable"
