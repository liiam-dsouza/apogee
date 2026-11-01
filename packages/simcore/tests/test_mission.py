import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simcore.mission import (
    Mission,
    canonical_json,
    dump_yaml,
    load_mission,
    migrate,
    mission_hash,
    parse_yaml,
    validate_mission,
)
from simcore.mission.migrations import MigrationError

SITE = {
    "latitude_deg": -31.05,
    "longitude_deg": 136.53,
    "elevation_m": 160.0,
    "rail_length_m": 6.0,
    "inclination_deg": 84.0,
    "heading_deg": 0.0,
}


def minimal(**overrides: Any) -> dict[str, Any]:
    return {"schema_version": 1, "meta": {"name": "Test"}, **overrides}


def test_every_schema_field_has_a_description() -> None:
    # The brief's rule: a field with no description fails CI.
    schema = Mission.model_json_schema()
    missing: list[str] = []

    def walk(node: dict[str, Any], where: str) -> None:
        for name, prop in node.get("properties", {}).items():
            if "description" not in prop:
                missing.append(f"{where}.{name}")

    walk(schema, "Mission")
    for def_name, definition in schema.get("$defs", {}).items():
        walk(definition, def_name)
    assert missing == []


def test_yaml_round_trip_is_lossless() -> None:
    m = load_mission(minimal(site=SITE))
    again = load_mission(parse_yaml(dump_yaml(m)))
    assert again == m
    assert mission_hash(again) == mission_hash(m)


def test_unknown_keys_are_errors() -> None:
    _, report = validate_mission(minimal(site={**SITE, "rail_lenght_m": 6}))
    assert not report.valid
    assert any(i.path == "site.rail_lenght_m" for i in report.issues)


def test_issue_paths_point_at_the_field() -> None:
    _, report = validate_mission(minimal(site={**SITE, "inclination_deg": 120}))
    assert [i.path for i in report.issues] == ["site.inclination_deg"]


def test_pad_outside_boundary_is_a_warning() -> None:
    far_box = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    mission, report = validate_mission(minimal(site={**SITE, "boundary": far_box}))
    assert mission is not None
    assert report.valid
    assert [i.code for i in report.issues] == ["pad_outside_boundary"]


def test_pad_inside_hazard_is_an_error() -> None:
    lon, lat = SITE["longitude_deg"], SITE["latitude_deg"]
    box = [
        (lon - 0.01, lat - 0.01),
        (lon + 0.01, lat - 0.01),
        (lon + 0.01, lat + 0.01),
        (lon - 0.01, lat + 0.01),
    ]
    _, report = validate_mission(minimal(site={**SITE, "hazards": [box]}))
    assert not report.valid
    assert report.issues[0].path == "site.hazards[0]"


def test_future_schema_version_is_refused() -> None:
    with pytest.raises(MigrationError):
        migrate({"schema_version": 99})


def test_migrate_is_idempotent() -> None:
    data = minimal()
    assert migrate(migrate(dict(data))) == migrate(dict(data))


json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=20,
)


@given(st.dictionaries(st.text(), json_values))
def test_canonical_json_ignores_key_order(d: dict[str, Any]) -> None:
    reversed_d = dict(reversed(list(d.items())))
    assert canonical_json(d) == canonical_json(reversed_d)


def test_canonical_json_normalises_float_formatting() -> None:
    assert canonical_json({"a": 1.0}) == canonical_json({"a": 1})
    assert canonical_json({"a": 0.1 + 0.2}) == canonical_json({"a": 0.3})
    assert canonical_json({"a": -0.0}) == canonical_json({"a": 0})
    assert json.loads(canonical_json({"b": 2, "a": 1})) == {"a": 1, "b": 2}


CALISTO_YAML = (
    __import__("pathlib").Path(__file__).parents[3]
    / "tests"
    / "fixtures"
    / "calisto"
    / "calisto.mission.yaml"
)


def calisto() -> dict[str, Any]:
    return parse_yaml(CALISTO_YAML.read_text())


def test_calisto_fixture_is_clean() -> None:
    mission, report = validate_mission(calisto())
    assert mission is not None
    assert report.issues == []


def test_v1_empty_sections_migrate_to_v2() -> None:
    data = {
        "schema_version": 1,
        "meta": {"name": "Old"},
        "rocket": {},
        "motor": {},
        "recovery": {},
        "environment": {},
    }
    mission = load_mission(data)
    assert mission.schema_version == 2
    assert mission.rocket is None
    assert mission.recovery.devices == []


def test_v1_non_empty_free_form_sections_are_reported_not_dropped() -> None:
    _, report = validate_mission(
        {"schema_version": 1, "meta": {"name": "Old"}, "rocket": {"foo": 1}}
    )
    assert not report.valid
    assert any(i.path.startswith("rocket.") for i in report.issues)


def test_missing_asset_points_at_the_field() -> None:
    data = calisto()
    data["assets"] = {}
    _, report = validate_mission(data)
    assert not report.valid
    assert {i.path for i in report.issues} == {
        "motor.thrust_curve",
        "rocket.drag.power_off.table",
        "rocket.drag.power_on.table",
    }


def test_cg_forward_of_nose_tip_is_an_error() -> None:
    data = calisto()
    data["rocket"]["dry_cg_m"] = -0.1
    _, report = validate_mission(data)
    assert [(i.path, i.code) for i in report.issues] == [("rocket.dry_cg_m", "cg_forward_of_nose")]


def test_rail_buttons_out_of_order_is_an_error() -> None:
    data = calisto()
    rb = data["rocket"]["rail_buttons"]
    rb["upper_position_m"], rb["lower_position_m"] = rb["lower_position_m"], rb["upper_position_m"]
    _, report = validate_mission(data)
    assert [i.code for i in report.issues] == ["rail_buttons_order"]


def test_drag_curve_needs_exactly_one_source() -> None:
    data = calisto()
    data["rocket"]["drag"]["power_off"] = {"table": None, "constant_cd": None}
    _, report = validate_mission(data)
    assert any(i.path.startswith("rocket.drag.power_off") for i in report.issues)
