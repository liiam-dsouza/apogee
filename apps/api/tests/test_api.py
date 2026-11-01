from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apogee_api.main import create_app
from apogee_api.settings import get_settings

SITE = {
    "latitude_deg": -31.05,
    "longitude_deg": 136.53,
    "elevation_m": 160.0,
    "rail_length_m": 6.0,
    "inclination_deg": 84.0,
    "heading_deg": 0.0,
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APOGEE_DATA_DIR", str(tmp_path))
    # Nothing listens here: exercises the "queue unavailable" path.
    monkeypatch.setenv("APOGEE_REDIS_URL", "redis://127.0.0.1:1")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def mission(name: str = "Lanius", **extra: Any) -> dict[str, Any]:
    return {"meta": {"name": name}, "site": SITE, **extra}


def test_system_info_without_redis(client: TestClient) -> None:
    info = client.get("/api/system/info").json()
    assert info["queue_available"] is False
    assert info["worker_count"] == 0
    assert info["rocketpy_version"] == "1.13.0"


def test_mission_lifecycle(client: TestClient) -> None:
    created = client.post("/api/missions", json=mission())
    assert created.status_code == 201
    doc = created.json()
    mission_id = doc["mission"]["meta"]["id"]

    assert [m["id"] for m in client.get("/api/missions").json()] == [mission_id]

    doc["mission"]["meta"]["name"] = "Lanius II"
    updated = client.put(f"/api/missions/{mission_id}", json=doc["mission"]).json()
    assert updated["mission"]["meta"]["name"] == "Lanius II"
    assert updated["config_hash"] != doc["config_hash"]

    exported = client.get(f"/api/missions/{mission_id}/export")
    assert exported.headers["content-type"].startswith("application/yaml")
    assert "Lanius II" in exported.text
    assert 'filename="lanius-ii.mission.yaml"' in exported.headers["content-disposition"]

    assert client.delete(f"/api/missions/{mission_id}").status_code == 204
    assert client.get(f"/api/missions/{mission_id}").status_code == 404


def test_errors_are_problem_details_with_paths(client: TestClient) -> None:
    bad = mission(site={**SITE, "rail_length_m": -1})
    r = client.post("/api/missions", json=bad)
    assert r.status_code == 422
    assert r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert body["code"] == "invalid_request"
    assert [i["path"] for i in body["issues"]] == ["site.rail_length_m"]


def test_validate_reports_without_storing(client: TestClient) -> None:
    report = client.post("/api/missions/validate", json={"schema_version": 99}).json()
    assert report["valid"] is False
    assert report["issues"][0]["path"] == "schema_version"
    assert client.get("/api/missions").json() == []


def test_import_round_trips_export(client: TestClient) -> None:
    doc = client.post("/api/missions", json=mission()).json()
    mission_id = doc["mission"]["meta"]["id"]
    yaml_text = client.get(f"/api/missions/{mission_id}/export").text
    client.delete(f"/api/missions/{mission_id}")

    r = client.post("/api/missions/import", files={"file": ("m.mission.yaml", yaml_text)})
    assert r.status_code == 201
    assert r.json()["config_hash"] == doc["config_hash"]


def test_duplicate_import_conflicts(client: TestClient) -> None:
    doc = client.post("/api/missions", json=mission()).json()
    yaml_text = client.get(f"/api/missions/{doc['mission']['meta']['id']}/export").text
    r = client.post("/api/missions/import", files={"file": ("m.yaml", yaml_text)})
    assert r.status_code == 409
    assert r.json()["code"] == "mission_exists"


def _local_redis_up() -> bool:
    import socket

    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", 6379)) == 0


@pytest.mark.skipif(not _local_redis_up(), reason="needs Redis on localhost:6379")
def test_system_info_counts_worker_heartbeats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import redis

    from apogee_api.queue import WORKER_HEARTBEAT_PREFIX

    key = f"{WORKER_HEARTBEAT_PREFIX}pytest"
    r = redis.Redis()
    before = len(list(r.scan_iter(match=f"{WORKER_HEARTBEAT_PREFIX}*")))
    r.set(key, "1", ex=10)
    monkeypatch.setenv("APOGEE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APOGEE_REDIS_URL", "redis://127.0.0.1:6379")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as c:
            info = c.get("/api/system/info").json()
        assert info["queue_available"] is True
        assert info["worker_count"] == before + 1
    finally:
        r.delete(key)
        get_settings.cache_clear()
