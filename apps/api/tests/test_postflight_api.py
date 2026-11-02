import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from apogee_api.main import create_app
from apogee_api.settings import get_settings
from simcore.assets import MemoryAssetStore
from simcore.engine import run_flight
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


def _mission_and_log(client: TestClient) -> tuple[dict[str, Any], bytes]:
    store = MemoryAssetStore()
    for name, kind in (
        ("Cesaroni_M1670.eng", "thrust_curve"),
        ("powerOffDragCurve.csv", "drag_table"),
    ):
        data = (CALISTO / name).read_bytes()
        store.put(data)
        client.post("/api/assets", files={"file": (name, data)}, data={"kind": kind})
    mission = load_mission(parse_yaml((CALISTO / "calisto.mission.yaml").read_text()))
    flown = mission.model_copy(deep=True)
    assert flown.rocket is not None
    flown.rocket.drag.multiplier = 1.1
    r = run_flight(flown, store, terminate_on_apogee=True)
    t, alt = np.asarray(r.trajectory["time_s"]), np.asarray(r.trajectory["altitude_agl_m"])
    grid = np.arange(0, t[-1] + 4, 0.05)
    log = "time,altitude_m\n" + "\n".join(
        f"{g:.2f},{np.interp(g - 2, t, alt, left=0.0, right=alt[-1]):.2f}" for g in grid
    )
    return mission.model_dump(mode="json"), log.encode()


def test_upload_preview_fit_and_reuse(client: TestClient) -> None:
    mission, log = _mission_and_log(client)
    preview = client.post("/api/postflight/logs", files={"file": ("flight.csv", log)}).json()
    assert (preview["time_column"], preview["altitude_column"], preview["altitude_units"]) == (
        "time",
        "altitude_m",
        "m",
    )
    body = {
        "mission": mission,
        "log_sha256": preview["sha256"],
        "time_column": "time",
        "altitude_column": "altitude_m",
        "altitude_units": "m",
    }
    run = client.post("/api/postflight/fit", json=body).json()
    deadline = time.monotonic() + 120
    while client.get(f"/api/postflight/fits/{run['result_id']}").status_code == 404:
        assert time.monotonic() < deadline
        time.sleep(0.3)
    result = client.get(f"/api/postflight/fits/{run['result_id']}").json()
    assert result["drag_multiplier"] == pytest.approx(1.1, rel=0.02)
    assert client.post("/api/postflight/fit", json=body).json()["status"] == "done"


def test_unreadable_log_is_422(client: TestClient) -> None:
    r = client.post("/api/postflight/logs", files={"file": ("x.csv", b"1,2\n3,4\n5,6\n")})
    assert r.status_code == 422 and r.json()["code"] == "unreadable_log"
