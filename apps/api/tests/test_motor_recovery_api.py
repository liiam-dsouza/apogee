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


def test_storage_lists_stores_and_clears_only_recomputable_ones(client: TestClient) -> None:
    client.post("/api/imports/motor", files={"file": ("M1670.eng", ENG)})
    stores = {s["name"]: s for s in client.get("/api/system/storage").json()}
    assert stores["assets"]["items"] == 1 and stores["assets"]["recomputable"] is False
    assert client.delete("/api/system/storage/assets").status_code == 409
    assert client.delete("/api/system/storage/results").status_code == 204
    assert client.delete("/api/system/storage/nope").status_code == 404


def test_flight_path_is_aligned_and_lookup_runs_nothing(client: TestClient) -> None:
    mission = _calisto(client)
    before = client.post("/api/sim/flight/lookup", json={"mission": mission}).json()
    assert before["available"] is False
    client.post("/api/sim/flight", json={"mission": mission}, params={"wait_s": 60})
    after = client.post("/api/sim/flight/lookup", json={"mission": mission}).json()
    assert after == {"result_id": before["result_id"], "available": True}
    path = client.get(f"/api/results/{after['result_id']}/path", params={"max_points": 300}).json()
    n = len(path["t"])
    assert 10 < n <= 300
    assert len(path["east_m"]) == len(path["north_m"]) == len(path["altitude_agl_m"]) == n
    assert max(path["altitude_agl_m"]) == pytest.approx(3305, abs=2)  # apogee survives downsampling


def test_runs_are_listed_and_compared_with_their_settings(client: TestClient) -> None:
    mission = _calisto(client)
    a = client.post("/api/sim/flight", json={"mission": mission}, params={"wait_s": 60}).json()
    mission["rocket"]["drag"]["multiplier"] = 1.2
    b = client.post("/api/sim/flight", json={"mission": mission}, params={"wait_s": 60}).json()
    listed = client.get("/api/results", params={"mission_id": mission["meta"]["id"]}).json()
    assert [r["id"] for r in listed] == [b["result_id"], a["result_id"]]  # newest first
    cmp = client.get(f"/api/results/compare/{a['result_id']}/{b['result_id']}").json()
    assert cmp["settings_known"] is True
    assert [(d["path"], d["a"], d["b"]) for d in cmp["differences"]] == [
        ("rocket.drag.multiplier", 1.0, 1.2)
    ]
    assert cmp["b"]["summary"]["apogee_agl_m"] < cmp["a"]["summary"]["apogee_agl_m"]


def test_fin_flutter_from_the_flight(client: TestClient) -> None:
    mission = _calisto(client)
    materials = client.get("/api/structures/fin-materials").json()
    g10 = next(m for m in materials if m["id"] == "g10")
    mission["rocket"]["fins"][0] |= {
        "thickness_m": 0.004,
        "material": {"name": g10["name"], "shear_modulus_pa": g10["shear_modulus_pa"]},
    }

    before = client.post("/api/structures/flutter", json={"mission": mission}).json()
    assert before["flight_run"] is False
    assert before["required_margin"] == 1.5 and "AURC" in before["required_by"]
    assert before["fin_sets"] == [
        {"fin_set": 1, "checked": True, "flutter": None, "thinnest_m": None}
    ]

    client.post("/api/sim/flight", json={"mission": mission}, params={"wait_s": 60})
    mission["constraints"] = {"profile": "aurc-2026", "category": "30k-cots-solid"}
    after = client.post("/api/structures/flutter", json={"mission": mission}).json()
    (row,) = after["fin_sets"]
    assert after["flight_run"] is True and "Spec 4.2.1" in after["required_by"]
    assert row["flutter"]["min_margin"] == pytest.approx(1.8, abs=0.1)
    assert row["thinnest_m"] == pytest.approx(0.0035, abs=0.0002)

    def rule(m: dict[str, Any]) -> dict[str, Any]:
        rows = client.post("/api/constraints/board", json={"mission": m}).json()["board"]["rows"]
        return next(r for r in rows if r["id"] == "fin_flutter")

    assert rule(mission)["status"] == "missing"  # judged at p95: needs a campaign
    mission["constraints"]["overrides"] = {"fin_flutter": {"evaluate_on": "nominal"}}
    judged = rule(mission)
    assert judged["status"] == "pass" and judged["value_low"] == row["flutter"]["min_margin"]

    del mission["rocket"]["fins"][0]["material"]  # a different flight, not run
    client.post("/api/sim/flight", json={"mission": mission}, params={"wait_s": 60})
    unset = rule(mission)
    assert unset["status"] == "missing" and "fin thickness and material" in unset["note"]


def test_fin_flutter_needs_a_rocket(client: TestClient) -> None:
    r = client.post("/api/structures/flutter", json={"mission": {"meta": {"name": "x"}}})
    assert r.status_code == 422


def test_ejection_charges_use_the_flight(client: TestClient) -> None:
    mission = _calisto(client)
    mission["ejection"] = {
        "bays": [
            {
                "name": "Drogue bay",
                "device": "Drogue",
                "inner_diameter_m": 0.12,
                "free_length_m": 0.3,
                "forward_mass_kg": 3.0,
                "shear_pins": 2,
                "pin_strength_n": 156,
            }
        ]
    }
    before = client.post("/api/recovery/ejection", json={"mission": mission}).json()
    assert before["flight_run"] is False and before["bays"][0]["drag_separation_n"] is None
    assert before["bays"][0]["primary_charge_kg"] > 0

    client.post("/api/sim/flight", json={"mission": mission}, params={"wait_s": 60})
    after = client.post("/api/recovery/ejection", json={"mission": mission}).json()
    (bay,) = after["bays"]
    assert after["flight_run"] is True
    assert bay["drag_separation_n"] == pytest.approx(3.0 * after["coast_drag_deceleration_ms2"])
    assert bay["hold_margin"] == pytest.approx(312 / bay["drag_separation_n"])


def test_recovery_failures_fly_and_report(client: TestClient) -> None:
    mission = _calisto(client)

    def ask() -> dict[str, Any]:
        r = client.post("/api/recovery/failures", json={"mission": mission})
        assert r.status_code == 200, r.text
        return r.json()

    first = ask()
    assert [o["mode"] for o in first["outcomes"]] == ["drogue_fails", "main_fails", "nothing_opens"]
    for _ in range(100):  # the flights run as jobs; ask again until they land
        done = ask()
        if all(o["run"]["status"] == "done" for o in done["outcomes"]):
            break
        time.sleep(0.1)
    by = {o["mode"]: o for o in done["outcomes"]}
    assert by["main_fails"]["devices"] == ["Drogue"]
    assert by["nothing_opens"]["landing_speed_ms"] > 3 * by["main_fails"]["landing_speed_ms"]
    assert by["drogue_fails"]["opening_speed_ms"] > 50
    assert by["nothing_opens"]["opening_speed_ms"] is None
    assert by["main_fails"]["outside_boundary"] is None  # Calisto's site has no boundary


def test_a_campaign_can_fly_a_recovery_failure(client: TestClient) -> None:
    mission = _calisto(client)
    mission["monte_carlo"] = {"samples": 10}
    nominal = client.post("/api/sim/montecarlo", json={"mission": mission}).json()
    failed = client.post(
        "/api/sim/montecarlo", json={"mission": mission, "failure": "main_fails"}
    ).json()
    assert failed["id"] != nominal["id"]
    again = client.post("/api/sim/montecarlo", json={"mission": mission, "failure": "main_fails"})
    assert again.json()["id"] == failed["id"]


def test_the_tour_mission_is_ready_to_fly_and_resets(client: TestClient) -> None:
    first = client.post("/api/missions/tour").json()
    mission = first["mission"]
    assert mission["meta"]["name"] == "Calisto (tour)"
    assert mission["constraints"]["profile"] == "aurc-2026"
    assert mission["rocket"]["fins"][0]["material"]["name"].startswith("G10")
    run = client.post("/api/sim/flight", json={"mission": mission}, params={"wait_s": 60})
    assert run.json()["status"] == "done"  # its assets are in the store

    edited = mission | {"meta": mission["meta"] | {"name": "Changed"}}
    client.put(f"/api/missions/{mission['meta']['id']}", json=edited)
    again = client.post("/api/missions/tour").json()
    assert again["mission"]["meta"]["name"] == "Calisto (tour)"
    assert [m["name"] for m in client.get("/api/missions").json()] == ["Calisto (tour)"]
