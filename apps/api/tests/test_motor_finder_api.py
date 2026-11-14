import base64
import json
import time
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apogee_api import thrustcurve
from apogee_api.main import create_app
from apogee_api.settings import get_settings
from simcore.importers.thrust import parse_eng
from simcore.mission import load_mission, parse_yaml

ROOT = Path(__file__).parents[3]
CALISTO = ROOT / "tests" / "fixtures" / "calisto"
M1670 = (CALISTO / "Cesaroni_M1670.eng").read_bytes()


def _row(motor_id: str, designation: str, diameter: float, length: float, scale: float) -> Any:
    """A catalogue row like ThrustCurve.org's, from the M1670's numbers scaled."""
    curve = parse_eng(M1670.decode())
    return {
        "motorId": motor_id,
        "manufacturer": "Cesaroni Technology",
        "manufacturerAbbrev": "Cesaroni",
        "designation": designation,
        "commonName": designation.split("-")[0],
        "impulseClass": "M",
        "diameter": diameter,
        "length": length,
        "type": "reload",
        "avgThrustN": curve.average_thrust_n * scale,
        "totImpulseNs": curve.total_impulse_ns * scale,
        "burnTimeS": curve.burn_time_s,
        "totalWeightG": curve.total_mass_kg * 1000,
        "propWeightG": curve.propellant_mass_kg * 1000 * scale,
        "availability": "regular",
    }


CATALOGUE = [
    _row("m1670", "M1670-BS", 75, 757, 1.0),
    _row("small", "L800-XX", 75, 600, 0.5),  # no .eng on the site
    _row("long", "M2000-XX", 75, 1000, 1.2),  # too long for the mount
    _row("wide", "N3000-XX", 98, 700, 2.0),  # another diameter
]


class FakeThrustCurve:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.offline = False

    def __call__(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, body))
        if self.offline:
            raise urllib.error.URLError("no route to host")
        if path == "search.json":
            return {"results": [r for r in CATALOGUE if r["diameter"] == body["diameter"]]}
        assert path == "download.json"
        data = base64.b64encode(M1670).decode()
        files = [{"motorId": "m1670", "format": "RASP", "data": data}]
        return {"results": [f for f in files if f["motorId"] in body["motorIds"]]}


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeThrustCurve:
    fake = FakeThrustCurve()
    monkeypatch.setattr(thrustcurve, "_post", fake)
    return fake


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APOGEE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APOGEE_QUEUE", "inline")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


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
    mission = load_mission(parse_yaml((CALISTO / "calisto.mission.yaml").read_text()))
    data = mission.model_dump(mode="json")
    data["constraints"] = {"profile": "aurc-2026", "category": "10k-cots"}
    return data


MOUNT = {"diameter_mm": 75, "max_length_mm": 800}


def test_finder_screens_flies_and_judges(client: TestClient, site: FakeThrustCurve) -> None:
    mission = _calisto(client)

    def ask() -> dict[str, Any]:
        r = client.post("/api/motors/finder", json={"mission": mission, "mount": MOUNT})
        assert r.status_code == 200, r.text
        return r.json()

    first = ask()
    assert first["target_apogee_m"] == pytest.approx(3048) and first["target_from"] == "category"
    assert first["catalogue_count"] == 3
    # Too long and too wide are left out; the rest are screened.
    assert {r["candidate"]["motor_id"] for r in first["rows"]} == {"m1670", "small"}
    for _ in range(100):  # the flights run as jobs; ask again until they land
        body = ask()
        if all(r["run"] is None or r["run"]["status"] == "done" for r in body["rows"]):
            break
        time.sleep(0.1)
    m1670, small = body["rows"]
    assert m1670["candidate"]["motor_id"] == "m1670"
    # Flown as a generic motor estimated from the file's header, not Calisto's grains.
    assert m1670["flown"]["apogee_agl_m"] == pytest.approx(3305, rel=0.04)
    assert m1670["estimate"]["apogee_agl_m"] == pytest.approx(3305, rel=0.06)
    assert m1670["judgement"]["verdict"] == "no_go"  # Calisto's drogue is too small for AURC
    assert m1670["judgement"]["points"] > 0
    assert m1670["motor"]["kind"] == "generic"
    assert m1670["asset"]["thrust_curve"]["designation"] == "M1670-BS"
    # No .eng on the site: screened, not flown.
    assert small["run"] is None and small["flown"] is None
    assert small["estimate"]["apogee_agl_m"] < m1670["estimate"]["apogee_agl_m"]

    # The catalogue and the curve are kept: asking again needs no internet.
    site.offline = True
    again = ask()
    assert again["rows"][0]["flown"] is not None and again["curves_fetched"]


def test_finder_needs_a_target(client: TestClient, site: FakeThrustCurve) -> None:
    mission = _calisto(client)
    mission["constraints"] = {}
    r = client.post("/api/motors/finder", json={"mission": mission, "mount": MOUNT})
    assert r.status_code == 422 and r.json()["code"] == "no_target"
    r = client.post(
        "/api/motors/finder",
        json={"mission": mission, "mount": MOUNT, "target_apogee_m": 1500, "flights": 0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_from"] == "request"
    assert all(row["run"] is None for row in body["rows"])
    # Nearest the target first: the smaller motor.
    assert body["rows"][0]["candidate"]["motor_id"] == "small"
    assert not [c for c in site.calls if c[0] == "download.json"]


def test_finder_offline_with_nothing_kept(client: TestClient, site: FakeThrustCurve) -> None:
    site.offline = True
    r = client.post("/api/motors/finder", json={"mission": _calisto(client), "mount": MOUNT})
    assert r.status_code == 503


def test_an_old_catalogue_is_used_when_offline(
    client: TestClient, site: FakeThrustCurve, tmp_path: Path
) -> None:
    kept = tmp_path / "thrustcurve" / "search-75-available.json"
    kept.parent.mkdir(parents=True)
    kept.write_text(json.dumps({"fetched_at": 0, "results": CATALOGUE[:2]}))
    site.offline = True
    r = client.post(
        "/api/motors/finder",
        json={"mission": _calisto(client), "mount": MOUNT},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["catalogue_fetched_at"] == 0
    # Tried for a fresh list, then for the curves; screened only.
    assert [c[0] for c in site.calls] == ["search.json", "download.json"]
    assert not body["curves_fetched"]
    assert all(row["run"] is None for row in body["rows"])


def test_the_mount_defaults_to_the_current_motor(client: TestClient, site: FakeThrustCurve) -> None:
    r = client.post("/api/motors/finder", json={"mission": _calisto(client), "flights": 0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mount"] == {"diameter_mm": 75, "max_length_mm": 757}  # the M1670's case
    assert [row["candidate"]["motor_id"] for row in body["rows"]] == ["m1670", "small"]
