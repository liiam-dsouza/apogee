"""The flight path end to end, with the inline queue (no Redis needed)."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apogee_api.main import create_app
from apogee_api.settings import get_settings
from simcore.mission import CURRENT_SCHEMA_VERSION, load_mission, parse_yaml

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"
GOLDEN = json.loads((Path(__file__).parents[3] / "tests" / "golden" / "calisto.json").read_text())
THRUST_SHA = "a18a3ae712108760c5fdbf5c5ddaefe50bb6a429d75bc5ab4bcf7ce7716548d8"
DRAG_SHA = "94760a42d5f5fad4fb815f448db72201fafd2b2a3c6ec2d2c83618b2953207e0"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APOGEE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APOGEE_QUEUE", "inline")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def calisto() -> dict[str, Any]:
    """The fixture as JSON, the way a client sends it."""
    return load_mission(parse_yaml((CALISTO / "calisto.mission.yaml").read_text())).model_dump(
        mode="json"
    )


def upload(client: TestClient, name: str, kind: str) -> dict[str, Any]:
    r = client.post(
        "/api/assets", files={"file": (name, (CALISTO / name).read_bytes())}, data={"kind": kind}
    )
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def upload_calisto_assets(client: TestClient) -> None:
    assert upload(client, "Cesaroni_M1670.eng", "thrust_curve")["sha256"] == THRUST_SHA
    assert upload(client, "powerOffDragCurve.csv", "drag_table")["sha256"] == DRAG_SHA


def test_thrust_upload_reports_motor_data(client: TestClient) -> None:
    info = upload(client, "Cesaroni_M1670.eng", "thrust_curve")
    assert info["thrust_curve"]["designation"] == "M1670-BS"
    assert 5120 < info["thrust_curve"]["total_impulse_ns"] < 10240


def test_unparseable_thrust_curve_is_refused(client: TestClient) -> None:
    r = client.post(
        "/api/assets", files={"file": ("bad.eng", b"nonsense")}, data={"kind": "thrust_curve"}
    )
    assert r.status_code == 422
    assert r.json()["code"] == "unreadable_asset"


def test_fly_calisto_and_read_the_result(client: TestClient) -> None:
    upload_calisto_assets(client)
    run = client.post("/api/sim/flight?wait_s=30", json={"mission": calisto()}).json()
    assert run["status"] == "done", run
    assert run["cached"] is False

    record = client.get(f"/api/results/{run['result_id']}").json()
    assert record["summary"]["apogee_agl_m"] == pytest.approx(
        GOLDEN["summary"]["apogee_agl_m"], rel=1e-9
    )
    assert record["provenance"]["rocketpy_version"] == "1.13.0"
    assert record["provenance"]["thrust_curve"] == THRUST_SHA

    [alt, mach] = client.get(
        f"/api/results/{run['result_id']}/series?vars=altitude_agl_m,mach&max_points=300"
    ).json()
    assert len(alt["t"]) == 300
    assert max(alt["y"]) == pytest.approx(record["summary"]["apogee_agl_m"], rel=1e-6)
    assert mach["units"] == "1"

    again = client.post("/api/sim/flight?wait_s=30", json={"mission": calisto()}).json()
    assert again == {**run, "cached": True, "job_id": None}


def test_ascent_only_is_a_separate_result_without_landing(client: TestClient) -> None:
    upload_calisto_assets(client)
    full = client.post("/api/sim/flight?wait_s=30", json={"mission": calisto()}).json()
    ascent = client.post(
        "/api/sim/flight?wait_s=30", json={"mission": calisto(), "ascent_only": True}
    ).json()
    assert ascent["result_id"] != full["result_id"]
    record = client.get(f"/api/results/{ascent['result_id']}").json()
    assert record["summary"]["landing"] is None


def test_a_mission_without_a_rocket_says_what_is_missing(client: TestClient) -> None:
    r = client.post("/api/sim/flight", json={"mission": {"meta": {"name": "Empty"}}})
    assert r.status_code == 422
    assert sorted(i["path"] for i in r.json()["issues"]) == ["motor", "rocket", "site"]


def test_unuploaded_assets_block_the_run(client: TestClient) -> None:
    r = client.post("/api/sim/flight", json={"mission": calisto()})
    assert r.status_code == 422
    assert {i["code"] for i in r.json()["issues"]} == {"asset_not_uploaded"}


def test_unknown_series_channel_is_a_problem(client: TestClient) -> None:
    upload_calisto_assets(client)
    run = client.post("/api/sim/flight?wait_s=30", json={"mission": calisto()}).json()
    r = client.get(f"/api/results/{run['result_id']}/series?vars=altitude_agl_m,warp_factor")
    assert r.status_code == 422
    assert "warp_factor" in r.json()["title"]


def test_bundle_import_brings_assets_and_flies(client: TestClient) -> None:
    bundle = (
        Path(__file__).parents[3] / "missions" / "examples" / "calisto.mission.zip"
    ).read_bytes()
    r = client.post("/api/missions/import", files={"file": ("calisto.mission.zip", bundle)})
    assert r.status_code == 201, r.text
    mission = r.json()["mission"]
    run = client.post("/api/sim/flight?wait_s=30", json={"mission": mission}).json()
    assert run["status"] == "done"

    exported = client.get(f"/api/missions/{mission['meta']['id']}/export?format=zip")
    assert exported.headers["content-type"] == "application/zip"
    assert exported.content[:2] == b"PK"


def test_v1_stored_mission_is_migrated_on_read(client: TestClient) -> None:
    from datetime import UTC, datetime

    from sqlmodel import Session

    from apogee_api import db

    assert db._engine is not None
    with Session(db._engine) as session:
        session.add(
            db.MissionRecord(
                id="01OLDV1",
                name="Old",
                config_hash="x",
                yaml="schema_version: 1\nmeta: {name: Old, id: 01OLDV1}\nrocket: {}\nmotor: {}\n",
                created_utc=datetime.now(UTC),
            )
        )
        session.commit()
    doc = client.get("/api/missions/01OLDV1").json()
    assert doc["mission"]["schema_version"] == CURRENT_SCHEMA_VERSION
    assert doc["mission"]["rocket"] is None
