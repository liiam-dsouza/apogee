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
    return m.model_dump(mode="json")


def test_solve_runs_once_and_is_reused(client: TestClient) -> None:
    mission = _mission(client)
    mission["ballast"] |= {"position_m": 0.4, "target_apogee_m": 3000, "increment_kg": 0.1}
    run = client.post("/api/ballast/solve", json={"mission": mission}).json()
    deadline = time.monotonic() + 300
    while client.get(f"/api/ballast/{run['result_id']}").status_code == 404:
        assert time.monotonic() < deadline
        time.sleep(0.5)
    solution = client.get(f"/api/ballast/{run['result_id']}").json()
    assert solution["status"] == "ok"
    assert solution["samples"] == 100
    assert solution["report"]["rows"]
    # Installing the answer doesn't change the question.
    mission["ballast"]["installed_kg"] = solution["recommended_kg"]
    again = client.post("/api/ballast/solve", json={"mission": mission}).json()
    assert again == {"status": "done", "result_id": run["result_id"], "job_id": None, "error": None}


def test_solve_needs_a_target_and_a_bay(client: TestClient) -> None:
    mission = _mission(client)
    r = client.post("/api/ballast/solve", json={"mission": mission})
    assert r.status_code == 422 and r.json()["code"] == "no_target"
    mission["ballast"]["target_apogee_m"] = 3000
    r = client.post("/api/ballast/solve", json={"mission": mission})
    assert r.status_code == 422 and r.json()["code"] == "no_bay"
