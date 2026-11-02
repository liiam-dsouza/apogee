import base64
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apogee_api.main import create_app
from apogee_api.routers import imports
from apogee_api.settings import get_settings

ROOT = Path(__file__).parents[3]
LANIUS = ROOT / "data" / "Lanius.ork"
M1340W = ROOT / "tests" / "fixtures" / "motors" / "AeroTech_M1340W.eng"
SMALL = (ROOT / "packages" / "simcore" / "tests" / "test_openrocket.py").read_text()
SMALL_ORK = SMALL.split('SMALL = b"""', 1)[1].split('"""', 1)[0].encode()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APOGEE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APOGEE_QUEUE", "inline")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_small_design_imports_as_a_draft(client: TestClient) -> None:
    r = client.post("/api/imports/openrocket", files={"file": ("tiny.ork", SMALL_ORK)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rocket"]["nose"]["kind"] == "conical"
    assert body["motor"] is None
    assert body["motor_reference"]["designation"] == "H100"
    assert any("thrust curve" in w for w in body["report"]["warnings"])


def test_garbage_is_a_problem_not_a_crash(client: TestClient) -> None:
    r = client.post("/api/imports/openrocket", files={"file": ("x.ork", b"not a rocket")})
    assert r.status_code == 422
    assert r.json()["code"] == "unreadable_ork"


@pytest.mark.skipif(not LANIUS.exists(), reason="team's Lanius.ork is not in data/")
def test_lanius_with_its_motor_gets_flight_cross_checks(client: TestClient) -> None:
    r = client.post(
        "/api/imports/openrocket",
        files={
            "file": ("Lanius.ork", LANIUS.read_bytes()),
            "thrust_curve": ("AeroTech_M1340W.eng", M1340W.read_bytes()),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["motor"]["kind"] == "generic"
    checks = {c["quantity"]: c for c in body["report"]["cross_checks"]}
    assert checks["Apogee"]["status"] == "ok"
    assert checks["Dry mass"]["status"] == "ok"
    # Everything the draft refers to is stored, so the rocket can fly at once.
    for sha in body["assets"]:
        assert client.get(f"/api/assets/{sha}").status_code == 200


def test_thrustcurve_fetch_parses_and_stores(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path == "search.json":
            return {"results": [{"motorId": "abc"}]}
        data = base64.b64encode(M1340W.read_bytes()).decode()
        return {"results": [{"format": "RASP", "data": data, "source": "cert", "license": "PD"}]}

    monkeypatch.setattr(imports, "_thrustcurve", fake)
    r = client.post(
        "/api/imports/thrustcurve", json={"manufacturer": "AeroTech", "designation": "M1340W"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["asset"]["thrust_curve"]["designation"] == "M1340W"
    assert body["motor"]["propellant_mass_kg"] == pytest.approx(4.036)
    assert client.get(f"/api/assets/{body['asset']['sha256']}").status_code == 200


def test_thrustcurve_offline_says_what_to_do(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def offline(path: str, body: dict[str, Any]) -> dict[str, Any]:
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(imports, "_thrustcurve", offline)
    r = client.post(
        "/api/imports/thrustcurve", json={"manufacturer": "AeroTech", "designation": "M1340W"}
    )
    assert r.status_code == 503
    assert "upload" in r.json()["detail"]


@pytest.mark.skipif(not LANIUS.exists(), reason="team's Lanius.ork is not in data/")
def test_lanius_with_a_stored_thrust_curve(client: TestClient) -> None:
    asset = client.post(
        "/api/assets",
        files={"file": ("AeroTech_M1340W.eng", M1340W.read_bytes())},
        data={"kind": "thrust_curve"},
    ).json()
    r = client.post(
        "/api/imports/openrocket",
        files={"file": ("Lanius.ork", LANIUS.read_bytes())},
        data={"thrust_curve_sha": asset["sha256"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["motor"]["thrust_curve"] == asset["sha256"]


def test_thrustcurve_refusal_is_not_called_offline(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(path: str, body: dict[str, Any]) -> dict[str, Any]:
        raise urllib.error.HTTPError("https://x", 403, "Forbidden", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(imports, "_thrustcurve", refused)
    r = client.post(
        "/api/imports/thrustcurve", json={"manufacturer": "AeroTech", "designation": "M1340W"}
    )
    assert r.status_code == 502
    assert "403" in r.json()["title"]
